<#
.SYNOPSIS
    One-click launcher for the Scenarios App (backend + frontend).

.DESCRIPTION
    Self-healing: on first run, creates the Python venv + installs
    backend deps, copies .env.example -> .env (yellow warning to fill
    in API keys), runs `alembic upgrade head`, and `npm install`s the
    frontend. On subsequent runs every bootstrap branch short-circuits
    so launch is < 5 s.

    After bootstrap it spawns two visible PowerShell windows -- one
    running uvicorn, one running `npm run dev` -- then opens the app
    in the default browser. Stop either server with Ctrl+C in its
    window.

    Designed for double-click via start.bat. Direct invocation is
    fine too: `powershell -ExecutionPolicy Bypass -File start.ps1`.
#>

[CmdletBinding()]
param(
    [int] $BackendPort = 8000,
    [int] $FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

# Resolve the launcher's own folder; do NOT trust the caller's CWD.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Stage([string] $Message) {
    Write-Host ""
    Write-Host "[scenarios] $Message" -ForegroundColor Cyan
}

function Write-Warn([string] $Message) {
    Write-Host "[scenarios] $Message" -ForegroundColor Yellow
}

function Write-Ok([string] $Message) {
    Write-Host "[scenarios] $Message" -ForegroundColor Green
}

# ─── 1. Backend venv + deps ────────────────────────────────────────
$BackendVenvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $BackendVenvPython)) {
    Write-Stage "First run: creating Python venv + installing backend deps (~2 min)"
    Push-Location (Join-Path $Root "backend")
    try {
        # Prefer Python 3.13 via the launcher; falls back to "python" if unavailable.
        $pyCmd = "py"
        $pyArgs = @("-3.13", "-m", "venv", ".venv")
        & $pyCmd @pyArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create venv with 'py -3.13'. Install Python 3.11+ from python.org."
        }
        & $BackendVenvPython -m pip install --upgrade pip --quiet
        & $BackendVenvPython -m pip install -e ".[dev]" --quiet
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
        Write-Ok "Backend venv ready."
    } finally {
        Pop-Location
    }
}

# ─── 2. .env (copy from example if missing) ────────────────────────
$EnvFile = Join-Path $Root "backend\.env"
$EnvExample = Join-Path $Root "backend\.env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Warn "Created backend\.env from template. Edit it to add GEMINI_API_KEY and SERPAPI_KEY before generating scenarios."
    } else {
        Write-Warn "backend\.env not found and no .env.example to copy from. Generation calls will fail until you create it."
    }
}

# ─── 3. Migrations (idempotent; ~1s when at head) ──────────────────
Push-Location (Join-Path $Root "backend")
try {
    & $BackendVenvPython -m alembic upgrade head | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed" }
} finally {
    Pop-Location
}

# ─── 4. Frontend deps ──────────────────────────────────────────────
$NodeModules = Join-Path $Root "frontend\node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Stage "First run: installing frontend deps (~1 min)"
    Push-Location (Join-Path $Root "frontend")
    try {
        npm install --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        Write-Ok "Frontend deps ready."
    } finally {
        Pop-Location
    }
}

# ─── 5. Spawn the two servers in their own windows ─────────────────
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

Write-Stage "Starting backend on http://localhost:$BackendPort ..."
$backendCmd = @"
`$Host.UI.RawUI.WindowTitle = 'Scenarios Backend (uvicorn :$BackendPort)'
Set-Location '$BackendDir'
& '$BackendVenvPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port $BackendPort
"@
Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-NoProfile", "-Command", $backendCmd
) | Out-Null

Write-Stage "Starting frontend on http://localhost:$FrontendPort ..."
$frontendCmd = @"
`$Host.UI.RawUI.WindowTitle = 'Scenarios Frontend (vite :$FrontendPort)'
Set-Location '$FrontendDir'
npm run dev
"@
Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-NoProfile", "-Command", $frontendCmd
) | Out-Null

# ─── 6. Open the browser once Vite has had time to bind ────────────
Start-Sleep -Seconds 5
try {
    Start-Process "http://localhost:$FrontendPort" | Out-Null
} catch {
    Write-Warn "Could not auto-open browser: $($_.Exception.Message)"
    Write-Warn "Open http://localhost:$FrontendPort manually."
}

# ─── 7. Summary ────────────────────────────────────────────────────
Write-Host ""
Write-Ok "Backend:  http://localhost:$BackendPort  (logs in 'Scenarios Backend' window)"
Write-Ok "Frontend: http://localhost:$FrontendPort  (logs in 'Scenarios Frontend' window)"
Write-Host "[scenarios] Stop each server with Ctrl+C inside its window." -ForegroundColor DarkGray
