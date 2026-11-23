"""Parámetros globales de configuración del entorno OCPP 1.6J e IA."""

HOST = "127.0.0.1"
CSMS_PORT = 8766         # Puerto del servidor central CSMS
MIDDLEWARE_PORT = 8765   # Puerto del proxy inverso (Middleware)

# Estaciones autorizadas (Lista blanca)
WHITELIST_EVSE = ["CP_001", "CP_002", "CP_003"]

# Límites físicos del sistema eléctrico
P_EVSE_MAX_W = 22000.0   # Potencia máxima por cargador AC (22 kW)
P_GRID_MAX_W = 45000.0   # Límite térmico del transformador local (45 kW)
MAX_DELTA_SOC = 15.0     # Cambio máximo físicamente posible de SoC en 15 min (%)

# Parámetros del filtro estadístico (Z-score móvil)
Z_THRESHOLD = 3.0        # Umbral tau = 3.0
Z_WINDOW_SIZE = 10       # Ventana móvil de lecturas recientes

# Parámetros de simulación
STEPS_PER_SCENARIO = 48  # 48 intervalos de 15 min (12 horas simuladas)
RANDOM_SEED = 42