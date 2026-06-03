"""Structural Telemetry — per-run fingerprint with S(t) state decomposition.

Writes a structural fingerprint + four-factor decomposition after each pipeline run.
No logic changes, no parameter drift. Read-only instrumentation.

S(t) decomposition into four orthogonal factors:
  H_source    — input diversity (entropy of evidence across sources)
  coverage    — clustering recall (evidence_in_clusters / total)
  H_cluster   — cluster shape (entropy of size distribution)
  compression — LLM synthesis efficiency (events / clusters)

Accumulating 3+ fingerprints enables drift attribution:
  "yield dropped because H_source ↑ +0.3" (not "yield dropped")
"""

import json
import logging
import math
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class StateDecomposition:
    """Four-factor decomposition of system state S(t).

    Each factor isolates a distinct structural dimension:
      h_source      — input-side: did the source mix change?
      coverage      — clustering: did evidence find structure?
      h_cluster     — shape: is evidence distributed evenly or peaked?
      compression   — synthesis: is LLM merging or preserving clusters?
    """
    h_source: float
    coverage: float
    h_cluster: float
    compression_ratio: float

    def to_dict(self) -> dict:
        return {
            "h_source": round(self.h_source, 4),
            "coverage": round(self.coverage, 4),
            "h_cluster": round(self.h_cluster, 4),
            "compression_ratio": round(self.compression_ratio, 4),
            "interpretation": self._interpret(),
        }

    def _interpret(self) -> str:
        parts = []
        if self.h_source > 1.5:
            parts.append("diverse sources")
        elif self.h_source > 0.8:
            parts.append("moderate source spread")
        else:
            parts.append("concentrated sources")
        if self.coverage > 0.65:
            parts.append("high structural recall")
        elif self.coverage > 0.45:
            parts.append("moderate clustering")
        else:
            parts.append("low clustering (orphan-dominant)")
        if self.compression_ratio < 0.3:
            parts.append("aggressive LLM merge")
        elif self.compression_ratio < 0.6:
            parts.append("balanced compression")
        else:
            parts.append("low compression (event-rich)")
        return "; ".join(parts)


def compute_source_entropy(evidence_list: list) -> float:
    """Shannon entropy of evidence distribution across sources.

    H_source = -sum(p_i * ln(p_i)) where p_i = evidence_from_source_i / total.
    High = diverse inputs. Low = 1-2 sources dominate.
    """
    if not evidence_list:
        return 0.0
    counter = Counter(ev.source.name.lower() for ev in evidence_list)
    total = len(evidence_list)
    entropy = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log(p)
    return entropy


def decompose_state(
    evidence_list: list,
    clusters: list,
    orphans: list,
    event_count: int,
    cluster_entropy_fn,
) -> StateDecomposition:
    """Decompose system state S(t) into four orthogonal structural factors."""
    total = max(len(evidence_list), 1)
    n_clusters = max(len(clusters), 1)

    h_source = compute_source_entropy(evidence_list)
    coverage = sum(len(c) for c in clusters) / total
    h_cluster = cluster_entropy_fn(clusters, orphans)
    compression_ratio = event_count / n_clusters

    return StateDecomposition(
        h_source=h_source,
        coverage=coverage,
        h_cluster=h_cluster,
        compression_ratio=compression_ratio,
    )


@dataclass
class StructuralFingerprint:
    """One pipeline run's structural state — minimal, tractable, diffable."""
    timestamp: str
    evidence_count: int
    cluster_count: int
    evidence_in_clusters: int
    orphan_count: int
    orphan_ratio: float
    cluster_entropy: float
    mean_cluster_size: float
    aggregation_ratio: float
    event_count: int
    event_yield: float
    source_count: int
    cluster_size_distribution: dict[str, int]
    decomposition: dict = field(default_factory=dict)


def compute_fingerprint(
    evidence_list: list,
    clusters: list,
    orphans: list,
    event_count: int,
    cluster_entropy_fn,
) -> StructuralFingerprint:
    """Build a StructuralFingerprint with S(t) decomposition from pipeline outputs."""
    total_ev = max(len(evidence_list), 1)
    cluster_ev = sum(len(c) for c in clusters)
    orphan_n = len(orphans)

    # Cluster size distribution
    size_dist: dict[str, int] = {}
    for c in clusters:
        sz = len(c)
        key = f"size_{sz}" if sz < 7 else "size_7+"
        size_dist[key] = size_dist.get(key, 0) + 1
    if orphan_n > 0:
        size_dist["size_1"] = size_dist.get("size_1", 0) + orphan_n

    entropy = cluster_entropy_fn(clusters, orphans)
    source_count = len(set(ev.source.name.lower() for ev in evidence_list))

    # State decomposition
    decomp = decompose_state(evidence_list, clusters, orphans, event_count, cluster_entropy_fn)

    return StructuralFingerprint(
        timestamp=datetime.now(timezone.utc).isoformat(),
        evidence_count=total_ev,
        cluster_count=len(clusters),
        evidence_in_clusters=cluster_ev,
        orphan_count=orphan_n,
        orphan_ratio=round(orphan_n / total_ev, 4),
        cluster_entropy=round(entropy, 4),
        mean_cluster_size=round(cluster_ev / max(len(clusters), 1), 2),
        aggregation_ratio=round(cluster_ev / max(len(clusters), 1), 2),
        event_count=event_count,
        event_yield=round(event_count / total_ev, 4),
        source_count=source_count,
        cluster_size_distribution=size_dist,
        decomposition=decomp.to_dict(),
    )


def save_fingerprint(fp: StructuralFingerprint, base_dir: str) -> str:
    """Write fingerprint to telemetry dir. Returns file path."""
    out_dir = Path(base_dir) / "telemetry"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = out_dir / f"structural_fingerprint_{ts}.json"
    path.write_text(json.dumps(asdict(fp), indent=2, ensure_ascii=False), encoding="utf-8")
    interp = fp.decomposition.get("interpretation", "")
    logger.info("Structural fingerprint: %s (H_src=%.3f cov=%.0f%% H_cl=%.3f comp=%.2f | %s)",
                path.name, fp.decomposition.get("h_source", 0),
                fp.decomposition.get("coverage", 0) * 100,
                fp.decomposition.get("h_cluster", 0),
                fp.decomposition.get("compression_ratio", 0),
                interp)
    return str(path)
