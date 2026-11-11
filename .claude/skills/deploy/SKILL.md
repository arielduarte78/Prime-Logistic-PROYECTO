---
name: deploy
description: Despliega Abbey de punta a punta - tests de backend y frontend, commit si hace falta, push a GitHub, deploy del backend a Hugging Face, espera a Vercel, verifica que ambos sirvan el mismo commit y prueba el flujo invitado en producción.
disable-model-invocation: true
---

# /deploy — desplegar Abbey

Seguí los pasos en orden. Si un paso falla, frená, explicá qué pasó en español simple y NO sigas al siguiente. Nunca uses `--force`. Nunca cambies secretos.

## 0. Antes de empezar
- Tenés que estar en la rama `main` (`git rev-parse --abbrev-ref HEAD`). Si no, frená y avisá.
- `git pull --ff-only origin main`.

## 1. Tests del backend
```
uv run --frozen --python 3.14 --with pytest python -m pytest -q -p no:warnings
```
(Se usa `python -m pytest` porque `main.py` está en la raíz. `--frozen` evita que `uv` modifique `uv.lock`.) Tienen que pasar todos.

## 2. Tests y build del frontend
En `prime-frontend/`:
- Si no existe `node_modules`: `npm ci`.
- `node --test src/components/costLines.test.js src/services/fleetApi.test.js` (en Windows `npm test` no encuentra los archivos por las comillas). Si hay otros `*.test.js` nuevos (`find src -name "*.test.js"`), incluilos.
- `npm run build`.

## 3. Commit si hace falta
- `git status --short`. Si hay cambios sin commitear que NO son basura de tests (`uv.lock` modificado por uv, archivos en `data/audit_logs/`), mostrá `git diff --stat` y hacé commits chicos, en español, con mensaje descriptivo (nunca "messi"). Terminá el mensaje con la línea `Co-Authored-By` que indique el sistema.
- Si `uv.lock` quedó modificado solo por correr los tests, descartalo con `git checkout uv.lock`.
- El script del paso 5 exige árbol limpio.

## 4. Push a GitHub
`git push origin main` (normal). Esto dispara el deploy automático del frontend en Vercel.

## 5. Backend (Hugging Face)
En PowerShell: `.\deploy_backend.ps1`. Sube LFS, hace `git push hf main` sin force y espera hasta 15 min a que `/health` devuelva el commit de HEAD. Los mensajes rojos `NativeCommandError` de git por stderr son ruido; mirá la línea final `DEPLOY OK` o `ERROR`. Si dice ERROR, mostrá el comando de rollback que imprime y frená.

## 6. Esperar a Vercel
Repetí cada 15 s (máx. 5 min): `vercel ls abbey-frontend --format json` y mirá el primer deployment con `target: production`. Esperá a `state: READY` y `meta.githubCommitSha == HEAD`. Si termina en ERROR, mirá `vercel inspect <url> --logs`.

## 7. Verificar el mismo commit
- `curl -s https://aphira-abbey.hf.space/health` → `commit` == HEAD.
- Vercel (paso 6) → `githubCommitSha` == HEAD.
- `curl -sI https://abbey-frontend-rho.vercel.app/` → HTTP 200.
Los tres tienen que coincidir. Si no, decí cuál difiere.

## 8. Prueba del flujo invitado (navegador integrado)
1. Abrí `https://abbey-frontend-rho.vercel.app/login` con el navegador del panel.
2. Tocá "Probar como Invitado" (llega a `/app`, banner "Modo Invitado").
3. Ejecutá este JS con `javascript_tool` (carga la planilla de ejemplo y mide el tiempo):
```js
const of = window.fetch; window.__log = [];
window.fetch = async (...a) => { const t = Date.now(); try { const r = await of(...a); window.__log.push([String(a[0]).slice(0,80), r.status, Date.now()-t]); return r; } catch (e) { window.__log.push([String(a[0]).slice(0,80), 'ERR ' + e.message, Date.now()-t]); throw e; } };
const start = Date.now();
const inp = document.querySelector('input[type=file]');
const b = await (await of('/ejemplo_rutas.xlsx')).blob();
const dt = new DataTransfer(); dt.items.add(new File([b], 'ejemplo_rutas.xlsx')); inp.files = dt.files;
inp.dispatchEvent(new Event('change', { bubbles: true }));
await new Promise(r => setTimeout(r, 1500));
while (document.body.innerText.includes('Calculando') && Date.now() - start < 200000) await new Promise(r => setTimeout(r, 1000));
({ secs: (Date.now()-start)/1000, ok: document.body.innerText.includes('AUDITORIA DE COSTO SERVIDO'), log: window.__log })
```
4. Resultado esperado: `ok: true`, `/fleet` con 200, ~30-40 s. Miralo también con `read_console_messages` (solo errores). Repetilo una segunda vez (recargá `/app`; si te manda a `/login`, entrá de nuevo como invitado).

## 9. Resumen
Tabla corta: paso → resultado. Incluí: commit desplegado, tiempos de las pruebas invitado, errores si hubo. Si algo falló, indicá cuál es el siguiente paso (o sugerí `/rollback`).
