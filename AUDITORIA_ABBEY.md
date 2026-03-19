# AUDITORÍA TÉCNICA — ABBEY v1.5

> Generada automáticamente el 2026-03-19 desde el código fuente real del repositorio `Prime-Logistic-PROYECTO`.
> No contiene invención ni suposiciones. Todo lo documentado fue extraído de los archivos `.py`, `.json`, `.parquet` y `.yaml` del proyecto.

---

# VERSIÓN 1 — Auditoría Técnica (para investigadores / MIT)

## 1. Arquitectura General

Abbey es un motor de optimización de flotas logísticas para el AMBA (Área Metropolitana de Buenos Aires) compuesto por 5 bloques funcionales que operan en pipeline secuencial:

```
Bloque 1 → Bloque 2 → Bloque 3 → Bloque 4 → Bloque 5
(Grafo)    (Matrices)  (Bayesiano)  (Pareto)    (VRP)
```

El backend es una API FastAPI (`main.py`, 484 líneas) que ejecuta en Hugging Face Spaces via Docker (`uvicorn` + Python 3.14). El frontend es una aplicación React desplegada en Vercel.

### Stack tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Grafo | rustworkx (Rust bindings) | 0.17.1 |
| Geo-indexación | Uber H3 | 4.4.2 |
| Almacenamiento | DuckDB + Parquet | 1.4.4 |
| Inferencia bayesiana | NumPy (vectorizado) | 2.4.2 |
| Shortest-path | rustworkx.dijkstra_shortest_paths | Nativo C/Rust |
| VRP solver | Google OR-Tools (CVRPTW) | 9.15.6755 |
| Spatial index | scipy.spatial.cKDTree | 1.17.1 |
| API | FastAPI + Uvicorn | 0.135.1 / 0.41.0 |
| Validación | Pydantic v2 | 2.12.5 |

---

## 2. Bloque 1 — Construcción del Grafo e Ingestión Geoespacial

### `graph_builder.py` (143 líneas)

Construye un `rx.PyDiGraph` (dirigido) de rustworkx directamente desde DataFrames de DuckDB.

**Data contracts:**

- `NodePayload(frozen=True)`: `osm_id: int`, `lat: float`, `lon: float`
- `EdgePayload(frozen=True, slots=True)`: `u_osm`, `v_osm`, `alpha_prior`, `beta_prior`, `length`, `highway`, `h3_index`, `name`, `ref`

**Proceso:**
1. Extrae nodos únicos vectorizados con `pd.unique(df[['u','v']].values.ravel())`
2. Construye mapeos bidireccionales `osm_to_rx` / `rx_to_osm`
3. Itera filas con `itertuples()` para máximo rendimiento
4. Inyecta `EdgePayload` inmutables con priors bayesianos (`alpha_prior`, `beta_prior`) pre-cargados desde Parquet

**Datos reales:** Los archivos fuente son:
- `data/parquet_db/edges.parquet` (11.6 MB, ~527,411 aristas operacionales)
- `data/parquet_db/nodes.parquet` (4.9 MB)

Estos Parquets contienen topología real de OpenStreetMap del AMBA procesada previamente.

### `duckdb_ingestor.py` (69 líneas)

Extrae sub-grafos desde los Parquet usando DuckDB con filtrado por corredor H3:

```sql
SELECT u, v, length, highway, alpha_prior, beta_prior, h3_index_origin
FROM read_parquet('edges.parquet')
WHERE h3_index_origin IN (<hexágonos del corredor>)
```

También provee `get_nearest_node_osm_id()` que resuelve coordenadas lat/lon al nodo OSM más cercano usando distancia euclidiana parametrizada.

### `h3_router.py` (39 líneas)

Construye corredores geoespaciales con el sistema hexagonal H3 (resolución 8):

1. Convierte origen y destino a hexágonos H3
2. Traza línea recta con `h3.grid_path_cells()`
3. **Dilatación geométrica**: expande el corredor con `h3.grid_disk()` usando un radio dinámico basado en la distancia: `buffer_radius = max(1, min(5, int(1 + dist_grados * 25)))`

Esto permite al algoritmo "cruzar puentes" y encontrar rutas que no están exactamente sobre la línea recta.

---

## 3. Bloque 2 — Adaptador de Matrices

### `graph_adapter.py` (58 líneas)

Extrae matrices NumPy contíguas en memoria desde el grafo para Block 2 (Monte Carlo):

