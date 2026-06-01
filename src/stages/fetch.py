import logging
from dataclasses import dataclass, field
from src.pipeline.stage import PipelineContext
from src.models.article import Article

logger = logging.getLogger(__name__)

PRIORITY_LABELS = {1: "critical", 2: "core", 3: "supplementary"}


def _coerce_priority(value) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 2
    return priority if priority in PRIORITY_LABELS else 2


def _coerce_feed_type(value) -> str:
    return value if isinstance(value, str) and value else "rss"


@dataclass
class FeedHealth:
    name: str
    priority: int
    feed_type: str = "rss"
    status: str = "ok"       # ok / degraded / failed
    article_count: int = 0


@dataclass
class HealthReport:
    feeds: list[FeedHealth] = field(default_factory=list)
    total_articles: int = 0
    degrade_level: int = 0    # 0=normal 1=tier1_degraded 2=tier2_degraded

    @property
    def summary(self) -> str:
        tier1_ok = all(f.status == "ok" for f in self.feeds if f.priority == 1)
        tier1_dead = all(f.status == "failed" for f in self.feeds if f.priority == 1)
        tier2_ok = all(f.status == "ok" for f in self.feeds if f.priority <= 2)

        if tier1_ok and tier2_ok:
            return "🟢 全源正常"
        if tier1_ok:
            return "🟡 Tier 2 部分降级，已启用补充源"
        if not tier1_dead:
            return "🟠 Tier 1 部分降级，核心信号可能不完整"
        return "🔴 Tier 1 全宕，日报仅基于次级信源"


class FetchStage:
    def __init__(self, rss_adapter):
        self._rss = rss_adapter

    def process(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.get("config")
        seen_urls: set[str] = set()
        articles: list[Article] = []
        health: list[FeedHealth] = []

        for feed_cfg in config.feeds:
            if not feed_cfg.enabled:
                continue

            priority = _coerce_priority(getattr(feed_cfg, "priority", 2))
            feed_type = _coerce_feed_type(getattr(feed_cfg, "feed_type", "rss"))
            logger.info("Fetching: %s (%s) [%s]", feed_cfg.name, feed_cfg.url,
                        PRIORITY_LABELS.get(priority, "?"))

            try:
                raw_articles = self._rss.fetch(
                    url=feed_cfg.url,
                    source_name=feed_cfg.name,
                    max_articles=config.fetch.max_articles_per_feed,
                    feed_type=feed_type,
                )
            except Exception as e:
                logger.warning("Feed FAILED [%s]: %s — %s", PRIORITY_LABELS.get(priority, "?"),
                               feed_cfg.name, e)
                health.append(FeedHealth(name=feed_cfg.name, priority=priority,
                                         feed_type=feed_type,
                                         status="failed", article_count=0))
                continue

            count = 0
            for raw in raw_articles:
                if raw.link not in seen_urls:
                    seen_urls.add(raw.link)
                    articles.append(Article(
                        title=raw.title, link=raw.link, summary=raw.summary,
                        published=raw.published, source=raw.source,
                    ))
                    count += 1

            status = "ok" if count > 0 else "degraded"
            health.append(FeedHealth(name=feed_cfg.name, priority=priority,
                                     feed_type=feed_type,
                                     status=status, article_count=count))

        # ---- degrade assessment ----
        tier1_articles = sum(h.article_count for h in health if h.priority == 1)
        tier2_articles = sum(h.article_count for h in health if h.priority <= 2)
        degrade_level = 0
        if tier1_articles < 5:
            degrade_level = 2
        elif tier2_articles < 8:
            degrade_level = 1

        report = HealthReport(
            feeds=health,
            total_articles=len(articles),
            degrade_level=degrade_level,
        )

        ctx.set("health_report", report)
        logger.info("Fetched %d articles from %d feeds | degrade=%d | %s",
                     len(articles), len(config.feeds), degrade_level, report.summary)
        ctx.set("articles", articles)
        return ctx
