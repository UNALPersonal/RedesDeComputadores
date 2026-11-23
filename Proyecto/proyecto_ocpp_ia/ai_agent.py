"""Agente predictivo de demanda (scikit-learn) y planificador restringido de potencia."""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from config import P_GRID_MAX_W, RANDOM_SEED
from data_generator import generate_clean_dataset


class SmartChargingAIAgent:
    def __init__(self):
        self.model = RandomForestRegressor(
            n_estimators=60, max_depth=8, random_state=RANDOM_SEED
        )
        self.is_trained = False
        self.train_metrics = {}

    def train(self):
        """Entrena el modelo exclusivamente con datos limpios (70% train / 30% val)."""
        df = generate_clean_dataset(n_days=20)
        X = df[["p_curr", "p_prev", "soc", "hour"]].values
        y = df["p_next"].values

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.30, random_state=RANDOM_SEED
        )
        self.model.fit(X_train, y_train)
        preds = self.model.predict(X_val)

        self.train_metrics = {
            "val_mae": float(mean_absolute_error(y_val, preds)),
            "val_rmse": float(root_mean_squared_error(y_val, preds)),
        }
        self.is_trained = True
        return self.train_metrics

    def predict_next_power(self, p_curr: float, p_prev: float, soc: float, hour: float) -> float:
        """Pronostica la potencia requerida P_{t+1} para una estación."""
        if not self.is_trained:
            self.train()
        features = np.array([[p_curr, p_prev, soc, hour]])
        return float(self.model.predict(features)[0])

    @staticmethod
    def dispatch_power(predicted_demands: dict[str, float]) -> tuple[dict[str, float], bool]:
        """
        Planificador determinístico: limita la potencia asignada si la suma
        supera el límite térmico del transformador P_red,max.
        """
        total_pred = sum(predicted_demands.values())
        if total_pred <= P_GRID_MAX_W or total_pred == 0:
            return dict(predicted_demands), False

        scale = P_GRID_MAX_W / total_pred
        allocated = {cp: round(val * scale, 2) for cp, val in predicted_demands.items()}
        return allocated, True