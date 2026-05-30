import logging
from datetime import date
from src.pipeline.stage import PipelineContext
from src.adapters.llm import LLMAdapter
from src.adapters.content_fetcher import fetch_content
from src.config.loader import ContentConfig
from src.models.article import Article, Brief, BriefItem

logger = logging.getLogger(__name__)


class SummarizeStage:
    def __init__(self, llm_adapter: LLMAdapter):
        self._llm = llm_adapter

    def process(self, ctx: PipelineContext) -> PipelineContext:
        articles: list[Article] = ctx.get("articles", [])
        config = ctx.get("config")
        content_cfg = config.content if config else None

        if not articles:
            ctx.set("brief", Brief(date=date.today(), items=[]))
            return ctx

        items = []
        for a in articles:
            digest = self._generate_digest(a, content_cfg)
            items.append(BriefItem(
                title=a.title,
                source=a.source,
                score=a.score,
                digest=digest,
                link=a.link,
            ))

        brief = Brief(date=date.today(), items=items)
        ctx.set("brief", brief)
        return ctx

    def _generate_digest(self, article: Article,
                         content_cfg: ContentConfig | None = None) -> str:
        # Attempt to fetch full text if enabled
        fetch_enabled = content_cfg.fetch_fulltext if content_cfg else True
        timeout = content_cfg.timeout if content_cfg else 8
        max_chars = content_cfg.max_chars if content_cfg else 3000

        full_text = ""
        if fetch_enabled:
            full_text = fetch_content(article.link, timeout=timeout, max_chars=max_chars)

        if full_text and len(full_text) > 200:
            # Rich summary from full text
            prompt = (
                "Write a 2-3 sentence summary in Chinese about this article:\n\n"
                f"Title: {article.title}\n"
                f"Content: {full_text[:3000]}"
            )
        elif article.summary:
            # Fallback: short summary from RSS blurb
            prompt = (
                "Summarize in one Chinese sentence:\n\n"
                f"Title: {article.title}\n"
                f"Summary: {(article.summary or '')[:500]}"
            )
        else:
            return article.title  # last resort

        response = self._llm.chat([
            {"role": "system", "content": "You are a news editor. Reply in Chinese only."},
            {"role": "user", "content": prompt},
        ])
        return response.strip()
