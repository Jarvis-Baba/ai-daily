from typing import Any, Protocol

from src.metrics import StageMetrics


class PipelineContext:
    def __init__(self):
        self._data: dict[str, Any] = {}
        self._metrics: list[StageMetrics] = []

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def add_metric(self, metric: StageMetrics) -> None:
        """Append a stage metric to the pipeline run history."""
        self._metrics.append(metric)

    def get_metrics(self) -> list[StageMetrics]:
        """Return all recorded stage metrics."""
        return list(self._metrics)


class Stage(Protocol):
    def process(self, ctx: PipelineContext) -> PipelineContext:
        ...
