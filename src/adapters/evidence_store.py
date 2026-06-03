"""Evidence JSON persistence. Follows artifact_store.py pattern (plain functions)."""
import json
import logging
from pathlib import Path
from src.models.evidence import (
    Evidence, EvidenceSource, EvidenceConfidence, SupportingMaterial, EvidencePackage,
)

logger = logging.getLogger(__name__)


def _evidence_to_dict(ev: Evidence) -> dict:
    return {
        "evidence_id": ev.evidence_id,
        "fact_type": ev.fact_type,
        "source": {
            "name": ev.source.name,
            "type": ev.source.type,
            "url": ev.source.url,
            "published_at": ev.source.published_at,
        },
        "statement": ev.statement,
        "attribution": ev.attribution,
        "supporting_material": {
            "quote": ev.supporting_material.quote,
            "screenshot_refs": list(ev.supporting_material.screenshot_refs),
            "artifact_refs": list(ev.supporting_material.artifact_refs),
            "media_refs": list(ev.supporting_material.media_refs),
        },
        "confidence": {
            "source_reliability": ev.confidence.source_reliability,
            "evidence_strength": ev.confidence.evidence_strength,
            "verification_status": ev.confidence.verification_status,
        },
    }


def _dict_to_evidence(d: dict) -> Evidence:
    src = d.get("source", {})
    conf = d.get("confidence", {})
    sup = d.get("supporting_material", {})
    return Evidence(
        evidence_id=d["evidence_id"],
        fact_type=d["fact_type"],
        source=EvidenceSource(
            name=src.get("name", ""),
            type=src.get("type", ""),
            url=src.get("url", ""),
            published_at=src.get("published_at", ""),
        ),
        statement=d.get("statement", ""),
        attribution=d.get("attribution", ""),
        supporting_material=SupportingMaterial(
            quote=sup.get("quote", ""),
            screenshot_refs=sup.get("screenshot_refs", []),
            artifact_refs=sup.get("artifact_refs", []),
            media_refs=sup.get("media_refs", []),
        ),
        confidence=EvidenceConfidence(
            source_reliability=conf.get("source_reliability", 0.5),
            evidence_strength=conf.get("evidence_strength", 0.5),
            verification_status=conf.get("verification_status", "unverified"),
        ),
    )


def save_evidence(evidence: Evidence, base_dir: str) -> Path:
    out_dir = Path(base_dir) / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{evidence.evidence_id}.json"
    path.write_text(json.dumps(_evidence_to_dict(evidence), indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Evidence saved: %s", evidence.evidence_id)
    return path


def load_evidence(evidence_id: str, base_dir: str) -> Evidence | None:
    path = Path(base_dir) / "evidence" / f"{evidence_id}.json"
    if not path.exists():
        return None
    try:
        return _dict_to_evidence(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Corrupt evidence %s: %s", evidence_id, exc)
        return None


def save_package(package: EvidencePackage, base_dir: str) -> Path:
    out_dir = Path(base_dir) / "packages"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{package.package_id}.json"
    data = {
        "package_id": package.package_id,
        "topic": package.topic,
        "generated_at": package.generated_at,
        "artifacts": package.artifacts,
        "evidence": [_evidence_to_dict(e) for e in package.evidence],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Package saved: %s (%d evidence)", package.package_id, len(package.evidence))
    return path


def load_package(package_id: str, base_dir: str) -> EvidencePackage | None:
    path = Path(base_dir) / "packages" / f"{package_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return EvidencePackage(
            package_id=data["package_id"],
            topic=data.get("topic", ""),
            generated_at=data.get("generated_at", ""),
            artifacts=data.get("artifacts", []),
            evidence=[_dict_to_evidence(e) for e in data.get("evidence", [])],
        )
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Corrupt package %s: %s", package_id, exc)
        return None


def next_evidence_id(date_str: str, base_dir: str) -> str:
    evidence_dir = Path(base_dir) / "evidence"
    prefix = f"E-{date_str}-"
    if not evidence_dir.exists():
        return f"E-{date_str}-001"
    existing = sorted(evidence_dir.glob(f"{prefix}*.json"))
    if not existing:
        return f"E-{date_str}-001"
    max_n = 0
    for f in existing:
        try:
            n = int(f.stem.split("-")[-1])
            max_n = max(max_n, n)
        except (ValueError, IndexError):
            continue
    return f"E-{date_str}-{max_n + 1:03d}"


def next_package_id(date_str: str, base_dir: str) -> str:
    pkg_dir = Path(base_dir) / "packages"
    prefix = f"PKG-{date_str}-"
    if not pkg_dir.exists():
        return f"PKG-{date_str}-001"
    existing = sorted(pkg_dir.glob(f"{prefix}*.json"))
    if not existing:
        return f"PKG-{date_str}-001"
    max_n = 0
    for f in existing:
        try:
            n = int(f.stem.split("-")[-1])
            max_n = max(max_n, n)
        except (ValueError, IndexError):
            continue
    return f"PKG-{date_str}-{max_n + 1:03d}"
