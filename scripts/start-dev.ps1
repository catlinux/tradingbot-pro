# PowerShell script to start the development watcher and activate venv
param(
    [string]$Cmd = "python main.py"
)

Set-StrictMode -Version Latest

$venv = Join-Path $PSScriptRoot "..\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) {
    Write-Host "Activating virtualenv..."
    . $venv
} else {
    Write-Warning "No virtualenv activation script found at $venv. Ensure your environment is activated." -WarningAction Continue
}

Write-Host "Starting watcher (command: $Cmd)"
python -u "scripts/watcher_restart.py" --cmd $Cmd --paths . core web utils config data
