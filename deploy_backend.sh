#!/usr/bin/env bash
# deploy_backend.sh - Despliega SOLO el backend (Space de Hugging Face). No toca Vercel.
#
# El token de Hugging Face va SIEMPRE por variable de entorno (HF_TOKEN). Nunca se guarda
# en la URL del remote, en .git/config ni en ningun archivo, y la salida se enmascara.
#
# Uso:
#   HF_TOKEN=hf_xxx ./deploy_backend.sh            # despliega main
#   DRY_RUN=1 ./deploy_backend.sh                  # solo verificaciones, no sube nada
#   ROLLBACK=1 HF_TOKEN=hf_xxx ./deploy_backend.sh # vuelve al commit anterior (unico caso con --force)
set -euo pipefail

# ---------- Configuracion ----------
HF_URL="https://huggingface.co/spaces/Aphira/Abbey"
HF_USER="${HF_USER:-Aphira}"                      # el usuario no es secreto; lo que importa es el token
HEALTH_URL="https://aphira-abbey.hf.space/health"
COMMIT_ANTERIOR="a3ba522db34de42f912c918ad12ddc3982b97094"   # lo que habia en el Space antes del primer deploy
INTERVALO_SEG=30                                  # cada cuanto consultar /health
MAX_ESPERA_MIN=15                                 # cuanto esperar como maximo

cd "$(dirname "$0")"

fallar() { echo; echo "ERROR: $1" >&2; exit 1; }

# Consulta /health y devuelve el campo "commit" (vacio si no responde o es una version vieja).
commit_en_el_space() {
    curl -s --max-time 20 "$HEALTH_URL" 2>/dev/null | sed -n 's/.*"commit":"\([^"]*\)".*/\1/p' || true
}

# ---------- Paso 0: el token tiene que estar en el entorno ----------
if [ "${DRY_RUN:-0}" != "1" ] && [ -z "${HF_TOKEN:-}" ]; then
    fallar "Falta la variable de entorno HF_TOKEN (token de Hugging Face con permiso de escritura sobre el Space)."
fi

# ---------- Autenticacion sin dejar rastro ----------
# Git le pregunta usuario/clave a este mini-script, que los lee del entorno.
# El archivo temporal NO contiene el token y se borra al terminar.
ASKPASS="$(mktemp)"
trap 'rm -f "$ASKPASS"' EXIT
cat > "$ASKPASS" <<'ASK'
#!/bin/sh
case "$1" in
  *sername*) printf '%s\n' "$HF_USER" ;;
  *)         printf '%s\n' "$HF_TOKEN" ;;
esac
ASK
chmod 700 "$ASKPASS"
export HF_USER HF_TOKEN="${HF_TOKEN:-}" GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0

# Ejecuta un comando y tapa el token si por casualidad apareciera en la salida.
sin_token() {
    if [ -n "$HF_TOKEN" ]; then "$@" 2>&1 | sed "s/$HF_TOKEN/***/g"; else "$@" 2>&1; fi
}

# El remote 'hf' se crea si falta (sin credenciales en la URL).
if ! git remote get-url hf >/dev/null 2>&1; then
    git remote add hf "$HF_URL"
elif [ "$(git remote get-url hf)" != "$HF_URL" ]; then
    fallar "El remote 'hf' no apunta a $HF_URL."
fi

# ---------- Modo ROLLBACK ----------
if [ "${ROLLBACK:-0}" = "1" ]; then
    echo "ROLLBACK: el Space vuelve a ${COMMIT_ANTERIOR:0:7} (git push --force, solo en este modo)..."
    sin_token git push hf "${COMMIT_ANTERIOR}:refs/heads/main" --force
    echo "Listo. El Space se va a reconstruir; revisa $HEALTH_URL en unos minutos."
    exit 0
fi

# ---------- Paso 1: verificaciones previas ----------
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || fallar "No estas en la rama main (git checkout main)."
[ -z "$(git status --porcelain)" ] || fallar "Hay cambios sin commitear:
$(git status --short)"
git fetch -q origin main
HEAD_LOCAL="$(git rev-parse HEAD)"
[ "$HEAD_LOCAL" = "$(git rev-parse origin/main)" ] || fallar "main local no coincide con origin/main (usa git push / git pull)."
echo "OK: main, sin cambios pendientes, sincronizada con origin (${HEAD_LOCAL:0:7})."

# ---------- Paso 2: tests (si algo falla, se frena) ----------
echo "Corriendo pytest..."
python -m pytest -p no:cacheprovider -q 2>&1 | tail -3
if [ "${PIPESTATUS[0]}" -ne 0 ]; then fallar "pytest fallo: no se despliega."; fi
# Los tests de integracion escriben un log de auditoria; lo sacamos para dejar el arbol limpio.
git checkout -q -- data/audit_logs 2>/dev/null || true
git clean -fdq -- data/audit_logs 2>/dev/null || true

# ---------- Paso 3: que hay hoy en el Space y que vamos a subir ----------
sin_token git fetch hf main >/dev/null
EN_SPACE="$(git rev-parse hf/main)"
echo "Commit actual del Space : ${EN_SPACE:0:7}"
echo "Commit que se va a subir: ${HEAD_LOCAL:0:7}"
git merge-base --is-ancestor "$EN_SPACE" "$HEAD_LOCAL" \
    || fallar "El Space tiene commits que main no tiene. No se usa --force; revisalo a mano."
echo "Commits nuevos para el Space: $(git rev-list --count "$EN_SPACE..$HEAD_LOCAL")"

if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "DRY_RUN: verificaciones OK. No se sube nada."
    git lfs push --dry-run hf main 2>&1 | head -5 || true
    exit 0
fi

# ---------- Paso 4: subir (LFS primero, despues git; sin --force) ----------
if [ "$EN_SPACE" != "$HEAD_LOCAL" ]; then
    echo "Subiendo solo los objetos LFS que necesita main..."
    sin_token git lfs push hf main
    echo "git push hf main (sin --force)..."
    sin_token git push hf main
fi

# ---------- Paso 5: esperar que /health devuelva mi commit ----------
echo "Esperando que /health devuelva commit=${HEAD_LOCAL:0:7} (cada ${INTERVALO_SEG}s, maximo ${MAX_ESPERA_MIN} min)..."
LIMITE=$(( $(date +%s) + MAX_ESPERA_MIN * 60 ))
ULTIMO="sin respuesta"
while [ "$(date +%s)" -lt "$LIMITE" ]; do
    C="$(commit_en_el_space)"
    if [ "$C" = "$HEAD_LOCAL" ]; then
        echo; echo "DEPLOY OK - el Space esta corriendo ${HEAD_LOCAL:0:7}"; exit 0
    fi
    ULTIMO="${C:-sin respuesta o version vieja}"
    echo "[$(date +%H:%M:%S)] /health -> ${ULTIMO}"
    sleep "$INTERVALO_SEG"
done

echo
echo "ERROR: pasaron ${MAX_ESPERA_MIN} min y /health no devolvio el commit esperado (ultimo: ${ULTIMO})." >&2
[ "$ULTIMO" = "desconocido" ] && echo "El Space responde 'desconocido': la imagen no trae .git. Definir GIT_COMMIT en el Space." >&2
echo "Para volver al commit anterior:  ROLLBACK=1 HF_TOKEN=... ./deploy_backend.sh" >&2
echo "(equivale a: git push hf ${COMMIT_ANTERIOR}:main --force)" >&2
exit 1
