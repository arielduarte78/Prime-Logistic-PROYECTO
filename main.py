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
from bloque3.inference_engine import InferenceEngine  # noqa: E402
from bloque3.inference_engine import InferenceConfig  # noqa: E402
from bloque3.bayesian_judge import PriorConfig    # noqa: E402
from bloque3.auditor import FailureCriteria       # noqa: E402
from bloque4.schema import Graph, Node, Edge, OptimizerConfig # noqa: E402
from bloque4.engines import DijkstraEngine # noqa: E402
from bloque4.profiler import profile_route # noqa: E402
from bloque4.selector import select_strategic_options # noqa: E402
from bloque4.report import PrimeStrategicReporter, RenderProfile # noqa: E402
import numpy as np # noqa: E402

def ejecutar_pipeline():
    """
    Orquestación de la Verdad:
    Une la topología del Bloque 1 con el motor de crisis del Bloque 2
    y ejecuta inferencia Bayesiana del Bloque 3.
    """

    print("\n" + "=" * 80)
    print("PRIME LOGISTICS - SISTEMA DE SIMULACIÓN DE RIESGO")
    print("=" * 80)

    # 1. CONSTRUCCIÓN DE LA TOPOLOGÍA (BLOQUE 1)
    # ------------------------------------------------------------------------
    print("\n1. Reconstruyendo Topología Base...")
    indexer = NetworkIndexer()

    # Registro de Nodos
    indexer.register_node(
        NodeRecord.from_dict(
            {"id": "WAREHOUSE_001", "lat": -34.60, "lon": -58.38, "supply": 1000, "demand": 0}
        )
    )
    indexer.register_node(
        NodeRecord.from_dict(
            {"id": "CLIENT_001", "lat": -34.90, "lon": -57.95, "supply": 0, "demand": 500}
        )
    )

    # Registro de Arcos
    indexer.register_arc(
        ArcRecord.from_dict(
            {
                "id": "ARC_01",
                "origin": "WAREHOUSE_001",
                "destination": "CLIENT_001",
                "active": True,
                "capacity": 10000,
                "cost_profile": None,
                "speed_profile": None,
                "metadata": None,
            }
        )
    )

    tb = TopologyBuilder(indexer)
    tb.build_topology()
    topology_package = tb.export_matrices(sparse=False)
    node_ids = list(topology_package['nodes'])
    arc_ids = list(indexer._arcs.keys())
    print(f"   ✓ Topología estática lista: {len(node_ids)} nodos y {len(arc_ids)} arcos.")

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
    print("\n" + "-" * 50)
    print("AUDITORÍA DE INTEGRIDAD DE DATOS")
    has_k_sum = "base_k_sum" in pipeline.base_network.meta
    k_value = pipeline.base_network.meta.get("base_k_sum", 0)
    print(f"¿base_k_sum presente?: {has_k_sum}")
    print(f"Valor de capacidad base: {k_value}")
    print("-" * 50 + "\n")

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

    print("\n" + "-" * 40)
    print("RESUMEN DE RESILIENCIA LOGÍSTICA")
    print("-" * 40)
    print(f"Escenarios generados: {stats['n_scenarios']}")
    print(
        f"Escenarios con incidentes: {stats['scenarios_with_events']} ({stats['scenarios_with_events']/stats['n_scenarios']*100:.1f}%)"
    )
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

    scenarios_path = os.path.join(output_dir, "scenarios.pkl")
    pipeline.export_for_optimizer(scenarios_path)

    # Generamos reporte en texto para auditoría humana
    report_path = os.path.join(output_dir, "reporte_riesgo.txt")
    with open(report_path, "w") as f:
        f.write("REPORTE DE RIESGO - PRIME LOGISTICS\n")
        f.write(f"Fecha: {datetime.now()}\n")
        f.write(f"Escenarios: {stats['n_scenarios']}\n")
        f.write(f"Capacidad Promedio Retenida: {stats['avg_capacity_retention']*100:.2f}%\n")
        f.write(f"Peor Escenario ID: {worst.scenario_id} con {worst.get_capacity_reduction()*100:.2f}%\n")

   # 7. INFERENCIA BAYESIANA (BLOQUE 3) - VERSIÓN SIMPLIFICADA Y FUNCIONAL
    # ------------------------------------------------------------------------
    print("\n3. Ejecutando Auditoría Bayesiana (Bloque 3)...")
    
    # --- CONFIGURACIÓN SIMPLIFICADA ---
    # CORRECCIÓN CRÍTICA: get_capacity_reduction() RETORNA CAPACIDAD RETENIDA
    # 0.0 = 0% retenido, 1.0 = 100% retenido
    # El peor caso: capacidad_retained = 0.0 (0% retenido)
    
    estandar_falla = FailureCriteria(min_capacity_retained=0.85)
    prior_profesional = PriorConfig(alpha=9, beta=1)
    
    config_prime = InferenceConfig(
        criteria=estandar_falla, 
        prior=prior_profesional,
        use_impact_in_fragility=True
    )
    engine = InferenceEngine(config=config_prime)

    # ESTRATEGIA SIMPLIFICADA: Basada en el análisis de la salida anterior
    # 1. Los eventos probablemente NO tienen target_id específico
    # 2. Los eventos como 'PARO_NACIONAL_TRANSPORTE' afectan a TODA la red
    # 3. Vamos a asignar impacto proporcional a todos los componentes
    
    payloads = {}
    scenarios_for_audit = []
    
    print("  Creando payloads con estrategia simplificada...")
    
    for s in scenarios:
        # IMPORTANTE: get_capacity_reduction() retorna CAPACIDAD RETENIDA
        capacity_retained = s.get_capacity_reduction()  # 0.9 = 90% retenido, 0.0 = 0% retenido
        capacity_loss = 1.0 - capacity_retained  # Pérdida real
        
        node_impacts = {}
        arc_impacts = {}
        
        # ESTRATEGIA: Si hay eventos y hay pérdida, asignar impacto
        if hasattr(s, 'events') and s.events and capacity_loss > 0:
            # Contar eventos que realmente causan daño
            damaging_events = []
            for e in s.events:
                event_code = getattr(e, 'code', '')
                # Algunos eventos pueden tener severidad diferente
                severity = 1.0
                if hasattr(e, 'severity'):
                    severity = getattr(e, 'severity')
                elif hasattr(e, 'probability'):
                    severity = getattr(e, 'probability')
                
                damaging_events.append((event_code, severity))
            
            # Distribuir el impacto de pérdida entre los eventos dañinos
            if damaging_events:
                total_severity = sum(sev for _, sev in damaging_events)
                if total_severity > 0:
                    for event_code, severity in damaging_events:
                        # Impacto proporcional a severidad
                        event_impact = capacity_loss * (severity / total_severity)
                        
                        # Determinar qué componentes afecta este evento
                        # Basado en el código del evento
                        event_code_upper = event_code.upper()
                        
                        if 'WAREHOUSE' in event_code_upper:
                            node_impacts['WAREHOUSE_001'] = node_impacts.get('WAREHOUSE_001', 0) + event_impact
                        elif 'CLIENT' in event_code_upper:
                            node_impacts['CLIENT_001'] = node_impacts.get('CLIENT_001', 0) + event_impact
                        elif 'ARC' in event_code_upper or 'ROUTE' in event_code_upper or 'TRANSPORT' in event_code_upper:
                            arc_impacts['ARC_01'] = arc_impacts.get('ARC_01', 0) + event_impact
                        else:
                            # Evento genérico - afecta a todos por igual
                            node_impacts['WAREHOUSE_001'] = node_impacts.get('WAREHOUSE_001', 0) + event_impact / 2
                            node_impacts['CLIENT_001'] = node_impacts.get('CLIENT_001', 0) + event_impact / 2
        
        # Si después de todo no hay impactos asignados pero hay pérdida
        if not node_impacts and not arc_impacts and capacity_loss > 0:
            # Evento sistémico - afecta a toda la red
            node_impacts['WAREHOUSE_001'] = capacity_loss / 2
            node_impacts['CLIENT_001'] = capacity_loss / 2
        
        # Crear lista de componentes fallados (solo los que tienen impacto > 0)
        failed_nodes = [nid for nid, impact in node_impacts.items() if impact > 0]
        failed_arcs = [aid for aid, impact in arc_impacts.items() if impact > 0]
        
        # Crear payload
        payloads[str(s.scenario_id)] = {
            "failed_nodes": failed_nodes,
            "failed_arcs": failed_arcs,
            "node_impacts": node_impacts,
            "arc_impacts": arc_impacts,
            "capacity_retained": capacity_retained
        }
        
        # También preparar datos para auditoría
        scenario_dict = {
            "scenario_id": str(s.scenario_id),
            "capacity_retained": capacity_retained,
            "events": [{"code": e.code} for e in s.events] if hasattr(s, 'events') and s.events else []
        }
        scenarios_for_audit.append(scenario_dict)
    
    # Mostrar estadísticas de los payloads
    print(f"  Payloads creados: {len(payloads)}")
    
    # Contar escenarios con componentes afectados
    scenarios_with_affected_nodes = sum(1 for p in payloads.values() if p['failed_nodes'])
    scenarios_with_affected_arcs = sum(1 for p in payloads.values() if p['failed_arcs'])
    
    print(f"  Escenarios con nodos afectados: {scenarios_with_affected_nodes}")
    print(f"  Escenarios con arcos afectados: {scenarios_with_affected_arcs}")
    
    # Mostrar algunos ejemplos
    print("\n  Ejemplos de payloads:")
    example_count = 0
    for scenario_id, payload in payloads.items():
        if payload['failed_nodes'] or payload['failed_arcs']:
            print(f"    Escenario {scenario_id}:")
            if payload['failed_nodes']:
                print(f"      Nodos: {payload['failed_nodes']}")
                for node_id in payload['failed_nodes']:
                    impact = payload['node_impacts'].get(node_id, 0)
                    print(f"        {node_id}: {impact*100:.1f}% impacto")
            if payload['failed_arcs']:
                print(f"      Arcos: {payload['failed_arcs']}")
            example_count += 1
            if example_count >= 3:
                break
    
    # Mostrar el peor escenario
    worst_scenario_id = worst.scenario_id
    if str(worst_scenario_id) in payloads:
        worst_payload = payloads[str(worst_scenario_id)]
        print(f"\n  PEOR ESCENARIO ({worst_scenario_id}):")
        print(f"    Capacidad retenida: {worst_payload['capacity_retained']*100:.1f}%")
        print(f"    Pérdida: {(1.0 - worst_payload['capacity_retained'])*100:.1f}%")
        print(f"    Nodos afectados: {worst_payload['failed_nodes']}")
        if worst_payload['failed_nodes']:
            for node_id in worst_payload['failed_nodes']:
                impact = worst_payload['node_impacts'].get(node_id, 0)
                print(f"      {node_id}: {impact*100:.1f}% impacto")

    # Ejecutar inferencia
    report = engine.process(
        scenarios=scenarios_for_audit,
        scenario_payloads=payloads,
        node_index=node_ids
    )

    # Salida de resultados
    print("\n" + "-" * 40)
    print("DIAGNÓSTICO DE SUPERVIVENCIA PRIME")
    print("-" * 40)
    
    top_fragile = report.top_fragile_nodes(5)
    if top_fragile:
        print("  Nodos más frágiles (probabilidad × impacto):")
        for nid, frag in top_fragile:
            print(f"    [!] {nid}: {frag*100:.2f}% fragilidad")
    else:
        print("  No se identificaron nodos frágiles")
    
    # Mostrar métricas del sistema
    if hasattr(report, 'confidence_interval') and 'system' in report.confidence_interval:
        system_ci = report.confidence_interval['system']
        reliability_pct = system_ci.mean * 100
        print(f"\n  Confiabilidad del sistema: {reliability_pct:.1f}%")
        
        # Interpretación
        if reliability_pct >= 95:
            print("  ✓ SISTEMA ALTAMENTE CONFIABLE")
        elif reliability_pct >= 85:
            print("  ✓ SISTEMA CONFIABLE")
        elif reliability_pct >= 70:
            print("  ⚠ SISTEMA MODERADAMENTE CONFIABLE")
        else:
            print("  ⚠ SISTEMA DE BAJA CONFIABILIDAD")
    
    # Mostrar notas del reporte
    if hasattr(report, 'notes') and report.notes:
        print("\n  Notas del análisis:")
        for note in report.notes:
            print(f"    • {note}")
    
    print("\n" + "=" * 80)
    print("SIMULACIÓN COMPLETADA EXITOSAMENTE")
    print("=" * 80)
