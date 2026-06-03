"""Calibration persistence — domain-level source reliability learning.

Reads/writes output/artifacts/calibration/source_reliability.json.
Never modifies historical Evidence files.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from src.models.calibration import CalibrationEntry

logger = logging.getLogger(__name__)

_CALIBRATION_FILE = "source_reliability.json"


def load_calibrations(base_dir: str) -> dict[str, CalibrationEntry]:
    """Load all calibration entries keyed by domain. Returns empty dict if no file."""
    path = Path(base_dir) / "calibration" / _CALIBRATION_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            domain: CalibrationEntry.from_dict(entry)
            for domain, entry in data.get("entries", {}).items()
        }
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Corrupt calibration: %s", exc)
        return {}


def save_calibrations(entries: dict[str, CalibrationEntry], base_dir: str) -> Path:
    """Write all calibration entries. Creates directory if needed."""
    out_dir = Path(base_dir) / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / _CALIBRATION_FILE
    data = {
        "entries": {domain: entry.to_dict() for domain, entry in entries.items()},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Calibration saved: %d domains", len(entries))
    return path


def get_reliability(domain: str, prior: float, base_dir: str) -> float:
    """Return calibrated reliability for a domain, or fall back to prior."""
    calibrations = load_calibrations(base_dir)
    entry = calibrations.get(domain)
    if entry is None:
        return prior
    return entry.reliability
