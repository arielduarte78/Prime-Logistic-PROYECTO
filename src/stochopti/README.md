# Stochopti 🚀

**Stochopti** is a high-performance, domain-agnostic library for multi-objective stochastic optimization on directed graphs. It isolates Bayesian inference, Pareto scalarization, and Monte Carlo scenario generation from domain-specific business logic.

## Features

- **Bayesian Risk Engine:** O(1) NumPy-vectorized operations to maintain risk priors on graph edges, with zero-copy ephemeral clones for Monte Carlo simulations and HMAC-SHA256 integrity chains.
- **Multi-Objective Solver:** A dual-pass Dijkstra solver (via `rustworkx`) allowing linear scalarization of generic objectives.
- **Pareto Scaler & Scorer:** Algorithms for generating generic archetypes (Minimizer 1, Minimizer 2, Utopian Closest) from the Pareto frontier.
- **Monte Carlo Engine:** Highly decoupled stochastic event generation and adapter to map events into Bayesian priors.
- **Domain Agnostic:** Operates entirely on mathematical protocols (`EdgeCostFunction`, `PriorProvider`, `ThreatProvider`). It knows nothing about trucks, tolls, or spatial hexes.

## Installation

```bash
# Internal install
pip install -e .
```

## Basic Usage

```python
from stochopti.core.types import GraphSpec, NodeSpec, EdgeSpec
from stochopti.graph.solver import MultiObjectiveSolver

graph = GraphSpec(
    nodes=[NodeSpec("A"), NodeSpec("B")],
    edges=[EdgeSpec("e1", "A", "B", {"cost": 100, "risk": 0.05})],
    objective_names=("cost", "risk")
)

# You inject your own domain Cost Function
class SimpleCostFn:
    def __call__(self, edge, weights):
        return weights["cost"] * edge.objectives["cost"] + weights["risk"] * edge.objectives["risk"]

solver = MultiObjectiveSolver(graph, SimpleCostFn())
```
