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

## Decisiones tomadas (10/11/2026)
- Cola en vez de rebote: `src/api/cola.py`. `/fleet`: 1 cálculo a la vez, hasta 3 esperando, máximo 90 s de espera. `/route`: 3 a la vez, hasta 10 esperando, 30 s. Si rebota: 429 con mensaje claro y `Retry-After: 30`. El turno se libera siempre.
- Frontend (`fleetApi.js`): ante un 429 espera lo que dice `Retry-After`, avisa ("El motor está ocupado…") y reintenta 2 veces; corta a los 3 minutos con un mensaje claro.
- Panel de costos: las líneas suman `costo_total_ars`; `exposure_risk_ars` se muestra aparte como "estimación en revisión" (`src/components/costLines.js`).
- Tests del frontend: `cd prime-frontend && npm test` (runner de Node, sin dependencias nuevas).
- **Ojo: un push a `main` en GitHub despliega el frontend** (Vercel compila desde `main`, confirmado el 10/11). El Space no se sincroniza solo: el 10/11 pasó a `b10e68a` porque una sesión local de Claude Code (en la PC del autor) corrió `deploy_backend.ps1`, y el commit siguiente (solo docs) no se desplegó. El backend se despliega con `deploy_backend.sh`.
- Verificación del 10/11 en producción (con la clave del frontend): `/route` 200 en ~1 s; `/fleet` del Excel de invitado 200 en ~30-40 s; dos `/fleet` a la vez → los dos 200 (el segundo espera su turno). Desde el navegador del entorno cloud de Claude los pedidos se cortan a los 30 s por el proxy del entorno (no pasa con curl ni sin proxy): no es un problema de producción.

## Pendientes
- **Velocidad de `/fleet`** (medido en producción: ~29 s para 2 camiones, 4 destinos y 3 arquetipos; ~5 s con 1 camión, 3 destinos y 1 arquetipo). El tiempo se va en (a) el Pareto por tramo: los 3 hilos de arquetipos calculan los MISMOS tramos a la vez; y (b) la matriz de costos: un Dijkstra por punto sobre el mapa entero (528 mil aristas) con una función de Python por arista. Los hilos no corren en paralelo de verdad (GIL). Opciones: calcular cada tramo una sola vez para los 3 arquetipos; correr la matriz sobre el subgrafo de la zona (medido: la mitad de tiempo en esa etapa); que el invitado calcule 1 arquetipo (medido: 26 s → 10 s); hardware pago no ayuda mucho por el GIL.
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

## Accesos y operación
Qué herramienta controla qué (todas se usan por terminal; los logins los hace el autor en su PC):

| Servicio | Herramienta | Para qué | Dónde está la credencial |
|---|---|---|---|
| Código (GitHub `arielduarte78/Prime-Logistic-PROYECTO`) | `git`, `gh` | commits, push, PRs, CI | Windows Credential Manager (`gh auth login` y git lo guardan ahí) |
| Frontend (Vercel, proyecto `abbey-frontend`, raíz `prime-frontend`) | `vercel` | deploys, variables, rollback | `vercel login` → archivo de sesión del CLI en el perfil del usuario. Proyecto vinculado en `.vercel/` (ignorado por git) |
| Backend (Hugging Face Space `Aphira/Abbey`) | `hf`, `git push hf main` | logs de ejecución y de build, estado, deploy | `hf auth login` → token en `~/.cache/huggingface/` y credencial de git |
| Auth y base (Supabase, la que usa el frontend) | `npx -y supabase` (no hay instalador en winget) | proyectos, migraciones | `supabase login` en el navegador; la URL y la anon key del frontend están en las variables `VITE_SUPABASE_*` de Vercel |

- Variables de entorno de producción del frontend (solo nombres): `VITE_API_URL`, `VITE_API_KEY`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, en Vercel (Production/Preview/Development). Ninguna va en el repo.
- El backend NO se sincroniza solo con GitHub: se despliega con `deploy_backend.ps1`. El frontend SÍ: cada push a `main` despliega en Vercel.
- Permisos de Claude Code: `.claude/settings.local.json` (no se sube a git). Pide confirmación para `git push --force`, borrar archivos, cambiar secretos/variables en producción y cualquier cambio en la base de Supabase.
- Nunca pegar tokens en el chat ni en archivos del repo.

### Comandos propios (en `.claude/skills/`)
- `/estado`: solo lectura. Salud de producción, commit desplegado en el backend y el frontend, y errores recientes en los logs.
- `/deploy`: tests de backend y frontend → commit si hace falta → push a GitHub → `deploy_backend.ps1` → espera a Vercel → verifica que `/health` y Vercel sirvan el mismo commit → prueba del flujo invitado → resumen.
- `/rollback`: vuelve backend y frontend al último deploy estable, con confirmación en cada paso. Ojo: no cambia `main` en GitHub.

### Mantener los servicios gratis despiertos
- `.github/workflows/mantener-activo.yml`: una vez por día (12:17 UTC) y a mano (`gh workflow run mantener-activo.yml`) hace dos pings: (1) una consulta liviana a Supabase (`GET /rest/v1/consultas?select=id&limit=1`) porque el plan gratis pausa el proyecto tras ~7 días sin actividad, y (2) `GET /health` del Space, que se duerme tras 48 h sin tráfico. Si algún ping falla, el workflow queda en rojo y GitHub avisa por mail.
- Secretos de GitHub Actions (solo nombres): `SUPABASE_URL`, `SUPABASE_ANON_KEY`. Se cargan con `gh secret set` en la terminal del autor.
- Límite: GitHub desactiva los workflows programados de un repo público tras 60 días sin commits. Si pasa, se reactiva a mano desde la pestaña Actions.
- Si la tabla `consultas` cambia de nombre, hay que actualizar el ping.
- `supabase/` (lo crea `supabase link`) está en `.gitignore`: solo tiene archivos temporales. Si algún día se versionan migraciones, sacarlo del `.gitignore`.

Detalles de máquina (Windows): los tests del backend se corren con `uv run --frozen --python 3.14 --with pytest python -m pytest` (no hay Python 3.14 en el PATH global). `npm test` no encuentra los archivos en Windows por las comillas; usar `node --test <archivos>`.
