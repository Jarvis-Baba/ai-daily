"""L0 telemetry — structured JSONL log for artifact capture observability.

Writes one JSON line per fetch attempt to output/artifacts/telemetry/YYYY-MM-DD.jsonl.
This is the sole input for L1 design decisions (distribution, failure modes, sizing).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def write_telemetry(entry: dict, base_dir: str) -> Path | None:
    """Append a telemetry record to today's JSONL file. Returns the file path."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    telemetry_dir = Path(base_dir) / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    path = telemetry_dir / f"{today}.jsonl"
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path
    except OSError:
        logger.warning("Failed to write telemetry to %s", path, exc_info=True)
        return None
