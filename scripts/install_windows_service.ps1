<#
.SYNOPSIS
    Deploy Antares Output Visualizer as a Windows startup task (Scheduled Task).

.DESCRIPTION
    - Creates .venv if missing
    - Installs Python dependencies (optional corporate proxy for pip)
    - Registers a task that runs start_service.ps1 with the venv on boot

.EXAMPLE
    .\scripts\install_windows_service.ps1

.EXAMPLE
    .\scripts\install_windows_service.ps1 -ProxyUrl "http://USER:PASSWORD@proxy.example.com:8080" -Port 8050
#>
param(
    [string]$TaskName = "AntaresOutputVisualizer",
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8050,
    [string]$ProxyUrl = "",
    [string]$NoProxy = "localhost,127.0.0.1"
)

$ErrorActionPreference = "Stop"
$appPath = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $appPath "start_service.ps1"
$venvPath = Join-Path $appPath ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$requirementsFile = Join-Path $appPath "requirements.txt"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run PowerShell as Administrator."
    }
}

function Ensure-Venv {
    if (Test-Path $venvPython) {
        return
    }

    Write-Host "[deploy] Creating virtual environment at $venvPath ..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            & py -3 -m venv $venvPath
        }
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvPath
    }
    else {
        throw "Neither 'py' nor 'python' found in PATH."
    }

    if (-not (Test-Path $venvPython)) {
        throw "Failed to create venv at $venvPath"
    }
}

function Install-Dependencies {
    Write-Host "[deploy] Installing dependencies from requirements.txt ..."

    $pipUpgradeArgs = @("-m", "pip", "install", "--upgrade", "pip")
    $pipInstallArgs = @("-m", "pip", "install", "-r", $requirementsFile)

    if ($ProxyUrl -and $ProxyUrl.Trim()) {
        Write-Host "[deploy] Using proxy for pip: $ProxyUrl"
        $env:HTTP_PROXY = $ProxyUrl
        $env:HTTPS_PROXY = $ProxyUrl
        $env:NO_PROXY = $NoProxy
        $pipUpgradeArgs += @("--proxy", $ProxyUrl)
        $pipInstallArgs += @("--proxy", $ProxyUrl)
    }

    & $venvPython @pipUpgradeArgs
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }

    & $venvPython @pipInstallArgs
    if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }
}

function Register-ServiceTask {
    if (-not (Test-Path $startScript)) {
        throw "Missing start script: $startScript"
    }

    Write-Host "[deploy] Registering scheduled task '$TaskName' ..."

    $psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -AppPath `"$appPath`" -BindHost `"$BindHost`" -Port $Port"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $appPath
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 3650)
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Autostart task for Antares Output Visualizer (Waitress)" `
        -Force | Out-Null

    Start-ScheduledTask -TaskName $TaskName
}

Assert-Admin
Ensure-Venv
Install-Dependencies
Register-ServiceTask

Write-Host ""
Write-Host "Deployment complete."
Write-Host "Task name : $TaskName"
Write-Host "Listen on : http://${BindHost}:$Port"
Write-Host "Logs      : $appPath\logs\"
if ($ProxyUrl -and $ProxyUrl.Trim()) {
    Write-Host "Proxy     : used for pip during this install only"
}
