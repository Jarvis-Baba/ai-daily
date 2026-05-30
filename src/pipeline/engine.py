import logging
import time
from datetime import datetime, timezone

from src.pipeline.stage import Stage, PipelineContext
from src.metrics import StageMetrics

logger = logging.getLogger(__name__)


def _count_articles(ctx: PipelineContext) -> int:
    articles = ctx.get("articles")
    if articles is None:
        return 0
    return len(articles)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineEngine:
    def __init__(self, stages: list[Stage]):
        self._stages = stages

    def run(self, ctx: PipelineContext) -> PipelineContext:
        for stage in self._stages:
            stage_name = type(stage).__name__
            started_at = _now_iso()
            items_in = _count_articles(ctx)
            t0 = time.perf_counter()

            try:
                ctx = stage.process(ctx)
                duration_ms = (time.perf_counter() - t0) * 1000
                items_out = _count_articles(ctx)

                metric = StageMetrics(
                    stage=stage_name,
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_ms=round(duration_ms, 2),
                    items_in=items_in,
                    items_out=items_out,
                    status="ok",
                )
                ctx.add_metric(metric)

                logger.info(
                    "Stage completed",
                    extra={
                        "stage": stage_name,
                        "duration_ms": round(duration_ms, 2),
                        "items_in": items_in,
                        "items_out": items_out,
                        "status": "ok",
                    },
                )

            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                items_out = _count_articles(ctx)

                metric = StageMetrics(
                    stage=stage_name,
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_ms=round(duration_ms, 2),
                    items_in=items_in,
                    items_out=items_out,
                    status="error",
                    error=str(exc),
                )
                ctx.add_metric(metric)

                logger.error(
                    "Stage failed",
                    extra={
                        "stage": stage_name,
                        "duration_ms": round(duration_ms, 2),
                        "items_in": items_in,
                        "items_out": items_out,
                        "status": "error",
                        "error": str(exc),
                    },
                )

                raise

        return ctx
