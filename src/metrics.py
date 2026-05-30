"""Pipeline stage metrics."""

from dataclasses import dataclass


@dataclass
class StageMetrics:
    """Metrics recorded after a pipeline stage completes or fails."""

    stage: str
    started_at: str   # ISO-8601 timestamp
    finished_at: str  # ISO-8601 timestamp
    duration_ms: float
    items_in: int
    items_out: int
    status: str       # "ok" | "error"
    error: str | None = None
