param(
    [Parameter(Mandatory = $true)][string[]]$InputPaths,
    [string]$OutputDirectory = "outputs",
    [int]$MaxCalls = 0
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install requirements.lock.txt first.' }
$taskPreviousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $taskRoot 'src'
    $taskBudget = @()
    if ($MaxCalls -gt 0) { $taskBudget = @('--max-calls', $MaxCalls) }
    & $taskPython -m mosaic extract @InputPaths --output-dir $OutputDirectory @taskBudget
    if ($LASTEXITCODE -ne 0) { throw 'Conversion did not complete for all inputs; inspect failures.jsonl.' }
} finally { $env:PYTHONPATH = $taskPreviousPythonPath }
