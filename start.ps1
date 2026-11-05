$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Host 'Create a local environment first: py -m venv .venv'
    Write-Host 'Then install dependencies: .venv/Scripts/python.exe -m pip install -r requirements.txt'
    exit 1
}
& $taskPython run.py
