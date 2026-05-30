from unittest.mock import MagicMock, patch

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


def test_openai_like_adapter_initialization():
    """OpenAILikeAdapter creates an OpenAI client with the given params."""
    with patch("src.adapters.llm.OpenAI") as mock_openai:
        adapter = OpenAILikeAdapter(
            model="deepseek-chat",
            api_key="sk-test-key",
            base_url="https://api.deepseek.com",
        )
        assert adapter.model == "deepseek-chat"
        assert adapter.api_key == "sk-test-key"
        assert adapter.base_url == "https://api.deepseek.com"
        mock_openai.assert_called_once_with(
            api_key="sk-test-key",
            base_url="https://api.deepseek.com",
        )


def test_openai_like_adapter_default_base_url():
    """When base_url is None, defaults to https://api.deepseek.com."""
    with patch("src.adapters.llm.OpenAI") as mock_openai:
        adapter = OpenAILikeAdapter(
            model="deepseek-chat",
            api_key="sk-test-key",
        )
        mock_openai.assert_called_once_with(
            api_key="sk-test-key",
            base_url="https://api.deepseek.com",
        )


def test_openai_like_adapter_do_chat():
    """_do_chat calls the OpenAI client with correct model, messages, and defaults."""
    adapter = OpenAILikeAdapter(
        model="deepseek-chat",
        api_key="sk-test-key",
        base_url="https://api.deepseek.com",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from DeepSeek"
    adapter._client.chat.completions.create = MagicMock(return_value=mock_response)

    messages = [{"role": "user", "content": "Hi"}]
    result = adapter._do_chat(messages)

    assert result == "Hello from DeepSeek"
    adapter._client.chat.completions.create.assert_called_once_with(
        model="deepseek-chat",
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
    )


def test_openai_like_adapter_do_chat_custom_params():
    """_do_chat forwards temperature and max_tokens kwargs."""
    adapter = OpenAILikeAdapter(
        model="deepseek-chat",
        api_key="sk-test-key",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Custom"
    adapter._client.chat.completions.create = MagicMock(return_value=mock_response)

    result = adapter._do_chat(
        [{"role": "user", "content": "Hi"}],
        temperature=0.2,
        max_tokens=500,
    )

    assert result == "Custom"
    adapter._client.chat.completions.create.assert_called_once_with(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.2,
        max_tokens=500,
    )


def test_openai_like_adapter_chat_retry_wrapper():
    """chat() delegates to retry_call and ultimately _do_chat."""
    adapter = OpenAILikeAdapter(
        model="deepseek-chat",
        api_key="sk-test-key",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Retried response"
    adapter._client.chat.completions.create = MagicMock(return_value=mock_response)

    messages = [{"role": "user", "content": "Hello"}]
    result = adapter.chat(messages, temperature=0.5)

    assert result == "Retried response"
