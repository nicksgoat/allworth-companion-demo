# Launch the Flask backend wired to live Synapse using the planning-owned schema.
# Reads SYNAPSE_* creds from the workspace .env and maps them to the planning
# module's DW_* settings. All writes go to SYNAPSE_PLANNING_SCHEMA only.
param(
    [string]$EnvFile = "C:\Users\NicholasMcKenzie\SynapseMCP\.env",
    [string]$Python = "C:\Users\NicholasMcKenzie\SynapseMCP\.venv\Scripts\python.exe"
)

Set-Location $PSScriptRoot\..

Get-Content $EnvFile | Where-Object { $_ -match '^\s*[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim().Trim("'").Trim('"'), 'Process')
}

$env:DW_SERVER = $env:SYNAPSE_SERVER
$env:DW_DATABASE = $env:SYNAPSE_DATABASE
$env:DW_USER = $env:SYNAPSE_USERNAME
$env:DW_PW = $env:SYNAPSE_PASSWORD
$env:DW_PORT = '1433'
$env:AUTH_METHOD = 'SqlPassword'
$env:SYNAPSE_PLANNING_ENABLED = 'true'
$env:SYNAPSE_PLANNING_SCHEMA = 'planengine'
$env:AUTH_FIRM_ID = 'allworth'
$env:AUTH_DISABLE = '1'
$env:PYTHONIOENCODING = 'utf-8'

& $Python run_local.py
