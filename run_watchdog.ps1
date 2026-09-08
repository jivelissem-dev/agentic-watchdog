<#
.SYNOPSIS
    Entry point for running the Agentic Watchdog on Windows, meant to be
    called manually or registered as a Windows Task Scheduler action.

.DESCRIPTION
    - Creates a venv on first run if one doesn't exist
    - Installs/updates dependencies
    - Runs watchdog.py
    - Appends a timestamped log to logs\watchdog_run_<date>.log
    - Exits with watchdog.py's exit code, so Task Scheduler can flag
      failed runs (exit code 1 = escalated)
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$VenvPath = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    Write-Host "No venv found -- creating one at $VenvPath"
    python -m venv $VenvPath
}

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$PipExe    = Join-Path $VenvPath "Scripts\pip.exe"

& $PipExe install -r (Join-Path $ProjectRoot "requirements.txt") --quiet

$LogDir  = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("watchdog_run_{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

Write-Host "Running watchdog... (full log: $LogFile)"
& $PythonExe (Join-Path $ProjectRoot "watchdog.py") *>> $LogFile
$ExitCode = $LASTEXITCODE

Get-Content $LogFile -Tail 20

if ($ExitCode -ne 0) {
    Write-Host "Watchdog run ESCALATED. See $LogFile and logs\escalations.log" -ForegroundColor Red
} else {
    Write-Host "Watchdog run completed successfully." -ForegroundColor Green
}

exit $ExitCode
