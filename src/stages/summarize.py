import logging
from datetime import date
from src.pipeline.stage import PipelineContext
from src.adapters.llm import LLMAdapter
from src.models.article import Article, Brief, BriefItem

logger = logging.getLogger(__name__)


class SummarizeStage:
    def __init__(self, llm_adapter: LLMAdapter):
        self._llm = llm_adapter

    def process(self, ctx: PipelineContext) -> PipelineContext:
        articles: list[Article] = ctx.get("articles", [])

        if not articles:
            ctx.set("brief", Brief(date=date.today(), items=[]))
            return ctx

        items = []
        for a in articles:
            digest = self._generate_digest(a)
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

    def _generate_digest(self, article: Article) -> str:
        prompt = (
            f"Summarize the following article in one sentence (Chinese, under 80 chars):\n\n"
            f"Title: {article.title}\n"
            f"Summary: {(article.summary or '')[:500]}"
        )
        response = self._llm.chat([
            {"role": "system", "content": "You are a news editor. Reply in Chinese, one sentence only."},
            {"role": "user", "content": prompt},
        ])
        return response.strip()
