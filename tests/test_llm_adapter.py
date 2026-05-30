from src.adapters.llm import DummyAdapter, LLMAdapter, OpenAILikeAdapter


def test_dummy_adapter_returns_predictable_text():
    adapter = DummyAdapter()
    result = adapter.chat([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Summarize: test article"},
    ])
    assert isinstance(result, str)
    assert len(result) > 0
    assert "test article" in result


def test_dummy_adapter_empty_messages():
    adapter = DummyAdapter()
    result = adapter.chat([])
    assert isinstance(result, str)


def test_dummy_adapter_conforms_to_protocol():
    adapter = DummyAdapter()
    assert isinstance(adapter, LLMAdapter)
