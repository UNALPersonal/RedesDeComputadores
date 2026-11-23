"""Middleware explicable (Proxy Inverso WebSocket) con validación en 3 niveles."""
import json
import time
from collections import deque
import numpy as np
import websockets
from config import (
    HOST,
    CSMS_PORT,
    MIDDLEWARE_PORT,
    WHITELIST_EVSE,
    P_EVSE_MAX_W,
    MAX_DELTA_SOC,
    Z_THRESHOLD,
    Z_WINDOW_SIZE,
)


class OCPPValidationMiddleware:
    def __init__(self):
        self.reset_state()

    def reset_state(self):
        self.seen_unique_ids = set()
        self.session_states = {}  # Aislamiento por sesión WebSocket
        self.metrics = {"TP": 0, "FP": 0, "TN": 0, "FN": 0, "latencies_ms": []}

    def validate_frame(self, session_id: int, cp_id: str, raw_message: str) -> tuple[bool, str]:
        """
        Inspecciona la trama OCPP 1.6J en 3 niveles:
        (a) Sintaxis e identidad, (b) Invariantes físicos, (c) Z-score móvil sobre Delta P.
        """
        # --- Nivel (a): Validación sintáctica y de identidad ---
        if cp_id not in WHITELIST_EVSE:
            return False, "UNREGISTERED_CP_ID"

        try:
            frame = json.loads(raw_message)
            if not isinstance(frame, list) or len(frame) != 4 or frame[0] != 2:
                return False, "INVALID_OCPP_SCHEMA"
            _, unique_id, action, payload = frame
        except Exception:
            return False, "MALFORMED_JSON"

        if unique_id in self.seen_unique_ids:
            return False, "REPLAY_DUPLICATE_UNIQUE_ID"
        self.seen_unique_ids.add(unique_id)

        if action != "MeterValues":
            return True, "OK"

        try:
            power_w = float(payload["power_w"])
            soc = float(payload["soc"])
        except (KeyError, ValueError, TypeError):
            return False, "MISSING_TELEMETRY_FIELDS"

        # --- Nivel (b): Invariantes físicos del dominio ---
        if not (0.0 <= soc <= 100.0):
            return False, "PHYSICAL_SOC_OUT_OF_BOUNDS"
        if not (0.0 <= power_w <= P_EVSE_MAX_W):
            return False, "PHYSICAL_POWER_OUT_OF_BOUNDS"

        state = self.session_states.setdefault(
            session_id,
            {"last_soc": None, "last_p": None, "dp_window": deque(maxlen=Z_WINDOW_SIZE)},
        )

        if state["last_soc"] is not None:
            delta_soc = abs(soc - state["last_soc"])
            is_new_session = state["last_soc"] >= 90.0 and soc <= 35.0
            if delta_soc > MAX_DELTA_SOC and not is_new_session:
                return False, "PHYSICAL_DELTA_SOC_VIOLATION"

        # --- Nivel (c): Filtro estadístico ligero (Z-score sobre tasa de cambio Delta P) ---
        if state["last_p"] is not None:
            delta_p = power_w - state["last_p"]
            dp_window = state["dp_window"]
            if len(dp_window) >= 3:
                mean_dp = float(np.mean(dp_window))
                # Piso de ruido natural de 750 W para absorber curvatura diaria sin falsos positivos
                std_dp = max(float(np.std(dp_window)), 750.0)
                z_score = abs(delta_p - mean_dp) / std_dp
                if z_score > Z_THRESHOLD:
                    return False, f"STATISTICAL_ZSCORE_ANOMALY ({z_score:.2f})"
            dp_window.append(delta_p)

        # Actualizar estado histórico sano de la sesión
        state["last_soc"] = soc
        state["last_p"] = power_w
        return True, "OK"

    async def handle_client(self, client_ws):
        """Proxy inverso: recibe del EVSE/Atacante, valida y reenvía al CSMS."""
        path = getattr(client_ws, "path", None) or getattr(
            getattr(client_ws, "request", None), "path", "/UNKNOWN"
        )
        cp_id = path.strip("/")
        session_id = id(client_ws)
        csms_uri = f"ws://{HOST}:{CSMS_PORT}/{cp_id}"

        async with websockets.connect(csms_uri) as csms_ws:
            async for message in client_ws:
                t0 = time.perf_counter()
                is_valid, reason = self.validate_frame(session_id, cp_id, message)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                self.metrics["latencies_ms"].append(dt_ms)

                try:
                    frame = json.loads(message)
                    is_attack = bool(frame[3].get("_is_attack", False))
                    unique_id = frame[1]
                    action = frame[2]
                except Exception:
                    is_attack, unique_id, action = True, "0", "Unknown"

                if action == "MeterValues":
                    if is_attack and not is_valid:
                        self.metrics["TP"] += 1
                    elif not is_attack and not is_valid:
                        self.metrics["FP"] += 1
                    elif not is_attack and is_valid:
                        self.metrics["TN"] += 1
                    elif is_attack and is_valid:
                        self.metrics["FN"] += 1

                if is_valid:
                    await csms_ws.send(message)
                    csms_resp = await csms_ws.recv()
                    await client_ws.send(csms_resp)
                else:
                    error_frame = json.dumps([4, unique_id, "SecurityError", reason, {}])
                    await client_ws.send(error_frame)

    async def start_server(self):
        return await websockets.serve(self.handle_client, HOST, MIDDLEWARE_PORT)