# Prime Logistics — Bloque 1

Repositorio que implementa la ingestión, el modelado topológico y la exportación matricial de una red logística.  
Convierte nodos y arcos en tensores alineados listos para alimentar un optimizador en Bloque 2:

- A: matriz de adyacencia binaria  
- C: matriz de costos (moneda/unidad)  
- T: matriz de tiempos (horas)  
- K: matriz de capacidades por arco (toneladas)  
- D: vector de demanda neta (demand − supply)  
- nodes: índice maestro para alinear filas/columnas  


## Estructura del proyecto

- `src/bloque1/network.py` — **NetworkIndexer, Ingestor**: registro thread‑safe, validación de nodos/arcos y snapshot.  
- `src/bloque1/topology.py` — **GeometryEngine, TopologyBuilder**: cálculo de distancias, construcción de topología y `export_matrices()`.  
- `src/bloque1/models.py` — definiciones de **NodeRecord, ArcRecord, Metadata, CostProfile, SpeedProfile** (modelo de dominio).  
- `tests/` — tests unitarios y `conftest.py` con fixtures de ejemplo.  
- `requirements.txt` — dependencias opcionales como `numpy`, `scipy` (si se usa salida dispersa).

---

## Instalación rápida

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# opcional para matrices dispersas
pip install scipy
```

---

## Ejecutar tests

Asegurate de que `src` esté en el path y ejecutá:

```bash
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
pytest -q
```

Para ejecutar solo los tests de topology:

```bash
pytest -q tests/test_topology.py
```

---

## Uso básico de TopologyBuilder

```python
from src.bloque1.network import NetworkIndexer
from src.bloque1.models import NodeRecord, ArcRecord
from src.bloque1.topology import TopologyBuilder

idx = NetworkIndexer()
# registrar nodos y arcos (ver modelos)
idx.register_node(NodeRecord.from_dict({...}))
idx.register_arc(ArcRecord.from_dict({...}))

tb = TopologyBuilder(idx)
tb.build_topology()
package = tb.export_matrices(sparse=False)

# Paquete resultante
nodes = package["nodes"]
A = package["A"]   # adyacencia binaria
C = package["C"]   # costos $/unidad
T = package["T"]   # tiempos en horas
K = package["K"]   # capacidades por arco (toneladas)
D = package["D"]   # demanda neta (demand - supply)
meta = package["meta"]
```

---

## Convenciones y notas importantes

- Índice maestro: siempre usar `package["nodes"]` para alinear filas/columnas entre A, C, T, K y D.  
- Unidades:  
  - Distancias en km  
  - Tiempos en horas  
  - Costos en dolares
  - Capacidades en toneladas (se normalizan automáticamente según `capacity_unit`)  
  - Demanda en unidades  
- Valores especiales: `np.inf` en C/T/K indica ruta no disponible o sin límite; A es binaria (`np.bool_`) o `csr_matrix` si `sparse=True`.  
- Umbrales por modo: definidos en `config.py` (ej. truck=56 t, ship=80 000 t, air=102 t, rail=3100 t). Capacidades que exceden se clampean y generan un warning.  
- Compatibilidad estación ↔ modo**: validada en `Ingestor`. Ejemplo: `air` solo ↔ `airport`, `ship` ↔ `port`, etc.  
- Extensiones recomendadas: añadir `fixed_cost` en `ArcRecord`, validar unidades en `SpeedProfile`, y usar salida dispersa para redes grandes.


## Contribuir

- Abrí issues para bugs o mejoras.  
- Enviá PRs con tests que cubran cambios.  
- Mantener mensajes de commit claros y atómicos.  
