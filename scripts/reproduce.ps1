param([switch]$Fetch, [switch]$RefreshExtraction, [switch]$Train, [int]$Limit = 140)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $taskRoot 'src'
$env:PYTHONIOENCODING = 'utf-8'
function Invoke-Python([string[]]$Arguments) {
    # Windows PowerShell treats native stderr as an ErrorRecord. The process exit
    # code is authoritative; ordinary stderr diagnostics must not abort the script.
    $taskSavedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $taskPython @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { $_ }
        }
        $taskExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $taskSavedPreference
    }
    if ($taskExitCode -ne 0) { throw "Python command failed with exit code $taskExitCode" }
}
Invoke-Python -Arguments @('-m', 'pip', '--disable-pip-version-check', 'install', '-r', 'requirements.lock.txt')
if (Test-Path -LiteralPath 'data\platform_sources.lock.json') {
    Invoke-Python -Arguments @('-m', 'pip', '--disable-pip-version-check', 'install', '--no-index', '-r', 'requirements-platform.lock.txt')
}
function Invoke-Protocol([string[]]$Arguments) {
    Invoke-Python -Arguments (@('-m', 'protocol_risk') + $Arguments)
}
if ($Fetch) { Invoke-Protocol -Arguments @('fetch') }
if (-not (Test-Path -LiteralPath 'data\raw\reactions.parquet')) { Invoke-Protocol -Arguments @('ingest') }
if ($RefreshExtraction) {
    Invoke-Protocol -Arguments @('api-check')
    Invoke-Protocol -Arguments @('extract', '--limit', '200', '--workers', '4')
}
Invoke-Protocol -Arguments @('build', '--limit', "$Limit", '--per-risk', '12')
Invoke-Protocol -Arguments @('scan-amounts')
if (Test-Path -LiteralPath 'data\publications\members.lock.json') {
    Invoke-Protocol -Arguments @('prepare-publications')
    Invoke-Protocol -Arguments @('audit-publications')
    Invoke-Protocol -Arguments @('build-native-negatives')
    Invoke-Protocol -Arguments @('audit-native-negatives')
    if (Test-Path -LiteralPath 'data\platform_sources.lock.json') {
        Invoke-Protocol -Arguments @('validate-native-platform')
        Invoke-Protocol -Arguments @('audit-native-platform')
    }
}
if (Test-Path -LiteralPath 'data\sop_sources.lock.json') {
    Invoke-Protocol -Arguments @('build-sop')
}
Invoke-Protocol -Arguments @('audit')
if ($Train) { Invoke-Protocol -Arguments @('train') }
if ($Train -or (Test-Path -LiteralPath 'data\hte\contrasts.jsonl')) {
    Invoke-Protocol -Arguments @('hte-contrasts')
    Invoke-Protocol -Arguments @('audit-contrasts')
}
Invoke-Protocol -Arguments @('report')
Invoke-Python -Arguments @('-m', 'pytest', '-q')
