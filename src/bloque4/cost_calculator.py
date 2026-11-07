#src/bloque4/cost_calculator.py
import math
from src.block5.speed_profile_loader import get_h3_parent, get_velocity_multiplier

# Mapeo ref OSM → costo de peaje AMBA
# Fuente: datos reales de concesionarias AUSA y AUBASA
_REF_TOLL_MAP = {
    "RN7":  "acceso_norte_oeste_ars",   # Acceso Oeste — AUBASA
    "RN8":  "acceso_norte_oeste_ars",   # Acceso Norte — AUBASA
    "RN9":  "acceso_norte_oeste_ars",   # Acceso Norte ramal — AUBASA
    "AU1":  "ausa_25_mayo_ars",         # Autopista 25 de Mayo — AUSA
    "AU2":  "aubasa_sur_ars",           # Buenos Aires-La Plata — AUBASA
    "AU6":  "ausa_paseo_bajo_ars",      # Perito Moreno — AUSA
    "AU7":  "ausa_paseo_bajo_ars",      # Paseo del Bajo — AUSA
    "RN3":  "aubasa_sur_ars",           # Autopista del Sur — AUBASA
    "RN2":  "aubasa_sur_ars",           # Ruta 2 — AUBASA
}

# Km de autopista que cubre un peaje (aprox.). Mismo orden de magnitud que ruta_tipica_km.
KM_POR_PEAJE = 10.0

def _get_toll_from_ref(ref_value: str, cost_env) -> float:
    """
    Resuelve el costo de peaje desde el campo ref de OSM.
    Maneja refs compuestos tipo 'RN7;AU1' tomando el primer match.
    Retorna 0.0 si no hay match (la arista no es autopista con peaje conocido).
    """
    if not ref_value:
        return 0.0
    tokens = [t.strip() for t in str(ref_value).split(";")]
    for token in tokens:
        settings_key = _REF_TOLL_MAP.get(token)
        if settings_key:
            return float(getattr(cost_env, settings_key, 0.0))
    return 0.0

def compute_edge_cost(
    payload,
    u_rx: int,
    v_rx: int,
    cost_env,
    threat_matrix,
    judge,
    departure_hour: int,
    speed_profiles: dict,
    archetype: str
) -> tuple[float, bool]:
    """Centralized financial logic for evaluating single edges using CFO-Grade nested EconomicProfile."""
    if archetype == "tanque":
        lambda_cost, lambda_risk = 0.01, 0.99
    elif archetype == "apostador":
        lambda_cost, lambda_risk = 0.99, 0.01
    elif archetype == "equilibrista":
        lambda_cost, lambda_risk = 0.5, 0.5
    else:
        lambda_cost, lambda_risk = 1.0, 0.0

    # --- CFO Calculations (Refactor de Raíz) ---
    opex = cost_env.opex_movil
    personal = cost_env.personal
    capex = cost_env.capex

    # 1. Costo por KM (CKM)
    c_km_ars = (opex.gasoil_ars_l * opex.consumo_l_km) + opex.neumaticos_km_ars + opex.mantenimiento_km_ars

    # 2. Costo por Hora (CH)
    c_lab = (personal.sueldo_basico_ars * personal.cargas_sociales_factor) + \
            personal.bono_mensual_ars + \
            (personal.viatico_dia_ars * 22) + \
            personal.provision_sac_vacaciones_ars
    ch_lab = c_lab / personal.jornada_mensual_hs

    c_amort = (capex.valor_unidad_ars * (1 - capex.valor_recupero_pct)) / capex.vida_util_meses
    ch_est = (c_amort + capex.seguros_patentes_mes_ars + capex.telemetria_mes_ars) / personal.jornada_mensual_hs
    c_hora_ars = ch_lab + ch_est

    # 3. Auxiliares
    peaje_promedio_ars = getattr(cost_env, 'peaje_promedio_ars', 1200.0)
    vel_kmh = getattr(cost_env, 'velocidad_comercial_kmh', 40.0)
    dolar_mep = getattr(cost_env, 'dolar_mep_ars', 1420.0)
    custodia_hora_ars = getattr(cost_env, 'custodia_hora_ars', 0.0)
    franquicia_ars = getattr(cost_env, 'franquicia_seguro_usd', 1500.0) * dolar_mep
    
    ruta_tipica_km = 10.0

    # --- Lógica de Riesgo ---
    if callable(getattr(judge, 'get_params', None)):
        beta_params = judge.get_params(u_rx, v_rx)
        alpha = beta_params.alpha
        beta = beta_params.beta
    else:
        alpha = 100.0
        beta = 3.0

    p_survival = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.999999
    p_failure = 1.0 - p_survival

    # --- Lógica Financiera ---
    dist_km = payload.length / 1000.0
    h3_parent = get_h3_parent(payload.h3_index)
    multiplier = get_velocity_multiplier(speed_profiles, payload.highway, h3_parent, departure_hour)
    effective_velocity = vel_kmh * multiplier
    time_hr = dist_km / effective_velocity

    financial_cost_ars = (dist_km * c_km_ars) + (time_hr * c_hora_ars)

    if payload.h3_index and payload.h3_index in threat_matrix:
        mu = threat_matrix[payload.h3_index]
        financial_cost_ars += time_hr * custodia_hora_ars * mu

    used_toll_fallback = False
    if payload.highway in {"motorway", "motorway_link", "trunk", "trunk_link"}:
        # El peaje se paga por cruce, pero cada arista mide ~350 m. Para no cobrarlo en cada
        # arista, se reparte por largo: un peaje completo cada KM_POR_PEAJE km de autopista.
        fraccion_peaje = dist_km / KM_POR_PEAJE
        name_upper = payload.name.upper() if getattr(payload, 'name', None) else ""
        if "25 DE MAYO" in name_upper or "PERITO MORENO" in name_upper:
            peaje = getattr(cost_env, 'ausa_25_mayo_ars', 1200.0)
        elif "PASEO DEL BAJO" in name_upper:
            peaje = getattr(cost_env, 'ausa_paseo_bajo_ars', 1200.0)
        elif "PANAMERICANA" in name_upper or "ACCESO NORTE" in name_upper or "ACCESO OESTE" in name_upper:
            peaje = getattr(cost_env, 'acceso_norte_oeste_ars', 1300.0)
        elif "BUENOS AIRES - LA PLATA" in name_upper or "RICCHERI" in name_upper:
            peaje = getattr(cost_env, 'aubasa_sur_ars', 900.0)
        else:
            ref_value = getattr(payload, 'ref', None)
            peaje = _get_toll_from_ref(ref_value, cost_env)
            if peaje <= 0.0:
                peaje = peaje_promedio_ars
                used_toll_fallback = True
        financial_cost_ars += peaje * fraccion_peaje

    risk_cost_ars = p_failure * franquicia_ars * (dist_km / ruta_tipica_km)
    weight = float((lambda_cost * financial_cost_ars) + (lambda_risk * risk_cost_ars))
    
    return weight, used_toll_fallback
