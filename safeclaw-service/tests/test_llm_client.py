"""Tests for the Mistral client wrapper."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from safeclaw.config import SafeClawConfig


def test_create_client_returns_wrapper():
    """create_client returns a SafeClawLLMClient with correct config."""
    import sys

    mock_mistralai = MagicMock()
    sys.modules["mistralai"] = mock_mistralai
    try:
        # Force re-import after patching
        from safeclaw.llm.client import create_client

        config = SafeClawConfig(mistral_api_key="test-key-123")
        client = create_client(config)
        assert client is not None
        assert client.model == "mistral-small-latest"
        assert client.model_large == "mistral-large-latest"
        assert client.timeout_ms == 3000
    finally:
        del sys.modules["mistralai"]


def test_create_client_no_key_returns_none():
    """create_client returns None when no API key is configured."""
    from safeclaw.llm.client import create_client

    config = SafeClawConfig(mistral_api_key="")
    client = create_client(config)
    assert client is None


@pytest.mark.asyncio
async def test_chat_returns_content():
    """chat() calls Mistral and returns the text content."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from Mistral"
    mock_mistral.chat.complete_async = AsyncMock(return_value=mock_response)
    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
    assert result == "Hello from Mistral"
    mock_mistral.chat.complete_async.assert_called_once()


@pytest.mark.asyncio
async def test_chat_timeout_returns_none():
    """chat() returns None on timeout."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_mistral.chat.complete_async = AsyncMock(side_effect=Exception("timeout"))
    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat(messages=[{"role": "user", "content": "Hi"}])
    assert result is None


@pytest.mark.asyncio
async def test_chat_json_parses_response():
    """chat_json() parses JSON from LLM response."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"suspicious": false}'
    mock_mistral.chat.complete_async = AsyncMock(return_value=mock_response)
    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat_json(messages=[{"role": "user", "content": "review this"}])
    assert result == {"suspicious": False}


@pytest.mark.asyncio
async def test_chat_json_invalid_json_returns_none():
    """chat_json() returns None when LLM response is not valid JSON."""
    from safeclaw.llm.client import SafeClawLLMClient

    mock_mistral = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not json at all"
    mock_mistral.chat.complete_async = AsyncMock(return_value=mock_response)
    client = SafeClawLLMClient(
        mistral_client=mock_mistral,
        model="mistral-small-latest",
        model_large="mistral-large-latest",
        timeout_ms=3000,
    )
    result = await client.chat_json(messages=[{"role": "user", "content": "review this"}])
    assert result is None
