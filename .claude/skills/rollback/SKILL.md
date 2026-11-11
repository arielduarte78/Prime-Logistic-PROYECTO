---
name: rollback
description: Vuelve el backend (Hugging Face) y el frontend (Vercel) al último deploy estable, siempre pidiendo confirmación antes de cada paso.
disable-model-invocation: true
---

# /rollback — volver al último deploy estable

Regla: NO ejecutes ningún cambio sin que el usuario confirme en el chat, paso por paso. Primero mostrá, después preguntá.

## 1. Diagnóstico (solo lectura)
- Backend: `curl -s https://aphira-abbey.hf.space/health` (commit actual) y `git log hf/main --oneline -8` después de `git fetch hf main` (historial de lo desplegado en el Space).
- Frontend: `vercel ls abbey-frontend --format json` → lista de deployments de producción con `state`, `meta.githubCommitSha` y `meta.githubCommitMessage`.
- Proponé como "último estable" el deployment/commit anterior al actual que esté READY y, si tenés dudas, mostrá varios candidatos y dejá elegir.

## 2. Pedir confirmación
Mostrá: "Backend: <commit actual> → <commit estable>. Frontend: <deployment actual> → <deployment estable>." y preguntá si confirma, y si es los dos o solo uno.

## 3. Backend (solo si confirma)
Vuelve el Space al commit elegido. Es un `--force` sobre el remote `hf` (no toca GitHub), así que el sistema te va a pedir permiso:
```
git push hf <commit_estable>:main --force
```
Después esperá a que `curl -s https://aphira-abbey.hf.space/health` devuelva ese commit (revisá cada 30 s, máx. 15 min).

## 4. Frontend (solo si confirma)
```
vercel rollback <url_del_deployment_estable>
```
Después `vercel rollback status` y verificá con `curl -sI https://abbey-frontend-rho.vercel.app/` que responde 200.

## 5. Avisos importantes (decíselos al usuario)
- GitHub `main` NO cambia: sigue teniendo el commit malo. El próximo push a `main` volverá a desplegar el frontend con ese commit. Si quiere que se quede, hay que arreglar `main` con un `git revert` (que es un commit nuevo, sin force).
- El backend y el frontend tienen que ser compatibles entre sí (por ejemplo, CORS `Retry-After`, la cola de `/fleet`). Si se vuelve uno solo, probalo.

## 6. Verificación
Hacé una prueba rápida del flujo invitado como en el paso 8 de `/deploy` y resumí en una tabla: servicio → commit activo → OK/ERROR.
