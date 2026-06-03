"""Fetch raw HTTP response bytes for content hash computation.

Current fetchers (BasicFetcher, JinaFetcher, FirecrawlFetcher) all return
truncated text, unsuitable for hashing. This module returns the raw bytes
and content-type header for accurate SHA256 computation.
"""
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

USER_AGENT = "ai-daily/1.0 (news-briefing-bot; L0 Source Compiler)"


def fetch_raw(url: str, *, timeout: int = 15, max_bytes: int = 2_000_000) -> tuple[bytes, str]:
    """Fetch raw HTTP response body and content-type header.

    Returns (b"", "") on any failure. Caller must handle fallback.
    max_bytes caps response to prevent OOM on large pages (default 2 MB).
    """
    if not url.startswith(("http://", "https://")):
        return b"", ""

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_bytes)
            return raw, content_type
    except Exception:
        logger.debug("Raw fetch failed for %s", url, exc_info=True)
        return b"", ""
