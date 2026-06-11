param(
  [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "services/api"
$rnDir = Join-Path $repoRoot "app/AllworthCompanionRN"

function Test-BackendHealth {
  try {
    $res = Invoke-WebRequest -Uri "http://localhost:3000/api/health" -UseBasicParsing -TimeoutSec 2
    return $res.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found on PATH."
  }
}

Write-Host "==> Checking prerequisites"
Require-Command uv
Require-Command npm

Write-Host "==> Installing/syncing backend dependencies"
& uv --project $apiDir sync

Write-Host "==> Installing frontend dependencies"
& npm --prefix $rnDir install --no-audit --no-fund

if ($InstallOnly) {
  Write-Host "Install complete. Skipping process start because -InstallOnly was specified."
  exit 0
}

$backendCmd = "uv --project `"$apiDir`" run --directory `"$apiDir`" python -m uvicorn main:app --host 0.0.0.0 --port 3000"

if (Test-BackendHealth) {
  Write-Host "==> Backend already healthy on :3000, reusing existing process"
} else {
  Write-Host "==> Starting backend in a new PowerShell window"
  Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $backendCmd) | Out-Null
}

Write-Host "==> Waiting for backend health"
$ok = $false
for ($i = 0; $i -lt 45; $i++) {
  if (Test-BackendHealth) {
    $ok = $true
    break
  }
  if (($i + 1) % 10 -eq 0) {
    Write-Host "...still waiting for backend health ($($i + 1)/45)"
  }
  Start-Sleep -Milliseconds 500
}

if (-not $ok) {
  throw "Backend did not become healthy at http://localhost:3000/api/health"
}

Write-Host "==> Starting web app (Expo)"
Write-Host "Backend: http://localhost:3000"
Write-Host "Web: http://localhost:8081"

Set-Location $rnDir
# Prevent Expo from resolving modules from workspace root (which can pull a stale Expo install).
$env:EXPO_NO_METRO_WORKSPACE_ROOT = "1"

# Use the app-local Expo CLI directly to avoid global/root resolution drift.
& node .\node_modules\expo\bin\cli start --web --clear
