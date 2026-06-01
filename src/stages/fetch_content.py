import logging
from src.pipeline.stage import PipelineContext
from src.adapters.content_fetcher import fetch_content
from src.models.article import Article

logger = logging.getLogger(__name__)


class FetchContentStage:
    """Fetch full-text content for each article after filtering.

    Reads ctx["articles"], fetches full-text via the content router,
    and writes article.content back. Designed to sit between FilterStage
    and SummarizeStage so downstream stages can access full text.
    """

    def process(self, ctx: PipelineContext) -> PipelineContext:
        articles: list[Article] = ctx.get("articles", [])
        if not articles:
            return ctx

        config = ctx.get("config")
        content_cfg = config.content if config else None
        fetch_enabled = content_cfg.fetch_fulltext if content_cfg else True
        timeout = content_cfg.timeout if content_cfg else 8
        max_chars = content_cfg.max_chars if content_cfg else 3000

        if not fetch_enabled:
            logger.info("Full-text fetching disabled, skipping")
            return ctx

        success = 0
        for a in articles:
            try:
                a.content = fetch_content(a.link, timeout=timeout, max_chars=max_chars)
                if a.content:
                    success += 1
            except Exception:
                logger.debug("Content fetch failed for %s", a.link, exc_info=True)

        logger.info("Fetched full text for %d/%d articles", success, len(articles))
        ctx.set("articles", articles)
        return ctx
