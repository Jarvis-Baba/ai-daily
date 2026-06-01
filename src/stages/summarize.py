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
        full_text = article.content

        if full_text and len(full_text) > 200:
            prompt = (
                "你是AI行业分析师。针对以下文章输出中文摘要，格式：\n\n"
                "**发生了什么**：一句话简述事件\n"
                "**为什么重要**：一句点出关键意义\n"
                "**影响**：对行业/从业者有什么影响\n\n"
                "约束：每条不超过150字，不编造文章没说的事。\n\n"
                f"标题：{article.title}\n"
                f"正文：{full_text[:3000]}"
            )
        elif article.summary:
            prompt = (
                "用一句中文简述以下AI新闻，点出它为什么值得关注：\n\n"
                f"标题：{article.title}\n"
                f"摘要：{(article.summary or '')[:500]}"
            )
        else:
            return article.title

        response = self._llm.chat([
            {"role": "system", "content": "You are a tech analyst. Reply in Chinese. Concise."},
            {"role": "user", "content": prompt},
        ])
        return response.strip()
