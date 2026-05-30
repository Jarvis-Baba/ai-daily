import logging
import socket
import urllib.error
from typing import Protocol, runtime_checkable

from openai import OpenAI
from src.retry import retry_call

logger = logging.getLogger(__name__)

_RETRYABLE_LLM_EXCEPTIONS = (urllib.error.URLError, OSError, socket.timeout)


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
    """OpenAI-compatible API adapter (DeepSeek, OpenAI, etc.)."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        retry_attempts: int = 3,
        retry_backoff: float = 2.0,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.retry_attempts = retry_attempts
        self.retry_backoff = retry_backoff
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com",
        )

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        return retry_call(
            self._do_chat,
            messages,
            max_attempts=self.retry_attempts,
            backoff_seconds=self.retry_backoff,
            retryable_exceptions=_RETRYABLE_LLM_EXCEPTIONS,
            logger=logger,
            **kwargs,
        )

    def _do_chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2000),
        )
        return response.choices[0].message.content
