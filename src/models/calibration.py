"""Calibration models — online source reliability learning.

Converts source_reliability from a static config lookup to an adaptive variable
updated by L2 synthesis feedback. Never modifies historical Evidence objects.
"""

from dataclasses import dataclass, field


@dataclass
class DomainStats:
    referenced: int = 0       # times this domain's Evidence was available to L2
    adopted: int = 0          # times Evidence was used in event_ledger
    disputed: int = 0         # times Evidence was marked conflicting
    compressed: int = 0       # times Evidence was present but omitted


@dataclass
class CalibrationEntry:
    domain: str
    prior: float              # static SOURCE_RELIABILITY_DEFAULTS value
    stats: DomainStats
    behavioral_score: float
    reliability: float        # 0.7 * prior + 0.3 * behavioral_score
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "prior": self.prior,
            "stats": {
                "referenced": self.stats.referenced,
                "adopted": self.stats.adopted,
                "disputed": self.stats.disputed,
                "compressed": self.stats.compressed,
            },
            "computed": {
                "behavioral_score": round(self.behavioral_score, 4),
                "reliability": round(self.reliability, 4),
            },
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationEntry":
        stats = d.get("stats", {})
        computed = d.get("computed", {})
        return cls(
            domain=d["domain"],
            prior=d.get("prior", 0.5),
            stats=DomainStats(
                referenced=stats.get("referenced", 0),
                adopted=stats.get("adopted", 0),
                disputed=stats.get("disputed", 0),
                compressed=stats.get("compressed", 0),
            ),
            behavioral_score=computed.get("behavioral_score", 0.5),
            reliability=computed.get("reliability", 0.5),
            updated_at=d.get("updated_at", ""),
        )
