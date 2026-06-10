import argparse
import logging
import sys
from datetime import date
from pathlib import Path

# Allow running from any directory without PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.logging_setup import setup_logging
from src.pipeline.stage import PipelineContext
from src.pipeline.engine import PipelineEngine
from src.config.loader import load_config, AppConfig
from src.adapters.rss import RSSAdapter
from src.adapters.blog_scraper import CompositeFeedAdapter
from src.adapters.llm import DummyAdapter, OpenAILikeAdapter
from src.adapters.content_fetcher import set_router
from src.adapters.fetchers.router import ContentRouter
from src.stages.artifact_capture import L0CaptureStage
from src.stages.evidence_compiler import L1EvidenceStage
from src.stages.event_clustering import EventClusteringStage, cluster_entropy
from src.adapters.structural_telemetry import compute_fingerprint, save_fingerprint
from src.stages.fetch import FetchStage
from src.stages.filter import FilterStage
from src.stages.fetch_content import FetchContentStage
from src.stages.scoring import ScoringStage
from src.stages.theme import ThemeStage
from src.stages.summarize import SummarizeStage
from src.stages.synthesize import SynthesizeStage
from src.stages.role_assigner import RoleAssignerStage
from src.stages.article_compiler import ArticleCompilerStage
from src.stages.output import OutputStage

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("ai-daily")


def build_llm_adapter(config: AppConfig):
    provider = config.llm.provider
    if provider == "dummy":
        return DummyAdapter()
    if provider == "deepseek" or provider == "openai":
        return OpenAILikeAdapter(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            retry_attempts=config.retry.max_attempts,
            retry_backoff=config.retry.backoff_seconds,
        )
    raise ValueError(f"Unknown LLM provider: {provider}")


def build_pipeline(config: AppConfig, rss_adapter=None, llm_adapter=None):
    if rss_adapter is None:
        rss = RSSAdapter(
            timeout=config.fetch.timeout,
            max_articles=config.fetch.max_articles_per_feed,
            retry_attempts=config.retry.max_attempts,
            retry_backoff=config.retry.backoff_seconds,
        )
        rss_adapter = CompositeFeedAdapter(rss)

    if llm_adapter is None:
        llm_adapter = build_llm_adapter(config)

    return PipelineEngine([
        L0CaptureStage(),
        L1EvidenceStage(llm_adapter=llm_adapter),
        EventClusteringStage(),
        FetchStage(rss_adapter=rss_adapter),
        FilterStage(llm_adapter=llm_adapter, top_n=config.filter.top_n, min_score=config.filter.min_score),
        FetchContentStage(),
        ScoringStage(llm_adapter=llm_adapter),
        ThemeStage(),
        SummarizeStage(llm_adapter=llm_adapter),
        SynthesizeStage(llm_adapter=llm_adapter),
        RoleAssignerStage(),
        ArticleCompilerStage(llm_adapter=llm_adapter),
        OutputStage(),
    ])


def run_pipeline(engine: PipelineEngine, ctx: PipelineContext, resume: bool = False) -> PipelineContext:
    return engine.run(ctx, resume=resume)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="AI Daily — Morning Brief Generator")
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    args = parser.parse_args()

    logger.info("Loading config: %s", args.config)
    config = load_config(args.config)

    # Init content fetch router
    router = ContentRouter.from_config(config)
    set_router(router)
    logger.info("Content router: %d routes, fetchers=%s",
                 len(router._routes), router.fetcher_names)

    llm = build_llm_adapter(config)
    engine = build_pipeline(config, llm_adapter=llm)
    ctx = PipelineContext()
    ctx.set("config", config)
    ctx.set("output_dir", config.output.dir)
    ctx.set("llm_adapter", llm)
    ctx.set("report_date", date.today())

    result = run_pipeline(engine, ctx, resume=args.resume)
    logger.info("Brief saved to: %s", result.get("output_path"))
    logger.info("Fetch stats: %s", router.stats)

    # ── Structural telemetry fingerprint ──
    evidence = result.get("evidence", []) or []
    clusters = result.get("event_clusters", []) or []
    orphans = result.get("event_orphans", []) or []
    insight = result.get("insight_brief")
    event_count = len(insight.event_ledger) if insight else 0

    fp = compute_fingerprint(
        evidence_list=evidence,
        clusters=clusters,
        orphans=orphans,
        event_count=event_count,
        cluster_entropy_fn=cluster_entropy,
    )
    base_dir = getattr(getattr(config, "artifact", None), "output_dir", "./output/artifacts")
    save_fingerprint(fp, base_dir)

    # ── Daily summary (current-state only, no diff, no drift alert) ──
    editorial = result.get("editorial_telemetry") or {}

    def _role_icon(count):
        return "●" if count > 0 else "○"

    role_icons = ""
    if editorial:
        ra = editorial.get("role_assignment", {})
        role_icons = "  " + " ".join(
            f"{_role_icon(1 if r in ra else 0)} {r}"
            for r in ["hook", "context", "pivot", "amplifier", "contradiction", "closer"]
        )

    print(f"""
{'='*40}
STRUCTURAL  {'='*40}
  evidence={fp.evidence_count:>5}  clusters={fp.cluster_count:>3}  orphans={fp.orphan_count:>3}
  orphan_ratio={fp.orphan_ratio:>6.1%}  entropy={fp.cluster_entropy:>6.2f}  aggregation={fp.aggregation_ratio:>5.1f}
  event_yield={fp.event_yield:>6.1%}  sources={fp.source_count}

{'='*40}
EDITORIAL   {'='*40}
  events={editorial.get('candidate_events','?'):>5}  assigned={editorial.get('selected_events','?'):>3}  unassigned={editorial.get('unassigned_events','?'):>3}
{role_icons}
{'='*40}
""".strip())


if __name__ == "__main__":
    main()
