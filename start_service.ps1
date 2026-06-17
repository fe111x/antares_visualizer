<#
.SYNOPSIS
    Start the Antares Output Visualizer with Waitress (production WSGI server).

.DESCRIPTION
    Uses the project virtual environment directly (no manual Activate.ps1 required).
    Intended to be called from a Windows Scheduled Task via install_windows_service.ps1.
#>
param(
    [string]$AppPath = "",
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8050
)

$ErrorActionPreference = "Stop"

if (-not $AppPath -or -not (Test-Path $AppPath)) {
    $AppPath = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$venvPython = Join-Path $AppPath ".venv\Scripts\python.exe"
$venvWaitress = Join-Path $AppPath ".venv\Scripts\waitress-serve.exe"
$logDir = Join-Path $AppPath "logs"
$stdoutLog = Join-Path $logDir "dashboard.out.log"
$stderrLog = Join-Path $logDir "dashboard.err.log"
$serviceLog = Join-Path $logDir "service.log"

function Write-ServiceLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $serviceLog -Value $line
}

if (-not (Test-Path $venvPython)) {
    Write-ServiceLog "ERROR: Python venv not found at $venvPython. Run scripts\install_windows_service.ps1 first."
    exit 1
}

if (-not (Test-Path $venvWaitress)) {
    Write-ServiceLog "ERROR: waitress-serve not found at $venvWaitress. Re-run install_windows_service.ps1."
    exit 1
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $AppPath

$env:HOST = $BindHost
$env:PORT = "$Port"
$env:POLARS_SKIP_CPU_CHECK = "1"

$configPath = Join-Path $AppPath "visualizer_config.yaml"
if ((Test-Path $configPath) -and -not $env:VISUALIZER_CONFIG) {
    $env:VISUALIZER_CONFIG = $configPath
}

$listen = "{0}:{1}" -f $BindHost, $Port
Write-ServiceLog "Starting waitress on $listen (cwd: $AppPath)"

$waitressArgs = @(
    "--listen=$listen",
    "dashboard_app:app.server"
)

try {
    Start-Process `
        -FilePath $venvWaitress `
        -ArgumentList $waitressArgs `
        -WorkingDirectory $AppPath `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -NoNewWindow `
        -Wait
}
catch {
    Write-ServiceLog "ERROR: $($_.Exception.Message)"
    exit 1
}

Write-ServiceLog "Waitress process exited."
