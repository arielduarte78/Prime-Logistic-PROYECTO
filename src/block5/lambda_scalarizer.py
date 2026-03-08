#src/block5/lambda_scalarizer.py
import math
from typing import Callable, Any
from src.bloque1.graph_builder import EdgePayload
from src.block5.speed_profile_loader import get_h3_parent, get_velocity_multiplier

def get_weight_function(archetype: str, cost_env: Any, threat_matrix: dict, judge: Any, osm_to_rx: dict, departure_hour: int = 12, speed_profiles: dict = None) -> Callable[[Any], float]:
    if speed_profiles is None:
        speed_profiles = {}
        
    if archetype == "tanque":
        lambda_cost, lambda_risk = 0.1, 0.9
    elif archetype == "apostador":
        lambda_cost, lambda_risk = 0.9, 0.1
    elif archetype == "equilibrista":
        lambda_cost, lambda_risk = 0.5, 0.5
    else:
        lambda_cost, lambda_risk = 1.0, 0.0

    peaje_promedio = cost_env.peaje_promedio_ars
    c_km = cost_env.c_km_ars
    c_hora = cost_env.c_hora_ars
    vel_kmh = cost_env.velocidad_comercial_kmh
    franquicia_ars = cost_env.franquicia_seguro_usd * cost_env.dolar_mep_ars
    ruta_tipica_km = 10.0 

    # Capturar en closure para acceso rapido
    _departure_hour = departure_hour
    _speed_profiles = speed_profiles

    # CACHE DE MEMOIZACION PARA MATAR EL BOTTLENECK DEL GIL
    cache = {}

    def weight_func(edge: Any) -> float:
        payload = edge if isinstance(edge, EdgePayload) else edge[2]
        
        # Fast-Path: Busqueda en cache por (direccion de memoria, hora de salida)
        cache_key = (id(payload), _departure_hour)
        if cache_key in cache:
            return cache[cache_key]
            
        # 1. Riesgo Dinamico
        u_rx = osm_to_rx.get(payload.u_osm)
        v_rx = osm_to_rx.get(payload.v_osm)
        pos = judge._arc_index.get((u_rx, v_rx)) if u_rx is not None and v_rx is not None else None
        
        if pos is not None:
            alpha = float(judge._alphas[pos])
            beta = float(judge._betas[pos])
        else:
            alpha = payload.alpha_prior
            beta = payload.beta_prior
            
        p_survival = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.999999
        p_failure = 1.0 - p_survival

        # 2. Costo Financiero (ARS) — con velocidad efectiva por trafico
        dist_km = payload.length / 1000.0
        
        h3_parent = get_h3_parent(payload.h3_index)
        multiplier = get_velocity_multiplier(_speed_profiles, payload.highway, h3_parent, _departure_hour)
        effective_velocity = vel_kmh * multiplier
        time_hr = dist_km / effective_velocity
        
        financial_cost_ars = (dist_km * c_km) + (time_hr * c_hora)

        if payload.h3_index and payload.h3_index in threat_matrix:
            mu = threat_matrix[payload.h3_index]
            financial_cost_ars += time_hr * cost_env.custodia_hora_ars * mu

        if payload.highway in {"motorway", "motorway_link", "trunk", "trunk_link"}:
            name_upper = payload.name.upper() if payload.name else ""
            if "25 DE MAYO" in name_upper or "PERITO MORENO" in name_upper:
                financial_cost_ars += cost_env.ausa_25_mayo_ars
            elif "PASEO DEL BAJO" in name_upper or "BAJO" in name_upper:
                financial_cost_ars += cost_env.ausa_paseo_bajo_ars
            elif "PANAMERICANA" in name_upper or "ACCESO NORTE" in name_upper or "ACCESO OESTE" in name_upper:
                financial_cost_ars += cost_env.acceso_norte_oeste_ars
            elif "BUENOS AIRES - LA PLATA" in name_upper or "RICCHERI" in name_upper:
                financial_cost_ars += cost_env.aubasa_sur_ars
            else:
                financial_cost_ars += peaje_promedio

        risk_cost_ars = p_failure * franquicia_ars * (dist_km / ruta_tipica_km)
        weight = float((lambda_cost * financial_cost_ars) + (lambda_risk * risk_cost_ars))
        
        # Guardar en cache antes de retornar
        cache[cache_key] = weight
        return weight

    return weight_func
