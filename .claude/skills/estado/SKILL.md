---
name: estado
description: Muestra la salud de producción de Abbey (backend en Hugging Face y frontend en Vercel), el commit desplegado en cada lado y los errores recientes en los logs. Solo lectura, no despliega nada.
disable-model-invocation: true
---

# /estado — salud de producción (solo lectura)

No cambies nada, no despliegues. Corré los comandos de abajo (en lo posible en paralelo) y armá un resumen corto.

## 1. Commits
- `git fetch origin` y `git rev-parse origin/main` → commit de GitHub (lo llamamos MAIN).
- Backend: `curl -s https://aphira-abbey.hf.space/health` → campos `status` y `commit`.
- Space: `hf spaces info Aphira/Abbey` → `runtime.stage` (debe ser RUNNING) y `sha`.
- Frontend: `vercel ls abbey-frontend --format json` → mirá el primer deployment con `target: production`: `state` (READY), `meta.githubCommitSha`, `meta.githubCommitMessage`.

## 2. Comparar
- Si backend ≠ MAIN, corré `git diff --name-only <commit_backend> origin/main`. Si solo cambió documentación (`*.md`) no es un problema: decilo así. Si cambió código, el backend está atrasado: avisá que hay que correr `/deploy`.
- Si el frontend ≠ MAIN o el estado no es READY, avisá (puede estar construyéndose).
- El Space NO se sincroniza solo con GitHub; el frontend en Vercel SÍ.

## 3. Errores recientes
- Backend, run: `hf spaces logs Aphira/Abbey -n 300` y filtrá con grep líneas con `ERROR|Traceback|Exception| 500 | 502 | 503 | 429 `. Resumí cuántas hay y mostrá las 5 más recientes. Los `GET /health 200` son normales.
- Backend, build: `hf spaces logs Aphira/Abbey --build -n 30` (solo mirá si termina en DONE o hay error).
- Frontend: `vercel inspect <url del deployment de producción> --logs` y mostrá las últimas líneas si hay errores de build. El frontend es estático: no tiene logs de ejecución.

## 4. Otras comprobaciones rápidas
- `gh run list --limit 3` si `gh` está logueado (si no, decí "gh pendiente").
- `npx -y supabase projects list` si Supabase está logueado (si no, decí "supabase pendiente").

## 5. Resumen
Tabla corta: servicio → estado → commit → observaciones. Una línea final: "Todo OK" o qué falta atender. Si un comando falla por login, decí cuál login falta.
