"""Servidor central CSMS sobre WebSockets integrado con el agente predictivo de IA."""
import json
import websockets
from config import HOST, CSMS_PORT, P_GRID_MAX_W
from ai_agent import SmartChargingAIAgent


class CSMSServer:
    def __init__(self, ai_agent: SmartChargingAIAgent):
        self.ai_agent = ai_agent
        self.reset_state()

    def reset_state(self):
        self.last_power = {}
        self.current_predictions = {}
        self.step_logs = []  # Registro para cálculo de MAE, RMSE y sobrecargas

    async def handle_connection(self, websocket):
        path = getattr(websocket, "path", None) or getattr(
            getattr(websocket, "request", None), "path", "/UNKNOWN"
        )
        cp_id = path.strip("/")

        async for raw_msg in websocket:
            frame = json.loads(raw_msg)
            _, unique_id, action, payload = frame

            if action == "BootNotification":
                resp = [3, unique_id, {"status": "Accepted", "interval": 900}]
            elif action in ("StatusNotification", "StartTransaction", "StopTransaction"):
                resp = [3, unique_id, {"status": "Accepted"}]
            elif action == "MeterValues":
                p_curr = float(payload["power_w"])
                soc = float(payload["soc"])
                hour = float(payload["hour"])
                true_p_next = float(payload.get("_true_p_next", p_curr))
                step = int(payload.get("step", 0))

                p_prev = self.last_power.get(cp_id, p_curr)
                p_pred = self.ai_agent.predict_next_power(p_curr, p_prev, soc, hour)

                self.last_power[cp_id] = p_curr
                self.current_predictions[cp_id] = p_pred
                allocated, _ = self.ai_agent.dispatch_power(self.current_predictions)

                # Sobrecarga real: la demanda real agregada o la asignación corrompida supera P_red,max
                total_allocated = sum(allocated.values())
                # Si la IA subestima por telemetría falsa y no recorta a tiempo, hay sobrecarga real
                overload = (p_curr > P_GRID_MAX_W / 2.0) or (total_allocated > P_GRID_MAX_W)

                self.step_logs.append({
                    "step": step,
                    "cp_id": cp_id,
                    "p_received": p_curr,
                    "p_true_next": true_p_next,
                    "p_pred_next": p_pred,
                    "overload": overload,
                })
                resp = [3, unique_id, {"status": "Accepted", "allocated_w": allocated.get(cp_id, p_pred)}]
            else:
                resp = [4, unique_id, "NotSupported", "Action not supported", {}]

            await websocket.send(json.dumps(resp))

    async def start_server(self):
        return await websockets.serve(self.handle_connection, HOST, CSMS_PORT)