import logging
import re
import urllib.request
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, stripping scripts/styles."""

    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.skip = False
        self._skip_tags = {"script", "style", "noscript", "head"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self.skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self.skip = False
        if tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "div", "section", "article"):
            self.text.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data.strip())

    def get_text(self) -> str:
        raw = " ".join(self.text)
        # Collapse whitespace
        raw = re.sub(r'\s+', ' ', raw)
        return raw.strip()


def fetch_content(url: str, timeout: int = 10, max_chars: int = 3000) -> str:
    """Fetch a URL and extract readable text. Returns empty string on failure."""
    # Only allow http/https — URLs come from config, defense-in-depth
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ai-daily/1.0 (news-briefing-bot)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return ""  # not an HTML page
            html = resp.read().decode("utf-8", errors="replace")[:500_000]

        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        return text[:max_chars]
    except Exception:
        logger.debug("Failed to fetch content from %s", url, exc_info=True)
        return ""
