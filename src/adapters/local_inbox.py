"""Read Signal Inbox P0 export and convert to AI Daily Article objects.

This is a read-only extra input — it does NOT modify the 13-stage pipeline.
Articles from this source pass through the same Filter / Scoring / Theme /
Summarize / Synthesize stages as all other articles.

Usage (in FetchStage):
    from src.adapters.local_inbox import load_signal_inbox_articles
    extra_articles = load_signal_inbox_articles("/path/to/ai_daily_candidates.json")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from src.models.article import Article

logger = logging.getLogger(__name__)


def load_signal_inbox_articles(export_path: str, max_items: int = 15) -> list[Article]:
    """Load P0 signals from Signal Inbox export, return as Article list.

    Only reads the file — filtering, scoring, and curation still happen
    downstream in AI Daily's own pipeline stages.  Capped at max_items
    to prevent flooding the LLM filter budget.
    """
    path = Path(export_path)
    if not path.exists():
        logger.info("Signal Inbox export not found: %s — skipping", export_path)
        return []

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read Signal Inbox export: %s", e)
        return []

    items = data.get("items", [])
    if not items:
        return []

    logger.info("Signal Inbox: %d P0 candidates available, loading ≤%d",
                 len(items), max_items)

    articles = []
    for item in items[:max_items]:
        published = _parse_date(item.get("published_at", ""))
        summary = item.get("summary", "") or ""
        source_label = f"[SI] {item.get('source', 'unknown')}"

        articles.append(Article(
            title=item.get("title", "Untitled"),
            link=item.get("url", ""),
            summary=summary,
            published=published,
            source=source_label,
        ))

    logger.info("Signal Inbox: loaded %d articles as extra input", len(articles))
    return articles


def _parse_date(date_str: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime.now()
