import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

JINA_BASE = "https://r.jina.ai"


class JinaFetcher:
    """Fetch via Jina Reader — free, returns clean Markdown. No API key needed."""

    @property
    def name(self) -> str:
        return "jina"

    def fetch(self, url: str, *, timeout: int = 15, max_chars: int = 3000) -> str:
        jina_url = f"{JINA_BASE}/{url}"
        try:
            req = urllib.request.Request(
                jina_url,
                headers={
                    "Accept": "text/markdown",
                    "User-Agent": "ai-daily/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return text[:max_chars]
        except urllib.error.HTTPError as e:
            logger.debug("JinaFetcher HTTP %s for %s", e.code, url)
            return ""
        except Exception:
            logger.debug("JinaFetcher failed for %s", url, exc_info=True)
            return ""
