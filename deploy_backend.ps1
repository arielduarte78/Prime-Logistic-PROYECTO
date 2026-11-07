# deploy_backend.ps1 - Despliega SOLO el backend (Hugging Face Space). No toca Vercel.
#
# Que hace, en orden:
#   1. Verifica que estas en main, sin cambios sin commitear y sincronizado con origin.
#   2. Sube a Hugging Face los objetos LFS que necesita main (los parquet).
#   3. Hace "git push hf main" SIN --force.
#   4. Consulta /health cada 30 s (hasta 15 min) hasta que el commit coincida con tu HEAD.
#   5. Imprime "DEPLOY OK" o el error con el comando para volver al commit anterior.
#
# Uso (desde la raiz del repo, en PowerShell):   .\deploy_backend.ps1

# Con "Continue" los avisos que git escribe por stderr no cortan el script;
# los errores reales los revisamos nosotros mirando $LASTEXITCODE.
$ErrorActionPreference = "Continue"

# ---------- Configuracion ----------
$HF_REMOTE      = "hf"
$HF_URL         = "https://huggingface.co/spaces/Aphira/Abbey"
$HEALTH_URL     = "https://aphira-abbey.hf.space/health"
$COMMIT_ANTERIOR = "a3ba522db34de42f912c918ad12ddc3982b97094"   # lo que habia en el Space antes del deploy
$INTERVALO_SEG  = 30          # cada cuanto consultar /health
$MAX_ESPERA_MIN = 15          # cuanto esperar como maximo

# ---------- Funciones de ayuda ----------

# Frena el script con un mensaje claro. Si ya se hizo el push, agrega como volver atras.
function Fallar([string]$mensaje, [bool]$conRollback = $false) {
    Write-Host ""
    Write-Host "ERROR: $mensaje" -ForegroundColor Red
    if ($conRollback) {
        Write-Host ""
        Write-Host "Para volver al commit anterior ($($COMMIT_ANTERIOR.Substring(0,7))) ejecuta:" -ForegroundColor Yellow
        Write-Host "    git push $HF_REMOTE ${COMMIT_ANTERIOR}:main --force" -ForegroundColor Yellow
    }
    exit 1
}

# Ejecuta un comando de git y frena si falla.
function Git-Ok([string]$paraQue, [scriptblock]$comando, [bool]$conRollback = $false) {
    & $comando
    if ($LASTEXITCODE -ne 0) { Fallar "Fallo: $paraQue (codigo $LASTEXITCODE)." $conRollback }
}

Write-Host "=== Deploy del backend a Hugging Face ===" -ForegroundColor Cyan

# ---------- Paso 1: verificaciones previas ----------

# 1a. Tiene que estar en la rama main.
$rama = (git rev-parse --abbrev-ref HEAD).Trim()
if ($rama -ne "main") {
    Fallar "Estas en la rama '$rama'. Cambia a main con: git checkout main"
}

# 1b. No puede haber cambios sin commitear.
$cambios = git status --porcelain
if ($cambios) {
    Fallar "Hay cambios sin commitear. Hace commit o stash antes de desplegar:`n$cambios"
}

# 1c. main local tiene que ser igual a origin/main.
Git-Ok "git fetch origin main" { git fetch origin main }
$head   = (git rev-parse HEAD).Trim()
$origen = (git rev-parse origin/main).Trim()
if ($head -ne $origen) {
    $adelante = (git rev-list --count "origin/main..HEAD").Trim()
    $atras    = (git rev-list --count "HEAD..origin/main").Trim()
    Fallar "main local no esta sincronizado con origin/main (adelante: $adelante, atras: $atras). Usa 'git push origin main' o 'git pull origin main'."
}
Write-Host "OK: rama main, sin cambios pendientes, sincronizada con origin ($($head.Substring(0,7)))." -ForegroundColor Green

