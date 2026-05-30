import json
import logging
import re
from src.pipeline.stage import PipelineContext
from src.adapters.llm import LLMAdapter
from src.models.article import Article

logger = logging.getLogger(__name__)


class FilterStage:
    def __init__(self, llm_adapter: LLMAdapter, top_n: int = 10, min_score: int = 6):
        self._llm = llm_adapter
        self._top_n = top_n
        self._min_score = min_score

    def process(self, ctx: PipelineContext) -> PipelineContext:
        articles: list[Article] = ctx.get("articles", [])

        if not articles:
            ctx.set("articles", [])
            return ctx

        scored = self._score_articles(articles)
        scored.sort(key=lambda a: a.score, reverse=True)
        filtered = [a for a in scored if a.score >= self._min_score][:self._top_n]

        logger.info("Filtered %d → %d articles (min_score=%d, top_n=%d)",
                     len(articles), len(filtered), self._min_score, self._top_n)

        ctx.set("articles", filtered)
        return ctx

    def _score_articles(self, articles: list[Article]) -> list[Article]:
        entries = "\n".join(
            f"{i+1}. [{a.title}]({a.link}) — {a.source}\n   {a.summary[:200]}"
            for i, a in enumerate(articles)
        )
        prompt = (
            "Score each article 1-10 on importance/novelty for a tech professional's morning briefing.\n"
            "Return JSON only: [{\"index\": 1, \"score\": 7}, ...]\n\n"
            f"{entries}"
        )
        response = self._llm.chat([
            {"role": "system", "content": "You are a news editor. Return JSON only."},
            {"role": "user", "content": prompt},
        ])

        scores = self._parse_scores(response, len(articles))
        for i, score in enumerate(scores):
            if i < len(articles):
                articles[i].score = score
        return articles

    def _parse_scores(self, response: str, count: int) -> list[int]:
        # Try JSON parse first
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return [int(item.get("score", 5)) for item in data[:count]]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        # Fallback: extract JSON array from text
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [int(item.get("score", 5)) for item in data[:count]]
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        # Ultimate fallback: give all articles a neutral score
        logger.warning("Could not parse LLM scores, using defaults")
        return [7] * count
