import json
import logging
import re
from src.pipeline.stage import PipelineContext
from src.adapters.llm import LLMAdapter
from src.models.article import Article
from src.models.scored_article import Bucket, ScoredArticle

logger = logging.getLogger(__name__)


class ScoringStage:
    """3-dimensional article scoring: Impact, Novelty, Actionability.

    Reads ctx["articles"] (with content already populated by FetchContentStage),
    scores each article via LLM, assigns bucket labels via deterministic rules,
    and writes ctx["scored_articles"].
    """

    def __init__(self, llm_adapter: LLMAdapter):
        self._llm = llm_adapter

    def process(self, ctx: PipelineContext) -> PipelineContext:
        articles: list[Article] = ctx.get("articles", [])
        if not articles:
            ctx.set("scored_articles", [])
            return ctx

        scores = self._score_batch(articles)
        score_by_index = {}
        for s in scores:
            idx = s.get("index", 0)
            score_by_index[idx] = s

        scored = []
        for i, a in enumerate(articles):
            s = score_by_index.get(i + 1, {"impact": 5, "novelty": 5, "actionability": 5})
            impact = self._clamp(s.get("impact", 5), 1, 10)
            novelty = self._clamp(s.get("novelty", 5), 1, 10)
            actionability = self._clamp(s.get("actionability", 5), 1, 10)
            bucket = self._assign_bucket(impact, novelty, actionability)
            scored.append(ScoredArticle(
                article=a,
                impact=impact,
                novelty=novelty,
                actionability=actionability,
                bucket=bucket,
            ))

        alphas = sum(1 for s in scored if s.bucket == Bucket.ALPHA)
        betas = sum(1 for s in scored if s.bucket == Bucket.BETA)
        gammas = sum(1 for s in scored if s.bucket == Bucket.GAMMA)
        logger.info("Scored %d articles: Alpha=%d Beta=%d Gamma=%d",
                     len(scored), alphas, betas, gammas)
        ctx.set("scored_articles", scored)
        return ctx

    def _score_batch(self, articles: list[Article]) -> list[dict]:
        entries = "\n".join(
            f"{i+1}. [{a.title}]({a.link}) — {a.source}\n"
            f"   {a.content[:600] if a.content else (a.summary or '')[:300]}"
            for i, a in enumerate(articles)
        )
        prompt = (
            "Score each article on three independent dimensions (1-10):\n"
            "- impact: how much this changes the AI industry landscape\n"
            "- novelty: how new / surprising / non-obvious this is\n"
            "- actionability: can a practitioner take concrete action based on this\n\n"
            "Return JSON only: "
            '[{"index":1,"impact":8,"novelty":7,"actionability":6}, ...]\n\n'
            f"{entries}"
        )
        response = self._llm.chat([
            {"role": "system", "content": "You are an AI industry analyst. Return JSON only."},
            {"role": "user", "content": prompt},
        ])
        return self._parse_scores(response, len(articles))

    def _parse_scores(self, response: str, count: int) -> list[dict]:
        # Direct parse
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data[:count]
        except (json.JSONDecodeError, TypeError):
            pass
        # Extract from code block
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if match:
            try:
                data = json.loads(match.group(1))
                if isinstance(data, list):
                    return data[:count]
            except (json.JSONDecodeError, TypeError):
                pass
        # Extract JSON array
        match = re.search(r'\[[\s\S]*\]', response)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return data[:count]
            except (json.JSONDecodeError, TypeError):
                pass
        logger.warning("Could not parse scoring JSON, using defaults")
        return [{"impact": 5, "novelty": 5, "actionability": 5}] * count

    @staticmethod
    def _assign_bucket(impact: int, novelty: int, actionability: int) -> Bucket:
        total_score = 0.5 * impact + 0.3 * novelty + 0.2 * actionability
        if impact >= 8 and novelty >= 7:
            return Bucket.ALPHA
        if total_score >= 5.0 or impact >= 6:
            return Bucket.BETA
        return Bucket.GAMMA

    @staticmethod
    def _clamp(value: int, lo: int, hi: int) -> int:
        return max(lo, min(hi, int(value)))
