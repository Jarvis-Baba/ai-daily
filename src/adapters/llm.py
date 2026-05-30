from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMAdapter(Protocol):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send messages to LLM, return response text."""
        ...


class DummyAdapter:
    """Phase 1 no-op adapter. Returns last user message content unchanged."""

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return f"[DUMMY RESPONSE] {msg['content']}"
        return "[DUMMY RESPONSE] No user message found."


class OpenAILikeAdapter:
    """OpenAI-compatible API adapter. For Phase 2 use."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        retry_attempts: int = 3,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.retry_attempts = retry_attempts

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        # Phase 2: wrap the API call with retry_call() for network resilience.
        # Example pattern:
        #   import urllib.error, socket
        #   from src.retry import retry_call
        #   return retry_call(
        #       self._do_api_call, messages, **kwargs,
        #       max_attempts=self.retry_attempts,
        #       backoff_seconds=2.0,
        #       retryable_exceptions=(urllib.error.URLError, OSError, socket.timeout),
        #       logger=logging.getLogger(__name__),
        #   )
        raise NotImplementedError("OpenAILikeAdapter requires Phase 2 implementation")
