# main_bloque3.py
"""
Orquestador Principal del Bloque 3: Bayesian Inference Engine.
Une Auditor, Judge, Metrics y Report para procesar los escenarios del Bloque 2.
"""

from src.bloque3.auditor import load_scenarios, audit_scenarios, FailureCriteria
from src.bloque3.bayesian_judge import BayesianJudge, PriorConfig
from src.bloque3.metrics import compute_risk_matrix, compute_node_reliability
from src.bloque3 import ReliabilityReport 

def run_inference_pipeline(scenarios_path: str, node_ids: list[str]):
    # 1. Configuración de Criterios y Prior
    criteria = FailureCriteria(
        min_capacity_retained=0.85,
        max_time_multiplier=1.4,
        max_cost_multiplier=1.5
    )
    prior = PriorConfig(alpha=1.0, beta=1.0) # Prior no informativo
    
    # 2. Carga y Auditoría (Fase Forense)
    print(f"Cargando escenarios desde {scenarios_path}...")
    raw_scenarios = load_scenarios(scenarios_path)
    audit_records = audit_scenarios(raw_scenarios, criteria)
    
    # 3. Inferencia Bayesiana (Fase de Aprendizaje)
    judge = BayesianJudge(prior=prior)
    
    print("Iniciando juicio bayesiano de componentes...")
    for audit, scenario in zip(audit_records, raw_scenarios):
        # Extraemos qué falló específicamente en este escenario (Data del Bloque 2)
        # El Bloque 2 debe entregar estas llaves en el diccionario del escenario
        failed_nodes = scenario.get("failed_nodes", [])
        failed_arcs = scenario.get("failed_arcs", [])
        
        judge.observe(
            audit=audit, 
            failed_nodes=failed_nodes, 
            failed_arcs=failed_arcs
        )
    
    # 4. Cálculo de Métricas y Matriz L_total
    print("Calculando Tensor de Riesgo (L_total)...")
    risk_matrix = compute_risk_matrix(
        node_index=node_ids,
        arc_params=judge.arc_params(),
        node_params=judge.node_params(),
        system_params=judge.system_params(),
        prior=prior
    )
    
    node_reliability = compute_node_reliability(judge.node_params(), prior)
    
    # 5. Generación del Reporte Final (El Diploma)
    # Construimos los intervalos de confianza para el reporte
    conf_intervals = {}
    # (Opcional: podrías iterar y llenar ConfidenceInterval con la varianza aquí)
    
    report = ReliabilityReport(
        risk_matrix=risk_matrix,
        node_fragility=[(nid, 1.0 - rel) for nid, rel in node_reliability.items()],
        confidence_interval=conf_intervals,
        notes=[
            f"Procesados {len(raw_scenarios)} escenarios.",
            "Modelo de supervivencia: L_total = L_arc * L_node_i * L_node_j * L_sys"
        ]
    )
    
    return report

if __name__ == "__main__":
    # Ejemplo de uso (ajustar node_ids a tu topología del Bloque 1)
    MIS_NODOS = ["N_001", "N_002", "N_003", "N_004"] 
    PATH_DATA = "data/scenarios.pkl"
    
    try:
        resultado = run_inference_pipeline(PATH_DATA, MIS_NODOS)
        
        print("\n--- REPORTE DE CONFIABILIDAD PRIME ---")
        print(f"Nodos más frágiles: {resultado.top_fragile_nodes(3)}")
        print(f"Matriz de riesgo calculada: {len(resultado.risk_matrix)}x{len(resultado.risk_matrix[0])}")
        
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo en {PATH_DATA}. ¿Corriste el Bloque 2?")
    except Exception as e:
        print(f"Error en la ejecución: {e}")