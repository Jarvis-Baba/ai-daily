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
from src.stages.fetch import FetchStage
from src.stages.filter import FilterStage
from src.stages.fetch_content import FetchContentStage
from src.stages.scoring import ScoringStage
from src.stages.theme import ThemeStage
from src.stages.summarize import SummarizeStage
from src.stages.synthesize import SynthesizeStage
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
        FetchStage(rss_adapter=rss_adapter),
        FilterStage(llm_adapter=llm_adapter, top_n=config.filter.top_n, min_score=config.filter.min_score),
        FetchContentStage(),
        ScoringStage(llm_adapter=llm_adapter),
        ThemeStage(),
        SummarizeStage(llm_adapter=llm_adapter),
        SynthesizeStage(llm_adapter=llm_adapter),
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


if __name__ == "__main__":
    main()
