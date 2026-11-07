# ARQUITECTURA — Prime Logistics Engine

Documento generado leyendo el código (sin modificar nada de código). Todo lo que
aparece acá sale de lo que hace el código **hoy** (commit `b0f6eda`), no de lo que
dicen los comentarios o el README.

> **Nota sobre CLAUDE.md:** este repo **no tiene** `CLAUDE.md`. No lo inventé; este
> commit contiene solo `ARQUITECTURA.md`.

> **Cómo se verificó:** lectura de código + ejecución de `pytest` + reproducción
> puntual de un error en Python. **No se pudo correr la API de punta a punta**:
> los `.parquet` de `data/parquet_db/` son punteros de Git LFS (≈130 bytes) y sin
> el grafo real `lifespan` hace `sys.exit(1)`. Lo que digo del flujo completo es
> por lectura de código, y está marcado cuando es una conclusión no ejecutada.

---

## 0. Mapa rápido

```
main.py  (FastAPI, en la raíz)
 ├─ /route  → bloque1 (H3 + nearest node) → bloque3 (juez bayesiano) → bloque4 (costos + Pareto)
 ├─ /fleet  → block5 (orquestador) → OR-Tools + bloque4 (Pareto por tramo) [+ bloque2 si stochastic_mode]
 ├─ /auth/token, /auth/refresh, /admin/usage, /health
 └─ src/api (schemas, identity, security), src/config (cost_params.yaml)
```

Al arrancar (`lifespan`) se construye **una sola vez**: el grafo `rustworkx`
(`build_directed_graph`), el `BayesianJudge`, un `judge_premium` (clon con priors
estocásticos, si existe `stochastic_priors.parquet`), un KD-tree de nodos
(`scipy.cKDTree`), la matriz de amenazas H3 y los perfiles de velocidad.

---

## 1. `POST /route` — paso a paso

Entrada: `RouteRequest` (`vehicles`, `destinations`, `departure_time`,
`stochastic_mode`, `economic_profile`). Salida: `RouteResponse` con hasta 4
soluciones de Pareto (arquetipos).

### Paso 1 — Perímetro (decoradores y dependencias de `calculate_route`, `main.py`)
- `slowapi`: límite `10/minute;100/hour`.
- `require_role("operator","admin")` (`src/api/identity.py`): exige identidad.
- Pydantic **strict** (`src/api/schemas.py`): rangos físicos, `departure_time` HH:MM, etc.
- Semáforo de 3 requests simultáneos; si no consigue lugar en 0,1 s → **429**.

### Paso 2 — Guardas (`_validate_coords`, `_validate_not_same`)
- Toma **solo `vehicles[0]` y `destinations[0]`** (el resto se ignora sin avisar).
- Caja AMBA: lat ∈ [−35.5, −33.5], lon ∈ [−59.5, −57.5], si no → 400.
- Origen ≈ destino (|Δ| < 1e-6 en lat y lon) → 400.

### Paso 3 — Nodo más cercano (`get_nearest_node_osm_id`, `bloque1/duckdb_ingestor.py`)
- **Entra:** lat, lon. **Sale:** `osm_id` (int).
- Escanea `nodes.parquet` con DuckDB y ordena por distancia al cuadrado:

  `d² = (lat − lat₀)² + (lon − lon₀)²`  (en **grados**, no metros)

### Paso 4 — Perfil económico (`main.py`)
- Parte de `app.state.cost_settings` (`CostSettings`, de `config/cost_params.yaml`).
- Si viene `economic_profile`, intenta mezclarlo con `CostSettings(**dict)`.
- ⚠️ Ver tabla 2, ítem 1: este paso y el paso 7 están **rotos** en el código actual.

