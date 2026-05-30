"""Pipeline checkpoint — save/load completed stages per date."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    date: str              # "2026-05-30"
    completed: list[str]   # ["FetchStage", "FilterStage"]
    timestamp: str         # ISO 8601


def _checkpoint_filename(date_str: str) -> str:
    return f".checkpoint-{date_str}.json"


def save_checkpoint(output_dir: str, date_str: str, completed: list[str]) -> None:
    """Save checkpoint to {output_dir}/.checkpoint-{date}.json"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cp = Checkpoint(
        date=date_str,
        completed=list(completed),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    path = out / _checkpoint_filename(date_str)
    path.write_text(json.dumps(cp.__dict__, indent=2), encoding="utf-8")
    logger.debug("Checkpoint saved: %s, completed=%s", path, completed)


def load_checkpoint(output_dir: str, date_str: str) -> Checkpoint | None:
    """Load checkpoint from file. Returns None if file doesn't exist."""
    path = Path(output_dir) / _checkpoint_filename(date_str)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint(
            date=data["date"],
            completed=data["completed"],
            timestamp=data["timestamp"],
        )
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Corrupt checkpoint %s: %s", path, exc)
        return None
