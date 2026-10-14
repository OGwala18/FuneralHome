# Start the whole Induduzo stack: database, API, website.
#
#   .\start.ps1          start everything
#   .\start.ps1 -Stop    stop everything
#
# From Command Prompt (not PowerShell) use start.cmd instead — cmd.exe cannot
# execute a .ps1 directly and will just open it in Notepad.
#
# Requires Docker Desktop to be running.

param([switch]$Stop)

# NOT "Stop". Windows PowerShell 5.1 turns any native-command stderr output into
# a terminating error under that setting, and `docker compose` writes all of its
# progress ("Container X Starting") to stderr — so the script would die on a
# perfectly successful command. Native failures are detected via $LASTEXITCODE
# in Invoke-Docker instead.
$ErrorActionPreference = "Continue"

$root = $PSScriptRoot

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Bad($text)  { Write-Host $text -ForegroundColor Red }

# Docker is invoked directly rather than through a wrapper function. A
# PowerShell function with ValueFromRemainingArguments SILENTLY SWALLOWS the
# `-d` flag — the binder treats it as a parameter name, not a value — so
# `docker compose up -d` became `docker compose up`, which runs attached and
# never returns. The script appeared to hang with the containers already healthy.

function Stop-OnPort($port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

# --- Stop ------------------------------------------------------------------
if ($Stop) {
    Write-Step "Stopping website, portal and API"
    Stop-OnPort 8000
    Stop-OnPort 8080
    Stop-OnPort 8090

    Write-Step "Stopping containers"
    Push-Location $root
    & docker compose down | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Bad "docker compose down failed (exit $LASTEXITCODE)" }
    Pop-Location

    Write-Host "`nAll stopped. Your data is preserved in the induduzo_pgdata volume." -ForegroundColor Green
    return
}

# --- Preflight -------------------------------------------------------------
& docker info --format "{{.ServerVersion}}" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Bad "`nDocker Desktop is not running. Start it, wait for the whale icon to settle, then run this again."
    exit 1
}

# --- 1. Database -----------------------------------------------------------
Write-Step "Starting database (Postgres on 5433), Adminer and pgAdmin"
Push-Location $root
& docker compose up -d db adminer pgadmin | Out-Null
$composeExit = $LASTEXITCODE
Pop-Location
if ($composeExit -ne 0) {
    Write-Bad "docker compose up failed (exit $composeExit). Check:  docker compose logs"
    exit 1
}

Write-Host "    waiting for the database to report healthy..." -NoNewline
$state = ""
for ($i = 0; $i -lt 30; $i++) {
    $state = (& docker inspect -f "{{.State.Health.Status}}" induduzo-db 2>$null)
    if ($state -eq "healthy") { break }
    Start-Sleep -Seconds 2
    Write-Host "." -NoNewline
}
if ($state -ne "healthy") {
    Write-Host ""
    Write-Bad "Database did not become healthy. Check:  docker compose logs db"
    exit 1
}
Write-Host " healthy" -ForegroundColor Green

# --- 2. API ----------------------------------------------------------------
Write-Step "Starting API (FastAPI on 8000)"
Stop-OnPort 8000

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Bad "Backend venv missing at $python"
    Write-Bad "It must be built against Python 3.12 (pydantic-core has no 3.14 wheel). See README."
    exit 1
}

$logDir = Join-Path $root "backend\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory (Join-Path $root "backend") `
    -RedirectStandardOutput (Join-Path $logDir "api.log") `
    -RedirectStandardError  (Join-Path $logDir "api.err.log") `
    -WindowStyle Hidden

Write-Host "    waiting for the API..." -NoNewline
$health = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        if ($health.status -eq "ok") { break }
    } catch { Write-Host "." -NoNewline }
}
if (-not $health -or $health.status -ne "ok") {
    Write-Host ""
    Write-Bad "API did not come up. Check:  backend\logs\api.err.log"
    exit 1
}
Write-Host " ok (database: $($health.database), whatsapp: $($health.whatsapp))" -ForegroundColor Green

# --- 3. Website ------------------------------------------------------------
Write-Step "Starting website (Vite on 8080)"
Stop-OnPort 8080

Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory (Join-Path $root "frontend") `
    -WindowStyle Hidden

Write-Host "    waiting for Vite..." -NoNewline
$siteUp = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 2 -UseBasicParsing | Out-Null
        $siteUp = $true; break
    } catch { Write-Host "." -NoNewline }
}
if (-not $siteUp) {
    Write-Host ""
    Write-Bad "Website did not come up. Try running it directly:  npm --prefix frontend run dev"
    exit 1
}
Write-Host " ok" -ForegroundColor Green

# --- 4. Staff portal -------------------------------------------------------
# Deployed separately from the public site so no admin code ships in the public
# bundle. Skipped if dependencies have not been installed.
if (Test-Path (Join-Path $root "portal\node_modules")) {
    Write-Step "Starting staff portal (Vite on 8090)"
    Stop-OnPort 8090

    Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory (Join-Path $root "portal") `
        -WindowStyle Hidden

    Write-Host "    waiting for the portal..." -NoNewline
    $portalUp = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:8090" -TimeoutSec 2 -UseBasicParsing | Out-Null
            $portalUp = $true; break
        } catch { Write-Host "." -NoNewline }
    }
    if ($portalUp) { Write-Host " ok" -ForegroundColor Green }
    else { Write-Host ""; Write-Bad "Portal did not start. Try:  npm --prefix portal run dev" }
} else {
    Write-Step "Staff portal not installed (skipping)"
    Write-Host "    run:  npm --prefix portal install" -ForegroundColor Yellow
}

Write-Host @"

Everything is up.

  Website      http://localhost:8080
  Register     http://localhost:8080/register
  Staff portal http://localhost:8090
  API docs     http://localhost:8000/docs
  API health   http://localhost:8000/health

  Data:
  pgAdmin     http://localhost:8082   ERD diagrams + query tool + live data
              "Induduzo (local)" connects on its own, no password needed.
              ERD: right-click the 'induduzo' database -> ERD For Database
              (local dev password, if ever asked: induduzo_local_dev)
  Adminer     http://localhost:8081   quick peeks, no login
              server: db  user: induduzo  password: induduzo_local_dev  db: induduzo

  Stop it all with:  .\start.ps1 -Stop      (PowerShell)
                     induduzo.cmd -Stop     (Command Prompt)

"@ -ForegroundColor Green
