param(
  [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "backend"
$rnDir = Join-Path $repoRoot "frontend"

function Test-BackendHealth {
  try {
    $res = Invoke-WebRequest -Uri "http://localhost:3000/api/health" -UseBasicParsing -TimeoutSec 2
    return $res.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Test-PortOpen([int]$Port) {
  try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(1500, $false)
    if (-not $ok) {
      $tcp.Close()
      return $false
    }
    $tcp.EndConnect($iar) | Out-Null
    $tcp.Close()
    return $true
  } catch {
    return $false
  }
}

function Get-ListeningPidsOnPort([int]$Port) {
  return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-ListeningPidsOnPort([int]$Port) {
  $pids = Get-ListeningPidsOnPort -Port $Port
  foreach ($owningPid in $pids) {
    try {
      Stop-Process -Id $owningPid -Force -ErrorAction Stop
      Write-Host "==> Stopped stale process PID $owningPid on port $Port"
    } catch {
      Write-Host "==> Could not stop PID $owningPid on port ${Port}: $($_.Exception.Message)"
    }
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

$uvExe = (Get-Command uv -ErrorAction Stop).Source

Write-Host "==> Installing/syncing backend dependencies"
& uv --project $apiDir sync

Write-Host "==> Installing frontend dependencies"
& npm --prefix $rnDir install --no-audit --no-fund

if ($InstallOnly) {
  Write-Host "Install complete. Skipping process start because -InstallOnly was specified."
  exit 0
}

$logDir = Join-Path $repoRoot ".codex-run"
if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir | Out-Null
}
$backendOutLog = Join-Path $logDir "backend.out.log"
$backendErrLog = Join-Path $logDir "backend.err.log"

if (Test-BackendHealth) {
  Write-Host "==> Backend already healthy on :3000, reusing existing process"
} else {
  $preExisting = Get-ListeningPidsOnPort -Port 3000
  if ($preExisting.Count -gt 0) {
    Write-Host "==> Port 3000 is busy but backend health is down; cleaning stale listener(s)"
    Stop-ListeningPidsOnPort -Port 3000
    Start-Sleep -Milliseconds 500
  }

  Write-Host "==> Starting backend"
  Remove-Item $backendOutLog, $backendErrLog -Force -ErrorAction SilentlyContinue
  $backendProc = Start-Process -FilePath $uvExe `
    -ArgumentList @(
      "--project", $apiDir,
      "run",
      "--directory", $apiDir,
      "python", "-m", "uvicorn", "main:app",
      "--host", "0.0.0.0",
      "--port", "3000"
    ) `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOutLog `
    -RedirectStandardError $backendErrLog
  Write-Host "==> Backend PID: $($backendProc.Id)"
}

Write-Host "==> Waiting for backend health"
$ok = $false
for ($i = 0; $i -lt 120; $i++) {
  if ((Test-BackendHealth) -or (Test-PortOpen -Port 3000)) {
    $ok = $true
    break
  }
  if ($backendProc -and $backendProc.HasExited) {
    break
  }
  if (($i + 1) % 10 -eq 0) {
    Write-Host "...still waiting for backend health ($($i + 1)/120)"
  }
  Start-Sleep -Milliseconds 500
}

if (-not $ok) {
  $uvicornReadyInLog = $false
  if (Test-Path $backendErrLog) {
    $uvicornReadyInLog = [bool](Select-String -Path $backendErrLog -Pattern "Uvicorn running on http://0.0.0.0:3000" -Quiet)
  }

  if ((Get-ListeningPidsOnPort -Port 3000).Count -gt 0 -and $uvicornReadyInLog) {
    Write-Host "==> Backend reported ready in logs and port 3000 is listening; proceeding."
    $ok = $true
  }
}

if (-not $ok) {
  if (Get-ListeningPidsOnPort -Port 3000) {
    Write-Host "==> Port 3000 is still occupied. Try running this once, then retry:"
    Write-Host "    Get-NetTCPConnection -LocalPort 3000 -State Listen | Select-Object -Expand OwningProcess | %{ Stop-Process -Id `$_ -Force }"
  }
  if (Test-Path $backendErrLog) {
    Write-Host "==> Backend stderr (last 40 lines):"
    Get-Content $backendErrLog -Tail 40
  }
  if (Test-Path $backendOutLog) {
    Write-Host "==> Backend stdout (last 40 lines):"
    Get-Content $backendOutLog -Tail 40
  }
  throw "Backend did not become healthy at http://localhost:3000/api/health"
}

Write-Host "==> Backend is reachable on :3000"

Write-Host "==> Starting web app (Expo)"
Write-Host "Backend: http://localhost:3000"
Write-Host "Web: http://localhost:8081"

$webListeners = @(Get-ListeningPidsOnPort -Port 8081) + @(Get-ListeningPidsOnPort -Port 8082)
if ($webListeners.Count -gt 0) {
  Write-Host "==> Clearing stale web listener(s) on 8081/8082"
  Stop-ListeningPidsOnPort -Port 8081
  Stop-ListeningPidsOnPort -Port 8082
}

Set-Location $rnDir
# Prevent Expo from resolving modules from workspace root (which can pull a stale Expo install).
$env:EXPO_NO_METRO_WORKSPACE_ROOT = "1"

# Use the app-local Expo CLI directly to avoid global/root resolution drift.
& node .\node_modules\expo\bin\cli start --web --clear