- `edges_idx`: array `(N, 2)` de pares `(u_rx, v_rx)` en `int32`
- `C`: array de longitudes en `float32`
- `A`: array de parámetros alpha (Beta distribution) en `float32`
- `B`: array de parámetros beta (Beta distribution) en `float32`

> **Nota:** Este bloque extrae las matrices pero el Monte Carlo completo del Bloque 2 (`generator.py`, `incidents.py`, `integration.py`) no se invoca directamente en el pipeline de producción `/fleet`. Los priors bayesianos se consumen directamente desde el grafo singleton.

---

## 4. Bloque 3 — Motor de Inferencia Bayesiana

### `bayesian_judge.py` (106 líneas)

Implementa un juez bayesiano basado en distribuciones Beta conjugadas.

**Inicialización (`_initialize_priors`):**
1. Recorre todas las aristas del grafo extractando `alpha_prior` y `beta_prior` del `EdgePayload`
2. Aplica **degradación por zona roja H3**: si la arista pertenece a un hexágono marcado en la threat matrix, modifica los priors:
   ```
   alpha_degraded = alpha * (1.0 - mu * 0.5)
   beta_degraded  = beta  * (1.0 + mu * 0.5)
   ```
   donde `mu ∈ [0.1, 1.0]` es la severidad normalizada de la zona.
3. Almacena los priors en arrays NumPy contíguos `float32` indexados por `(u_rx, v_rx)`

**Consulta (`get_params`):**
- Retorna `FastBeta(alpha, beta)` para cualquier arista en O(1) via diccionario

**Actualización (`update_edge`):**
- Actualización posterior bayesiana conjugada: `alpha += successes`, `beta += failures`
- Esto permite aprendizaje incremental (no usado en producción actual)

**`load_stochastic_overrides`:**
- Permite sobreescribir priors con valores degradados desde `stochastic_priors.parquet` (3.7 MB)
- Activado con flag `stochastic_mode=True` en el request → usa `judge_premium` en lugar de `judge_standard`

### `threat_loader.py` (49 líneas)

Carga `data/threat_index.json` que contiene 4 zonas de riesgo del AMBA:

| Zona | Severidad |
|------|-----------|
| Central Market / Riccheri Node | 9/10 |
| South Bank / La Noria Bridge | 8/10 |
| RP4 Ring Road Corridor | 7/10 |
| West Access / RP23 Moreno | 9/10 |

Convierte bounding boxes a hexágonos H3 res-8 (88 hexágonos en total) y normaliza severidad a `[0.1, 1.0]` dividiendo por 10.

---

## 5. Bloque 4 — Motor Multi-Objetivo y Frontera de Pareto

### `cost_calculator.py` (132 líneas) — Función central de costos

La función `compute_edge_cost()` es la pieza matemática central. Calcula el peso de una arista como combinación convexa:

```
weight = λ_cost × financial_cost_ars + λ_risk × risk_cost_ars
```

**Coeficientes λ por arquetipo:**

| Arquetipo | `λ_cost` | `λ_risk` | Estrategia |
|-----------|----------|----------|------------|
| **Tanque** | 0.01 | 0.99 | Máxima seguridad, ignora costo |
| **Apostador** | 0.99 | 0.01 | Mínimo costo, ignora riesgo |
| **Equilibrista** | 0.50 | 0.50 | Balance 50/50 |
| `none` (default) | 1.00 | 0.00 | Solo costo financiero |

**Cálculo financiero (`financial_cost_ars`):**
```
CKM = (gasoil_ars/l × consumo_l/km) + neumáticos_km + mantenimiento_km
CH  = CH_laboral + CH_estructural
financial_cost = dist_km × CKM + time_hr × CH + peajes + custodia_zona_roja
```

Donde:
- `CH_laboral = (sueldo × cargas_sociales + bono + viáticos×22 + SAC) / jornada_hs`
- `CH_estructural = (amortización + seguros + telemetría) / jornada_hs`
- Velocidad efectiva: `vel_kmh × multiplier_tráfico`

**Cálculo de riesgo (`risk_cost_ars`):**
```
p_survival = alpha / (alpha + beta)
p_failure  = 1 - p_survival
risk_cost  = p_failure × franquicia_seguro_ars × (dist_km / ruta_típica_km)
```

**Detección de peajes:** Resuelve peajes reales por nombre de vía OSM (25 de Mayo, Panamericana, Paseo del Bajo, etc.) o por referencia (`RN7`, `AU1`, etc.). Fallback a `peaje_promedio_ars` si no identifica la concesionaria.