### Paso 5 — Corredor H3 (`build_h3_corridor`, `bloque1/h3_router.py`)
- **Entra:** coords de origen y destino. **Sale:** lista de hexágonos H3 (res. 8).
- Hexágono de origen y destino → línea de hexágonos entre ambos (`grid_path_cells`).
- Se "engorda" cada hexágono con un anillo de radio `k`:

  `d = √((lat₁−lat₂)² + (lon₁−lon₂)²)`  (grados)
  `k = max(1, min(5, int(1 + 25·d)))`

  y se une `grid_disk(hex, k)` de todos los hexágonos de la línea.

### Paso 6 — Nodos permitidos (`main.py`)
- Recorre **todas** las aristas del grafo (`weighted_edge_list()`); si el
  `h3_index` de la arista está en el corredor, agrega sus dos extremos a
  `allowed_nodes`. Se agregan también origen y destino.
- Si origen/destino no están en el grafo → 400. Si `len(allowed_nodes) > 50 000` → 422.

### Paso 7 — Juez y hora de salida
- Juez: `judge_premium` si `stochastic_mode` y existe; si no, `judge_standard`.
- `departure_hour`: hora de `payload.departure_time` (ISO o `HH:MM`); si falla o
  no viene, hora actual en Buenos Aires.

### Paso 8 — Proxy de grafo (`build_legacy_graph`, `bloque4/rx_adapter.py` → `LazyEdgeView`, `lazy_graph.py`)
- **Entra:** grafo base, juez, `allowed_nodes`, perfil económico, hora, perfiles de velocidad.
- **Sale:** un `LazyEdgeView` que fabrica objetos `Edge` **al vuelo** al iterar `.edges`
  (no copia el grafo). Para cada arista con ambos extremos permitidos calcula:

**8a. Riesgo bayesiano** (`BayesianJudge.get_params` → Beta(α, β)):

  `p_sobrevive = α / (α + β)`
  `p_falla = 1 − p_sobrevive`
  `w_survival = −ln(max(p_sobrevive, 1e-9))`  ← suma sobre la ruta = −ln(prob. de que no falle nada)

  Los priors iniciales (`BayesianJudge._initialize_priors`) en zona roja (matriz
  de amenazas, μ = severidad/10) se degradan: `α' = α·(1 − 0.5μ)`, `β' = β·(1 + 0.5μ)`,
  con piso 1.

**8b. Tiempo** (`get_velocity_multiplier`, `block5/speed_profile_loader.py`):

  `dist_km = length / 1000`
  `v_efectiva = velocidad_comercial_kmh × multiplicador(franja horaria, hexágono H3 res. 4, tipo de vía)`
  `t_horas = dist_km / v_efectiva`

**8c. Costo financiero** (`compute_edge_cost`, `bloque4/cost_calculator.py`):

  `c_km = gasoil·consumo_l_km + neumáticos_km + mantenimiento_km`
  `c_laboral = sueldo·cargas + bono + viático·22 + provisión_SAC`
  `ch_laboral = c_laboral / jornada_mensual_hs`
  `c_amort = valor_unidad·(1 − recupero) / vida_útil_meses`
  `ch_estructural = (c_amort + seguros + telemetría) / jornada_mensual_hs`
  `c_hora = ch_laboral + ch_estructural`

  `financiero = dist_km·c_km + t_horas·c_hora`
  `+ t_horas·custodia_hora·μ`  (solo si el hexágono está en zona roja)
  `+ peaje`  (solo `motorway/trunk[_link]`; por nombre → por `ref` → promedio con "fallback")

**8d. Riesgo en pesos:**

  `riesgo_ars = p_falla · franquicia_usd·dólar_mep · (dist_km / 10)`

**8e. Peso final por arquetipo:** `peso = λ_costo·financiero + λ_riesgo·riesgo_ars`
con (λ_costo, λ_riesgo) = tanque (0.01, 0.99), apostador (0.99, 0.01),
equilibrista (0.5, 0.5), otro (1, 0).
**En `/route` el proxy usa el arquetipo `"none"` → (1, 0)**, o sea `w_expected_cost`
es **solo costo financiero**, sin riesgo. El riesgo viaja aparte en `w_survival`.

