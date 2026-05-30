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

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        raise NotImplementedError("OpenAILikeAdapter requires Phase 2 implementation")
