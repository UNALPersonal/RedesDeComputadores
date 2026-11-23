"""Cliente simulador de estación de carga EVSE bajo protocolo OCPP 1.6J."""
import json
import uuid
import asyncio
import websockets


async def run_evse_session(
    cp_id: str,
    target_uri: str,
    profile: list[dict],
    delay_s: float = 0.01,
    captured_frames: list = None,
):
    """Ejecuta el ciclo OCPP 1.6J completo de una estación EVSE."""
    async with websockets.connect(f"{target_uri}/{cp_id}") as ws:
        # 1. BootNotification
        await ws.send(json.dumps([2, str(uuid.uuid4()), "BootNotification", {"chargePointModel": "UNAL-EVSE"}]))
        await ws.recv()

        # 2. StatusNotification & StartTransaction
        await ws.send(json.dumps([2, str(uuid.uuid4()), "StatusNotification", {"status": "Charging"}]))
        await ws.recv()
        await ws.send(json.dumps([2, str(uuid.uuid4()), "StartTransaction", {"connectorId": 1}]))
        await ws.recv()

        # 3. MeterValues periódicos
        for idx in range(len(profile) - 1):
            curr = profile[idx]
            nxt = profile[idx + 1]
            payload = {
                "step": curr["step"],
                "hour": curr["hour"],
                "power_w": curr["power_w"],
                "soc": curr["soc"],
                "_true_p_next": nxt["power_w"],
                "_is_attack": False,
            }
            frame_str = json.dumps([2, str(uuid.uuid4()), "MeterValues", payload])
            if captured_frames is not None and idx % 5 == 0:
                captured_frames.append(frame_str)  # El atacante sniffea tramas para replay

            await ws.send(frame_str)
            await ws.recv()
            await asyncio.sleep(delay_s)

        # 4. StopTransaction
        await ws.send(json.dumps([2, str(uuid.uuid4()), "StopTransaction", {"reason": "Local"}]))
        await ws.recv()