"""
Bloque 3 — Orquestador de Inferencia (V1.3)

Responsabilidad única:
  - Cargar los escenarios del Bloque 2.
  - Delegar el procesamiento al InferenceEngine.
  - Retornar el ReliabilityReport ortogonal.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Iterable

from src.bloque3.auditor import load_scenarios
from src.bloque3.inference_engine import InferenceEngine, InferenceConfig
from src.bloque3.reliability_report import ReliabilityReport

LOGGER = logging.getLogger(__name__)

def run_inference_pipeline(
    scenarios_path: str,
    node_ids: Iterable[str],
    scenario_payloads: Dict[str, Dict[str, Any]] | None = None
) -> ReliabilityReport:
    """
    Punto de entrada principal para el Bloque III.
    """
    LOGGER.info("Iniciando pipeline de inferencia...")

    # 1. Carga de datos forenses
    try:
        raw_scenarios = load_scenarios(scenarios_path)
        LOGGER.info("Se cargaron %d escenarios desde %s", len(raw_scenarios), scenarios_path)
    except Exception as exc:
        LOGGER.exception("Fallo crítico al cargar escenarios: %s", exc)
        raise

    # 2. Instanciación del motor principal del Bloque III
    config = InferenceConfig()
    engine = InferenceEngine(config=config)

    # 3. Procesamiento y extracción del reporte
    report = engine.process(
        scenarios=raw_scenarios,
        scenario_payloads=scenario_payloads,
        node_index=list(node_ids)
    )

    LOGGER.info("Pipeline de inferencia completado con éxito.")
    return report
