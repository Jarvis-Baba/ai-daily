import pytest
from src.pipeline.stage import Stage, PipelineContext
from src.pipeline.engine import PipelineEngine


class AppendStage:
    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value

    def process(self, ctx: PipelineContext) -> PipelineContext:
        ctx.set(self.key, ctx.get(self.key, "") + self.value)
        return ctx


class FailingStage:
    def process(self, ctx: PipelineContext) -> PipelineContext:
        raise RuntimeError("stage failure")


def test_engine_runs_stages_in_order():
    ctx = PipelineContext()
    engine = PipelineEngine([
        AppendStage("log", "A"),
        AppendStage("log", "B"),
        AppendStage("log", "C"),
    ])
    result = engine.run(ctx)
    assert result.get("log") == "ABC"


def test_engine_returns_context():
    ctx = PipelineContext()
    ctx.set("initial", True)
    engine = PipelineEngine([AppendStage("x", "done")])
    result = engine.run(ctx)
    assert result.get("initial") is True
    assert result.get("x") == "done"


def test_engine_stops_on_failure():
    ctx = PipelineContext()
    engine = PipelineEngine([
        AppendStage("log", "before"),
        FailingStage(),
        AppendStage("log", "after"),
    ])
    with pytest.raises(RuntimeError, match="stage failure"):
        engine.run(ctx)
    assert ctx.get("log") == "before"


def test_pipeline_context_default_value():
    ctx = PipelineContext()
    assert ctx.get("missing", "default") == "default"
    assert ctx.get("missing") is None
