# ProcGraph benchmark on the 14 reference graphs. Usage: ./scripts/pg_bench.ps1 [-Out outputs/pg_bench]
param([string]$Out = "outputs/pg_bench", [int]$Workers = 4)
$py = if (Test-Path ./.venv/Scripts/python.exe) { "./.venv/Scripts/python.exe" } else { "python" }
& $py -m mosaic.pg ping
if ($LASTEXITCODE -ne 0) { exit 1 }
& $py -m mosaic.pg bench --gold evaluation/procgraph_gold --out $Out --workers $Workers
Write-Host "Report: $Out/bench.md"
