param(
  [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "services/api"
$rnDir = Join-Path $repoRoot "app/AllworthCompanionRN"

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

Write-Host "==> Starting backend in a new PowerShell window"
Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $backendCmd) | Out-Null

Write-Host "==> Waiting for backend health"
$ok = $false
for ($i = 0; $i -lt 45; $i++) {
  try {
    $res = Invoke-WebRequest -Uri "http://localhost:3000/api/health" -UseBasicParsing -TimeoutSec 2
    if ($res.StatusCode -eq 200) {
      $ok = $true
      break
    }
  } catch {
    # Keep retrying while backend boots.
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
& npm run web