Cada `Edge` sale con: `cost = w_expected_cost`, `w_survival`, `risk = p_falla`,
`time = t_horas·3600` (segundos), `distance = length`.

### Paso 9 — Motor multiobjetivo (`MultiObjectiveEngine.solve`, `bloque4/multiobjective_engine.py`)
- **Entra:** `LazyEdgeView`, nodo origen, nodo destino (como strings del índice `rustworkx`).
- Arma un `PyDiGraph` temporal con las aristas (itera `graph.edges`, ver tabla 2).
- Hace **10 pasadas de Dijkstra** (`rx.dijkstra_shortest_paths`) con escalarización lineal:

  `λᵢ = i / 9`, i = 0…9
  `peso_arista = λ·w_survival + (1 − λ)·(w_expected_cost / 1000)`

  (el `/1000` es un reescalado de unidades para que ARS y −ln(p) sean comparables).
- Cada camino se reconstruye como cadena de `Label`, acumulando
  `w_survival = Σ w_survival`, `w_expected_cost = Σ w_expected_cost`, y se
  deduplica por el conjunto de aristas. **Sale:** lista de `Label` (≤ 10).
- Nota: es el método de las **sumas ponderadas**: solo encuentra puntos del
  casco convexo de la frontera de Pareto.

### Paso 10 — Arquetipos (`ParetoFrontResult`, `bloque4/pareto.py`)
- **Tanque:** `argmin w_survival`.
- **Apostador:** `argmin w_expected_cost`.
- **Equilibrista:** normaliza cada eje con min/max de la frontera,
  `n(x) = (x − min)/(max − min)` (0 si max ≤ min), y toma `argmin hypot(n_surv, n_cost)`.
- **Unicornio:** `sobrecosto = (costo_tanque − costo_apostador) / costo_apostador`;
  si ≥ 0.25 devuelve **el mismo objeto del Tanque**, si no `None`.

### Paso 11 — Respuesta (`main.py`)
- `confianza = 100·(w_max − w)/(w_max − w_min)` redondeada a 1 decimal, con
  `w_min/w_max` calculados **entre los arquetipos devueltos** (100 si todos
  empatan). Es un ranking relativo, **no** una probabilidad.
- Coordenadas: de cada nodo del camino con lat ≠ 0.
- `RouteResponse(processing_time_ms, total_edges=0, toll_fallback_edges, pareto_solutions)`.
- En background (`_write_audit_log`): línea JSONL en `data/audit_logs/AAAA-MM-DD.jsonl`
  con SHA-256 del request (`sort_keys=True`) y resumen de la respuesta.
- Cualquier excepción no HTTP → **422** con el texto del error.

---

## 2. `POST /fleet` — versión corta

Entrada: `FleetRequest` (vehículos ≤ 20, destinos ≤ 100, `allowed_archetypes`,
`time_limit_seconds`, ventanas horarias, `stochastic_mode`, `economic_profile`).
Salida: `FleetResponse` con un plan por arquetipo.

1. **Perímetro:** igual que `/route` pero semáforo de **1** (un `/fleet` a la vez).
   `calculate_fleet` (`block5/vrp_orchestrator.py`) corre en un executor.
2. **Fase 1 – nodos:** para cada vehículo y destino busca el nodo más cercano
   con el KD-tree (radio 0.01°, si no 0.05°; distancia² en grados). Arma
   `nodes_of_interest = vehículos + destinos`.
3. **Fase 2 – subgrafo:** círculo centrado en el centro de los puntos, de radio
   `max(0.5·diagonal, 0.10°)`, con `diagonal = √(Δlat² + Δlon²)`.
