"""Generación de perfiles sintéticos realistas de carga EV (ventanas de 15 min)."""
import numpy as np
import pandas as pd
from config import P_EVSE_MAX_W, RANDOM_SEED


def generate_clean_dataset(n_days: int = 15, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Genera series temporales limpias de potencia (W) y SoC (%) cada 15 min."""
    rng = np.random.default_rng(seed)
    records = []

    for day in range(n_days):
        soc = rng.uniform(15.0, 35.0)
        p_prev = 7000.0
        for step in range(96):  # 96 intervalos de 15 min = 24 horas
            hour = (step * 15) / 60.0
            # Curva bimodal realista (pico laboral mañana y pico residencial noche)
            base_demand = (
                6000.0
                + 8000.0 * np.exp(-0.5 * ((hour - 9.5) / 2.5) ** 2)
                + 11000.0 * np.exp(-0.5 * ((hour - 19.5) / 2.5) ** 2)
            )
            p_curr = float(np.clip(base_demand + rng.normal(0, 450.0), 1500.0, P_EVSE_MAX_W))

            # Evolución física del SoC (aprox. +2% a +8% por intervalo según potencia)
            delta_soc = (p_curr / P_EVSE_MAX_W) * 6.5
            soc = soc + delta_soc
            if soc >= 95.0:
                soc = rng.uniform(15.0, 30.0)  # Nuevo vehículo conectado

            # Potencia siguiente (objetivo a predecir)
            next_hour = ((step + 1) % 96 * 15) / 60.0
            next_base = (
                6000.0
                + 8000.0 * np.exp(-0.5 * ((next_hour - 9.5) / 2.5) ** 2)
                + 11000.0 * np.exp(-0.5 * ((next_hour - 19.5) / 2.5) ** 2)
            )
            p_next = float(np.clip(next_base + rng.normal(0, 400.0), 1500.0, P_EVSE_MAX_W))

            records.append({
                "p_curr": p_curr,
                "p_prev": p_prev,
                "soc": soc,
                "hour": hour,
                "p_next": p_next,
            })
            p_prev = p_curr

    return pd.DataFrame(records)


def generate_evse_session_profile(steps: int, seed_offset: int = 0) -> list[dict]:
    """Genera el perfil real de telemetría para una estación EVSE en un escenario."""
    rng = np.random.default_rng(RANDOM_SEED + seed_offset)
    profile = []
    soc = rng.uniform(20.0, 35.0)

    for step in range(steps):
        hour = (8.0 + (step * 15) / 60.0) % 24.0
        base = (
            6500.0
            + 7500.0 * np.exp(-0.5 * ((hour - 10.0) / 2.5) ** 2)
            + 10500.0 * np.exp(-0.5 * ((hour - 19.0) / 2.5) ** 2)
        )
        p_w = float(np.clip(base + rng.normal(0, 350.0), 2000.0, P_EVSE_MAX_W))
        soc = min(98.0, soc + (p_w / P_EVSE_MAX_W) * 5.0)
        if soc >= 96.0:
            soc = rng.uniform(20.0, 30.0)

        profile.append({
            "step": step,
            "hour": round(hour, 2),
            "power_w": round(p_w, 2),
            "soc": round(soc, 2),
        })
    return profile