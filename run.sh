#!/bin/bash
# ai-daily daily runner — designed for crontab
# Usage: ./run.sh [--resume]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/run-$(date +%Y-%m-%d).log"

echo "[$(date -Iseconds)] Starting ai-daily run..." >> "$LOG_FILE"

python3 src/main.py -c config.yaml "$@" >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "[$(date -Iseconds)] Exit code: $EXIT_CODE" >> "$LOG_FILE"
exit $EXIT_CODE
