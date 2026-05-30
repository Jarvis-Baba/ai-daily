from typing import Any, Protocol


class PipelineContext:
    def __init__(self):
        self._data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class Stage(Protocol):
    def process(self, ctx: PipelineContext) -> PipelineContext:
        ...
