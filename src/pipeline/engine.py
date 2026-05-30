import logging
import time
from datetime import date, datetime, timezone

from src.pipeline.stage import Stage, PipelineContext
from src.metrics import StageMetrics
from src.checkpoint import save_checkpoint, load_checkpoint

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

    def run(self, ctx: PipelineContext, resume: bool = False) -> PipelineContext:
        output_dir = ctx.get("output_dir", "./output")
        date_str = date.today().isoformat()
        completed_stages: list[str] = []
        skip_counters: dict[str, int] = {}

        if resume:
            checkpoint = load_checkpoint(output_dir, date_str)
            if checkpoint:
                completed_stages = list(checkpoint.completed)
                for name in checkpoint.completed:
                    skip_counters[name] = skip_counters.get(name, 0) + 1
                logger.info("Resuming checkpoint, skipping: %s", completed_stages)

        for stage in self._stages:
            stage_name = type(stage).__name__

            if skip_counters.get(stage_name, 0) > 0:
                skip_counters[stage_name] -= 1
                logger.info("Skipping %s (already completed)", stage_name)
                continue

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

                # Save checkpoint after each successful stage
                completed_stages.append(stage_name)
                save_checkpoint(output_dir, date_str, completed_stages)

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
