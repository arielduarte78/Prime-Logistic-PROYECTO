#!/usr/bin/env python3
# main.py — Orquestador maestro V1.3.5 (Agnostic CLI Orchestrator)
from __future__ import annotations

import argparse
import os
import sys
import logging
import pickle
from typing import Any, Dict, List, Optional

import numpy as np

# --- INYECCION DE RUTA ESTRUCTURAL ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# Bloque 1: Discovery Engine V1.3.5
from bloque1.network import NetworkIndexer, Ingestor
from bloque1.loader import ExcelLoader
from bloque1.models import ArcRecord, Metadata, CostProfile, SpeedProfile, NodeRecord
from bloque1.fleet_schema import FleetVehicle
from bloque1.discovery_engine import DiscoveryEngine, DiscoveredCandidate

from bloque1.smart_ingestor import SmartLazyIngestor
from bloque1.cache_manager import SafeCacheManager
from bloque1.config import H3RouterConfig

# Bloques 2-4 (pipeline existente sin cambios)
from bloque1.topology import TopologyBuilder
from bloque2.generator import ScenarioAnalyzer
from bloque2.integration import StochasticNetworkPipeline
from bloque3.inference_engine import InferenceEngine, InferenceConfig
from bloque3.bayesian_judge import PriorConfig
from bloque3.auditor import FailureCriteria
from bloque4.report import PrimeStrategicReporter, RenderProfile, build_strategic_options_from_frontier
from bloque4.schema import OptimizerConfig
from bloque4.assembler import GraphAssembler
from bloque4.weight_builder import build_edge_weights
from bloque4.config import Stage5Config
from bloque4.multiobjective_engine import MultiObjectiveEngine

from bloque1.logger import setup_logging

logger = logging.getLogger(__name__)

# Velocidades promedio por modo (km/h) para calculo de travel_time
AVG_SPEED_KMH: Dict[str, float] = {"truck": 60.0, "car": 80.0, "bus": 50.0}

def candidates_to_arc_records(survivors: List[DiscoveredCandidate]) -> List[ArcRecord]:
    arcs: List[ArcRecord] = []
    for cand in survivors:
        mode: str = cand.vehicle.mode
        vid: str = cand.vehicle.vehicle_id or mode
        arc_id = f"DISC_{cand.origin.id}_{cand.destination.id}_{vid}"

        phys_km: float = cand.physical_distance_km if cand.physical_distance_km > 0 else cand.estimated_distance_km
        cost_total: float = cand.vehicle.cost_per_km * phys_km
        avg_speed: float = AVG_SPEED_KMH.get(mode, 60.0)

        arc = ArcRecord(
            id=arc_id,
            origin=cand.origin.id,
            destination=cand.destination.id,
            capacity=cand.vehicle.capacity,
            cost_profile=CostProfile(
                cost_type="flat",
                params={"variable_coef": round(cost_total, 2)},
            ),
            speed_profile=SpeedProfile(default=avg_speed),
            metadata=Metadata(
                source="discovery_engine_v1.3.5",
                extras={
                    "mode": mode,
                    "vehicle_id": vid,
                    "haversine_km": round(cand.estimated_distance_km, 3),
                    "road_km": round(phys_km, 3),
                    "travel_time_h": round(phys_km / avg_speed, 3),
                },
            ),
        )
        arcs.append(arc)
    return arcs

