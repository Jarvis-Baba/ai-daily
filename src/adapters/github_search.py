"""GitHub trend adapter built on GitHub's repository search API."""

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from src.models.article import RawArticle

logger = logging.getLogger(__name__)

USER_AGENT = "ai-daily/1.0"


class GitHubSearchAdapter:
    """Rebuild a controllable GitHub Trending signal via Search API.

    Config examples:
      url: "stars:>100 pushed:>2026-05-24 topic:llm"
      url: "agent OR llm OR rag stars:>50"
    """

    def fetch(self, url: str, source_name: str,
              max_articles: int | None = None) -> list[RawArticle]:
        limit = max_articles or 20
        endpoint = self._endpoint_from_config(url, limit)
        try:
            req = urllib.request.Request(endpoint, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("GitHubSearchAdapter failed for %s: %s", source_name, e)
            return []

        articles: list[RawArticle] = []
        for item in payload.get("items", [])[:limit]:
            full_name = item.get("full_name") or item.get("name") or ""
            html_url = item.get("html_url") or ""
            if not full_name or not html_url:
                continue

            updated = self._parse_datetime(item.get("pushed_at") or item.get("updated_at"))
            description = item.get("description") or ""
            stars = item.get("stargazers_count", 0)
            forks = item.get("forks_count", 0)
            language = item.get("language") or "unknown"
            summary = f"{description}\nstars={stars}; forks={forks}; language={language}".strip()

            articles.append(RawArticle(
                title=full_name[:200],
                link=html_url,
                summary=summary[:800],
                published=updated,
                source=source_name,
            ))

        logger.info("GitHubSearchAdapter: %d repos from %s", len(articles), source_name)
        return articles

    @staticmethod
    def _endpoint_from_config(config_value: str, limit: int) -> str:
        if config_value.startswith("http://") or config_value.startswith("https://"):
            parsed = urllib.parse.urlparse(config_value)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            query.setdefault("per_page", str(limit))
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))

        since = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        query = config_value.strip() or f"stars:>100 pushed:>{since} topic:llm"
        if "pushed:" not in query and "created:" not in query:
            query = f"{query} pushed:>{since}"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(limit),
        }
        return "https://api.github.com/search/repositories?" + urllib.parse.urlencode(params)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
