# Abbey (Prime-Logistic) — contexto para Claude Code

## Qué es
Abbey es un optimizador de rutas para flotas en el AMBA (Buenos Aires).
- Backend: FastAPI (`main.py`) + rustworkx + OR-Tools, desplegado como Docker en Hugging Face Spaces (puerto 7860).
- Frontend: React + Vite + Tailwind + Leaflet en `prime-frontend/`, desplegado en Vercel (abbey-frontend-rho.vercel.app). Auth con Supabase y modo invitado.
- Motor matemático: `src/stochopti/` (también publicado aparte como repo Abbey-Engine).

Flujo de `/route`: nodo OSM más cercano → corredor H3 entre origen y destino → subgrafo → costos (km, hora, peajes, custodia; `config/cost_params.yaml`) + riesgo por hexágono H3 (`data/threat_index.json`, zonas con severidad 1-10) → priors Beta por arista (juez bayesiano) → ε-constraint / relajación lagrangiana → frontera de Pareto → arquetipos (Tanque = más segura, Apostador = menor costo, Equilibrista, Unicornio).
Flujo de `/fleet`: Excel de flota → matriz de costos → VRP con OR-Tools (capacidades, ventanas horarias, disjunctions).

## Sobre el autor (importante)
El autor tiene 20 años, Python básico, y el proyecto fue hecho mayormente con IA ("vibecodeado").
Objetivo actual: ENTENDER cada parte, simplificar y luego difundirlo en redes.
Por eso:
- Explicá en español simple qué hace cada cambio y la matemática detrás, con fórmulas cuando corresponda.
- No agregues complejidad, capas nuevas ni dependencias sin preguntar.
- Preferí código corto y legible a código "impresionante".
- Nada de nombres científicos para fórmulas que no lo son (ej.: no llamar "entropy" a algo que no es entropía).

## Problemas conocidos (no arreglar sin que se pida)
- `src/stochopti/pareto/scoring.py`: `if obj2 <= 1.0 * obj2` siempre es True (todas las rutas quedan LOW_COST). `entropy` y `redundancy_index` son fórmulas arbitrarias.
- El README de stochopti dice "LARAC" pero el solver es un subgradiente lagrangiano simple con paso 1/√k, sin fallback si no encuentra ruta factible.
- Sobreingeniería: cadena HMAC-SHA256, memoria compartida en /dev/shm con file locks, suma de Neumaier para ~20 aristas.
- Duplicación entre `src/bloqueN/` y `src/stochopti/` (integrity_chain, auditor, profiler, pareto). Nombres mezclados `bloque*` / `block5`.
- `prime-frontend/src/services/fleetApi.js` tiene una API key de respaldo hardcodeada; las variables VITE_ son públicas en el navegador de todos modos.
- `data/threat_index.json` no está en el repo (lo ignora `*.json` en .gitignore). Origen de las severidades: a documentar por el autor.

## Decisiones tomadas (07/11/2026)
- `config/cost_params.yaml` es la única fuente de parámetros económicos de `/route`, `/fleet` y `/health`. Los valores quedan como están: velocidad comercial 22 km/h, franquicia 80.000 USD. El cliente solo pisa los campos que manda explícitamente (`resolve_profile` en `src/config/settings.py`).
- `exposure_risk_ars` NO suma a `costo_total_ars`: se devuelve aparte, con `exposure_risk_nota: "estimación en revisión"`.
- `/auth/token`: sin `ABBEY_CLIENT_REGISTRY` rechaza todo (ya no existen `dev_operator`/`dev_admin`). La clave legacy `x-api-key` (`PRIME_API_KEYS`) que usa el frontend NO se toca.
- Peajes: se prorratean por largo (un peaje cada `KM_POR_PEAJE = 10` km de autopista), no por arista. Es una aproximación, a validar.
- `/health` devuelve `commit` (variable `GIT_COMMIT` o carpeta `.git`).
- Deploy del backend: `./deploy_backend.sh` (Linux/macOS, lo usa Claude) o `deploy_backend.ps1` (Windows). Sin `--force`, no tocan Vercel, verifican `/health` hasta que `commit` sea el HEAD de `main`. El token de Hugging Face va SIEMPRE por la variable de entorno `HF_TOKEN` (con `GIT_ASKPASS`): nunca en la URL del remote, en `.git/config` ni en archivos. Rollback: `ROLLBACK=1 HF_TOKEN=... ./deploy_backend.sh` (único caso con `--force`). `deploy.ps1` está DEPRECADO, no usar. Space: https://huggingface.co/spaces/Aphira/Abbey (app: https://aphira-abbey.hf.space). Commit anterior al primer deploy: `a3ba522`.
- Secrets del Space: solo `PRIME_API_KEYS`.

## Pendientes
- **Rehacer `exposure_risk_ars` en la etapa de datos reales.** Hoy es un 1% fijo de la franquicia (`0.01 * franquicia_usd * dólar`) que no usa el modelo de riesgo.
- Frontend: `CostBreakdownPanel.jsx` suma `exposure_risk_ars` en la línea "Riesgo Patrimonial y Custodia", pero el total ya no lo incluye (las líneas no suman el total). `fleetApi.js` sigue con API key de respaldo hardcodeada.
- Juez bayesiano y riesgo: la caché de costos usa una huella de α/β (`BayesianJudge.huella()`); el modelo de riesgo y `threat_index.json` siguen sin revisar.
- `_get_h3_polygons` filtra `mu > 1.1` pero `mu <= 1.0`: `risk_polygons` sale siempre vacío.
- Código muerto y duplicado: ver las tablas de `ARQUITECTURA.md` (nada se borra sin confirmación).
- Los `.parquet` están en Git LFS: hace falta `git lfs pull` para levantar la API.

## Reglas de trabajo
- Antes de borrar o mover archivos, listá qué vas a tocar y esperá confirmación.
- Corré los tests (`pytest`) antes y después de cada cambio.
- Commits chicos con mensajes descriptivos en español (no "messi").
- Nunca subas secretos; si aparece uno, avisá.
