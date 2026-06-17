<#
.SYNOPSIS
    Remove the Antares Output Visualizer Windows startup task.
#>
param(
    [string]$TaskName = "AntaresOutputVisualizer"
)

$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Task '$TaskName' does not exist."
    exit 0
}

try {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}
catch {
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Task '$TaskName' removed."
