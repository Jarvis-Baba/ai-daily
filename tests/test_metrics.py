"""Tests for pipeline stage metrics tracking."""

import pytest
from src.pipeline.stage import PipelineContext
from src.pipeline.engine import PipelineEngine
from src.metrics import StageMetrics


class _CountingStage:
    """A stage that sets articles to a known count for metrics testing."""

    def __init__(self, count: int):
        self._count = count

    def process(self, ctx: PipelineContext) -> PipelineContext:
        ctx.set("articles", ["art"] * self._count)
        return ctx


class _FailingStage:
    def process(self, ctx: PipelineContext) -> PipelineContext:
        raise ValueError("boom")


def test_pipeline_engine_records_metrics():
    ctx = PipelineContext()
    ctx.set("articles", [])
    engine = PipelineEngine([
        _CountingStage(10),
        _CountingStage(5),
    ])
    engine.run(ctx)

    metrics = ctx.get_metrics()
    assert len(metrics) == 2

    # First stage: 0 in, 10 out
    m0 = metrics[0]
    assert m0.stage == "_CountingStage"
    assert m0.items_in == 0
    assert m0.items_out == 10
    assert m0.status == "ok"
    assert m0.duration_ms >= 0

    # Second stage: 10 in, 5 out
    m1 = metrics[1]
    assert m1.stage == "_CountingStage"
    assert m1.items_in == 10
    assert m1.items_out == 5
    assert m1.status == "ok"


def test_metrics_stage_ok():
    ctx = PipelineContext()
    ctx.set("articles", [1, 2, 3])
    engine = PipelineEngine([_CountingStage(7)])
    engine.run(ctx)

    metrics = ctx.get_metrics()
    assert len(metrics) == 1
    m = metrics[0]
    assert m.status == "ok"
    assert m.error is None
    assert m.duration_ms >= 0


def test_metrics_stage_error():
    ctx = PipelineContext()
    ctx.set("articles", [1])
    engine = PipelineEngine([_FailingStage()])

    with pytest.raises(ValueError, match="boom"):
        engine.run(ctx)

    metrics = ctx.get_metrics()
    assert len(metrics) == 1
    m = metrics[0]
    assert m.status == "error"
    assert m.error == "boom"
    assert m.items_in == 1
    assert m.duration_ms >= 0


def test_metrics_includes_timestamps():
    ctx = PipelineContext()
    engine = PipelineEngine([_CountingStage(3)])
    engine.run(ctx)

    m = ctx.get_metrics()[0]
    # ISO-8601 format check
    assert "T" in m.started_at
    assert "T" in m.finished_at
    # finished_at should not be before started_at
    assert m.finished_at >= m.started_at


def test_metrics_no_articles_key():
    """When 'articles' key is not set, items_in/out should be 0."""
    ctx = PipelineContext()
    engine = PipelineEngine([_CountingStage(4)])
    engine.run(ctx)

    m = ctx.get_metrics()[0]
    assert m.items_in == 0
    assert m.items_out == 4


def test_get_metrics_returns_copy():
    ctx = PipelineContext()
    ctx.add_metric(StageMetrics(
        stage="test", started_at="", finished_at="",
        duration_ms=0, items_in=0, items_out=0, status="ok",
    ))
    metrics = ctx.get_metrics()
    metrics.append(None)
    assert len(ctx.get_metrics()) == 1
