param(
    [string]$RunDir = '',
    [switch]$Fetch,
    [switch]$Offline,
    [switch]$Publish,
    [string]$Database = 'audit/data/text_reviews.sqlite3',
    [int]$Positives = 100,
    [int]$PerRisk = 10,
    [int]$SourceLimit = 300,
    [int]$MaxCalls = 1600
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install requirements.lock.txt first.' }
$env:PYTHONPATH = Join-Path $taskRoot 'src'
$env:PYTHONIOENCODING = 'utf-8'
if ($Offline -and -not $RunDir) { throw 'Offline replay requires -RunDir; structured reconstruction is disabled.' }
function Invoke-Python([string[]]$Arguments) {
    $taskPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $taskPython @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { $_ }
        }
        $taskExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $taskPreference }
    if ($taskExitCode -ne 0) { throw "Python command failed: $($Arguments -join ' ')" }
}
if ($RunDir) {
    $taskArguments = @('-m', 'mosaic', 'resume', $RunDir)
    if ($Offline) { $taskArguments += '--offline' }
    Invoke-Python -Arguments $taskArguments
} else {
    if ($Fetch) { Invoke-Python -Arguments @('-m', 'protocol_risk', 'fetch') }
    if (-not (Test-Path -LiteralPath 'data/raw/reactions.parquet')) {
        Invoke-Python -Arguments @('-m', 'protocol_risk', 'ingest')
    }
    $taskArguments = @('-m','mosaic','run','--positives',"$Positives",'--per-risk',"$PerRisk")
    Invoke-Python -Arguments @('-m','protocol_risk','api-check')
    $taskArguments += @('--source-limit',"$SourceLimit",'--llm-perturbations','6','--max-calls',"$MaxCalls",
                        '--model','extractor=gpt-6.1-sol','--model','critic=gpt-6.1-sol',
                        '--model','library_curator=gpt-6.1-sol','--workers','6')
    Invoke-Python -Arguments $taskArguments
    $taskCurrent = Get-Content -LiteralPath 'data/mosaic/current.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $RunDir = Join-Path 'data/mosaic' $taskCurrent.run_id
}
Invoke-Python -Arguments @('-m','mosaic','verify',$RunDir)
if ($Publish) { Invoke-Python -Arguments @('-m','mosaic','publish',$RunDir,'--db',$Database) }
