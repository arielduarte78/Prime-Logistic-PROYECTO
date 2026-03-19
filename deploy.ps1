# Abbey Engine - Sync & Deploy Script (Windows)

$PRIME_FRONTEND_DIR = "prime-frontend"

# 1. Verification of branch
$currentBranch = git rev-parse --abbrev-ref HEAD
if ($currentBranch -ne "dev") {
    Write-Host "Error: You must be on the 'dev' branch to run this script." -ForegroundColor Red
    exit 1
}

Write-Host "--- Starting Deployment Workflow ---" -ForegroundColor Cyan

# 2. Check for uncommitted changes
$status = git status --porcelain
if ($status) {
    Write-Host "Error: You have uncommitted changes. Commit or stash them before deploying." -ForegroundColor Red
    exit 1
}

# 3. Merge dev -> main
Write-Host "--> Switching to main and merging dev..." -ForegroundColor Green
git checkout main
if ($LASTEXITCODE -ne 0) { exit 1 }

git merge dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "CRITICAL ERROR: Merge conflict detected! Aborting deployment." -ForegroundColor Red
    Write-Host "Please resolve conflicts manually or run 'git merge --abort'."
    exit 1
}

# 4. Push to remotes
Write-Host "--> Pushing to Origin (Vercel)..." -ForegroundColor Green
git push origin main
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "--> Pushing to Hugging Face (Backend)..." -ForegroundColor Green
git push hf main --force
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "--> Syncing LFS objects to Hugging Face..." -ForegroundColor Green
git lfs push hf main --all
if ($LASTEXITCODE -ne 0) { exit 1 }

# 5. Frontend Deployment (Optional if Vercel hook is active, but enforced here)
Write-Host "--> Triggering Vercel Production Build..." -ForegroundColor Green
vercel --prod --yes --cwd prime-frontend

# 6. Conclusion
Write-Host "`n--- Deployment Complete ---" -ForegroundColor Green
Write-Host "Verify Backend: https://aphira-abbey.hf.space/health" -ForegroundColor Blue
Write-Host "Verify Frontend: https://abbey-frontend.vercel.app" -ForegroundColor Blue
Write-Host "Back to 'dev' branch..."
git checkout dev
