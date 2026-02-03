import os
import sys
from datetime import datetime
# ============================================================================
# 1. ARQUITECTURA DE RUTAS (El Portero)
# ============================================================================
# Localizamos la raíz y el edificio 'src' para que Python sepa dónde buscar.
base_path = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(base_path, "src")
sys.path.append(src_path)

# ============================================================================
# 2. IMPORTACIONES CONSOLIDADAS (Higiene E402)
# ============================================================================
# Usamos # noqa: E402 porque la inyección del path debe ser previa a los imports.
from bloque1.network import NetworkIndexer  # noqa: E402
from bloque1.topology import TopologyBuilder  # noqa: E402
from bloque1.models import NodeRecord, ArcRecord  # noqa: E402
from bloque2.generator import ScenarioAnalyzer  # noqa: E402
from bloque2.integration import StochasticNetworkPipeline  # noqa: E402

def ejecutar_pipeline():
    """
    Orquestación de la Verdad: 
    Une la topología del Bloque 1 con el motor de crisis del Bloque 2.
    """
    
    print("\n" + "="*80)
    print("PRIME LOGISTICS - SISTEMA DE SIMULACIÓN DE RIESGO")
    print("="*80)

    # 1. CONSTRUCCIÓN DE LA TOPOLOGÍA (BLOQUE 1)
    # ------------------------------------------------------------------------
    print("\n1. Reconstruyendo Topología Base...")
    indexer = NetworkIndexer()
    
    # Registro de Nodos
    indexer.register_node(NodeRecord.from_dict({
        'id': 'WAREHOUSE_001', 'lat': -34.60, 'lon': -58.38, 'supply': 1000, 'demand': 0
    }))
    indexer.register_node(NodeRecord.from_dict({
        'id': 'CLIENT_001', 'lat': -34.90, 'lon': -57.95, 'supply': 0, 'demand': 500
    }))
    
    # Registro de Arcos
    indexer.register_arc(ArcRecord.from_dict({
        'id': 'ARC_01', 
        'origin': 'WAREHOUSE_001', 
        'destination': 'CLIENT_001', 
        'active': True,
        'capacity': 10000,
        'cost_profile': None, 
        'speed_profile': None,
        'metadata': None
    }))

    tb = TopologyBuilder(indexer)
    tb.build_topology()
    topology_package = tb.export_matrices(sparse=False)
    print(f"   ✓ Topología estática lista: {len(topology_package['nodes'])} nodos.")

    # 2. INICIALIZACIÓN DEL PIPELINE (BLOQUE 2)
    # ------------------------------------------------------------------------
    print("\n2. Ejecutando Motor de Riesgo Dinámico (Monte Carlo)...")
    pipeline = StochasticNetworkPipeline(seed=42)
    
    # Cargamos la topología en el pipeline
    pipeline.load_topology_from_bloque1(topology_package)

    # ========================================================================
    # PASO 3: VERIFICACIÓN DE RIGOR (AUDITORÍA DE INTEGRIDAD)
    # Este punto de control asegura que la capacidad base está registrada
    # para poder medir la pérdida real después.
    # ========================================================================
    print("\n" + "-"*50)
    print("AUDITORÍA DE INTEGRIDAD DE DATOS")
    has_k_sum = 'base_k_sum' in pipeline.base_network.meta
    k_value = pipeline.base_network.meta.get('base_k_sum', 0)
    print(f"¿base_k_sum presente?: {has_k_sum}")
    print(f"Valor de capacidad base: {k_value}")
    print("-"*50 + "\n")
    
    if not has_k_sum or k_value == 0:
        print("⚠ ADVERTENCIA: La auditoría detectó falta de métrica base.")
    # ========================================================================

    # 4. GENERACIÓN DE ESCENARIOS CON CONVERGENCIA
    # ------------------------------------------------------------------------
    manifest_path = os.path.join(src_path, "bloque2", "manifest.yaml")
    pipeline.load_incident_manifest(manifest_path)

    n_scenarios_limit = 5000
    print(f"   Iniciando simulación (Límite: {n_scenarios_limit} iteraciones)...")
    
    # El motor decidirá cuándo frenar basándose en Media, P95 y Varianza
    scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=n_scenarios_limit)

    # 5. ANÁLISIS DE RESILIENCIA
    # ------------------------------------------------------------------------
    # Usamos el ScenarioAnalyzer para procesar los resultados del Engine
    stats = ScenarioAnalyzer.compute_statistics(scenarios)
    
    print("\n" + "-"*40)
    print("RESUMEN DE RESILIENCIA LOGÍSTICA")
    print("-"*40)
    print(f"Escenarios generados: {stats['n_scenarios']}")
    print(f"Escenarios con incidentes: {stats['scenarios_with_events']} ({stats['scenarios_with_events']/stats['n_scenarios']*100:.1f}%)")
    print(f"Pérdida promedio de capacidad: {stats['avg_capacity_loss']*100:.2f}%")
    
    # Identificación del Peor Caso
    worst = ScenarioAnalyzer.get_worst_case_scenario(scenarios)
    print(f"\nCRITICAL: Peor escenario detectado (# {worst.scenario_id})")
    print(f"Eventos activos: {[e.code for e in worst.events]}")
    print(f"Capacidad retenida: {worst.get_capacity_reduction()*100:.1f}%")

    # 6. EXPORTACIÓN PARA EL OPTIMIZADOR (BLOQUE 3)
    # ------------------------------------------------------------------------
    output_dir = os.path.join(base_path, "output")
    os.makedirs(output_dir, exist_ok=True)

    pipeline.export_for_optimizer(os.path.join(output_dir, "scenarios.pkl"))
    
    # Generamos reporte en texto para auditoría humana
    report_path = os.path.join(output_dir, "reporte_riesgo.txt")
    with open(report_path, "w") as f:
        f.write("REPORTE DE RIESGO - PRIME LOGISTICS\n")
        f.write(f"Fecha: {datetime.now()}\n")
        f.write(f"Escenarios: {stats['n_scenarios']}\n")
        f.write(f"Capacidad Promedio Retenida: {stats['avg_capacity_retention']*100:.2f}%\n")
        f.write(f"Peor Escenario ID: {worst.scenario_id} con {worst.get_capacity_reduction()*100:.2f}%\n")

    print(f"\n✓ PROCESO COMPLETADO: {len(scenarios)} datos listos para la optimización.")
    print("="*80 + "\n")

if __name__ == "__main__":
    ejecutar_pipeline()
    
