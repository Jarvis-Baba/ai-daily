import logging
from src.pipeline.stage import PipelineContext
from src.adapters.rss import RSSAdapter
from src.models.article import Article

logger = logging.getLogger(__name__)


class FetchStage:
    def __init__(self, rss_adapter: RSSAdapter):
        self._rss = rss_adapter

    def process(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.get("config")
        seen_urls: set[str] = set()
        articles: list[Article] = []

        for feed_cfg in config.feeds:
            if not feed_cfg.enabled:
                continue

            logger.info("Fetching: %s (%s)", feed_cfg.name, feed_cfg.url)
            raw_articles = self._rss.fetch(
                url=feed_cfg.url,
                source_name=feed_cfg.name,
                max_articles=config.fetch.max_articles_per_feed,
            )

            for raw in raw_articles:
                if raw.link not in seen_urls:
                    seen_urls.add(raw.link)
                    articles.append(Article(
                        title=raw.title,
                        link=raw.link,
                        summary=raw.summary,
                        published=raw.published,
                        source=raw.source,
                    ))

        logger.info("Fetched %d articles from %d feeds", len(articles), len(config.feeds))
        ctx.set("articles", articles)
        return ctx
