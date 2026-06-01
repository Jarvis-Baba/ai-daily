import logging
import re
from dataclasses import dataclass, field

from src.adapters.fetchers.base import ContentFetcher
from src.adapters.fetchers.basic import BasicFetcher
from src.adapters.fetchers.jina import JinaFetcher
from src.adapters.fetchers.firecrawl import FirecrawlFetcher

logger = logging.getLogger(__name__)

# Built-in fetcher registry — name → instance
_BUILTIN: dict[str, ContentFetcher] = {
    "basic": BasicFetcher(),
    "jina": JinaFetcher(),
    "firecrawl": FirecrawlFetcher(),
}


@dataclass
class FetcherRoute:
    pattern: str  # domain substring or "*" for catch-all
    fetchers: list[str]  # ordered list of fetcher names to try


class ContentRouter:
    """Dispatch URL to fetcher chain based on domain pattern matching.

    Routes are tried in declaration order: first pattern match wins.
    Within a route, fetchers are tried in order until one returns non-empty content.
    """

    def __init__(self, routes: list[FetcherRoute] | None = None,
                 fetchers: dict[str, ContentFetcher] | None = None):
        self._routes = routes or []
        self._fetchers = fetchers or {}
        self._stats: dict[str, dict[str, int]] = {}  # fetcher_name → {ok, fail}

    def register(self, name: str, fetcher: ContentFetcher) -> None:
        self._fetchers[name] = fetcher

    def fetch(self, url: str, *, timeout: int = 10, max_chars: int = 3000) -> str:
        fetcher_names = self._resolve(url)
        if not fetcher_names:
            fetcher_names = ["basic"]

        for name in fetcher_names:
            fetcher = self._fetchers.get(name)
            if fetcher is None:
                fetcher = _BUILTIN.get(name)
            if fetcher is None:
                logger.warning("Unknown fetcher: %s", name)
                continue

            try:
                text = fetcher.fetch(url, timeout=timeout, max_chars=max_chars)
            except Exception:
                logger.debug("%s raised for %s", name, url, exc_info=True)
                text = ""

            self._record(name, bool(text))
            if text:
                logger.debug("fetcher=%s url=%s chars=%d", name, url[:80], len(text))
                return text

        return ""

    def _resolve(self, url: str) -> list[str]:
        for route in self._routes:
            if route.pattern == "*" or route.pattern in url:
                return list(route.fetchers)
        return []

    def _record(self, name: str, success: bool) -> None:
        if name not in self._stats:
            self._stats[name] = {"ok": 0, "fail": 0}
        key = "ok" if success else "fail"
        self._stats[name][key] += 1

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    @property
    def fetcher_names(self) -> list[str]:
        """All available fetcher names (custom + built-in)."""
        names = set(self._fetchers.keys()) | set(_BUILTIN.keys())
        return sorted(names)

    @classmethod
    def from_config(cls, config) -> "ContentRouter":
        """Build router from AppConfig's content.routes section."""
        routes = []
        route_cfgs = getattr(config.content, "routes", None) or []
        for rc in route_cfgs:
            routes.append(FetcherRoute(
                pattern=rc.get("pattern", "*"),
                fetchers=rc.get("fetchers", ["jina", "basic"]),
            ))
        return cls(routes=routes)
