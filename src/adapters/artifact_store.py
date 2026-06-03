"""Artifact JSON persistence. Follows checkpoint.py pattern (plain functions, no class)."""
import json
import logging
from pathlib import Path
from src.models.artifact import Artifact

logger = logging.getLogger(__name__)


def save(artifact: Artifact, base_dir: str) -> Path:
    """Write artifact to {base_dir}/{artifact_id}.json. Returns file path."""
    out_dir = Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{artifact.artifact_id}.json"
    data = {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "source_url": artifact.source_url,
        "canonical_url": artifact.canonical_url,
        "retrieved_at": artifact.retrieved_at,
        "content_hash": artifact.content_hash,
        "content_type": artifact.content_type,
        "raw_content": artifact.raw_content,
        "source_name": artifact.source_name,
        "title": artifact.title,
        "published_at": artifact.published_at,
        "authors": artifact.authors,
        "screenshot_refs": artifact.screenshot_refs,
        "retrieved_via": artifact.retrieved_via,
        "media_items": artifact.media_items,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Artifact saved: %s (%d chars)", artifact.artifact_id, len(artifact.raw_content))
    return path


def load(artifact_id: str, base_dir: str) -> Artifact | None:
    """Load an artifact by ID. Returns None if not found or corrupt."""
    path = Path(base_dir) / f"{artifact_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Artifact(
            artifact_id=data["artifact_id"],
            artifact_type=data["artifact_type"],
            source_url=data["source_url"],
            canonical_url=data.get("canonical_url", data["source_url"]),
            retrieved_at=data["retrieved_at"],
            content_hash=data["content_hash"],
            raw_content=data["raw_content"],
            content_type=data.get("content_type", ""),
            source_name=data.get("source_name", ""),
            title=data.get("title", ""),
            published_at=data.get("published_at", ""),
            authors=data.get("authors", []),
            screenshot_refs=data.get("screenshot_refs", []),
            retrieved_via=data.get("retrieved_via", ""),
            media_items=data.get("media_items", []),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Corrupt artifact %s: %s", artifact_id, exc)
        return None


def find_by_url(date_str: str, canonical_url: str, base_dir: str) -> Artifact | None:
    """Scan today's artifacts for one matching canonical_url. Returns None if not found."""
    artifact_dir = Path(base_dir)
    if not artifact_dir.exists():
        return None
    prefix = f"A-{date_str}-"
    for f in sorted(artifact_dir.glob(f"{prefix}*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("canonical_url") == canonical_url:
                return load(data["artifact_id"], base_dir)
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def next_id(date_str: str, base_dir: str) -> str:
    """Generate next sequential artifact_id for the given date.

    Returns "A-YYYYMMDD-001" if no artifacts exist for that date.
    """
    artifact_dir = Path(base_dir)
    prefix = f"A-{date_str}-"
    if not artifact_dir.exists():
        return f"A-{date_str}-001"
    existing = sorted(artifact_dir.glob(f"{prefix}*.json"))
    if not existing:
        return f"A-{date_str}-001"
    max_n = 0
    for f in existing:
        try:
            n = int(f.stem.split("-")[-1])
            max_n = max(max_n, n)
        except (ValueError, IndexError):
            continue
    return f"A-{date_str}-{max_n + 1:03d}"
