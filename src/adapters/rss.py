import logging
import socket
import urllib.error
from datetime import datetime
from time import mktime
import feedparser

from src.models.article import RawArticle
from src.retry import retry_call

logger = logging.getLogger(__name__)

_RETRYABLE_RSS_EXCEPTIONS = (urllib.error.URLError, OSError, socket.timeout)


class RSSAdapter:
    def __init__(
        self,
        timeout: int = 30,
        max_articles: int = 20,
        retry_attempts: int = 3,
        retry_backoff: float = 1.0,
    ):
        self.timeout = timeout
        self.max_articles = max_articles
        self.retry_attempts = retry_attempts
        self.retry_backoff = retry_backoff

    def fetch(self, url: str, source_name: str, max_articles: int | None = None) -> list[RawArticle]:
        limit = max_articles if max_articles is not None else self.max_articles
        articles: list[RawArticle] = []

        try:
            feed = retry_call(
                feedparser.parse,
                url,
                max_attempts=self.retry_attempts,
                backoff_seconds=self.retry_backoff,
                retryable_exceptions=_RETRYABLE_RSS_EXCEPTIONS,
                logger=logger,
            )
        except _RETRYABLE_RSS_EXCEPTIONS:
            logger.warning("RSS fetch failed after retries: %s (%s)", source_name, url)
            return []

        if feed.bozo:
            logger.warning("RSS parse warning for %s: %s", source_name, feed.bozo_exception)
            if not feed.entries:
                return []

        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            published = datetime.now()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime.fromtimestamp(mktime(entry.published_parsed))
                except (OverflowError, ValueError, TypeError):
                    pass

            articles.append(RawArticle(
                title=title,
                link=link,
                summary=entry.get("summary", ""),
                published=published,
                source=source_name,
            ))

        return articles
