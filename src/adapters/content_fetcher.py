"""Content fetching via router. Module-level router set by main.py at startup."""

import logging

from src.adapters.fetchers.basic import _TextExtractor

logger = logging.getLogger(__name__)

_router = None


def set_router(router) -> None:
    global _router
    _router = router


def get_router():
    return _router


def fetch_content(url: str, timeout: int = 10, max_chars: int = 3000) -> str:
    """Fetch full-text content from a URL. Delegates to configured router."""
    if _router is None:
        logger.warning("No router configured, falling back to basic fetch")
        from src.adapters.fetchers.basic import BasicFetcher
        return BasicFetcher().fetch(url, timeout=timeout, max_chars=max_chars)
    return _router.fetch(url, timeout=timeout, max_chars=max_chars)
