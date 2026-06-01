from typing import Protocol, runtime_checkable


@runtime_checkable
class ContentFetcher(Protocol):
    """Fetch full-text content from a URL. Returns empty string on failure."""

    @property
    def name(self) -> str:
        ...

    def fetch(self, url: str, *, timeout: int = 10, max_chars: int = 3000) -> str:
        ...
