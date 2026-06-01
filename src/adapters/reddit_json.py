"""Reddit listing adapter backed by Reddit's public JSON endpoints."""

import json
import logging
import shlex
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from src.models.article import RawArticle

logger = logging.getLogger(__name__)

USER_AGENT = "ai-daily/1.0 by jarvis"


class RedditJsonAdapter:
    """Fetch subreddit listings without depending on page scraping.

    Config examples:
      url: "MachineLearning top week"
      url: "MachineLearning new"
      url: "https://www.reddit.com/r/MachineLearning/top.json?t=week"
    """

    def fetch(self, url: str, source_name: str,
              max_articles: int | None = None) -> list[RawArticle]:
        limit = max_articles or 20
        endpoint = self._endpoint_from_config(url, limit)
        try:
            req = urllib.request.Request(endpoint, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("RedditJsonAdapter failed for %s: %s", source_name, e)
            return []

        children = payload.get("data", {}).get("children", [])
        articles: list[RawArticle] = []
        for child in children[:limit]:
            data = child.get("data", {})
            title = (data.get("title") or "").strip()
            permalink = data.get("permalink") or ""
            if not title or not permalink:
                continue

            created = data.get("created_utc")
            published = datetime.now(timezone.utc)
            if isinstance(created, (int, float)):
                published = datetime.fromtimestamp(created, tz=timezone.utc)

            score = data.get("score", 0)
            comments = data.get("num_comments", 0)
            external_url = data.get("url") or ""
            summary = data.get("selftext") or data.get("link_flair_text") or ""
            if external_url and external_url != f"https://www.reddit.com{permalink}":
                summary = f"{summary}\nExternal: {external_url}".strip()
            summary = f"score={score}; comments={comments}\n{summary}".strip()

            articles.append(RawArticle(
                title=title[:200],
                link=f"https://www.reddit.com{permalink}",
                summary=summary[:800],
                published=published,
                source=source_name,
            ))

        logger.info("RedditJsonAdapter: %d posts from %s", len(articles), source_name)
        return articles

    @staticmethod
    def _endpoint_from_config(config_value: str, limit: int) -> str:
        if config_value.startswith("http://") or config_value.startswith("https://"):
            parsed = urllib.parse.urlparse(config_value)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            query.setdefault("limit", str(limit))
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))

        parts = shlex.split(config_value)
        subreddit = parts[0].removeprefix("r/") if parts else "MachineLearning"
        sort = parts[1] if len(parts) > 1 else "top"
        time_window = parts[2] if len(parts) > 2 else "week"
        sort = sort if sort in {"hot", "new", "top", "rising"} else "top"
        query = {"limit": str(limit)}
        if sort == "top":
            query["t"] = time_window
        return f"https://www.reddit.com/r/{subreddit}/{sort}.json?{urllib.parse.urlencode(query)}"
