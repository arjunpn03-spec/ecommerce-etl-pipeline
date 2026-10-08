#!/usr/bin/env bash
# One-command pipeline: generate raw data -> ETL + quality checks -> SQL queries.
# Every step is timestamped in logs/. Exits non-zero if any step (or quality check) fails.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
LOG="logs/pipeline_$(date +%Y%m%d_%H%M%S).log"
PY="${PYTHON:-python3}"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "START pipeline"
log "Step 1/3: generate raw data";            $PY generate_data.py 2>&1 | tee -a "$LOG"
log "Step 2/3: ETL + data-quality checks";    $PY etl.py           2>&1 | tee -a "$LOG"
log "Step 3/3: analytical SQL queries";       $PY run_queries.py   2>&1 | tee -a "$LOG"
log "SUCCESS pipeline finished"
