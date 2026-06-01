"""Meta AI blog adapter with sitemap and HTML fallbacks."""

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

from src.models.article import RawArticle

logger = logging.getLogger(__name__)

USER_AGENT = "ai-daily/1.0"
DEFAULT_SITEMAP = "https://ai.meta.com/sitemap.xml"


class _MetaLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href = ""
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if "/blog/" in href:
            self._current_href = href
            self._buffer = []

    def handle_data(self, data):
        if self._current_href:
            self._buffer.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._current_href:
            title = " ".join(part for part in self._buffer if part).strip()
            self.links.append((self._current_href, title))
            self._current_href = ""
            self._buffer = []


class MetaAIBlogAdapter:
    """Fetch Meta AI blog links without relying on Firecrawl output shape."""

    def fetch(self, url: str, source_name: str,
              max_articles: int | None = None) -> list[RawArticle]:
        limit = max_articles or 20
        base_url = url or "https://ai.meta.com/blog/"
        articles = self._from_sitemap(limit, source_name)
        if not articles:
            articles = self._from_blog_index(base_url, limit, source_name)
        logger.info("MetaAIBlogAdapter: %d articles from %s", len(articles), source_name)
        return articles[:limit]

    def _from_sitemap(self, limit: int, source_name: str) -> list[RawArticle]:
        try:
            xml = self._read(DEFAULT_SITEMAP, timeout=20)
            root = ET.fromstring(xml)
        except Exception as e:
            logger.debug("Meta sitemap failed: %s", e)
            return []

        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls: list[tuple[str, str]] = []
        for url_node in root.findall(".//sm:url", ns):
            loc = (url_node.findtext("sm:loc", default="", namespaces=ns) or "").strip()
            lastmod = (url_node.findtext("sm:lastmod", default="", namespaces=ns) or "").strip()
            if "/blog/" in loc and loc.rstrip("/") != "https://ai.meta.com/blog":
                urls.append((loc, lastmod))

        articles = []
        for loc, lastmod in urls[:limit]:
            articles.append(RawArticle(
                title=self._title_from_url(loc),
                link=loc,
                summary="",
                published=self._parse_date(lastmod),
                source=source_name,
            ))
        return articles

    def _from_blog_index(self, url: str, limit: int, source_name: str) -> list[RawArticle]:
        try:
            html = self._read(url, timeout=25)
        except Exception as e:
            logger.warning("MetaAIBlogAdapter failed for %s: %s", source_name, e)
            return []

        parser = _MetaLinkParser()
        parser.feed(html)
        seen = set()
        articles = []
        for href, title in parser.links:
            link = href if href.startswith("http") else f"https://ai.meta.com{href}"
            if link in seen:
                continue
            seen.add(link)
            articles.append(RawArticle(
                title=title or self._title_from_url(link),
                link=link,
                summary="",
                published=datetime.now(timezone.utc),
                source=source_name,
            ))
            if len(articles) >= limit:
                break
        return articles

    @staticmethod
    def _read(url: str, timeout: int) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    @staticmethod
    def _title_from_url(url: str) -> str:
        slug = url.rstrip("/").split("/")[-1]
        return re.sub(r"[-_]+", " ", slug).strip().title()

    @staticmethod
    def _parse_date(value: str) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
