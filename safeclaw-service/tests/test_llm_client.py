"""Tests for the OpenAI-compatible LLM client wrapper."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from safeclaw.config import SafeClawConfig


def test_create_client_with_new_provider():
    """create_client uses llm_provider + llm_api_key when set."""
    from safeclaw.llm.client import create_client

    with patch("safeclaw.llm.client.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        config = SafeClawConfig(llm_provider="openai", llm_api_key="sk-test")
        client = create_client(config)
        assert client is not None
        assert client.model == "gpt-4o-mini"
        assert client.model_large == "gpt-4o"
        mock_cls.assert_called_once_with(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )


def test_create_client_legacy_mistral_fallback():
    """create_client falls back to mistral_api_key when llm_provider is not set."""
    from safeclaw.llm.client import create_client

    with patch("safeclaw.llm.client.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        config = SafeClawConfig(mistral_api_key="old-mistral-key")
        client = create_client(config)
        assert client is not None
        assert client.model == "mistral-small-latest"
        mock_cls.assert_called_once_with(
            api_key="old-mistral-key",
            base_url="https://api.mistral.ai/v1",
        )


def test_create_client_new_provider_overrides_legacy():
    """When both llm_provider and mistral_api_key are set, llm_provider wins."""
    from safeclaw.llm.client import create_client

    with patch("safeclaw.llm.client.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        config = SafeClawConfig(
            llm_provider="groq",
            llm_api_key="gsk-new",
            mistral_api_key="old-key",
        )
        client = create_client(config)
        assert client is not None
        assert client.model == "llama-3.3-70b-versatile"
        mock_cls.assert_called_once_with(
            api_key="gsk-new",
            base_url="https://api.groq.com/openai/v1",
        )


def test_create_client_custom_provider():
    """create_client works with custom provider using user-supplied base_url."""
    from safeclaw.llm.client import create_client

    with patch("safeclaw.llm.client.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        config = SafeClawConfig(
            llm_provider="custom",
            llm_api_key="my-key",
            llm_base_url="http://localhost:11434/v1",
            llm_model="llama3",
        )
        client = create_client(config)
        assert client is not None
        assert client.model == "llama3"
        mock_cls.assert_called_once_with(
            api_key="my-key",
            base_url="http://localhost:11434/v1",
        )


def test_create_client_custom_provider_no_key():
    """Custom provider works without API key (for Ollama etc.)."""
    from safeclaw.llm.client import create_client

    with patch("safeclaw.llm.client.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        config = SafeClawConfig(
            llm_provider="custom",
            llm_base_url="http://localhost:11434/v1",
            llm_model="llama3",
        )
        client = create_client(config)
        assert client is not None
        mock_cls.assert_called_once_with(
            api_key="unused",
            base_url="http://localhost:11434/v1",
        )


def test_create_client_no_key_no_provider_returns_none():
    """create_client returns None when no API key and no provider configured."""
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    assert client is None


def test_create_client_model_override():
    """llm_model and llm_model_large override provider defaults."""
    from safeclaw.llm.client import create_client

    with patch("safeclaw.llm.client.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        config = SafeClawConfig(
            llm_provider="openai",
            llm_api_key="sk-test",
            llm_model="gpt-3.5-turbo",
            llm_model_large="gpt-4-turbo",
        )
        client = create_client(config)
        assert client.model == "gpt-3.5-turbo"
        assert client.model_large == "gpt-4-turbo"


def test_create_client_unknown_provider_returns_none():
    """create_client returns None for an unknown provider ID."""
    from safeclaw.llm.client import create_client

    config = SafeClawConfig(llm_provider="nonexistent", llm_api_key="key")
    client = create_client(config)
    assert client is None


@pytest.mark.asyncio
async def test_chat_returns_content():
    """chat() calls OpenAI and returns the text content."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_openai = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from OpenAI"
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = SafeClawLLMClient(
        openai_client=mock_openai,
        model="gpt-4o-mini",
        model_large="gpt-4o",
        timeout_ms=3000,
    )
    result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
    assert result == "Hello from OpenAI"
    mock_openai.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_chat_timeout_returns_none():
    """chat() returns None on timeout."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))

    client = SafeClawLLMClient(
        openai_client=mock_openai,
        model="gpt-4o-mini",
        model_large="gpt-4o",
        timeout_ms=3000,
    )
    result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
    assert result is None


@pytest.mark.asyncio
async def test_chat_json_parses_response():
    """chat_json() parses JSON from LLM response."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_openai = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"suspicious": false}'
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = SafeClawLLMClient(
        openai_client=mock_openai,
        model="gpt-4o-mini",
        model_large="gpt-4o",
        timeout_ms=3000,
    )
    result = await client.chat_json(messages=[{"role": "user", "content": "review"}])
    assert result == {"suspicious": False}


@pytest.mark.asyncio
async def test_chat_json_invalid_json_returns_none():
    """chat_json() returns None when LLM response is not valid JSON."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_openai = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not json at all"
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = SafeClawLLMClient(
        openai_client=mock_openai,
        model="gpt-4o-mini",
        model_large="gpt-4o",
        timeout_ms=3000,
    )
    result = await client.chat_json(messages=[{"role": "user", "content": "review"}])
    assert result is None
