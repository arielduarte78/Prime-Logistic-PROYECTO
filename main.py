import os
import sys

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

    # 1. CARGA DE LA RED BASE (BLOQUE 1)
    # ------------------------------------------------------------------------
    print("\n1. Reconstruyendo Topología Base...")
    indexer = NetworkIndexer()
    
    # CONTRATO DE NODOS: Usamos 'lat' y 'lon' como pide tu modelo.
    indexer.register_node(NodeRecord.from_dict({
        'id': 'WAREHOUSE_001', 'lat': -34.60, 'lon': -58.38, 'supply': 1000, 'demand': 0
    }))
    indexer.register_node(NodeRecord.from_dict({
        'id': 'CLIENT_001', 'lat': -34.90, 'lon': -57.95, 'supply': 0, 'demand': 500
    }))
    
    # CONTRATO DE ARCOS: Respetamos los campos reales (cost_profile, speed_profile)
    # y eliminamos 'transport_mode' que no existe en tu ArcRecord.
    indexer.register_arc(ArcRecord.from_dict({
        'id': 'ARC_01', 
        'origin': 'WAREHOUSE_001', 
        'destination': 'CLIENT_001', 
        'active': True,
        'cost_profile': None,  # Tu modelo espera un objeto o None
        'speed_profile': None,
        'metadata': None
    }))

    tb = TopologyBuilder(indexer)
    tb.build_topology()
    topology_package = tb.export_matrices(sparse=False)
    print(f"   ✓ Topología estática lista: {len(topology_package['nodes'])} nodos.")

    # 2. GENERACIÓN DE ESCENARIOS (BLOQUE 2)
    # ------------------------------------------------------------------------
    print("\n2. Ejecutando Motor de Riesgo Dinámico (Monte Carlo)...")
    pipeline = StochasticNetworkPipeline(seed=42)
    
    # Inyectamos el mapa y las leyes de probabilidad (manifest.yaml)
    pipeline.load_topology_from_bloque1(topology_package)
    
    manifest_path = os.path.join(src_path, "bloque2", "manifest.yaml")
    pipeline.load_incident_manifest(manifest_path)

    n_scenarios = 500
    print(f"   Generando {n_scenarios} escenarios de crisis para Argentina...")
    scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=n_scenarios)

    # 3. AUDITORÍA DE IMPACTO
    # ------------------------------------------------------------------------
    stats = pipeline.get_statistics()
    print("\n" + "-"*40)
    print("RESUMEN DE RESILIENCIA LOGÍSTICA")
    print("-"*40)
    print(f"Escenarios con incidentes: {stats['scenarios_with_events']} ({stats['scenarios_with_events']/n_scenarios*100:.1f}%)")
    print(f"Pérdida promedio de capacidad: {stats['avg_capacity_loss']*100:.2f}%")
    
    # Identificación del Peor Caso mediante el Analizador
    worst = ScenarioAnalyzer.get_worst_case_scenario(scenarios)
    print(f"\nCRITICAL: Peor escenario detectado (# {worst.scenario_id})")
    print(f"Capacidad retenida: {worst.get_capacity_reduction()*100:.1f}%")

    # 4. EXPORTACIÓN PARA EL OPTIMIZADOR (BLOQUE 3)
    # ------------------------------------------------------------------------
    output_dir = os.path.join(base_path, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    pipeline.export_for_optimizer(os.path.join(output_dir, "scenarios.pkl"))
    pipeline.generate_report(os.path.join(output_dir, "reporte_riesgo.txt"))

    print("\n✓ PROCESO COMPLETADO: Datos listos para la optimización.")
    print("="*80 + "\n")

if __name__ == "__main__":
    ejecutar_pipeline()