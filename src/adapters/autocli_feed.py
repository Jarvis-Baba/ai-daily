"""Autocli feed adapter — wrap any autocli platform as a feed source."""

import json
import logging
import re
import subprocess
from datetime import datetime, timezone

from src.models.article import RawArticle

logger = logging.getLogger(__name__)

AUTOCLI = "autocli"

# Known field mappings: autocli JSON keys → RawArticle fields
# Each platform returns slightly different JSON schemas.
FIELD_MAPS = {
    "hackernews": {
        "title": ["title"],
        "link": ["url", "link"],
        "summary": ["description", "summary", "snippet"],
        "published": ["time", "published", "date", "created"],
    },
    "medium": {
        "title": ["title"],
        "link": ["url", "link"],
        "summary": ["subtitle", "description", "summary", "snippet"],
        "published": ["published", "date", "created", "updated"],
    },
    "zhihu": {
        "title": ["title", "question_title"],
        "link": ["url", "link"],
        "summary": ["excerpt", "summary", "description", "content"],
        "published": ["created", "published", "date", "updated"],
    },
    "arxiv": {
        "title": ["title"],
        "link": ["url", "link", "id"],
        "summary": ["summary", "abstract", "description"],
        "published": ["published", "updated", "date"],
    },
}


class AutocliFeedAdapter:
    """Generic feed adapter backed by autocli commands.

    Config format (in config.yaml feeds section):
      - name: "HN Top"
        url: "hackernews top --limit 10"    # autocli command + args
        enabled: true
        feed_type: autocli
    """

    def fetch(self, url: str, source_name: str,
              max_articles: int | None = None) -> list[RawArticle]:
        """url is the autocli command string, e.g. 'hackernews top --limit 10'."""
        platform = url.split()[0]

        # Build command
        cmd = [AUTOCLI] + url.split() + ["--format", "json"]
        if max_articles and "--limit" not in url:
            cmd.insert(-2, "--limit")
            cmd.insert(-2, str(max_articles))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            logger.warning("autocli timeout for %s", source_name)
            return []
        except FileNotFoundError:
            logger.warning("autocli not found")
            return []

        if result.returncode != 0:
            logger.warning("autocli failed for %s: %s", source_name, result.stderr[:200])
            return []

        data = self._parse_json(result.stdout)
        if not isinstance(data, list):
            # Some platforms return {posts: [...]} or {data: [...]}
            if isinstance(data, dict):
                for key in ("posts", "data", "items", "results", "stories"):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
                else:
                    logger.warning("Unexpected autocli response shape for %s", source_name)
                    return []
            else:
                return []

        articles = []
        field_map = FIELD_MAPS.get(platform, {})

        for item in data:
            if not isinstance(item, dict):
                continue

            title = self._pick(item, field_map.get("title", ["title"]))
            link = self._pick(item, field_map.get("link", ["url", "link"]))
            if not title or not link:
                continue

            summary = self._pick(item, field_map.get("summary", ["summary", "description"]))
            published = self._parse_date(
                self._pick(item, field_map.get("published", ["published", "date"]))
            )

            articles.append(RawArticle(
                title=str(title)[:200],
                link=str(link),
                summary=str(summary)[:500] if summary else "",
                published=published,
                source=source_name,
            ))

        logger.info("AutocliFeed: %d articles from %s", len(articles), source_name)
        return articles

    @staticmethod
    def _pick(obj: dict, keys: list[str]) -> str | None:
        for k in keys:
            val = obj.get(k)
            if val and str(val).strip():
                return str(val).strip()
        return None

    @staticmethod
    def _parse_date(val: str | None) -> datetime:
        if not val:
            return datetime.now(timezone.utc)
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=timezone.utc)
        val = str(val).strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
            "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
        ):
            try:
                return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_json(text: str):
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r'[\[{][\s\S]*[}\]]', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None