### `multiobjective_engine.py` (261 líneas) — λ-Scalarización

Implementa un motor dual-pass Dijkstra que explora la frontera de Pareto mediante 10 pasadas de escalarización:

```python
for i in range(10):
    λ = i / 9    # λ ∈ {0.0, 0.111, ..., 1.0}
    weight_fn = λ * w_survival + (1 - λ) * (w_expected_cost / 1000.0)
    paths = rx.dijkstra_shortest_paths(graph, src, tgt, weight_fn)
```

**Funcionamiento:**
1. Construye un grafo temporal `rx.PyDiGraph` desde el `LazyEdgeView`
2. Ejecuta 10 pasadas de Dijkstra con λ variando de 0 a 1
3. Cada pasada produce una ruta óptima para esa combinación de objetivos
4. Deduplica rutas por composición exacta de aristas (`frozenset(edge_ids)`)
5. Reconstruye `Label` chains con costos acumulativos

**Complejidad:** O(10 × E log V) donde E = aristas del subgrafo y V = nodos.

### `pareto.py` (168 líneas) — Extracción de Arquetipos

Construye un `ParetoFrontResult` desde las etiquetas y extrae 4 arquetipos:

| Arquetipo | Método | Definición Matemática |
|-----------|--------|----------------------|
| **Tanque** | `extract_tank()` | `argmin(w_survival)` — mínimo riesgo acumulado |
| **Apostador** | `extract_gambler()` | `argmin(w_expected_cost)` — mínimo costo esperado |
| **Equilibrista** | `extract_tightrope()` | Mínima distancia euclidiana al utópico tras normalización min-max |
| **Unicornio** | `extract_unicorn()` | Condicional: si `overcost(Tanque vs Apostador) ≥ 25%`, devuelve el Tanque como anomalía |

**Equilibrista (detalle):**
```
ns = (w_survival - min_surv) / (max_surv - min_surv)
nc = (w_cost - min_cost) / (max_cost - min_cost)
score = √(ns² + nc²)
best = argmin(score)
```

### `lazy_graph.py` (112 líneas)

Duck-types el schema `Graph` para evitar materializar todas las aristas en memoria. Itera lazily sobre el grafo rustworkx aplicando el perfil económico del usuario en tiempo real.

### `weight_builder.py` (67 líneas)

Convierte el grafo con priors bayesianos a objetos `Edge` con pesos operacionales:
- `w_survival = -log(max(p_survival, 1e-9))` — transformación logarítmica aditiva
- `w_expected_cost = length + (p_failure × length)` — costo esperado con penalización probabilística

---

## 6. Bloque 5 — Orquestador VRP

### `vrp_orchestrator.py` (727 líneas) — Pipeline principal

`calculate_fleet()` es el punto de entrada del endpoint `/fleet`. Ejecuta un pipeline de 4 fases:

**Fase 1 — Filtrado Espacial:**
- Calcula un bounding box con 15% de padding sobre vehículos y destinos
- Usa `cKDTree.query_ball_point()` para obtener nodos relevantes del grafo singleton
- Resuelve vehículos y destinos al nodo OSM más cercano via `get_nearest_node_osm_id()`

**Fase 2 — Construcción de Matrices de Costo:**
- `build_time_matrix_only()`: Dijkstra temporal compartida entre arquetipos (caché por `(id(payload), departure_hour)`)
- `build_dense_cost_matrix()`: Dijkstra financiera por arquetipo con peso escalado ×100 para OR-Tools (enteros)

**Fase 3 — Solver VRP (Google OR-Tools):**
- Modelo CVRPTW (Capacitated VRP with Time Windows)
- Depots individuales por vehículo (`RoutingIndexManager` con starts/ends por vehículo)
- Dimensiones: Cost (arc cost), Capacity (demanda/capacidad), Time (ventanas horarias + service times)
- Metaheurística: `GUIDED_LOCAL_SEARCH` para ≥10 nodos, `AUTOMATIC` para menos
- Disjunctions con penalización `max_real_cost × 3` para permitir nodos no servidos
- Soporta: horarios de salida individuales, jornada máxima por vehículo, tiempo de servicio por destino