def run_pipeline(dataset_path: str, source: Optional[str] = None, target: Optional[str] = None) -> None:
    setup_logging()
    base_path = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(base_path, "src")

    logger.info("\n" + "=" * 80)
    logger.info("PRIME LOGISTICS V1.3.5 - DISCOVERY ENGINE & AGNOSTIC ORCHESTRATOR")
    logger.info("=" * 80)

    if not os.path.exists(dataset_path):
        # Fallback al directorio data/ si se paso un nombre de archivo relativo corto
        dataset_path_alt = os.path.join(base_path, "data", dataset_path)
        if os.path.exists(dataset_path_alt):
            dataset_path = dataset_path_alt
        else:
            logger.error("[ERROR] No existe el dataset en la ruta especificada: %s", dataset_path)
            sys.exit(1)

    # ==================================================================
    # BLOQUE 1: Ingesta V1.3.5 (NODES + FLEET, sin ARCS manuales)
    # ==================================================================
    logger.info("\n1. [BLOQUE 1] Cargando NODES y FLEET desde %s...", dataset_path)
    loader = ExcelLoader(dataset_path)
    nodes, fleet = loader.run()

    if not nodes:
        logger.error("[ERROR CRITICO] 0 nodos cargados.")
        sys.exit(1)
    if not fleet:
        logger.error("[ERROR CRITICO] 0 vehiculos cargados.")
        sys.exit(1)

    logger.info("   Nodos cargados : %d", len(nodes))
    logger.info("   Vehiculos flota: %d", len(fleet))

    # --- Indexer para la topologia ---
    indexer = NetworkIndexer()
    ingestor = Ingestor(indexer)

    for node in nodes:
        indexer.register_node(node)

    # ==================================================================
    # DISCOVERY ENGINE: Descubrimiento automatico de arcos
    # ==================================================================
    logger.info("\n2. [DISCOVERY ENGINE] Ejecutando pipeline de descubrimiento...")

    engine = DiscoveryEngine(nodes, fleet)
    candidates, telemetry = engine.run_filters_1_2()

    logger.info("   Candidatos F1/F2: %d", len(candidates))

    # --- Filter 3: Validacion fisica via OSMnx ---
    cache_mgr = SafeCacheManager(cache_dir=os.path.join(base_path, "data", "osm_cache"))
    h3_config = H3RouterConfig()
    osm_ingestor = SmartLazyIngestor(cache_manager=cache_mgr, config=h3_config)

    output_csv = os.path.join(base_path, "output", "discovery_audit.csv")
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    survivors = engine.run_filter_3(
        candidates, osm_ingestor, telemetry, output_csv=output_csv
    )

    logger.info("   Candidatos F3 (supervivientes): %d", len(survivors))

    if not survivors:
        logger.error("[ERROR CRITICO] 0 arcos descubiertos. No hay topologia viable.")
        sys.exit(1)

    # ==================================================================
    # Conversion de candidatos a ArcRecord e inyeccion
    # ==================================================================
    logger.info("\n3. [INYECCION] Convirtiendo %d candidatos a ArcRecord...", len(survivors))
    discovered_arcs = candidates_to_arc_records(survivors)

    for arc in discovered_arcs:
        indexer.register_discovered_arc(arc)

    logger.info("   Arcos inyectados en topologia: %d", indexer.arc_count)

    # ==================================================================
    # BLOQUE 1: Topologia
    # ==================================================================
    tb = TopologyBuilder(indexer)
    tb.build_topology()
    topology_package = tb.export_matrices(sparse=False)

    node_ids: List[str] = [str(nid) for nid in topology_package["nodes"]]
    logger.info("   Topologia abstracta generada. Procesando %d nodos y %d arcos.", len(node_ids), indexer.arc_count)

    # INTELLIGENT NODE VALIDATION (Stop at Block 4 requirement)
    if not source or not target:
        print("\n" + "*" * 80)
        print(f" Topologia construida exitosamente con {len(node_ids)} nodos y {indexer.arc_count} arcos.")
        print(" Nodos disponibles en la red:")
        for nid in node_ids:
            print(f"  - {nid}")
        print("*" * 80)
        print("\n[!] Topologia cargada y estabilizada.")
        print("[!] To run the multi-target engine, re-run specifying `--source` and `--target`.")
        sys.exit(0)

    start_node: str = source
    end_node: str = target

    if start_node not in node_ids or end_node not in node_ids:
        logger.error("[ERROR CRITICO] Origen '%s' o Destino '%s' no validos en la topologia.", start_node, end_node)
        sys.exit(1)

    logger.info("   Ruta Objetivo: %s -> %s", start_node, end_node)

    # ==================================================================
    # BLOQUE 2: Motor de riesgo
    # ==================================================================
    logger.info("\n4. Ejecutando Motor de Riesgo (Convergencia Automatica)...")
    pipeline = StochasticNetworkPipeline(seed=42)
    pipeline.load_topology_from_bloque1(topology_package)
    manifest_path = os.path.join(src_path, "bloque2", "manifest.yaml")
    pipeline.load_incident_manifest(manifest_path)
    scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=5000)

    stats = ScenarioAnalyzer.compute_statistics(scenarios)
    worst = ScenarioAnalyzer.get_worst_case_scenario(scenarios)

    logger.info("   [RESULTADOS] Escenarios Simulados: %d", stats.get('n_scenarios', len(scenarios)))
    logger.info("   [RESULTADOS] Perdida Promedio: %.2f%%", stats.get('avg_capacity_loss', 0.0)*100)
    logger.info("   [CRITICAL] Peor escenario: ID %s (Retencion: %.1f%%)",
                worst.get('scenario_id', 'N/A'), worst.get('capacity_retained', 0.0)*100)

    output_dir = os.path.join(base_path, "output")
    os.makedirs(output_dir, exist_ok=True)
    ruta_pkl = os.path.join(output_dir, "scenarios.pkl")
    with open(ruta_pkl, "wb") as f:
        pickle.dump(scenarios, f)
    logger.info("Archivo de escenarios guardado en: %s", ruta_pkl)

    # ==================================================================
    # BLOQUE 3: Auditoria Bayesiana
    # ==================================================================
    logger.info("\n5. Ejecutando Auditoria Bayesiana...")
    config_prime = InferenceConfig(
        criteria=FailureCriteria(min_capacity_retained=0.85),
        prior=PriorConfig(alpha=9, beta=1),
    )
    inference_engine = InferenceEngine(config=config_prime)

    scenarios_for_audit = []
    payloads: Dict[str, Dict[str, Any]] = {}

    for s in scenarios:
        s_id = str(getattr(s, "scenario_id", s.get("scenario_id") if isinstance(s, dict) else None))
        
        if hasattr(s, "get_capacity_reduction"):
            retention = float(s.get_capacity_reduction())
        else:
            retention = float(s.get("capacity_retained", 1.0) if isinstance(s, dict) else 1.0)
            
        cap_loss = max(0.0, 1.0 - retention)
        node_impacts: Dict[str, float] = {}
        
        events = getattr(s, "events", s.get("events", []) if isinstance(s, dict) else [])

        if events and cap_loss > 0:
            impact_val = cap_loss / max(1, len(events))
            for e in events:
                code = getattr(e, "code", e.get("code") if isinstance(e, dict) else None)
                if code and "WAREHOUSE" in code:
                    node_impacts[start_node] = node_impacts.get(start_node, 0.0) + impact_val
                elif code and "CLIENT" in code:
                    node_impacts[end_node] = node_impacts.get(end_node, 0.0) + impact_val
                else:
                    node_impacts[start_node] = node_impacts.get(start_node, 0.0) + impact_val / 2
                    node_impacts[end_node] = node_impacts.get(end_node, 0.0) + impact_val / 2

        scenarios_for_audit.append(s)
        payloads[s_id] = {"node_impacts": node_impacts, "arc_impacts": {}, "failed_nodes": list(node_impacts.keys())}

    report = inference_engine.process(scenarios=scenarios_for_audit, scenario_payloads=payloads, node_index=node_ids)

    # ==================================================================
    # BLOQUE 4: Optimizacion multiobjetivo
    # ==================================================================
    logger.info("\n6. Ejecutando Prime Optimizer (Frontera de Pareto)...")
    total_nodos = len(node_ids)
    all_fragilities = report.top_fragile_nodes(total_nodos)
    fragility_map = dict(all_fragilities) if all_fragilities else {nid: 0.0 for nid in node_ids}

    prime_graph = GraphAssembler.assemble(indexer, node_ids, fragility_map)

    rel_report = getattr(prime_graph, "reliability_report", None)
    if not rel_report:
        edges_report = {}
        for e in prime_graph.edges:
            prob = float(getattr(e, "risk", 0.0) or 0.0)
            impact = float(getattr(e, "capacity", getattr(e, "impact", 0.0)) or 0.0)
            edges_report[str(e.edge_id)] = {"prob_failure": prob, "impact_mean": impact}
        rel_report = {"edges": edges_report}

    build_edge_weights(prime_graph.edges, rel_report)

    w_survival_vec = np.array([getattr(e, "w_survival", 0.0) for e in prime_graph.edges], dtype=float)
    w_expected_vec = np.array([getattr(e, "w_expected_cost", float(getattr(e, "cost", 0.0))) for e in prime_graph.edges], dtype=float)

    cfg_stage5 = Stage5Config(eps_1= 1, eps_2=0.02)
    try:
        engine_b4 = MultiObjectiveEngine(
            eps_1=cfg_stage5.eps_1,
            eps_2=cfg_stage5.eps_2,
            max_labels_per_node=getattr(cfg_stage5, "max_labels_per_node", 30),
            max_total_labels=getattr(cfg_stage5, "max_total_labels", 10000),
            max_iterations=getattr(cfg_stage5, "max_iterations", 10000)
        )
    except TypeError:
        logger.warning("Fallback: creando MultiObjectiveEngine sin parametros")
        engine_b4 = MultiObjectiveEngine()

    try:
        assert callable(build_strategic_options_from_frontier)
    except (NameError, AssertionError):
        raise RuntimeError("build_strategic_options_from_frontier no disponible en bloque4.report")

    pareto_labels = None
    try:
        pareto_labels = engine_b4.solve(prime_graph, source=start_node, target=end_node)
    except TypeError:
        try:
            pareto_labels = engine_b4.solve(prime_graph, w_survival_vec, w_expected_vec, config=OptimizerConfig( # type: ignore
                source_node_id=start_node, target_node_id=end_node, kappa=0.0))
        except Exception as exc:
            logger.exception("MultiObjectiveEngine.solve failed: %s", exc)
            raise

    if pareto_labels:
        master_config = OptimizerConfig(
            source_node_id=start_node,
            target_node_id=end_node,
            kappa=0.0,
            cost_weight=0.6,
            risk_weight=0.4,
            entropy_weight=0.1,
        )

        strategic_options = build_strategic_options_from_frontier(pareto_labels, engine_b4, master_config)

        filtered_options = []
        for opt in strategic_options:
            cost = getattr(opt, "total_cost", opt.get("total_cost", 0.0) if isinstance(opt, dict) else 0.0)
            if all(abs(cost - getattr(acc, "total_cost", acc.get("total_cost", 0.0) if isinstance(acc, dict) else 0.0)) > 1.0 for acc in filtered_options):
                filtered_options.append(opt)
                if len(filtered_options) == 3:
                    break

        strategic_options = filtered_options

        reporter = PrimeStrategicReporter(master_config, RenderProfile(use_emojis=True))
        logger.info("\n" + "#" * 65)
        report_text = reporter.generate_full_report(strategic_options)
        print(report_text)
        logger.info("#" * 65 + "\n")

        with open(os.path.join(output_dir, "reporte_estrategico.txt"), "w", encoding="utf-8") as f:
            f.write(report_text)
    else:
        logger.error("[CRITICO] El motor multiobjetivo no encontro rutas entre origen y destino.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prime Logistics - Agnostic Orchestrator V1.3.5")
    parser.add_argument("--dataset", required=True, help="Ruta al archivo Excel/Parquet de la red (NODES y FLEET)")
    parser.add_argument("--source", required=False, help="ID del nodo de origen")
    parser.add_argument("--target", required=False, help="ID del nodo de destino (objetivo)")
    
    args = parser.parse_args()
    
    run_pipeline(dataset_path=args.dataset, source=args.source, target=args.target)