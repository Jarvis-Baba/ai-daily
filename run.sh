#!/bin/bash
# ai-daily daily runner — designed for crontab
# Usage: ./run.sh [--resume]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if it exists
[ -f .env ] && set -a && source .env && set +a

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/run-$(date +%Y-%m-%d).log"

echo "[$(date -Iseconds)] Starting ai-daily run..." >> "$LOG_FILE"

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

exit $EXIT_CODE
