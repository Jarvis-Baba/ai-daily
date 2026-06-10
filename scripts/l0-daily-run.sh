#!/usr/bin/env bash
# L0 Daily Artifact Capture — invoked by systemd timer at 07:00 UTC daily.
#
# Guardrails:
#   1. Lockfile: prevents concurrent runs. Stale locks (>2h) auto-cleared on next run.
#   2. Run log: output/logs/YYYY-MM-DD.log
#   3. Failure isolation: non-zero exit but never blocks next day's run.
#   4. Telemetry: written by the Python stage itself — this script just wraps it.
set -euo pipefail

PROJECT_DIR="/home/jarvis/cc-workspace/ai-daily"
LOCKFILE="$PROJECT_DIR/output/.l0-daily.lock"
TODAY=$(date -u +%Y%m%d)
LOG_DIR="$PROJECT_DIR/output/logs"
LOG_FILE="$LOG_DIR/$TODAY.log"

mkdir -p "$LOG_DIR"

# ── Lockfile guard ──
if [ -f "$LOCKFILE" ]; then
    # Check if lock is stale (>2 hours)
    if [ "$(find "$LOCKFILE" -mmin +120 2>/dev/null)" ]; then
        echo "[$(date -Iseconds)] WARNING: stale lockfile (>2h), removing" | tee -a "$LOG_FILE"
        rm -f "$LOCKFILE"
    else
        echo "[$(date -Iseconds)] L0 daily run skipped: lockfile exists (another run in progress)" | tee -a "$LOG_FILE"
        exit 0
    fi
fi

touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# ── Run ──
{
    echo "=== L0 Daily Capture $TODAY ==="
    echo "Start: $(date -Iseconds)"
    echo ""

    cd "$PROJECT_DIR"
    export PYTHONPATH="$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"

    python3 -c "
from src.config.loader import load_config
from src.pipeline.stage import PipelineContext
from src.stages.artifact_capture import L0CaptureStage

config = load_config('config.yaml')
stage = L0CaptureStage()
ctx = PipelineContext()
ctx.set('config', config)
result = stage.process(ctx)
artifacts = result.get('artifacts', [])
refs = result.get('artifact_refs', [])

print(f'Artifacts captured: {len(artifacts)}')
for a in artifacts:
    print(f'  {a.artifact_id} via {a.retrieved_via} ({len(a.raw_content)} chars) [{a.source_name}]')
print(f'Refs: {refs}')
" 2>&1

    echo ""
    echo "End: $(date -Iseconds)"
    echo "Exit code: $?"
} >> "$LOG_FILE" 2>&1

    # ── Distribution report ──
    echo "" >> "$LOG_FILE"
    echo "=== Distribution Report ===" >> "$LOG_FILE"
    python3 -c "
import json
from src.adapters.telemetry_analyzer import analyze_day, analyze_range, format_report, format_trend

today_stats = analyze_day('output/artifacts/telemetry', '$TODAY')
trend = analyze_range('output/artifacts/telemetry', days=7)

# Human-readable report to run log
print(format_report(today_stats))
print()
print(format_trend(trend))

# Machine-readable summary JSON
summary = {
    'date': today_stats['date'],
    'attempts': today_stats['total_attempts'],
    'success_rate': today_stats['success_rate'],
    'fetch_distribution': today_stats['fetch_distribution'],
    'size_histogram': today_stats['size_histogram'],
    'content_length_avg': today_stats['content_length']['avg'],
    'media_avg_per_artifact': today_stats['media']['avg_images_per_artifact'],
    'latency_p50_ms': today_stats['latency']['p50_ms'],
    'latency_p95_ms': today_stats['latency']['p95_ms'],
    'sources': list(today_stats.get('sources', {}).keys()),
    'days_of_data': len([d for d in trend if not d.get('error') and d.get('total_attempts', 0) > 0]),
}
summary_path = f'output/artifacts/telemetry/daily_summary_{\"$TODAY\"}.json'
with open(summary_path, 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f'Summary saved: {summary_path}')
" >> "$LOG_FILE" 2>&1

echo "[$(date -Iseconds)] L0 daily run complete" >> "$LOG_FILE"