**Fase 4 — Evaluación Pareto por Tramo:**
- Para cada par consecutivo (source, target) de la ruta VRP:
  1. Construye un subgrafo local via `cKDTree` (radio = 60% diagonal + 0.05° mínimo)
  2. Instancia `LazyEdgeView` con el perfil económico del usuario
  3. Ejecuta `MultiObjectiveEngine.solve()` (10 pasadas λ-scalarization)
  4. Extrae los 4 arquetipos de la frontera de Pareto
  5. Traduce nodos internos a coordenadas geográficas para renderizado en mapa

**Ejecución paralela:** Los arquetipos se computan en paralelo via `ThreadPoolExecutor(max_workers=4)` + `asyncio.gather()`.

**Cost Breakdown:** Calcula desglose financiero completo por vehículo:
- OPEX Distancia (combustible + neumáticos + mantenimiento)
- OPEX Tiempo (costo laboral horario × duración + espera)
- CAPEX (amortización + seguros + telemetría prorrateados por hora)
- Fijos (peajes + viáticos)
- Custodia (por hora en zona de riesgo)
- Riesgo Patrimonial (1% × franquicia en ARS)

### `vrp_solver.py` (188 líneas)

Wrapper estricto de Google OR-Tools:
- `RoutingIndexManager` con depots individuales
- Callback de costo: `cost_matrix[from][to]`
- Callback de tiempo: `time_matrix[from][to] + service_time[from]`
- Slack de 1440 min (24h) para permitir esperas
- Extracción de cronogramas con `CumulVar` para arrival times

### `speed_profile_loader.py` (114 líneas)

Carga `config/speed_profiles.yaml` y provee multiplicadores de velocidad por:
- Franja horaria (`pico`, `valle`, `libre`)
- Tipo de vía OSM (`motorway`, `residential`, etc.)
- Zona H3 resolución 4

Fallback jerárquico: zona específica → zona DEFAULT → 1.0

### `lambda_scalarizer.py` (86 líneas)

Cache LRU módulo-nivel (500K entradas) para costos de aristas. Evita re-cómputo entre requests. Clave: `(id(payload), departure_hour, archetype)`.

---

## 7. API y Seguridad

### `main.py` — Lifespan y Endpoints

**Lifespan (singleton):**
- Carga grafo completo desde Parquets en memoria
- Construye `BayesianJudge` (standard + premium con overrides estocásticos)
- Construye `cKDTree` spatial index sobre coordenadas de nodos
- Carga cost settings, threat matrix, speed profiles

**Endpoints:**
- `POST /fleet` — Optimización de flotas completa (rate limit: 5/min)
- `POST /route` — Ruta única Pareto (rate limit: 10/min)
- `GET /health` — Health check con estado del grafo

**Seguridad:**
- API Key via header `X-API-Key` (keys en `PRIME_API_KEYS` env var)
- Rate limiting por IP (slowapi) + por API key (custom in-memory)
- CORS restringido a `*.vercel.app`, `*.hf.space`, localhost
- Audit logs forenses con hash SHA-256 del payload

### `schemas.py` — Contratos de Datos

- `EconomicProfile`: perfil financiero anidado con defaults de mercado argentino (gasoil $1865/l, sueldos, CAPEX, etc.)
- `FleetRequest`: hasta 20 vehículos, 100 destinos, arquetipos seleccionables
- `FleetResponse`: planes por arquetipo, segmentos Pareto, desglose de costos
- `CostBreakdown`: 25+ campos financieros con fuente de precios auditable

---

## 8. Datos Reales vs. Simulados

### Datos REALES (extraídos de fuentes verificables):

| Dato | Fuente | Archivo |
|------|--------|---------|
| Topología vial AMBA | OpenStreetMap | `edges.parquet`, `nodes.parquet` |
| Coordenadas de nodos | OSM Node IDs | `nodes.parquet` |
| Tipos de vía (highway tags) | OSM | `edges.parquet` |
| Longitudes de aristas | OSM (metros) | `edges.parquet` |
| Zonas de riesgo | Curación manual (4 zonas AMBA) | `threat_index.json` |
| Costos de peajes AUSA/AUBASA | Tarifas reales 2026 | `cost_params.yaml` |
| Precios combustible/neumáticos | Mercado argentino Mar 2026 | `schemas.py` defaults |

### Datos MODELADOS (basados en supuestos razonables):

