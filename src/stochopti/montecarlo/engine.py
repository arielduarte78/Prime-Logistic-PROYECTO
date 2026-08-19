"""stochopti/montecarlo/engine.py — Agnostic Monte Carlo Simulation Engine with Multiprocessing."""

import logging
import concurrent.futures
from typing import Any, Callable, Dict, List, Protocol, Sequence, Tuple

logger = logging.getLogger(__name__)

class GraphMutator(Protocol):
    """Protocolo inyectado para mutar el estado (grafo u otro) y retornar intensidad."""
    def apply_event(self, state: Any, event: Any) -> float:
        ...

class EventGenerator(Protocol):
    """Protocolo inyectado para generar perturbaciones estocásticas."""
    def generate_events(self) -> List[Any]:
        ...

class ScenarioEvaluator(Protocol):
    """Protocolo inyectado para medir el impacto de la perturbación (resiliencia)."""
    def evaluate(self, state: Any) -> Dict[str, float]:
        ...

def _worker_simulate(
    scenario_id: int,
    state_factory: Callable[[], Any],
    event_generator: EventGenerator,
    mutator: GraphMutator,
    evaluator: ScenarioEvaluator
) -> Dict[str, Any]:
    """Top-level worker function to allow pickling in ProcessPoolExecutor."""
    state = state_factory()
    events = event_generator.generate_events()
    
    applied_events = []
    for ev in events:
        intensity = mutator.apply_event(state, ev)
        applied_events.append({
            "event": ev,
            "intensity_multiplier": intensity
        })
        
    metrics = evaluator.evaluate(state)
    
    return {
        "scenario_id": str(scenario_id),
        "events": applied_events,
        "metrics": metrics
    }

class MonteCarloEngine:
    """Motor de simulación estocástica puramente abstracto con concurrencia por procesos."""
    
    def __init__(
        self, 
        state_factory: Callable[[], Any],
        event_generator: EventGenerator,
        mutator: GraphMutator,
        evaluator: ScenarioEvaluator,
        max_workers: int = 4
    ):
        self.state_factory = state_factory
        self.event_generator = event_generator
        self.mutator = mutator
        self.evaluator = evaluator
        self.max_workers = max_workers

    def run(self, max_iter: int = 5000) -> List[Dict[str, Any]]:
        """Ejecuta N simulaciones y recolecta métricas y perturbaciones usando multiprocesamiento."""
        results = []
        
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers)
        try:
            futures = []
            for i in range(1, max_iter + 1):
                futures.append(
                    executor.submit(
                        _worker_simulate,
                        i,
                        self.state_factory,
                        self.event_generator,
                        self.mutator,
                        self.evaluator
                    )
                )
            
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                
        finally:
            # Ensures resources are cleaned up even if workers crash or an exception is raised
            executor.shutdown(wait=True, cancel_futures=True)
            
        logger.info("MonteCarloEngine completed %d iterations across %d workers.", max_iter, self.max_workers)
        return results
