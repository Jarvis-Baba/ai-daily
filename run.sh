#!/bin/bash
# ai-daily daily runner — systemd timer
# Usage: ./run.sh [--resume]
#
# Contract: TODAY's deliverables MUST land in E:\Jarvis\Outputs\<date>_AI日报/
# Delivery is incremental: only today's products are copied, never history.
#
# Error-handling design (2026-06-10, PLAN.md step 2):
#   set -e was removed deliberately. Under set -e any failing command aborted
#   the script before the FATAL checks could run, so EXIT_CODE=$? could only
#   ever observe 0 and the failure path was unreachable. trap ERR was rejected
#   because bash silently disables it in conditional contexts. Explicit checks
#   below make the failure path a structural guarantee:
#   every failure → FATAL log line + logs/FAILED-<date>.flag + non-zero exit.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Load .env if it exists
[ -f .env ] && set -a && source .env && set +a

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

RUN_DATE="$(date +%Y-%m-%d)"
LOG_FILE="$LOG_DIR/run-$RUN_DATE.log"
FAIL_FLAG="$LOG_DIR/FAILED-$RUN_DATE.flag"

log() {
    echo "[$(date -Iseconds)] $1" >> "$LOG_FILE"
}

# Single failure exit: FATAL log + observable marker file + non-zero exit code.
fail() {
    log "[FATAL] $1"
    echo "[$(date -Iseconds)] $1" >> "$FAIL_FLAG"
    exit "${2:-1}"
}

log "Starting ai-daily run..."

# Pre: run telemetry daily summary (best-effort, never blocks)
log "Running telemetry summary..."
python3 "$HOME/cc-workspace/runtime/telemetry/daily-summary.py" >> "$LOG_FILE" 2>&1 || true

# ── Generation ──
PYTHONPATH=. python3 src/main.py -c config.yaml "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
log "Exit code: $EXIT_CODE"

if [ "$EXIT_CODE" -ne 0 ]; then
    fail "main.py failed (exit $EXIT_CODE) — no delivery attempted" "$EXIT_CODE"
fi

# ── Post-generation: Content Compiler CI loop ──
# A visual-pipeline failure must not block delivery of today's brief,
# but it must stay observable: we deliver first, then exit non-zero below.
log "Starting daily pipeline..."
python3 daily_pipeline.py --cron >> "$LOG_FILE" 2>&1
PIPELINE_EXIT=$?
log "Pipeline exit code: $PIPELINE_EXIT"

# ── Output Contract Enforcement (always reached when generation succeeded) ──
OUT_DIR="$SCRIPT_DIR/output"
E_BASE="${AI_DAILY_E_BASE:-/mnt/e/Jarvis/Outputs}"   # override is for tests only
E_DIR="$E_BASE/${RUN_DATE}_AI日报"

[ -d "$OUT_DIR" ] || fail "output dir missing: $OUT_DIR"
[ -f "$OUT_DIR/morning-$RUN_DATE.md" ] || fail "today's brief missing: morning-$RUN_DATE.md"
[ -d "$E_BASE" ] || fail "delivery base unreachable (E: not mounted?): $E_BASE"

mkdir -p "$E_DIR" || fail "cannot create delivery dir: $E_DIR"

# Incremental delivery: copy one of today's products into a subpath of E_DIR.
DELIVERED=0
deliver() {
    local src="$1" dest="$2"
    [ -e "$src" ] || return 0
    mkdir -p "$dest" || fail "cannot create $dest"
    cp -r "$src" "$dest/" || fail "copy failed: $src"
    log "delivered: ${src#"$OUT_DIR"/}"
    DELIVERED=$((DELIVERED + 1))
}

deliver "$OUT_DIR/morning-$RUN_DATE.md"                      "$E_DIR"
deliver "$OUT_DIR/morning-$RUN_DATE.ir.json"                 "$E_DIR"
deliver "$OUT_DIR/summary-$RUN_DATE.txt"                     "$E_DIR"
deliver "$OUT_DIR/articles/$RUN_DATE"                        "$E_DIR/articles"
deliver "$OUT_DIR/visual-$RUN_DATE"                          "$E_DIR"
deliver "$OUT_DIR/daily-summaries/daily-$RUN_DATE.json"      "$E_DIR/daily-summaries"

[ "$DELIVERED" -ge 1 ] || fail "nothing delivered for $RUN_DATE"
log "Delivered $DELIVERED item(s) to $E_DIR"

if [ "$PIPELINE_EXIT" -ne 0 ]; then
    fail "daily_pipeline failed (exit $PIPELINE_EXIT); brief was delivered" "$PIPELINE_EXIT"
fi

exit 0