| Dato | Supuesto | Ubicación |
|------|----------|-----------|
| Priors bayesianos (alpha, beta) | Pre-calculados offline, distribución Beta | `edges.parquet` |
| Priors estocásticos | Monte Carlo pre-computado | `stochastic_priors.parquet` |
| Speed profiles (pico/valle) | Multiplicadores estáticos por zona H3 | `speed_profiles.yaml` |
| Siniestralidad por ruta | 1% de probabilidad fija como fallback | `vrp_orchestrator.py:171` |
| Velocidad comercial base | 40 km/h fija | `schemas.py` |
| Ruta típica para normalización | 10 km fija | `rx_adapter.py:22` |

---

## 9. Limitaciones Actuales Honestas

### Arquitectura

1. **Grafo estático**: La topología se carga una vez al startup desde Parquet pre-procesado. No hay actualización en tiempo real de incidentes viales, cortes, ni semáforos.
2. **Sin aprendizaje online**: `update_edge()` del BayesianJudge existe pero **nunca se invoca en producción**. Los priors son estáticos entre deploys.
3. **Velocidad comercial uniforme**: 40 km/h base para todo tipo de vía, modulada solo por multiplicadores estáticos de speed profiles. No hay integración con APIs de tráfico en tiempo real.
4. **Sin re-optimización dinámica**: Una vez asignada la ruta, no se recalcula ante desvíos o cambios en la demanda.

### Precisión Financiera

5. **Peajes por heurística de nombre**: La detección de peajes depende de strings en el campo `name` de OSM (`"25 DE MAYO"`, `"PANAMERICANA"`, etc.). Aristas sin nombre usan un `peaje_promedio_ars` genérico (contabilizado como `toll_fallback_edges`).
6. **Riesgo patrimonial simplificado**: `0.01 × franquicia_seguro` por ruta completa. No modela correlación entre siniestros ni frecuencia diferencial por zona.
7. **CAPEX lineal**: Amortización lineal sin depreciación acelerada ni valor residual de mercado.
8. **Sin costos de carga/descarga**: El sistema asume que `service_time_min` cubre el tiempo operativo pero no calcula costos adicionales de manipulación.

### Escala

9. **Single node**: El backend corre en un solo contenedor (Hugging Face Space free tier con 16GB RAM). Sin auto-scaling ni distribución de carga.
10. **Concurrencia limitada**: Semáforo de 1 request simultáneo para `/fleet`, 3 para `/route`. Requests adicionales son rechazados con 429.
11. **Límite de 100 destinos**: Hardcoded en el schema Pydantic. La complejidad del VRP crece exponencialmente.
12. **Caché no distribuido**: LRU en memoria de proceso (500K entries). Se pierde en cada restart del contenedor.

### Datos

13. **Cobertura geográfica fija**: Solo AMBA (bounding box hardcoded: lat -35.5/-33.5, lon -59.5/-57.5). Coordenadas fuera del área retornan HTTP 400.
14. **Threat matrix manual**: Solo 4 zonas, 88 hexágonos. No se actualiza automáticamente con datos de siniestralidad.
15. **Sin datos de tráfico real**: Los speed profiles son estáticos. No hay integración con Waze, Google, ni conteos vehiculares.

---

---

# VERSIÓN 2 — Para cualquier persona (sin jerga técnica)

## ¿Qué problema resuelve Abbey?

**Abbey te dice cómo repartir mejor tu mercadería usando tus camiones, cuánto te va a costar, y cuál es la ruta más segura y barata para cada uno.**

---

## ¿Cómo funciona, paso a paso?

### Paso 1: Vos subís un Excel

Abrís la aplicación web, arrastrás tu planilla de Excel y Abbey la lee automáticamente. En esa planilla tenés:
- **Tus camiones**: dónde están estacionados, cuánto cargan y a qué hora salen
- **Tus destinos**: dónde tiene que llegar la mercadería, cuánto pesa cada entrega y en qué horario aceptan la entrega

### Paso 2: Abbey busca los caminos reales

Abbey tiene un mapa digital completo del Área Metropolitana de Buenos Aires (AMBA). No es un mapa dibujado a mano: son los mismos datos que usa Google Maps (OpenStreetMap), con más de **527,000 tramos de calle** y todos sus detalles (autopistas, avenidas, calles, puentes, etc.).

Cuando recibe tus datos, Abbey recorta solo la zona del mapa que necesita (como si cortara la parte del mapa que importa para tu reparto) y tira todo lo demás para ir más rápido.

### Paso 3: Abbey entiende el riesgo de cada calle

Cada tramo de calle tiene una "calificación de confiabilidad": qué tan probable es que puedas pasar sin problema. Esta calificación viene de un modelo estadístico (tipo encuesta) que le dice al sistema "esta calle es segura" o "esta zona es peligrosa".

