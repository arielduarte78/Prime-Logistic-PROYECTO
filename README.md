# PRIME LOGISTICS | INTERNAL DEV HUB

**Status:** MVP v1.0 (Stable Core)
**Access:** Internal Team & Contributors Only

 **CONFIDENTIAL**
This repository contains proprietary algorithms for stochastic optimization and Bayesian inference.
Do not share outside the team.

##  Objetivo Técnico

Prime Logistics es una plataforma modular para modelar, simular y optimizar redes logísticas bajo incertidumbre extrema.

El objetivo de ingeniería es mantener una arquitectura stateless y data-driven, donde la topología y el riesgo fluyen a través de cuatro bloques aislados que se comunican exclusivamente mediante contratos de datos inmutables. Produce recomendaciones de rutas robustas y explicables bajo incertidumbre.

##  Arquitectura del Sistema

El sistema implementa un pipeline secuencial estricto.

```
graph LR
    B1[B1: Topología] -->|Matrices A/C/T/K/D| B2[B2: Chaos Engine]
    B2 -->|Escenarios Monte Carlo| B3[B3: Auditor]
    B3 -->|Mapa de Riesgo (Phi)| B4[B4: Optimizer]
    B4 -->|Reporte Estratégico| User
```

##  Mapa de Módulos (Source of Truth)

| Módulo | Responsabilidad Técnica | Archivos Clave |
|--------|--------------------------|----------------|
| **B1: Topology** | Ingesta: Valida y transforma la red física en tensores. | `topology.py`, `network.py` |
| **B2: Chaos** | Simulación: Genera fallos estocásticos y cisnes negros. | `generator.py`, `integration.py` |
| **B3: Auditor** | Inferencia: Calcula probabilidades posteriores (Beta-Binomial). | `inference_engine.py`, `bayesian_judge.py` |
| **B4: Optimizer** | Decisión: Optimiza rutas y genera narrativa de negocio. | `selector.py`, `reporter.py` |
| **Main** | Orquestación: Conecta los cables entre bloques. | `main.py` |

##  Quick Start

### 1. Instalación

```bash
# 1. Clonar repo
git clone git@github.com:arielduarte78/prime-logistic.git
cd prime-logistic

# 2. Crear entorno virtual (Python 3.9+)
python -m venv .venv
source .venv/bin/activate  

# 3. Instalar dependencias
pip install -r requirements.txt
```

### 2. Ejecutar Pipeline Completo 

```bash
python main.py
```

**Expected Output:** Logs de auditoría de los 4 bloques, análisis de riesgo y un reporte estratégico ASCII en consola. Se generarán artefactos en `output/`.

## Guía de Uso por Bloque 

### Bloque 1: Ingesta de Topología

```python
from src.bloque1.network import NetworkIndexer
from src.bloque1.models import NodeRecord, ArcRecord
from src.bloque1.topology import TopologyBuilder

idx = NetworkIndexer()
idx.register_node(NodeRecord.from_dict({"id": "WH_001", "lat": -34.6, "lon": -58.38}))
idx.register_arc(ArcRecord.from_dict({
    "id": "ARC_01", "origin": "WH_001", "destination": "CLIENT_001",
    "capacity": 10000, "active": True
}))

tb = TopologyBuilder(idx)
tb.build_topology()
package = tb.export_matrices(sparse=False) # Output: Matrices listas para B2
```

### Bloque 2: Simulación Estocástica

```python
from src.bloque2.integration import StochasticNetworkPipeline

pipeline = StochasticNetworkPipeline(seed=42)
pipeline.load_topology_from_bloque1(package)
pipeline.load_incident_manifest("src/bloque2/manifest.yaml")

# Genera 5000 futuros posibles con convergencia estadística
scenarios = pipeline.generate_stochastic_scenarios(n_scenarios=5000)
```

### Bloque 3: Auditoría Bayesiana

```python
from src.bloque3.inference_engine import InferenceEngine, InferenceConfig
from src.bloque3.auditor import FailureCriteria
from src.bloque3.bayesian_judge import PriorConfig

engine = InferenceEngine(InferenceConfig(
    criteria=FailureCriteria(min_capacity_retained=0.85),
    prior=PriorConfig(alpha=9, beta=1), # Prior optimista
    use_impact_in_fragility=True,
))
report = engine.process(scenarios) # Output: Mapa de fragilidad (phi)
```
modela la confiabilidad estructural de la red

### Bloque 4: Estrategia & Reporte

```python
from src.bloque4.engines import DijkstraEngine
from src.bloque4.selector import select_strategic_options
from src.bloque4.reporter import PrimeStrategicReporter

# Resuelve optimización multiobjetivo (Costo vs Riesgo vs Entropía)
solution = DijkstraEngine().solve(graph, phi_vector, optimizer_config)
options = select_strategic_options([solution], profiles, optimizer_config)

# Genera narrativa de negocio
print(PrimeStrategicReporter(optimizer_config).generate_full_report(options))
```
el optimizador no busca optimalidad determinista, sino trade-offs robustos.

##  Estándares de Código

Exigimos rigor en cada commit.

**Type Hinting Obligatorio:**
```
❌ def calcular(a, b):
✅ def calcular(a: float, b: int) -> float:
```
Usamos mypy para validación estática.

**Inmutabilidad por Defecto:**
- Usar `@dataclass(frozen=True)` para objetos de dominio (Nodos, Arcos, Configs).
- Evitar efectos secundarios (side-effects) en las funciones core.

**Manejo de Errores:**
- No usar `try/except pass`.
- Los errores de topología deben levantar ValueError con mensajes descriptivos.
- Usar el LOGGER configurado, no print() (salvo en CLI output).

##  Roadmap & Status

| Fase | Estado | Objetivo |
|------|--------|----------|
| Fase 1: MVP | Completado | Core Pipeline funcional (B1->B4) + Reporte Consola. |
| Fase 2: Robustez | En Progreso | Persistencia JSON, Tests Unitarios (Pytest), Logs Rotativos. |
| Fase 3: Escala | Futuro | Integración OpenStreetMap, API REST (FastAPI), Dashboard Web. |

##  Troubleshooting

**Error:** `ImportError: no module named src...`
**Solución:** Ejecutar siempre desde la raíz del proyecto: `python main.py`.

**Error:** `ZeroDivisionError` en el reporte.
**Solución:** Verificar que los costos de los arcos sean > 0.0 en la definición.

##  Contacto Interno

**Lead Architect:** Ariel
**Tech Stack:** Python 3.9+ / NumPy / SciPy

