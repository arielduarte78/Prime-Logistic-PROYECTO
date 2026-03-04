# =============================================================================
# CONTRATO DE UNIDADES Y ESCALAS (LA FUENTE DE LA VERDAD)
# =============================================================================
UNIDAD_CARGA = "t"        # Toneladas métricas (Estándar del sistema)
UNIDAD_COSTO = "USD"      # Dólares americanos

# Límites de Cordura (Sanity Checks)
# Si un dato de entrada supera estos valores, el Bloque 1 lanzará una alerta.
MAX_CAPACIDAD_FISICA = 50000.0  # Máximo absoluto (ej. un carguero masivo)
MAX_COSTO_OPERATIVO = 100000.0  # Máximo costo variable por arco

# =============================================================================
# PARÁMETROS DE LA INFRAESTRUCTURA (BLOQUE 1)
# =============================================================================
# Valores por defecto si el dato de entrada es nulo o faltante
DEFAULT_CAPACIDAD = 1000.0
DEFAULT_COSTO_FIJO = 2500.0

# =============================================================================
# PARÁMETROS DE INCERTIDUMBRE Y RIESGO (BLOQUE 2 Y 3)
# =============================================================================
N_ESCENARIOS = 5000           # Simulaciones de Monte Carlo para Bayes
SIGMA_DEMANDA = 0.15          # Volatilidad relativa (15%)

# Hiperparámetro de Aversión al Riesgo
# 0.0 = Ignora el riesgo (Temerario)
# 10.0+ = Prioriza seguridad absoluta (Conservador)
LAMBDA_RIESGO = 5.0



# --- POLÍTICA TEMPORAL ---
SYSTEM_TIMEZONE = "UTC" # Todo timestamp naive se interpreta como UTC

# --- UNIDADES ESTÁNDAR ---
UNIT_DISTANCE = "km"
UNIT_SPEED = "km/h"
UNIT_COST = "USD"
UNIT_MASS = "t"

# --- LIMITES DE CORDURA ---
MAX_LATITUDE = 90.0
MIN_LATITUDE = -90.0
MAX_LONGITUDE = 180.0
MIN_LONGITUDE = -180.0