Hay 4 zonas del AMBA que Abbey ya tiene marcadas como de alto riesgo: Mercado Central, Puente La Noria, Camino de Cintura, y la intersección de Acceso Oeste con RP23 en Moreno. En esas zonas, Abbey automáticamente busca alternativas más seguras.

### Paso 4: Abbey calcula los costos reales

Para cada tramo de ruta, Abbey calcula **exactamente cuánto te cuesta**:
- **Combustible**: litros que consume tu camión × precio del gasoil
- **Neumáticos y mantenimiento**: desgaste proporcional al kilometraje
- **Sueldo del chofer**: proporcional a las horas de viaje (incluyendo cargas sociales, bono, viáticos y SAC)
- **Desgaste del camión**: la parte del valor del vehículo que "usás" cada hora
- **Peajes**: detecta si tu ruta pasa por autopistas con peaje (25 de Mayo, Panamericana, Acceso Oeste, etc.) y los suma
- **Seguro**: el riesgo proporcional de tener un siniestro en esa ruta

Todos estos valores vienen con precios reales del mercado argentino (marzo 2026). Vos podés cambiarlos desde la app si tus costos son diferentes.

### Paso 5: Abbey te da cuatro opciones diferentes

En vez de darte una sola ruta, Abbey te ofrece **cuatro estrategias de negocio** para que vos elijas:

🛡️ **El Tanque**: La ruta más segura. Puede ser más cara, pero minimiza la probabilidad de problemas (robos, accidentes, cortes). Ideal si llevás mercadería de alto valor.

🎲 **El Apostador**: La ruta más barata. Puede pasar por zonas más complicadas, pero te ahorra plata. Ideal si tu margen es ajustado y la carga no es delicada.

⚖️ **El Equilibrista**: El mejor balance entre seguridad y costo. Es la opción que la mayoría de las empresas debería usar. Ni tan cara como el Tanque, ni tan riesgosa como el Apostador.

🦄 **El Unicornio**: Aparece solo cuando hay una anomalía: cuando la ruta segura sale más del 25% más cara que la barata. Es una alerta de que algo raro está pasando y deberías prestar atención.

### Paso 6: Abbey arma la hoja de ruta completa

Una vez elegida la estrategia, Abbey te arma un plan completo por cada camión:
- **Qué destinos visita** y en qué orden
- **A qué hora llega a cada lugar**
- **A qué hora vuelve a la base**
- **Cuánto le costó ese viaje en pesos y dólares**
- **Cuántos litros de gasoil usó**
- **Cuántos peajes pagó**

Todo esto lo ves en un mapa interactivo donde cada camión tiene un color diferente y podés filtrar para ver la ruta de uno solo.

---

## ¿Por qué le sirve a una PyME del AMBA?

1. **Deja de adivinar**: En vez de armar las rutas "a ojo" o por costumbre, tenés un cálculo real basado en el mapa actual y tus costos reales.

2. **Sabés cuánto cuesta cada reparto**: Abbey te desglosa el costo total en combustible, mano de obra, desgaste del camión, peajes y riesgo. Podés saber si un cliente te deja margen o te da pérdida.

3. **Cuidás tu mercadería**: Las zonas peligrosas del AMBA ya están cargadas. Si tenés carga valiosa, podés elegir la ruta "Tanque" y evitar problemas.

4. **Respetás los horarios**: Si tu cliente solo recibe entre las 9 y las 12, Abbey lo tiene en cuenta y programa la llegada dentro de esa ventana.

5. **No necesitás un sistema caro**: Abbey corre en la nube. No tenés que instalar nada. Subís tu Excel y en menos de un minuto tenés el plan.

6. **Datos argentinos reales**: Los precios de gasoil, sueldos, peajes y seguros son de marzo 2026. No son valores genéricos de otro país.

---

## Lo que Abbey todavía NO hace

- **No actualiza el tráfico en tiempo real**: El sistema sabe que a las 8 de la mañana hay más tráfico, pero no puede ver un accidente que acaba de pasar.
- **No recalcula si algo cambia**: Si un cliente cancela, tenés que volver a generar el plan desde cero.
- **Solo funciona en el AMBA**: No cubre rutas de larga distancia fuera de Buenos Aires y su área metropolitana.
- **Límite de escala**: Soporta hasta 20 camiones y 100 destinos por corrida. Para flotas más grandes habría que escalar la infraestructura.
