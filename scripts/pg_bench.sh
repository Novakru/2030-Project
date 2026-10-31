#!/usr/bin/env bash
# ProcGraph benchmark on the 14 reference graphs. Usage: scripts/pg_bench.sh [out_dir]
set -euo pipefail
OUT=${1:-outputs/pg_bench}
python -m mosaic.pg ping
python -m mosaic.pg bench --gold evaluation/procgraph_gold --out "$OUT" --workers 4
echo "Report: $OUT/bench.md"