4. **(Opcional) `stochastic_mode`:** clona el juez y corre Monte Carlo
   (`bloque2`, semilla fija **42**, hasta 500 iteraciones, ventana de convergencia
   20/50) para degradar priors y generar `network_risk`. Si falla, vuelve al juez normal.
5. **Perfil económico:** `economic_profile` o `EconomicProfile()` por defecto
   (valores de `schemas.py`, **no** del YAML).
6. **Matriz de tiempos (una vez):** `build_time_matrix_only`: Dijkstra por origen con
   peso `t_horas = dist_km / (v_com·multiplicador)`; luego
   `minutos = ceil(horas·60)`; sin camino → 1440.
7. **Por arquetipo (en paralelo, `ThreadPoolExecutor`)** — `_compute_archetype_plan`:
   - **Matriz de costos:** Dijkstra por origen con el `compute_edge_cost` de arriba
     (pesos λ del arquetipo); `costo_entero = round(costo·100)`; inalcanzable = `10¹³`.
   - **VRP** (`block5/vrp_solver.py`, OR-Tools): minimiza la suma de la matriz de
     costos; capacidad con `int(ton·1000)`; dimensión `Time` (ventanas, servicio,
     jornada máx.) solo si hace falta; destinos opcionales con
     `penalidad = 3 · costo_real_máximo`; `PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH`
     (`AUTOMATIC` si ≤ 10 nodos) con `time_limit_seconds`.
   - **Tramos:** por cada par consecutivo de la ruta, mismo pipeline que `/route`
     (proxy + 10 pasadas de Dijkstra + arquetipos) sobre un subgrafo de radio
     `max(0.6·diagonal, 0.05°)`; hay caché compartida entre arquetipos. La distancia
     real se mide con **haversine**: `a = sin²(Δφ/2) + cosφ₁·cosφ₂·sin²(Δλ/2)`,
     `d = 2·6371·atan2(√a, √(1−a))` km.
   - **Desglose de costos** (`_calculate_cost_breakdown`):
     `opex_dist = km·(consumo·gasoil + neum + mant)`,
     `opex_tiempo = (horas_ruta + horas_espera)·ch_laboral`,
     `capex = horas_ruta·ch_estructural`, `fijos = peajes + viático`,
     `custodia = horas_ruta·custodia_hora`,
     `exposición = 0.01·franquicia_usd·dólar` (constante),
     `total = suma`, `USD = total/dólar`.
8. **Respuesta:** `plans[arquetipo]`, `network_risk` (aristas con `prob_falla > 0.65`),
   `integrity_compromised` si la cadena HMAC del juez falló. El arquetipo
   "unicornio" se descarta en `/fleet`.

---

## 3. Resultado de `pytest`

Entorno: Python 3.13 (el proyecto pide ≥ 3.14), dependencias instaladas con `pip`
sin fijar versiones (solo en el entorno, no en el repo).

| Comando | Resultado |
|---|---|
| `python -m pytest` | **No ejecuta ningún test**: error de colección. `tests/conftest.py:15` hace `from src.api.main import app`, y `src/api/main.py` **no existe** (la app está en `main.py` de la raíz). Exit code 2. |
| `python -m pytest --noconftest` | **24 passed, 4 failed, 3 errors** (0,7 s). |

Detalle con `--noconftest`:
- 4 failed — `tests/unit/test_cost_calculator.py` (4 tests de peajes/residencial):
  `AttributeError: 'CostSettings' object has no attribute 'opex_movil'`
  (`bloque4/cost_calculator.py:56`).
- 3 errors — `tests/integration/test_api_endpoints.py`: `fixture 'test_client' not found`
  (esa fixture vive en el `conftest.py` que no carga).
- 24 passed — todos de `tests/stochopti/` (la librería `stochopti`, que `main.py` no usa).

Conclusión: **ningún test cubre hoy `/route` ni `/fleet`**.

---

## 4. Tabla 1 — Código muerto o duplicado (qué usa realmente `main.py`)

