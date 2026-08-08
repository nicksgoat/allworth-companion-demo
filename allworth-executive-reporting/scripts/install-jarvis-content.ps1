<#
.SYNOPSIS
  Populate backend/jarvis/knowledge/ + backend/jarvis/static/ with YAMLs and
  the Allworth logo copied from SynapseMCP.

.DESCRIPTION
  The jarvis Blueprint code lives in this repo, but the content (the ~45
  framework YAMLs + the logo PNG) lives in SynapseMCP. This script copies
  those assets in so the Flask app has something to serve.

  Run this once after cloning the repo, and whenever SynapseMCP's framework
  content changes and you want to re-sync.

.PARAMETER Source
  Path to the SynapseMCP repo root. Default: C:\Users\NicholasMcKenzie\SynapseMCP.

.EXAMPLE
  .\scripts\install-jarvis-content.ps1

.EXAMPLE
  .\scripts\install-jarvis-content.ps1 -Source D:\repos\SynapseMCP
#>

param(
  [string]$Source = "C:\Users\NicholasMcKenzie\SynapseMCP"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item -Path .).FullName

$SrcYamls = Join-Path $Source "wealth_mcp\context\frameworks"
$SrcLogo  = Join-Path $Source "wealth_mcp\tools\tooling\reports\logo.png"

$DstYamls = Join-Path $RepoRoot "backend\jarvis\knowledge"
$DstLogo  = Join-Path $RepoRoot "backend\jarvis\static\logo.png"

if (-not (Test-Path $SrcYamls)) { throw "YAML source not found: $SrcYamls. Pass -Source <path-to-SynapseMCP>." }
if (-not (Test-Path $SrcLogo))  { throw "Logo source not found: $SrcLogo." }

Write-Host ""
Write-Host "=== Installing Jarvis content ===" -ForegroundColor Cyan
Write-Host "  From: $Source"
Write-Host "  Into: $RepoRoot\backend\jarvis"
Write-Host ""

# YAMLs
if (-not (Test-Path $DstYamls)) { New-Item -ItemType Directory -Path $DstYamls | Out-Null }
$yamlCount = 0
Get-ChildItem -Path $SrcYamls -Filter "*.yaml" | ForEach-Object {
  Copy-Item -Path $_.FullName -Destination (Join-Path $DstYamls $_.Name) -Force
  $yamlCount++
}
Write-Host "  Copied $yamlCount YAML files." -ForegroundColor Green

# Also pull history log if one exists on the source side
$SrcHist = Join-Path $SrcYamls ".jarvis-history"
if (Test-Path $SrcHist) {
  $DstHist = Join-Path $DstYamls ".jarvis-history"
  if (-not (Test-Path $DstHist)) { New-Item -ItemType Directory -Path $DstHist | Out-Null }
  Copy-Item -Path (Join-Path $SrcHist "*") -Destination $DstHist -Recurse -Force
  Write-Host "  Copied existing .jarvis-history/." -ForegroundColor Green
}

# Logo
$LogoDir = Split-Path $DstLogo -Parent
if (-not (Test-Path $LogoDir)) { New-Item -ItemType Directory -Path $LogoDir | Out-Null }
Copy-Item -Path $SrcLogo -Destination $DstLogo -Force
Write-Host "  Copied logo.png." -ForegroundColor Green

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. pip install -r backend\requirements.txt  # picks up pyyaml + markdown"
Write-Host "  2. cd backend && python app.py               # Flask dev server on :5000"
Write-Host "  3. Open http://localhost:5000/jarvis/        # confirm the page loads"
Write-Host ""
Write-Host "For full-stack local testing with nginx:" -ForegroundColor Yellow
Write-Host "  docker-compose up --build"
Write-Host "  Open http://localhost/jarvis/"