# --- FIN BLOQUE 3 ---
# ========================================================================
    # 8. OPTIMIZACIÓN Y REPORTE ESTRATÉGICO (BLOQUE 4)
    # ========================================================================
    print("\n4. Ejecutando Prime Optimizer (Bloque 4)...")

    # A. TRADUCCIÓN DE DATOS (Bridging B1/B3 -> B4)
    # ------------------------------------------------------------------------
    print("  Integrando Topología y Riesgo Bayesiano...")
    
    # 1. Convertir Nodos
    b4_nodes = []
    for nid in node_ids:
        b4_nodes.append(Node(node_id=nid))

    # 2. Convertir Arcos e Inyectar Riesgo (Mapping)
    b4_edges = []
    
    # Extraemos el mapa de fragilidad (probabilidad media de fallo) del reporte B3
    # Asumimos que report.nodes[id].mean nos da la probabilidad de fallo
    fragility_map = {}
    if hasattr(report, 'nodes'):
        for nid, dist in report.nodes.items():
            fragility_map[nid] = dist.mean

    for arc_id, arc_data in indexer._arcs.items():
        # Lógica de Riesgo: El riesgo de un arco es una función de sus nodos
        # En este MVP simplificado, tomamos el riesgo del nodo destino
        target_node = arc_data.destination
        risk_prob = fragility_map.get(target_node, 0.0)
        
        # Guardrail de seguridad (phi < 1.0)
        risk_prob = min(risk_prob, 0.9999)

        b4_edges.append(Edge(
            edge_id=arc_id,
            source=arc_data.origin,
            target=arc_data.destination,
            cost=100.0, # Costo base hardcodeado para la demo (o usar arc_data.cost)
            risk=risk_prob
        ))

    # Crear el Grafo Inmutable
    prime_graph = Graph(
        nodes=b4_nodes,
        edges=b4_edges,
        edge_indexer={e.edge_id: i for i, e in enumerate(b4_edges)}
    )

    # B. SIMULACIÓN DE ESTRATEGIAS (Generación de Dilemas)
    # ------------------------------------------------------------------------
    # Como la topología es simple (1 arco), simularemos diferentes "Kappas"
    # para ver cómo el sistema evalúa la misma ruta bajo lentes distintos.
    
    strategies = [0.0, 10.0, 50.0] # Neutro, Cauteloso, Paranoico
    raw_solutions = []
    
    # Vector de probabilidades (phi) para el motor
    phi_vector = np.array([e.risk for e in prime_graph.edges])

    print(f"  Simulando {len(strategies)} perspectivas estratégicas...")
    
    engine = DijkstraEngine()
    
    for k in strategies:
        # Configuración Dinámica
        config_iter = OptimizerConfig(
            source_node_id="WAREHOUSE_001",
            target_node_id="CLIENT_001",
            kappa=k,
            # Pesos para el selector
            cost_weight=0.6,
            risk_weight=0.4,
            entropy_weight=0.5
        )
        
        try:
            # 1. Resolver (Motor)
            sol = engine.solve(prime_graph, phi_vector, config_iter)
            
            # Hack para diferenciar soluciones en el selector si la ruta es idéntica
            # (En producción esto no es necesario, pero ayuda en demos de 1 arco)
            sol.optimized_cost = sol.total_cost + (k * sol.total_risk)
            
            raw_solutions.append((sol, config_iter))
        except Exception as e:
            print(f"  [!] Fallo en estrategia k={k}: {e}")

    # C. PROFILING Y SELECCIÓN
    # ------------------------------------------------------------------------
    final_solutions = []
    final_profiles = []
    
    # Usamos la config de la estrategia más balanceada para el reporte final
    master_config = raw_solutions[1][1] if len(raw_solutions) > 1 else raw_solutions[0][1]

    for sol, conf in raw_solutions:
        # 2. Perfilado (Profiler)
        prof = profile_route(prime_graph, sol, conf)
        final_solutions.append(sol)
        final_profiles.append(prof)

    # 3. Selección (Selector)
    strategic_options = select_strategic_options(
        solutions=final_solutions,
        profiles=final_profiles,
        config=master_config
    )

    # D. GENERACIÓN DEL REPORTE (Reporter)
    # ------------------------------------------------------------------------
    print("  Generando narrativa de decisión...")
    
    # Configuración Visual
    visual_profile = RenderProfile(
        use_emojis=True,
        border_top="┌" + "─"*60 + "┐",
        border_bottom="└" + "─"*60 + "┘"
    )
    
    reporter = PrimeStrategicReporter(
        config=master_config, 
        render_profile=visual_profile,
        top_n_analysis=3
    )
    
    full_report = reporter.generate_full_report(strategic_options)

    print("\n" + "#" * 65)
    print(full_report)
    print("#" * 65 + "\n")

if __name__ == "__main__":
    ejecutar_pipeline()