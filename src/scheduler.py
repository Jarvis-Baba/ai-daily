"""Simple daily scheduler for ai-daily.
Usage: python3 src/scheduler.py -c config.yaml --at 07:00

Runs the pipeline once immediately, then waits until the next scheduled time.
Uses sleep-based polling (checks every 60 seconds) — no external deps.
"""

import argparse
import signal
import time
import sys
from datetime import datetime, timedelta
from src.pipeline.stage import PipelineContext
from src.config.loader import load_config
from src.logging_setup import setup_logging
import logging

logger = logging.getLogger("ai-daily.scheduler")
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True
    logger.info("Received signal %s, shutting down...", signum)


def run_scheduler(config_path: str, run_at: str):
    setup_logging()
    # Lazy import — main.py calls logging.basicConfig at module level,
    # which is a no-op when root already has a handler (from setup_logging above).
    from src.main import build_pipeline, run_pipeline  # noqa: E402

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    target_hour, target_min = map(int, run_at.split(":"))

    while not _shutdown:
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info("Next run at %s (%.0f seconds)", target.isoformat(), wait_seconds)

        # Sleep in 60-second chunks, checking shutdown flag
        while wait_seconds > 0 and not _shutdown:
            time.sleep(min(60, wait_seconds))
            wait_seconds -= 60

        if _shutdown:
            break

        logger.info("Running daily pipeline...")
        try:
            config = load_config(config_path)
            engine = build_pipeline(config)
            ctx = PipelineContext()
            ctx.set("config", config)
            ctx.set("output_dir", config.output.dir)
            ctx.set("output_template", config.output.template)
            result = run_pipeline(engine, ctx)
            logger.info("Pipeline complete: %s", result.get("output_path"))
        except Exception as e:
            logger.error("Pipeline failed: %s", e, exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="AI Daily Scheduler")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--at", default="07:00", help="Run time HH:MM (default: 07:00)")
    args = parser.parse_args()
    run_scheduler(args.config, args.at)


if __name__ == "__main__":
    main()