"Usado" = alcanzable por imports desde `main.py` (cierre transitivo calculado con `ast`).
No se miraron `scripts/` ni notebooks; algo marcado como muerto puede usarse desde ahí.

| Carpeta | Usado desde `main.py` | Importado pero nunca llamado | Muerto / roto |
|---|---|---|---|
| `src/bloque1` | `h3_router`, `graph_builder`, `duckdb_ingestor` (solo `get_nearest_node_osm_id`) | `extract_subgraph_edges` (importada en `main.py:31`, jamás llamada) | `cache_manager`, `config`, `fleet_schema`, `loader`, `logger`, `models`, `network`, `smart_ingestor`, `station_normalizer`, `validators` (~2 400 líneas) |
| `src/bloque2` | `generator`, `incidents`, `stochastic_adapter` (solo con `stochastic_mode` en `/fleet`), `graph_adapter` | `get_matrices`: `app.state.mc_matrices` se calcula al arrancar y **nadie la lee** | `integration`, `example_advanced`, `test_incidents` (un test dentro de `src/`, fuera de `testpaths`) |
| `src/bloque3` | `bayesian_judge`, `integrity_chain`, `threat_loader` | — | `inference_engine`, `auditor`, `metrics`, `reliability_report.py` (el juez tiene su propio método `reliability_report`) |
| `src/bloque4` | `schema`, `rx_adapter`, `lazy_graph`, `cost_calculator`, `multiobjective_engine`, `pareto` | `weight_builder.build_pareto_edges` (importada en `main.py:35`, no se llama); `engines.py` y `profiler.py` se ejecutan al importar el paquete (`__init__.py`) pero nada los usa | `assembler` y `smoke_weight_builder` (importan `build_edge_weights`, que **no existe**), `config`, `report`, `utils`, `tests/test_engine.py` |
| `src/block5` | **Todo**: `vrp_orchestrator`, `vrp_solver`, `cost_matrix_builder`, `lambda_scalarizer`, `speed_profile_loader` | — | — |
| `src/stochopti` | **Nada.** Solo lo usan `tests/stochopti/` | — | Librería completa (~2 000 líneas, con su propio `pyproject.toml`) |

Duplicados funcionales entre versiones (la columna "se usa" es la que ejecuta `main.py`):

| Función | Versión que se usa | Duplicado que NO se usa |
|---|---|---|
| Juez bayesiano / priors Beta | `bloque3/bayesian_judge.py` (`BayesianJudge`) | `stochopti/bayesian/engine.py` (`BayesianRiskEngine`, `SharedBayesianState`) |
| Cadena de integridad HMAC | `bloque3/integrity_chain.py` | `stochopti/bayesian/integrity.py` |
| Solver multiobjetivo (λ-Dijkstra) | `bloque4/multiobjective_engine.py` | `stochopti/graph/solver.py` (`MultiObjectiveSolver`, `EpsilonConstraintSolver`) y `bloque4/engines.py` |
| Arquetipos de Pareto | `bloque4/pareto.py` | `stochopti/pareto/frontier.py` + `scoring.py` |
| Monte Carlo | `bloque2/generator.py` (`MonteCarloEngine`) | `stochopti/montecarlo/engine.py` |
| Perfilado de ruta | — (ninguno) | `bloque4/profiler.py` y `stochopti/graph/profiler.py` |
| Costo por arista | `bloque4/cost_calculator.py` | `bloque4/weight_builder.py` (otra fórmula: `longitud·(1 + p_falla)`) |
| Peajes en el reporte | `vrp_orchestrator._detect_toll_crossings` (por nombre) | `cost_calculator._get_toll_from_ref` (por `ref`); las dos reglas **no coinciden** |

---

## 5. Tabla 2 — Lo que está mal o es engañoso

