import os
import sys

# ============================================================================
# 1. ARQUITECTURA DE RUTAS (El Portero)
# ============================================================================
base_path = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(base_path, "src")
sys.path.append(src_path)

# ============================================================================
# 2. IMPORTACIONES CONSOLIDADAS
# ============================================================================
from bloque1.network import NetworkIndexer, Ingestor  # noqa: E402
from bloque1.topology import TopologyBuilder          # noqa: E402
from bloque2.generator import ScenarioAnalyzer        # noqa: E402
from bloque2.integration import StochasticNetworkPipeline  # noqa: E402
from bloque3.inference_engine import InferenceEngine  # noqa: E402
from bloque3.inference_engine import InferenceConfig  # noqa: E402
from bloque3.bayesian_judge import PriorConfig        # noqa: E402
from bloque3.auditor import FailureCriteria           # noqa: E402
from bloque4.engines import DijkstraEngine            # noqa: E402
from bloque4.profiler import profile_route            # noqa: E402
from bloque4.selector import select_strategic_options # noqa: E402
from bloque4.report import PrimeStrategicReporter, RenderProfile  # noqa: E402
from bloque4.schema import OptimizerConfig            # noqa: E402
from bloque4.assembler import GraphAssembler          # noqa: E402
import numpy as np                                    # noqa: E402


def conversion_cache_parquet(excel_path):
    """
    Toma el Excel del usuario, lo convierte a Parquet para máxima velocidad
    y devuelve las rutas de los archivos temporales.
    """
    import pandas as pd
    print("⚡ Optimizando datos: Convirtiendo Excel a Parquet...")

    # Creamos rutas para los archivos Parquet
    path_nodes = excel_path.replace(".xlsx", "_nodes.parquet")
    path_arcs = excel_path.replace(".xlsx", "_arcs.parquet")

    # Leemos el Excel una única vez
    df_nodes = pd.read_excel(excel_path, sheet_name="NODES")
    df_arcs = pd.read_excel(excel_path, sheet_name="ARCS")

    # Guardamos en Parquet (Mucho más liviano y rápido)
    df_nodes.to_parquet(path_nodes, engine='pyarrow')
    df_arcs.to_parquet(path_arcs, engine='pyarrow')

    return path_nodes, path_arcs


