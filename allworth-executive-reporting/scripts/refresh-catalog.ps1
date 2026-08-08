<#
.SYNOPSIS
  Rebuild the Data Catalog data from source repos (ThoughtSpot TML, schema_index,
  and the allworthsynapse notebooks). Intended to run on a schedule (e.g. weekly)
  or on demand.

.DESCRIPTION
  Pulls the latest from each source (when -Pull is set), then runs the catalog
  generator, which rewrites backend/catalog/data/*. Curated overlays under
  data/overlays/ are preserved.

  Cadence guidance: weekly is reasonable — the inputs are reference metadata that
  change infrequently, and generation is pure parsing (no Spark/compute cost).
  Wire this into an Azure DevOps pipeline / GitHub Actions cron, or a scheduled
  task, and publish the regenerated data/ to the dir the app reads (CATALOG_DATA_DIR),
  or commit it back to the app repo.

.PARAMETER TmlDir
  Path to the ThoughtSpot 'thoughtspot_tml_version_control' folder.

.PARAMETER SchemaIndex
  Path to schema_index.yaml (optional enrichment).

.PARAMETER SynapseDir
  Path to the allworthsynapse 'notebook' folder (business logic source).

.PARAMETER Pull
  If set, run 'git pull' in each source repo before generating.

.PARAMETER Publish
  If set, load the regenerated data into Synapse (meta.Data_Dictionary_*) via
  backend/catalog/sql_publish.py after generation.

.PARAMETER AuthMethod
  Auth mode for -Publish. Default 'AccessToken' acquires an AAD token via the
  Azure CLI ('az account get-access-token'). Other values (ServicePrincipal,
  SqlPassword, ActiveDirectoryInteractive) rely on the matching env vars.

.EXAMPLE
  .\scripts\refresh-catalog.ps1 -Pull

.EXAMPLE
  .\scripts\refresh-catalog.ps1 -Pull -Publish
#>
[CmdletBinding()]
param(
  [string]$TmlDir      = "$PSScriptRoot\..\..\tml\thoughtspot_tml_version_control",
  [string]$SchemaIndex = "$PSScriptRoot\..\..\schema_index.yaml",
  [string]$SynapseDir  = "$PSScriptRoot\..\..\az_dev_ops\allworthsynapse\notebook",
  [switch]$Pull,
  [switch]$Publish,
  [string]$AuthMethod  = "AccessToken"
)

$ErrorActionPreference = "Stop"
$backend = Resolve-Path "$PSScriptRoot\..\backend"
$python  = Join-Path $backend "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

function Pull-Repo([string]$startPath) {
  if (-not (Test-Path $startPath)) { return }
  $repo = (& git -C $startPath rev-parse --show-toplevel 2>$null)
  if ($LASTEXITCODE -eq 0 -and $repo) {
    Write-Host "git pull $repo"
    & git -C $repo pull --ff-only 2>&1 | Out-Host
  }
}

if ($Pull) {
  Pull-Repo $TmlDir
  Pull-Repo (Split-Path $SchemaIndex -Parent)
  Pull-Repo $SynapseDir
}

$env:CATALOG_TML_DIR      = (Resolve-Path $TmlDir).Path
if (Test-Path $SchemaIndex) { $env:CATALOG_SCHEMA_INDEX = (Resolve-Path $SchemaIndex).Path }
if (Test-Path $SynapseDir)  { $env:CATALOG_SYNAPSE_DIR  = (Resolve-Path $SynapseDir).Path }

Write-Host "Regenerating catalog data..."
Push-Location $backend
try {
  & $python "catalog\generate.py"
} finally {
  Pop-Location
}
Write-Host "Done. Review backend/catalog/data/ and commit or publish to CATALOG_DATA_DIR."

if ($Publish) {
  Write-Host "Publishing data dictionary to Synapse (meta.Data_Dictionary_*)..."
  $env:AUTH_METHOD = $AuthMethod
  if ($AuthMethod -eq "AccessToken" -and -not $env:AZURE_SQL_ACCESS_TOKEN) {
    Write-Host "Acquiring AAD SQL token via Azure CLI..."
    $env:AZURE_SQL_ACCESS_TOKEN = (& az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv)
    if (-not $env:AZURE_SQL_ACCESS_TOKEN) { throw "Failed to acquire AAD token (az account get-access-token)." }
  }
  Push-Location $backend
  try {
    & $python "-m" "catalog.sql_publish"
  } finally {
    Pop-Location
  }
  Write-Host "Published meta.Data_Dictionary_* to Synapse."

  # Re-apply the code-authored business content (wealth_mcp.domain.tables /
  # glossary) — sql_publish is a full replace, so the authored overlay must
  # follow it. Also refreshes the catalog overlay YAMLs.
  $wealthRoot = Resolve-Path "$PSScriptRoot\..\.."
  $wealthPython = Join-Path $wealthRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path $wealthPython)) { $wealthPython = "python" }
  if (Test-Path (Join-Path $wealthRoot "wealth_mcp\domain\tables.py")) {
    Write-Host "Re-applying code-authored dictionary content (wealth_mcp.domain)..."
    Push-Location $wealthRoot
    try {
      & $wealthPython "-m" "wealth_mcp.tools.admin.publish_dictionary" "--all"
    } finally {
      Pop-Location
    }
  }
}
