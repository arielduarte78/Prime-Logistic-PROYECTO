#!/usr/bin/env python3
# main.py - Orquestador maestro (versión robusta)
from __future__ import annotations

import os
import sys
import logging
import pickle
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import numpy as np

# Bloques del proyecto
from bloque1.network import NetworkIndexer, Ingestor
from bloque1.topology import TopologyBuilder
from bloque2.generator import ScenarioAnalyzer
from bloque2.integration import StochasticNetworkPipeline
from bloque3.inference_engine import InferenceEngine, InferenceConfig
from bloque3.bayesian_judge import PriorConfig
from bloque3.auditor import FailureCriteria
from bloque4.profiler import profile_route
from bloque4.selector import select_strategic_options
from bloque4.report import PrimeStrategicReporter, RenderProfile
from bloque4.schema import OptimizerConfig, Edge
from bloque4.assembler import GraphAssembler
from bloque4.weight_builder import build_edge_weights
from bloque4.config import Stage5Config
from bloque4.multiobjective_engine import MultiObjectiveEngine
from bloque4.utils import normalize_solution


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# -------------------------
# Pipeline principal
# -------------------------
def ejecutar_pipeline():
    base_path = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(base_path, "src")
    # argumentos y archivo por defecto
    if len(sys.argv) > 1:
        nombre_archivo = sys.argv[1]
    else:
        nombre_archivo = "red_realista_argentina.xlsx"
        print(f"⚠ No se especificó archivo. Usando default: {nombre_archivo}")

    print("\n" + "=" * 80)
    print(f"PRIME LOGISTICS - EJECUCIÓN MAESTRA: {nombre_archivo.upper()}")
    print("=" * 80)

    excel_path = os.path.join(base_path, "data", nombre_archivo)
    if not os.path.exists(excel_path):
        print(f"❌ ERROR: No existe {excel_path}")
        sys.exit(1)

    # Conversión a parquet (si existe)
    try:
        from main import conversion_cache_parquet  # si existe en el repo
        p_nodes, p_arcs = conversion_cache_parquet(excel_path)
    except Exception:
        # Fallback simple: leer directo con pandas
        import pandas as pd
        df_nodes = pd.read_excel(excel_path, sheet_name="NODES")
        df_arcs = pd.read_excel(excel_path, sheet_name="ARCS")
        p_nodes = os.path.join(base_path, "tmp_nodes.parquet")
        p_arcs = os.path.join(base_path, "tmp_arcs.parquet")
        df_nodes.to_parquet(p_nodes, engine="pyarrow")
        df_arcs.to_parquet(p_arcs, engine="pyarrow")

    import pandas as pd
    df_n = pd.read_parquet(p_nodes)
    df_a = pd.read_parquet(p_arcs)

    indexer = NetworkIndexer()
    ingestor = Ingestor(indexer)

    print(f"   [BLOQUE 1] Ingestando topología: {len(df_n)} nodos, {len(df_a)} arcos...")

    for record in df_n.to_dict("records"):
        clean_node = {
            "id": str(record.get("id")),
            "lat": float(record.get("lat") or 0.0),
            "lon": float(record.get("lon") or 0.0),
            "processing_cost": float(record.get("proc_cost", 0.0) or 0.0),
            "supply": float(record.get("supply", 0.0) or 0.0),
            "demand": float(record.get("demand", 0.0) or 0.0)
        }
        clean_node["metadata"] = {"station_type": record.get("station_type", "warehouse")}
        ingestor.load_node(clean_node)

    for record in df_a.to_dict("records"):
        clean_arc = {
            "id": str(record.get("id")),
            "origin": str(record.get("origin")),
            "destination": str(record.get("destination")),
            "capacity": float(record.get("capacity", 10000.0) or 10000.0)
        }
        clean_arc["metadata"] = {
            "mode": record.get("mode", "truck"),
            "original_cost": float(record.get("cost", 0.0) or 0.0)
        }
        ingestor.load_arc(clean_arc)

    if indexer.arc_count == 0:
        print("\n❌ ERROR CRÍTICO: 0 Arcos cargados.")
        return

    tb = TopologyBuilder(indexer)
    tb.build_topology()
    topology_package = tb.export_matrices(sparse=False)

    node_ids = list(topology_package["nodes"])
    start_node, end_node = node_ids[0], node_ids[-1]

    print(f"   ✓ Topología lista: {len(node_ids)} nodos y {len(indexer._arcs)} arcos.")
    print(f"   ✓ Ruta Objetivo: {start_node} ➔ {end_node}")

    # -------------------------
    # Motor de riesgo (Bloque 2)
    # -------------------------
    print("\n2. Ejecutando Motor de Riesgo (Convergencia Automática)...")
    pipeline = StochasticNetworkPipeline(seed=42)
    pipeline.load_topology_from_bloque1(topology_package)
    manifest_path = os.path.join(src_path, "bloque2", "manifest.yaml")
    pipeline.load_incident_manifest(manifest_path)
    scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=5000)

    stats = ScenarioAnalyzer.compute_statistics(scenarios)
    worst = ScenarioAnalyzer.get_worst_case_scenario(scenarios)

    print(f"   [RESULTADOS] Escenarios Simulados: {stats.get('n_scenarios', len(scenarios))}")
    print(f"   [RESULTADOS] Pérdida Promedio: {stats.get('avg_capacity_loss', 0.0)*100:.2f}%")
    print(f"   [CRITICAL] Peor escenario: ID {worst.get('scenario_id', 'N/A')} (Retención: {worst.get('capacity_retained', 0.0)*100:.1f}%)")

    # Guardado de seguridad
    output_dir = os.path.join(base_path, "output")
    os.makedirs(output_dir, exist_ok=True)
    ruta_pkl = os.path.join(output_dir, "scenarios.pkl")
    with open(ruta_pkl, "wb") as f:
        pickle.dump(scenarios, f)
    print(f"✅ Archivo de escenarios guardado en: {ruta_pkl}")

    # -------------------------
    # Auditoría Bayesiana (Bloque 3)
    # -------------------------
    print("\n3. Ejecutando Auditoría Bayesiana...")
    config_prime = InferenceConfig(
        criteria=FailureCriteria(min_capacity_retained=0.85),
        prior=PriorConfig(alpha=9, beta=1),
    )
    engine = InferenceEngine(config=config_prime)

    scenarios_for_audit = []
    payloads: Dict[str, Dict[str, Any]] = {}

    for s in scenarios:
        s_id = str(s.get("scenario_id", s.get("id", "unknown")))
        retention = float(s.get("capacity_retained", 1.0) or 1.0)
        cap_loss = max(0.0, 1.0 - retention)
        node_impacts: Dict[str, float] = {}
        events = s.get("events", []) if isinstance(s, dict) else []

        if events and cap_loss > 0:
            impact_val = cap_loss / max(1, len(events))
            for e in events:
                code = e.get("code", "") if isinstance(e, dict) else ""
                if "WAREHOUSE" in code:
                    node_impacts[start_node] = node_impacts.get(start_node, 0.0) + impact_val
                elif "CLIENT" in code:
                    node_impacts[end_node] = node_impacts.get(end_node, 0.0) + impact_val
                else:
                    node_impacts[start_node] = node_impacts.get(start_node, 0.0) + impact_val / 2
                    node_impacts[end_node] = node_impacts.get(end_node, 0.0) + impact_val / 2

        scenarios_for_audit.append(s)
        payloads[s_id] = {"node_impacts": node_impacts, "arc_impacts": {}, "failed_nodes": list(node_impacts.keys())}

    report = engine.process(scenarios=scenarios_for_audit, scenario_payloads=payloads, node_index=node_ids)

    # -------------------------
    # Bloque 4: ensamblado y pesos
    # -------------------------
    print("\n4. Ejecutando Prime Optimizer (Barrido de Estrategias)...")
    total_nodos = len(node_ids)
    all_fragilities = report.top_fragile_nodes(total_nodos)
    fragility_map = dict(all_fragilities) if all_fragilities else {nid: 0.0 for nid in node_ids}

    prime_graph = GraphAssembler.assemble(indexer, node_ids, fragility_map)

    # Construir reliability_report mínimo si no existe
    if not hasattr(prime_graph, "reliability_report"):
        edges_report = {}
        for e in prime_graph.edges:
            prob = float(getattr(e, "risk", 0.0) or 0.0)
            impact = float(getattr(e, "capacity", getattr(e, "impact", 0.0)) or 0.0)
            edges_report[str(e.edge_id)] = {"prob_failure": prob, "impact_mean": impact}
        prime_graph.reliability_report = {"edges": edges_report}

    # Precalculo de pesos por arco
    build_edge_weights(prime_graph.edges, prime_graph.reliability_report)

    # Construir ordered_edges respetando edge_indexer
    ordered_edges: List[Optional[Edge]] = [None] * len(prime_graph.edges)
    fallback_edges: List[Edge] = []
    if hasattr(prime_graph, "edge_indexer") and isinstance(prime_graph.edge_indexer, dict):
        for e in prime_graph.edges:
            idx = prime_graph.edge_indexer.get(str(e.edge_id))
            if idx is None or not (0 <= idx < len(ordered_edges)):
                fallback_edges.append(e)
            else:
                ordered_edges[idx] = e
        # rellenar huecos con fallback_edges
        fill_iter = iter(fallback_edges)
        for i in range(len(ordered_edges)):
            if ordered_edges[i] is None:
                try:
                    ordered_edges[i] = next(fill_iter)
                except StopIteration:
                    ordered_edges[i] = None
        ordered_edges = [e for e in ordered_edges if e is not None]
    else:
        ordered_edges = list(prime_graph.edges)

    w_survival_vec = np.array([getattr(e, "w_survival", 0.0) for e in ordered_edges], dtype=float)
    w_expected_vec = np.array([getattr(e, "w_expected_cost", float(getattr(e, "cost", 0.0))) for e in ordered_edges], dtype=float)

    # Configuración motor multiobjetivo
    cfg_stage5 = Stage5Config(eps_1=0.001, eps_2=1.0)
    try:
        engine_b4 = MultiObjectiveEngine(
            eps_1=cfg_stage5.eps_1,
            eps_2=cfg_stage5.eps_2,
            max_labels_per_node=1000,
            max_total_labels=100000,
            max_iterations=getattr(cfg_stage5, "max_iterations", 1000000)
        )
    except TypeError:
        engine_b4 = MultiObjectiveEngine()

    k_strategies = [0.0, 10.0, 50.0]
    solutions_found: List[SimpleNamespace] = []
    profiles_found: List[Any] = []
    configs_found: List[OptimizerConfig] = []

    for k in k_strategies:
        print(f"   -> Calculando ruta óptima para Kappa={k}...")
        config_iter = OptimizerConfig(
            source_node_id=start_node, target_node_id=end_node,
            kappa=k,
            cost_weight=0.6, risk_weight=0.4, entropy_weight=0.1
        )

        try:
            # Intentar varias firmas de solve de forma defensiva
            sol = None
            try:
                sol = engine_b4.solve(prime_graph, w_survival_vec, w_expected_vec, config_iter)
            except TypeError:
                try:
                    sol = engine_b4.solve(prime_graph, source=start_node, target=end_node, config=config_iter)
                except TypeError:
                    sol = engine_b4.solve(prime_graph, start_node, end_node)

            if sol:
                sol_norm = normalize_solution(sol, prime_graph, ordered_edges)
                prof = profile_route(prime_graph, sol_norm, config_iter)
                solutions_found.append(sol_norm)
                profiles_found.append(prof)
                configs_found.append(config_iter)
            else:
                print(f"      [WARN] No hubo ruta viable para k={k}")
        except Exception:
            logger.exception("Fallo inesperado en cálculo k=%s", k)
            raise

    # Selección y reporte
    if solutions_found:
        index_master = 1 if len(solutions_found) > 1 else 0
        master_config = configs_found[index_master]

        strategic_options = select_strategic_options(solutions_found, profiles_found, master_config)
        reporter = PrimeStrategicReporter(master_config, RenderProfile(use_emojis=True))

        print("\n" + "#" * 65)
        report_text = reporter.generate_full_report(strategic_options)
        print(report_text)
        print("#" * 65 + "\n")

        with open(os.path.join(output_dir, "reporte_estrategico.txt"), "w", encoding="utf-8") as f:
            f.write(report_text)
    else:
        print("❌ CRÍTICO: El sistema no pudo conectar el origen con el destino bajo ninguna estrategia.")


if __name__ == "__main__":
    ejecutar_pipeline()