def ejecutar_pipeline():
    """
    Orquestación Maestra para Tesis:
    1. Carga Blindada.
    2. Riesgo con Convergencia.
    3. Auditoría Bayesiana.
    4. Optimización Multiestrategia (FIX: Manejo de configs).
    """
    # 0. SETUP
    if len(sys.argv) > 1:
        nombre_archivo = sys.argv[1]
    else:
        nombre_archivo = "red_realista_argentina.xlsx"
        print(f"⚠ No se especificó archivo. Usando default: {nombre_archivo}")

    print("\n" + "=" * 80)
    print(f"PRIME LOGISTICS - EJECUCIÓN MAESTRA: {nombre_archivo.upper()}")
    print("=" * 80)

    # ========================================================================
    # 1. CARGA DE DATOS
    # ========================================================================
    excel_path = os.path.join(base_path, "data", nombre_archivo)
    if not os.path.exists(excel_path):
        print(f"❌ ERROR: No existe {excel_path}")
        sys.exit(1)

    p_nodes, p_arcs = conversion_cache_parquet(excel_path)

    import pandas as pd
    df_n = pd.read_parquet(p_nodes)
    df_a = pd.read_parquet(p_arcs)

    indexer = NetworkIndexer()
    ingestor = Ingestor(indexer)

    print(f"   [BLOQUE 1] Ingestando topología: {len(df_n)} nodos, {len(df_a)} arcos...")

    # Ingestión NODOS
    for record in df_n.to_dict('records'):
        clean_node = {
            "id": str(record['id']),
            "lat": float(record['lat']),
            "lon": float(record['lon']),
            "processing_cost": float(record.get('proc_cost', 0.0)),
            "supply": float(record.get('supply', 0.0)),
            "demand": float(record.get('demand', 0.0))
        }
        clean_node["metadata"] = {"station_type": record.get("station_type", "warehouse")}
        ingestor.load_node(clean_node)

    # Ingestión ARCOS
    for record in df_a.to_dict('records'):
        clean_arc = {
            "id": str(record['id']),
            "origin": str(record['origin']),
            "destination": str(record['destination']),
            "capacity": float(record.get('capacity', 10000.0))
        }
        clean_arc["metadata"] = {
            "mode": record.get("mode", "truck"),
            "original_cost": float(record.get("cost", 0.0))
        }
        ingestor.load_arc(clean_arc)

    if indexer.arc_count == 0:
        print("\n❌ ERROR CRÍTICO: 0 Arcos cargados.")
        return

    tb = TopologyBuilder(indexer)
    tb.build_topology()
    topology_package = tb.export_matrices(sparse=False)

    node_ids = list(topology_package['nodes'])
    start_node, end_node = node_ids[0], node_ids[-1]

    print(f"   ✓ Topología lista: {len(node_ids)} nodos y {len(indexer._arcs)} arcos.")
    print(f"   ✓ Ruta Objetivo: {start_node} ➔ {end_node}")

    # ========================================================================
    # 2. MOTOR DE RIESGO
    # ========================================================================
    print("\n2. Ejecutando Motor de Riesgo (Convergencia Automática)...")
    pipeline = StochasticNetworkPipeline(seed=42)
    pipeline.load_topology_from_bloque1(topology_package)

    manifest_path = os.path.join(src_path, "bloque2", "manifest.yaml")
    pipeline.load_incident_manifest(manifest_path)

    # Convergencia hasta 5000
    scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=5000)

    stats = ScenarioAnalyzer.compute_statistics(scenarios)
    worst = ScenarioAnalyzer.get_worst_case_scenario(scenarios)

    print(f"   [RESULTADOS] Escenarios Simulados: {stats['n_scenarios']}")
    print(f"   [RESULTADOS] Pérdida Promedio: {stats['avg_capacity_loss']*100:.2f}%")
    print(f"   [CRITICAL] Peor escenario: ID {worst['scenario_id']} (Retención: {worst['capacity_retained']*100:.1f}%)")

    # ========================================================================
    # 2.5 GUARDADO DE SEGURIDAD 
    # ========================================================================
    import pickle
    output_dir = os.path.join(base_path, "output")
    os.makedirs(output_dir, exist_ok=True) # Crea la carpeta si no existe
    
    ruta_pkl = os.path.join(output_dir, "scenarios.pkl")
    with open(ruta_pkl, "wb") as f:
        pickle.dump(scenarios, f)
    
    print(f"✅ Archivo de escenarios guardado en: {ruta_pkl}")
    # ========================================================================

    # ========================================================================
    # 3. AUDITORÍA BAYESIANA (ACTUALIZADO PARA DICTS)
    # ========================================================================
    print("\n3. Ejecutando Auditoría Bayesiana...")

    config_prime = InferenceConfig(
        criteria=FailureCriteria(min_capacity_retained=0.85),
        prior=PriorConfig(alpha=9, beta=1),
        use_impact_in_fragility=True
    )
    engine = InferenceEngine(config=config_prime)

    scenarios_for_audit = []
    payloads = {}

    for s in scenarios:
        # CAMBIO: Acceso por llave ['...'] en lugar de método .get_capacity_reduction()
        retention = s['capacity_retained']
        cap_loss = 1.0 - retention
        node_impacts = {}

        # CAMBIO: s['events'] es una lista de dicts
        events = s.get('events', [])

        if events and cap_loss > 0:
            impact_val = cap_loss / len(events)
            for e in events:
                # CAMBIO: e es un dict, usamos e['code']
                code = e['code']
                if 'WAREHOUSE' in code:
                    node_impacts[start_node] = impact_val
                elif 'CLIENT' in code:
                    node_impacts[end_node] = impact_val
                else:
                    node_impacts[start_node] = impact_val / 2
                    node_impacts[end_node] = impact_val / 2

        # Ya no hace falta reconstruir el dict porque s YA ES UN DICT liviano
        # Pero mantenemos el ID para los payloads
        s_id = str(s['scenario_id'])

        scenarios_for_audit.append(s)  # Usamos el que ya tenemos

        payloads[s_id] = {
            "node_impacts": node_impacts,
            "arc_impacts": {},
            "failed_nodes": list(node_impacts.keys())
        }

    report = engine.process(
        scenarios=scenarios_for_audit,
        scenario_payloads=payloads,
        node_index=node_ids
    )

    # ========================================================================
    # 4. OPTIMIZACIÓN MULTI-ESTRATEGIA (Bloque 4)
    # ========================================================================
    print("\n4. Ejecutando Prime Optimizer (Barrido de Estrategias)...")

    total_nodos = len(node_ids)
    all_fragilities = report.top_fragile_nodes(total_nodos)
    fragility_map = dict(all_fragilities)
    if not fragility_map:
        fragility_map = {nid: 0.0 for nid in node_ids}

    prime_graph = GraphAssembler.assemble(indexer, node_ids, fragility_map)
    engine_b4 = DijkstraEngine()
    phi_vector = np.array([e.risk for e in prime_graph.edges])

    # BUCLE DE ESTRATEGIAS
    k_strategies = [0.0, 10.0, 50.0]

    solutions_found = []
    profiles_found = []
    configs_found = []  # <--- LISTA CRÍTICA AGREGADA

    for k in k_strategies:
        print(f"   -> Calculando ruta óptima para Kappa={k}...")
        config_iter = OptimizerConfig(
            source_node_id=start_node, target_node_id=end_node,
            kappa=k,
            cost_weight=0.6, risk_weight=0.4, entropy_weight=0.1
        )

        try:
            sol = engine_b4.solve(prime_graph, phi_vector, config_iter)
            if sol:
                prof = profile_route(prime_graph, sol, config_iter)
                solutions_found.append(sol)
                profiles_found.append(prof)
                configs_found.append(config_iter)  # <--- GUARDAMOS LA CONFIG AQUÍ
            else:
                print(f"      [WARN] No hubo ruta viable para k={k}")
        except Exception as e:
            print(f"      [!] Fallo cálculo k={k}: {e}")

    # SELECCIÓN Y REPORTE
    if solutions_found:
        # [SOLUCIÓN DEL ERROR] Usamos la lista configs_found
        index_master = 1 if len(solutions_found) > 1 else 0
        master_config = configs_found[index_master]

        strategic_options = select_strategic_options(solutions_found, profiles_found, master_config)

        reporter = PrimeStrategicReporter(master_config, RenderProfile(use_emojis=True))
        print("\n" + "#" * 65)
        print(reporter.generate_full_report(strategic_options))
        print("#" * 65 + "\n")

        full_report = reporter.generate_full_report(strategic_options)
        with open(os.path.join(output_dir, "reporte_estrategico.txt"), "w", encoding="utf-8") as f:
            f.write(full_report)
            
        # 5. MAPA
        try:
            import folium
            best_sol = strategic_options[0].solution
            m = folium.Map(location=[-38.0, -64.0], zoom_start=4, tiles='CartoDB positron')

            path_coords = []
            for nid in best_sol.path:
                n_obj = next((n for n in prime_graph.nodes if n.node_id == nid), None)
                if n_obj:
                    path_coords.append((n_obj.lat, n_obj.lon))

            if path_coords:
                folium.PolyLine(path_coords, color="blue", weight=3, opacity=0.7).add_to(m)
                folium.Marker(path_coords[0], popup="Inicio", icon=folium.Icon(color='green')).add_to(m)
                folium.Marker(path_coords[-1], popup="Fin", icon=folium.Icon(color='red')).add_to(m)

                out_map = os.path.join(base_path, "output", "mapa_tesis.html")
                m.save(out_map)
                print(f"🗺️  Mapa generado en: {out_map}")
        except:  # noqa: E722
            pass

    else:
        print("❌ CRÍTICO: El sistema no pudo conectar el origen con el destino bajo ninguna estrategia.")


if __name__ == "__main__":
    ejecutar_pipeline()