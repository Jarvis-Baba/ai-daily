"""Blog scraper adapter — fetch articles from blog index pages via Firecrawl."""

import logging
import re
import subprocess
from datetime import datetime, timezone
from urllib.parse import urljoin

from src.models.article import RawArticle

logger = logging.getLogger(__name__)

BRIDGE = "/home/jarvis/scripts/firecrawl_bridge.py"

# URL patterns that look like article links on each blog
SITE_RULES = {
    "https://www.anthropic.com/research": {
        "link_pattern": re.compile(r"/research/[^/\s)]+"),
        "base": "https://www.anthropic.com",
        "exclude": re.compile(r"/research/team"),
    },
    "https://openai.com/blog": {
        "link_pattern": re.compile(r"/index/[^/\s)]+"),
        "base": "https://openai.com",
    },
    "https://huggingface.co/papers": {
        "link_pattern": re.compile(r"/papers/[^/\s)]+"),
        "base": "https://huggingface.co",
    },
    "https://github.com/trending": {
        "link_pattern": re.compile(r"/(?!trending)[^/\s)]+/[^/\s)]+"),
        "base": "https://github.com",
    },
}


class BlogScraper:
    """Scrape blog index pages via Firecrawl, parse article links from markdown.

    Duck-typed interface matching RSSAdapter:
        fetch(url, source_name, max_articles) -> list[RawArticle]
    """

    def fetch(self, url: str, source_name: str,
              max_articles: int | None = None) -> list[RawArticle]:
        limit = max_articles or 10

        try:
            articles = self._scrape_index(url, source_name)
        except Exception as e:
            logger.warning("BlogScraper failed for %s: %s", source_name, e)
            return []

        return articles[:limit]

    def _scrape_index(self, url: str, source_name: str) -> list[RawArticle]:
        # 1. Scrape the blog index page with Firecrawl
        result = subprocess.run(
            ["python3", BRIDGE, "scrape", url, "--timeout", "30000"],
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            logger.warning("Firecrawl bridge failed for %s: %s", url, result.stderr[:200])
            return []

        markdown = result.stdout
        if not markdown or len(markdown) < 100:
            logger.warning("Firecrawl returned empty/short content for %s", url)
            return []

        # 2. Parse article links from markdown
        articles = self._parse_links(markdown, url, source_name)
        logger.info("BlogScraper: %d articles from %s", len(articles), source_name)
        return articles

    def _parse_links(self, markdown: str, page_url: str,
                     source_name: str) -> list[RawArticle]:
        """Extract article links and titles from the scraped markdown."""
        rule = SITE_RULES.get(page_url.rstrip("/"))
        base = rule["base"] if rule else page_url
        link_pattern = rule["link_pattern"] if rule else None
        exclude_pattern = rule.get("exclude") if rule else None

        seen_urls = set()
        articles = []

        # Strategy 1: Use known link patterns for the site
        if link_pattern:
            for match in link_pattern.finditer(markdown):
                path = match.group()
                if exclude_pattern and exclude_pattern.search(path):
                    continue
                full_url = urljoin(base, path)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = self._extract_title_for_link(markdown, path)
                if not title or len(title) < 5:
                    continue  # skip obvious non-article links

                articles.append(RawArticle(
                    title=title,
                    link=full_url,
                    summary="",
                    published=datetime.now(timezone.utc),
                    source=source_name,
                ))

        # Strategy 2: Fallback — all markdown links that look like articles
        if not articles:
            md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', markdown)
            for title, href in md_links:
                if not title or len(title) < 3:
                    continue
                if href.startswith("#") or href.startswith("mailto:"):
                    continue
                full_url = urljoin(base, href)
                if full_url in seen_urls:
                    continue
                # Only include links that are child paths of the blog
                if not full_url.startswith(base):
                    continue
                seen_urls.add(full_url)
                articles.append(RawArticle(
                    title=title.strip(),
                    link=full_url,
                    summary="",
                    published=datetime.now(timezone.utc),
                    source=source_name,
                ))

        return articles

    @staticmethod
    def _extract_title_for_link(markdown: str, path: str) -> str:
        """Extract clean title from markdown link text for a given URL path."""
        escaped = re.escape(path)
        # Find full markdown link: [text...](...path...)
        match = re.search(rf'\[([^\]]*{escaped}[^\]]*)\]\([^)]*{escaped}[^)]*\)', markdown)
        if not match:
            # Try simpler: find any link with this path
            match = re.search(rf'\[([^\]]+)\]\([^)]*{escaped}[^)]*\)', markdown)
        if not match:
            return ""

        link_text = match.group(1)

        # Strategy 1: Extract bold text (article title is usually **bold**)
        bold_match = re.search(r'\*\*([^*]+)\*\*', link_text)
        if bold_match:
            return bold_match.group(1).strip()

        # Strategy 2: First line before any \\ or newline
        first_line = link_text.split("\\\\")[0].split("\\")[0].strip()
        # Remove common metadata prefixes like "CategoryMon DD, YYYY"
        cleaned = re.sub(r'^[A-Z][a-z]+[A-Z][a-z]+\s*\d{1,2},\s*\d{4}\s*', '', first_line)
        cleaned = re.sub(r'^[A-Z][a-z]+\d{1,2},\s*\d{4}\s*', '', cleaned)
        if cleaned.strip():
            return cleaned.strip()

        return first_line[:80]


# ── Composite adapter: dispatch by feed config ──


class CompositeFeedAdapter:
    """Routes feeds to correct adapter based on feed_type."""

    def __init__(self, rss_adapter, blog_scraper=None, autocli_adapter=None, sec_adapter=None):
        self._rss = rss_adapter
        self._blog = blog_scraper or BlogScraper()
        self._autocli = autocli_adapter
        self._sec = sec_adapter
        self._reddit = None
        self._github_search = None
        self._meta_ai_blog = None

    def fetch(self, url: str, source_name: str,
              max_articles: int | None = None,
              feed_type: str = "rss") -> list[RawArticle]:
        if feed_type == "blog":
            return self._blog.fetch(url, source_name, max_articles)
        if feed_type == "autocli":
            if self._autocli is None:
                from src.adapters.autocli_feed import AutocliFeedAdapter
                self._autocli = AutocliFeedAdapter()
            return self._autocli.fetch(url, source_name, max_articles)
        if feed_type == "sec":
            if self._sec is None:
                from src.adapters.sec_edgar import SECEdgarAdapter
                self._sec = SECEdgarAdapter()
            return self._sec.fetch(url, source_name, max_articles)
        if feed_type in ("reddit", "reddit_json"):
            if self._reddit is None:
                from src.adapters.reddit_json import RedditJsonAdapter
                self._reddit = RedditJsonAdapter()
            return self._reddit.fetch(url, source_name, max_articles)
        if feed_type in ("github_search", "github_trending"):
            if self._github_search is None:
                from src.adapters.github_search import GitHubSearchAdapter
                self._github_search = GitHubSearchAdapter()
            return self._github_search.fetch(url, source_name, max_articles)
        if feed_type == "meta_ai_blog":
            if self._meta_ai_blog is None:
                from src.adapters.meta_ai_blog import MetaAIBlogAdapter
                self._meta_ai_blog = MetaAIBlogAdapter()
            return self._meta_ai_blog.fetch(url, source_name, max_articles)
        return self._rss.fetch(url, source_name, max_articles)
