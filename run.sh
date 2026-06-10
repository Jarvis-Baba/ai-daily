#!/bin/bash
# ai-daily daily runner — systemd timer
# Usage: ./run.sh [--resume]
#
# Contract: output MUST land in E:\Jarvis\Outputs\<date>_AI日报/
# If E: drive is unreachable or output is missing, fail fast.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if it exists
[ -f .env ] && set -a && source .env && set +a

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/run-$(date +%Y-%m-%d).log"

echo "[$(date -Iseconds)] Starting ai-daily run..." >> "$LOG_FILE"

# Pre: run telemetry daily summary
echo "[$(date -Iseconds)] Running telemetry summary..." >> "$LOG_FILE"
python3 "$HOME/cc-workspace/runtime/telemetry/daily-summary.py" >> "$LOG_FILE" 2>&1 || true

PYTHONPATH=. python3 src/main.py -c config.yaml "$@" >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "[$(date -Iseconds)] Exit code: $EXIT_CODE" >> "$LOG_FILE"

# Post-generation: run the Content Compiler CI loop
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date -Iseconds)] Starting daily pipeline..." >> "$LOG_FILE"
    python3 daily_pipeline.py --cron >> "$LOG_FILE" 2>&1
    PIPELINE_EXIT=$?
    echo "[$(date -Iseconds)] Pipeline exit code: $PIPELINE_EXIT" >> "$LOG_FILE"
fi

# ── Output Contract Enforcement ──
OUT_DIR="$SCRIPT_DIR/output"
E_DATE="$(date +%Y-%m-%d)_AI日报"
E_DIR="/mnt/e/Jarvis/Outputs/$E_DATE"

if [ ! -d "$OUT_DIR" ]; then
    echo "[$(date -Iseconds)] [FATAL] output dir missing: $OUT_DIR" >> "$LOG_FILE"
    exit 1
fi

if [ -z "$(ls -A "$OUT_DIR" 2>/dev/null)" ]; then
    echo "[$(date -Iseconds)] [FATAL] output dir empty: $OUT_DIR" >> "$LOG_FILE"
    exit 1
fi

if [ ! -d /mnt/e/Jarvis ]; then
    echo "[$(date -Iseconds)] [FATAL] E: drive not mounted" >> "$LOG_FILE"
    exit 1
fi

mkdir -p "$E_DIR"
cp -r "$OUT_DIR"/* "$E_DIR/" || {
    echo "[$(date -Iseconds)] [FATAL] copy to E: failed" >> "$LOG_FILE"
    exit 1
}

echo "[$(date -Iseconds)] Delivered to $E_DIR" >> "$LOG_FILE"

exit $EXIT_CODE
