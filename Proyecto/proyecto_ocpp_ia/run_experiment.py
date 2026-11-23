"""Orquestador experimental de los escenarios E1, E2 y E3 + métricas y gráficas."""
import asyncio
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from config import HOST, CSMS_PORT, MIDDLEWARE_PORT, WHITELIST_EVSE, STEPS_PER_SCENARIO
from data_generator import generate_evse_session_profile
from ai_agent import SmartChargingAIAgent
from csms_server import CSMSServer
from middleware_proxy import OCPPValidationMiddleware
from evse_client import run_evse_session
from attacker import run_attack_campaign

# Ruta automática hacia Proyecto/Data sin importar desde dónde se ejecute VS Code
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "Data"


def compute_ia_metrics(logs: list[dict]) -> dict:
    df = pd.DataFrame(logs)
    mae = float(np.mean(np.abs(df["p_true_next"] - df["p_pred_next"])))
    rmse = float(np.sqrt(np.mean((df["p_true_next"] - df["p_pred_next"]) ** 2)))
    overloads = int(df["overload"].sum())
    return {"MAE_W": round(mae, 2), "RMSE_W": round(rmse, 2), "Sobrecargas": overloads}


async def run_all_scenarios():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Entrenando agente predictivo de IA con datos limpios...")
    agent = SmartChargingAIAgent()
    train_info = agent.train()
    print(f"      Validación IA -> MAE: {train_info['val_mae']:.2f} W | RMSE: {train_info['val_rmse']:.2f} W")

    csms = CSMSServer(agent)
    middleware = OCPPValidationMiddleware()

    csms_srv = await csms.start_server()
    mw_srv = await middleware.start_server()

    profiles = {
        cp: generate_evse_session_profile(STEPS_PER_SCENARIO, seed_offset=i * 10)
        for i, cp in enumerate(WHITELIST_EVSE)
    }

    results = {}

    # --- ESCENARIO E1: Operación Normal ---
    print("[2/4] Ejecutando Escenario E1 (Línea base normal)...")
    csms.reset_state()
    await asyncio.gather(*[
        run_evse_session(cp, f"ws://{HOST}:{CSMS_PORT}", profiles[cp])
        for cp in WHITELIST_EVSE
    ])
    results["E1_Normal"] = compute_ia_metrics(csms.step_logs)

    # --- ESCENARIO E2: Ataque sin Mitigación ---
    print("[3/4] Ejecutando Escenario E2 (Ataque sin filtro)...")
    csms.reset_state()
    captured = []
    await asyncio.gather(
        *[run_evse_session(cp, f"ws://{HOST}:{CSMS_PORT}", profiles[cp], captured_frames=captured)
          for cp in WHITELIST_EVSE],
        run_attack_campaign(f"ws://{HOST}:{CSMS_PORT}", captured)
    )
    results["E2_Ataque_Sin_Filtro"] = compute_ia_metrics(csms.step_logs)

    # --- ESCENARIO E3: Ataque con Middleware Activo ---
    print("[4/4] Ejecutando Escenario E3 (Ataque mitigado por Middleware)...")
    csms.reset_state()
    middleware.reset_state()
    captured = []
    await asyncio.gather(
        *[run_evse_session(cp, f"ws://{HOST}:{MIDDLEWARE_PORT}", profiles[cp], captured_frames=captured)
          for cp in WHITELIST_EVSE],
        run_attack_campaign(f"ws://{HOST}:{MIDDLEWARE_PORT}", captured)
    )
    results["E3_Ataque_Con_Middleware"] = compute_ia_metrics(csms.step_logs)

    csms_srv.close()
    mw_srv.close()
    await csms_srv.wait_closed()
    await mw_srv.wait_closed()

    # --- Métricas del Middleware ---
    m = middleware.metrics
    tp, fp, tn, fn = m["TP"], m["FP"], m["TN"], m["FN"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    avg_rtt = float(np.mean(m["latencies_ms"])) if m["latencies_ms"] else 0.0

    res_df = pd.DataFrame(results).T
    csv_path = DATA_DIR / "resumen_metricas.csv"
    res_df.to_csv(csv_path)

    print("\n================ RESULTADOS AGENTE DE IA ================")
    print(res_df.to_string())

    print("\n================ DESEMPEÑO DEL MIDDLEWARE ================")
    print(f"TP: {tp} | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"Precisión: {precision*100:.2f}% | Sensibilidad (Recall): {recall*100:.2f}% | FPR: {fpr*100:.2f}%")
    print(f"Latencia adicional promedio (Delta RTT): {avg_rtt:.3f} ms")

    # Generar gráfica comparativa directamente en Proyecto/Data
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    scenarios = ["E1 (Normal)", "E2 (Ataque)", "E3 (Mitigado)"]
    maes = [results[k]["MAE_W"] for k in results]
    rmses = [results[k]["RMSE_W"] for k in results]
    overloads = [results[k]["Sobrecargas"] for k in results]

    x = np.arange(len(scenarios))
    axes[0].bar(x - 0.18, maes, 0.35, label="MAE (W)", color="#2b5c8f")
    axes[0].bar(x + 0.18, rmses, 0.35, label="RMSE (W)", color="#d95f02")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(scenarios)
    axes[0].set_ylabel("Error de Predicción (W)")
    axes[0].set_title("Degradación y Recuperación del Agente IA")
    axes[0].legend()
    axes[0].grid(axis="y", linestyle="--", alpha=0.5)

    axes[1].bar(scenarios, overloads, color=["#1b9e77", "#e7298a", "#7570b3"])
    axes[1].set_ylabel("Eventos de Sobrecarga")
    axes[1].set_title("Impacto en Estabilidad Eléctrica")
    axes[1].grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plot_path = DATA_DIR / "comparativa_escenarios.png"
    plt.savefig(plot_path, dpi=300)
    print(f"\nGráfica guardada automáticamente en: {plot_path}")
    print(f"Tabla CSV guardada automáticamente en: {csv_path}")


if __name__ == "__main__":
    asyncio.run(run_all_scenarios())