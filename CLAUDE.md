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

## Reglas de trabajo
- Antes de borrar o mover archivos, listá qué vas a tocar y esperá confirmación.
- Corré los tests (`pytest`) antes y después de cada cambio.
- Commits chicos con mensajes descriptivos en español (no "messi").
- Nunca subas secretos; si aparece uno, avisá.
