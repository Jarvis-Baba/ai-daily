import json
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta

from src.pipeline.stage import PipelineContext
from src.models.scored_article import ScoredArticle

logger = logging.getLogger(__name__)

SEED_THEMES: dict[str, dict] = {
    "anthropic_scaling": {
        "keywords": ["anthropic", "claude", "opus", "sonnet"],
    },
    "openai_evolution": {
        "keywords": ["openai", "gpt", "chatgpt", "codex", "operator"],
    },
    "ai_hardware": {
        "keywords": ["gpu", "chip", "groq", "nvidia", "inference", "tpu", "cerebras"],
    },
    "agent_stack": {
        "keywords": ["agent", "mcp", "tool use", "function calling", "autonomous"],
    },
    "regulation": {
        "keywords": ["regulation", "policy", "government", "omb", "compliance", "executive order"],
    },
    "opensource_ai": {
        "keywords": ["open source", "llama", "mistral", "open model", "weights", "fine-tune"],
    },
}


@dataclass
class ThemeState:
    keywords: list[str]
    first_seen: str = ""
    last_seen: str = ""
    consecutive_days: int = 0
    strength: float = 0.3


class ThemeMemory:
    """Persistent cross-day theme tracker. Stored in .theme-memory.json."""

    def __init__(self, path: str = ".theme-memory.json"):
        self._path = path
        self.themes: dict[str, ThemeState] = {}

    def load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    raw = json.load(f)
                for tid, data in raw.get("themes", {}).items():
                    self.themes[tid] = ThemeState(
                        keywords=data["keywords"],
                        first_seen=data["first_seen"],
                        last_seen=data["last_seen"],
                        consecutive_days=data.get("consecutive_days", 0),
                        strength=data.get("strength", 0.3),
                    )
                logger.debug("Loaded %d themes from %s", len(self.themes), self._path)
                return
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning("Corrupt theme memory, re-seeding: %s", e)
        self._seed()

    def _seed(self) -> None:
        for tid, data in SEED_THEMES.items():
            self.themes[tid] = ThemeState(keywords=data["keywords"])
        logger.info("Seeded %d default themes", len(self.themes))

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump({
                "themes": {
                    tid: {
                        "keywords": ts.keywords,
                        "first_seen": ts.first_seen,
                        "last_seen": ts.last_seen,
                        "consecutive_days": ts.consecutive_days,
                        "strength": round(ts.strength, 2),
                    }
                    for tid, ts in self.themes.items()
                }
            }, f, indent=2, ensure_ascii=False)
        logger.debug("Saved %d themes to %s", len(self.themes), self._path)

    def match(self, text: str) -> tuple[str | None, float]:
        """Return (best_theme_id, confidence) for the given article text."""
        text_lower = text.lower()
        best_id = None
        best_conf = 0.0

        for tid, ts in self.themes.items():
            matched = sum(1 for kw in ts.keywords if kw.lower() in text_lower)
            conf = matched / len(ts.keywords) if ts.keywords else 0.0
            if conf > best_conf:
                best_conf = conf
                best_id = tid

        if best_conf < 0.15:
            return None, 0.0
        return best_id, best_conf

    def trajectory(self, theme_id: str, today: date | None = None) -> str:
        """Determine trajectory for a theme on the given date (default today)."""
        _today = today or date.today()
        ts = self.themes.get(theme_id)
        if ts is None:
            return "NEW"
        if ts.consecutive_days >= 2:
            return "ACCELERATE"
        if ts.last_seen and ts.last_seen >= str(_today - timedelta(days=1)):
            return "CONTINUE"
        return "DECAY"

    def update_all(self, seen_theme_ids: set[str], today: date | None = None) -> None:
        """Update all themes: bump strength+consecutive for seen, decay for unseen."""
        _today = today or date.today()
        today_str = str(_today)
        yesterday_str = str(_today - timedelta(days=1))

        for tid, ts in self.themes.items():
            if tid in seen_theme_ids:
                if not ts.first_seen:
                    ts.first_seen = today_str
                # consecutive: +1 if was seen yesterday, else reset to 1
                if ts.last_seen == yesterday_str:
                    ts.consecutive_days += 1
                elif ts.last_seen != today_str:
                    ts.consecutive_days = 1
                ts.last_seen = today_str
                ts.strength = min(1.0, ts.strength + 0.15)
            else:
                # Decay: if not seen yesterday or today, reset consecutive
                if ts.last_seen and ts.last_seen < yesterday_str:
                    ts.consecutive_days = 0
                    ts.strength = max(0.05, ts.strength * 0.8)


class ThemeStage:
    """Cross-day theme tracker. Annotates each ScoredArticle with theme metadata.

    Reads ctx["scored_articles"], matches against ThemeMemory, annotates
    theme_id / theme_confidence / trajectory per article, persists memory.
    """

    def __init__(self, memory_path: str = ".theme-memory.json"):
        self._memory_path = memory_path

    def process(self, ctx: PipelineContext) -> PipelineContext:
        scored: list[ScoredArticle] = ctx.get("scored_articles", [])
        if not scored:
            return ctx

        memory = ThemeMemory(self._memory_path)
        memory.load()

        seen_ids: set[str] = set()
        for sa in scored:
            text = self._article_text(sa)
            theme_id, confidence = memory.match(text)
            if theme_id:
                sa.theme_id = theme_id
                sa.theme_confidence = round(confidence, 2)
                seen_ids.add(theme_id)

        report_date = ctx.get("report_date", date.today())

        for sa in scored:
            if sa.theme_id:
                sa.trajectory = memory.trajectory(sa.theme_id, today=report_date)
            else:
                sa.trajectory = "NEW"

        memory.update_all(seen_ids, today=report_date)
        memory.save()

        tagged = sum(1 for sa in scored if sa.theme_id)
        logger.info("Themes tagged: %d/%d articles, %d themes active",
                     tagged, len(scored), len(seen_ids))
        ctx.set("scored_articles", scored)
        return ctx

    @staticmethod
    def _article_text(sa: ScoredArticle) -> str:
        a = sa.article
        return f"{a.title} {a.summary} {a.content}"
