param([string]$Database = "", [int]$Port = 8501)
$ErrorActionPreference = "Stop"
$taskPython = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw "Create audit/.venv and install audit/requirements.txt first. See audit/README.md."
}
$previousDatabase = $env:AUDIT_DB
try {
    if ($Database) { $env:AUDIT_DB = $Database }
    & $taskPython -m streamlit run (Join-Path $PSScriptRoot "app.py") --server.address 127.0.0.1 --server.port $Port --browser.gatherUsageStats false --theme.base light --theme.primaryColor '#196b55' --theme.backgroundColor '#fafbf9' --theme.secondaryBackgroundColor '#f0f3ef' --theme.textColor '#1b2926'
} finally {
    $env:AUDIT_DB = $previousDatabase
}