# 1d. El remote de Hugging Face tiene que existir (si falta, lo agregamos; si apunta a otro lado, frenamos).
$urlActual = (git remote get-url $HF_REMOTE 2>$null)
if (-not $urlActual) {
    Write-Host "Agregando remote '$HF_REMOTE' -> $HF_URL"
    Git-Ok "git remote add" { git remote add $HF_REMOTE $HF_URL }
} elseif ($urlActual.Trim() -ne $HF_URL) {
    Fallar "El remote '$HF_REMOTE' apunta a '$urlActual' y se esperaba '$HF_URL'."
}

# 1e. Mostramos que hay hoy en el Space y que vamos a subir (para que lo veas antes de que pase).
Git-Ok "git fetch $HF_REMOTE main" { git fetch $HF_REMOTE main }
$enSpace = (git rev-parse "$HF_REMOTE/main").Trim()
Write-Host "Commit actual del Space : $($enSpace.Substring(0,7))"
Write-Host "Commit que se va a subir: $($head.Substring(0,7))"
if ($enSpace -eq $head) {
    Write-Host "El Space ya tiene este commit. Solo se verifica /health." -ForegroundColor Yellow
}
# Si el Space tiene algo que main no tiene, un push normal fallaria: frenamos con aviso claro.
git merge-base --is-ancestor $enSpace $head
if ($LASTEXITCODE -ne 0) {
    Fallar "El Space tiene commits que main no tiene. No se usa --force; revisalo a mano."
}

# ---------- Paso 2: objetos LFS ----------
# Se suben ANTES del push de git: si faltan, Hugging Face rechaza el push.
# Sin --all: solo los objetos que necesita main, no todo el historial.
if ($enSpace -ne $head) {
    Write-Host "Subiendo objetos LFS necesarios para main..." -ForegroundColor Cyan
    Git-Ok "git lfs push $HF_REMOTE main" { git lfs push $HF_REMOTE main }

    # ---------- Paso 3: push a Hugging Face (SIN --force) ----------
    Write-Host "Haciendo git push $HF_REMOTE main (sin --force)..." -ForegroundColor Cyan
    Git-Ok "git push $HF_REMOTE main" { git push $HF_REMOTE main }
}

# ---------- Paso 4: esperar a que /health devuelva mi commit ----------
Write-Host "Esperando que el Space reconstruya y devuelva commit = $($head.Substring(0,7)) (cada $INTERVALO_SEG s, maximo $MAX_ESPERA_MIN min)..." -ForegroundColor Cyan
$limite  = (Get-Date).AddMinutes($MAX_ESPERA_MIN)
$ultimo  = "sin respuesta"
$ok      = $false
while ((Get-Date) -lt $limite) {
    try {
        $resp = Invoke-RestMethod -Uri $HEALTH_URL -TimeoutSec 20
        if ($resp.commit) { $ultimo = [string]$resp.commit } else { $ultimo = "version vieja (sin campo commit)" }
        if ($resp.commit -eq $head) { $ok = $true; break }
    } catch {
        # Mientras reconstruye, el Space no responde: es normal.
        $ultimo = "sin respuesta (reconstruyendo)"
    }
    Write-Host ("[{0}] /health -> {1}" -f (Get-Date -Format "HH:mm:ss"), $ultimo)
    Start-Sleep -Seconds $INTERVALO_SEG
}

# ---------- Paso 5: resultado ----------
if ($ok) {
    Write-Host ""
    Write-Host "DEPLOY OK - el Space esta corriendo $($head.Substring(0,7))" -ForegroundColor Green
    exit 0
}

$extra = ""
if ($ultimo -eq "desconocido") {
    $extra = " El Space responde 'desconocido': la imagen no incluye la carpeta .git. Define la variable GIT_COMMIT en el Space o revisa el Dockerfile."
}
Fallar "Pasaron $MAX_ESPERA_MIN minutos y /health no devolvio el commit esperado (ultimo valor: $ultimo).$extra" $true
