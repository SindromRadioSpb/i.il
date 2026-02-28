#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Creates the NewsHubEngineAutonomous Task Scheduler task.

.DESCRIPTION
    Registers a scheduled task that runs the local engine in daemon mode
    (python main.py --loop) at system startup and repeats every 15 minutes
    as a watchdog in case the process exits unexpectedly.

    Run this script once from an elevated PowerShell session:

        powershell -ExecutionPolicy Bypass -File .\create_task_scheduler_autonomous.ps1

.PARAMETER PythonPath
    Path to the Python executable. Defaults to C:\Python314\python.exe.

.PARAMETER EnginePath
    Path to the main.py file. Defaults to J:\Project_Vibe\i.il\apps\local-engine\main.py.

.PARAMETER WorkingDir
    Working directory for the task. Defaults to J:\Project_Vibe\i.il\apps\local-engine.

.PARAMETER TaskName
    Name of the scheduled task. Defaults to NewsHubEngineAutonomous.
#>

param(
    [string]$PythonPath  = "C:\Python314\python.exe",
    [string]$EnginePath  = "J:\Project_Vibe\i.il\apps\local-engine\main.py",
    [string]$WorkingDir  = "J:\Project_Vibe\i.il\apps\local-engine",
    [string]$TaskName    = "NewsHubEngineAutonomous"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Validate prerequisites ────────────────────────────────────────────────────

if (-not (Test-Path $PythonPath)) {
    Write-Error "Python not found at: $PythonPath`nSet -PythonPath to the correct path."
    exit 1
}

if (-not (Test-Path $EnginePath)) {
    Write-Error "main.py not found at: $EnginePath`nSet -EnginePath to the correct path."
    exit 1
}

if (-not (Test-Path $WorkingDir)) {
    Write-Error "Working directory not found: $WorkingDir"
    exit 1
}

$envFile = Join-Path $WorkingDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Warning ".env not found at $envFile`nMake sure to create it before the task runs."
}

# ── Remove existing task (idempotent) ─────────────────────────────────────────

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# ── Build task components ─────────────────────────────────────────────────────

$action = New-ScheduledTaskAction `
    -Execute  $PythonPath `
    -Argument "$EnginePath --loop" `
    -WorkingDirectory $WorkingDir

# Trigger 1: At system startup (with 2-minute delay to let services settle)
$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$triggerStartup.Delay = "PT2M"

# Trigger 2: Watchdog — repeat every 15 minutes indefinitely.
# This restarts the task if --loop exits for any reason.
$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$principal = New-ScheduledTaskPrincipal `
    -UserId    "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel  Highest

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit       (New-TimeSpan -Hours 12) `
    -MultipleInstances        IgnoreNew `
    -StartWhenAvailable       $true `
    -RunOnlyIfNetworkAvailable $false `
    -Compatibility            Win8

# ── Register task ─────────────────────────────────────────────────────────────

$task = Register-ScheduledTask `
    -TaskName   $TaskName `
    -Action     $action `
    -Trigger    @($triggerStartup, $triggerRepeat) `
    -Principal  $principal `
    -Settings   $settings `
    -Description "News Hub local engine: autonomous ingest + summary + FB posting loop"

Write-Host ""
Write-Host "Task registered successfully: $TaskName"
Write-Host "  Python:      $PythonPath"
Write-Host "  Script:      $EnginePath --loop"
Write-Host "  Working dir: $WorkingDir"
Write-Host ""
Write-Host "Triggers:"
Write-Host "  - At system startup (2-minute delay)"
Write-Host "  - Repeat every 15 minutes (watchdog)"
Write-Host ""
Write-Host "Settings:"
Write-Host "  - If already running: IgnoreNew (no duplicate instances)"
Write-Host "  - Max execution time: 12 hours"
Write-Host "  - Runs as: SYSTEM"
Write-Host ""

# ── Verify ────────────────────────────────────────────────────────────────────

$check = Get-ScheduledTask -TaskName $TaskName
Write-Host "Current state: $($check.State)"
Write-Host ""
Write-Host "To start the task immediately:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To verify it is running:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
Write-Host ""
Write-Host "To remove the task:"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
