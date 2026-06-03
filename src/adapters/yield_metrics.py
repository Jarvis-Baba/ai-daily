"""Pipeline yield metrics — measures information compression at each layer.

Three yields track how much information survives each L0→L1→L2 transition.
Not opinion — measurement.
"""

from dataclasses import dataclass, field
from collections import Counter


@dataclass
class YieldSnapshot:
    """One pipeline run's yield metrics."""
    artifact_count: int = 0
    evidence_count: int = 0
    event_count: int = 0
    adopted_event_count: int = 0
    matched_domain_count: int = 0
    total_domain_count: int = 0
    type_distribution: dict = field(default_factory=dict)

    @property
    def evidence_yield(self) -> float:
        """Artifact → Evidence conversion rate."""
        return self.evidence_count / max(self.artifact_count, 1)

    @property
    def event_yield(self) -> float:
        """Evidence → Event conversion rate."""
        return self.event_count / max(self.evidence_count, 1)

    @property
    def adoption_yield(self) -> float:
        """Event → Adopted (source-matched) rate."""
        return self.adopted_event_count / max(self.event_count, 1)

    @property
    def domain_adoption(self) -> float:
        """Fraction of evidence domains with ≥1 event match."""
        return self.matched_domain_count / max(self.total_domain_count, 1)

    def to_dict(self) -> dict:
        return {
            "artifact_count": self.artifact_count,
            "evidence_count": self.evidence_count,
            "event_count": self.event_count,
            "adopted_event_count": self.adopted_event_count,
            "matched_domain_count": self.matched_domain_count,
            "total_domain_count": self.total_domain_count,
            "evidence_yield": round(self.evidence_yield, 4),
            "event_yield": round(self.event_yield, 4),
            "adoption_yield": round(self.adoption_yield, 4),
            "domain_adoption": round(self.domain_adoption, 4),
            "type_distribution": self.type_distribution,
            "compression_chain": (
                f"{self.artifact_count} → {self.evidence_count} → "
                f"{self.event_count} → {self.adopted_event_count}"
            ),
        }


def compute_yields(
    artifact_count: int,
    evidence_list: list,
    event_ledger: list,
    stage=None,
) -> YieldSnapshot:
    """Compute all yield metrics from pipeline outputs.

    Args:
        artifact_count: Number of L0 artifacts
        evidence_list: List of Evidence objects
        event_ledger: List of event dicts or EventLedgerItem objects
        stage: SynthesizeStage instance for source matching (optional)

    Returns:
        YieldSnapshot with all computed yields
    """
    ev_domains = set(ev.source.name.lower() for ev in evidence_list)

    matched_domains = set()
    adopted_count = 0

    for event in event_ledger:
        if hasattr(event, "source"):
            src, link = event.source or "", event.link or ""
        elif isinstance(event, dict):
            src, link = event.get("source", ""), event.get("link", "")
        else:
            continue

        event_matched = False
        if stage:
            for ev in evidence_list:
                domain = ev.source.name.lower()
                if stage._source_matches_evidence(src, link, ev.source.name, ev.source.url):
                    event_matched = True
                    matched_domains.add(domain)
                    break
        else:
            # Fallback: substring match only
            for ev in evidence_list:
                domain = ev.source.name.lower()
                if src.lower() in domain or domain in src.lower():
                    event_matched = True
                    matched_domains.add(domain)
                    break

        if event_matched:
            adopted_count += 1

    # Type distribution
    type_dist = {}
    for event in event_ledger:
        t = event.type if hasattr(event, "type") else event.get("type", "unknown")
        type_dist[t] = type_dist.get(t, 0) + 1

    return YieldSnapshot(
        artifact_count=artifact_count,
        evidence_count=len(evidence_list),
        event_count=len(event_ledger),
        adopted_event_count=adopted_count,
        matched_domain_count=len(matched_domains),
        total_domain_count=len(ev_domains),
        type_distribution=type_dist,
    )