Severidad: **A** = rompe o da resultados incorrectos, **M** = engañoso/riesgo, **B** = menor.
"Verificado" = lo reproduje/ejecuté; "Por lectura" = conclusión de leer el código.

| # | Sev. | Dónde | Qué pasa | Evidencia |
|---|---|---|---|---|
| 1 | A | `main.py` (`/route`), `rx_adapter.py:67`, `cost_calculator.py:56` | `/route` pasa un `CostSettings` plano, pero el código nuevo exige `cost_env.opex_movil/personal/capex` (solo existen en `EconomicProfile`). Sin `economic_profile` → `AttributeError`; con `economic_profile` → `CostSettings(**{... 'opex_movil': ...})` → `TypeError`. En ambos casos el `except` lo convierte en **422**. `/fleet` sí funciona porque usa `EconomicProfile` directo. | Verificado: 4 tests unitarios fallan con ese `AttributeError`; el `TypeError` lo reproduje en Python. HTTP completo: por lectura (sin datos reales). |
| 2 | A | `tests/conftest.py:15` | Importa `src.api.main`, que no existe → `pytest` normal no corre nada. | Verificado. |
| 3 | A | `block5/lambda_scalarizer.py`, `cost_matrix_builder.py` | Cachés globales con clave `(id(payload), hora, arquetipo)` / `(id(payload), hora)`. **No incluyen** perfil económico, juez ni velocidad. El comentario asume que son singletons, pero en `/fleet` el perfil es **por request** y el juez puede ser un clon estocástico → un request puede recibir costos/tiempos de otro request con distinto perfil. | Por lectura. |
| 4 | A | `cost_calculator.py` (peaje) | El peaje se suma **por arista** de autopista, no por cruce de cabina: una autopista de 30 aristas cobra ~30 peajes. Distorsiona costo y ruteo (el costo "financiero" de las rutas con autopista queda inflado). | Por lectura. |
| 5 | A | `cost_calculator.py` | La regla `"BAJO" in name` captura cualquier nombre con "bajo" (p. ej. "Bajo Belgrano") y le cobra Paseo del Bajo. | Por lectura. |
| 6 | M | `/fleet` vs `config/cost_params.yaml` | `/fleet` ignora el YAML: usa los defaults de `EconomicProfile`. Difieren mucho: velocidad 40 vs **22** km/h, franquicia 1 500 vs **80 000** USD, peaje promedio 1 200 vs **6 000**, 25 de Mayo 1 200 vs **6 305**. Además `c_km_ars` y `c_hora_ars` del YAML no se usan en ninguna fórmula (se recalculan desde `opex/personal/capex`). Y `/health` devuelve `ckm_ars: 807.85` / `ch_ars: 19130.79` **hardcodeados**. | Por lectura. |
| 7 | M | `main.py` (`/route`) | Solo se rutea `vehicles[0]` → `destinations[0]`; el resto del payload se ignora sin avisar. | Por lectura. |
| 8 | M | `multiobjective_engine.py` | Se describe como "dual-pass" / "A*-guiado" (docstring y comentarios de `main.py`); en realidad son **10 pasadas** de Dijkstra con suma ponderada. `eps_1`, `eps_2`, `max_total_labels`, `node_coords` se pasan pero **no se usan**. Solo halla soluciones del casco convexo. | Por lectura. |
| 9 | M | `multiobjective_engine.py`, `rx_adapter.py`, `lazy_graph.py` | `graph.edges` recalcula todo cada vez que se itera: `solve` lo itera 2 veces, y `build_legacy_graph` además muestrea 500 aristas para un log. El costo por arista se calcula ≥ 2×, y `toll_fallback_edges` se **cuenta de más** (incrementa en cada pasada). | Por lectura. |
| 10 | M | `lazy_graph.py` | `w_expected_cost` ("costo esperado") es solo costo financiero (arquetipo `none` → λ_riesgo = 0); no incluye el riesgo esperado. El nombre sugiere otra cosa. | Por lectura. |
| 11 | M | `pareto.py` | "Unicornio" devuelve el **mismo** objeto que el Tanque con otro nombre; no es una ruta distinta. `confidence` es relativa entre arquetipos (siempre hay uno en 100 y otro en 0), no una probabilidad. | Por lectura. |
| 12 | M | `vrp_orchestrator._get_h3_polygons` | Filtra `mu > 1.1`, pero `mu = severidad/10 ≤ 1.0` → `risk_polygons` siempre vacío. | Por lectura. |
| 13 | M | `vrp_orchestrator._calculate_cost_breakdown` | `exposure_risk` es una constante (1 % de la franquicia) que no usa el modelo bayesiano; `custodia` no usa μ (en el ruteo sí); el viático se cobra una vez por vehículo, pero `peajes` se calculan con otra regla distinta a la del ruteo (ver tabla 1). El desglose no reconcilia con el peso que optimizó el ruteo. | Por lectura. |
| 14 | M | `main.py` (`_load_client_registry`) | Si `ABBEY_CLIENT_REGISTRY` no está seteada, se habilitan `dev_operator` / `dev_admin` con **secretos conocidos en el código**. En producción, cualquiera obtiene un token. También: comparación de secreto con `!=` (no constante) y secretos en texto plano; y si faltan `ABBEY_HMAC_KEY`/`ABBEY_JWT_SECRET` se generan claves efímeras (los tokens mueren al reiniciar). | Por lectura. |
| 15 | M | `.env` | Archivo `.env` **versionado en git** (hoy solo contiene `PYTHONPATH`, pero el patrón es riesgoso). | Verificado (`git ls-files`). |
| 16 | M | `bayesian_judge.get_params` vs `cost_calculator` | Arista desconocida → `FastBeta(1, 1)` (p = 0.5, muy riesgosa) en el juez, pero `compute_edge_cost` usa `(100, 3)` (p ≈ 0.97) si el juez no tiene `get_params`. Dos "defaults" distintos. | Por lectura. |
| 17 | M | `main.py` | Errores internos se devuelven como **422** (debería ser 500) con `str(e)` al cliente (filtra detalles internos). | Por lectura. |
| 18 | B | `main.py` | `gc` solo se importa dentro de `lifespan`; en el `finally` de `/route` `gc.collect()` lanza `NameError` que se traga el `except NameError` → nunca corre. Imports sin uso (`extract_subgraph_edges`, `build_pareto_edges`, `get_matrices`, `math`, `verify_api_key`, …). Encabezado `#src/api/main.py` pero el archivo está en la raíz. | Por lectura. |
| 19 | B | `duckdb_ingestor.get_nearest_node_osm_id` y `/route` | Escanea el parquet de nodos completo en cada request; y recorre todas las aristas del grafo para armar `allowed_nodes`. Distancia en grados (1° de lon ≈ 0.82 de 1° de lat a −34.6°), con leve sesgo este-oeste. | Por lectura. |
| 20 | B | `cost_calculator.py` | Recalcula `c_km`, `c_hora` (constantes por request) en cada arista. | Por lectura. |
| 21 | B | versiones | Título "V1.4", `/health` dice "Abbey 1.5", `pyproject` dice 1.3.5 y pide Python ≥ 3.14. | Por lectura. |
| 22 | B | `/fleet` (`main.py`) | El flag `integrity_compromised` mira `judge_premium`/`judge_standard`, pero en `stochastic_mode` el orquestador usa un clon efímero nuevo; el flag puede no reflejar el juez realmente usado (comparten la misma cadena HMAC, así que el riesgo es bajo). Monte Carlo con semilla fija 42 → mismos escenarios siempre. | Por lectura. |
| 23 | B | `data/parquet_db/*.parquet` | En este checkout son punteros Git LFS (~130 bytes): la app no arranca sin `git lfs pull`. | Verificado. |
