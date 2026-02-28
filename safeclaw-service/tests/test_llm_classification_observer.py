"""Tests for the Classification Observer."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from safeclaw.constraints.action_classifier import ClassifiedAction


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat_json = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_observe_default_classification(mock_llm_client, tmp_path):
    """Observer fires and returns suggestion when classifier used defaults."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    mock_llm_client.chat_json.return_value = {
        "suggested_class": "NetworkRequest",
        "suggested_risk": "HighRisk",
        "is_reversible": True,
        "affects_scope": "ExternalWorld",
        "reasoning": "This tool makes HTTP requests to external services",
    }

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="Action",
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="http_client",
        params={"url": "https://api.example.com"},
    )
    suggestion = await observer.observe("http_client", {"url": "https://api.example.com"}, action)
    assert suggestion is not None
    assert suggestion.suggested_class == "NetworkRequest"
    assert suggestion.suggested_risk == "HighRisk"


@pytest.mark.asyncio
async def test_observe_skips_non_default(mock_llm_client, tmp_path):
    """Observer does NOT fire when classifier returned a specific class."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="ReadFile",
        risk_level="LowRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    suggestion = await observer.observe("read", {"file_path": "/src/main.py"}, action)
    assert suggestion is None
    mock_llm_client.chat_json.assert_not_called()


@pytest.mark.asyncio
async def test_observe_writes_to_suggestions_file(mock_llm_client, tmp_path):
    """Suggestions are appended to the JSONL file."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    mock_llm_client.chat_json.return_value = {
        "suggested_class": "WebFetch",
        "suggested_risk": "MediumRisk",
        "is_reversible": True,
        "affects_scope": "ExternalWorld",
        "reasoning": "Fetches content from URLs",
    }

    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="Action",
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="fetch",
        params={"url": "https://example.com"},
    )
    await observer.observe("fetch", {"url": "https://example.com"}, action)

    assert suggestions_file.exists()
    lines = suggestions_file.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["suggested_class"] == "WebFetch"
    assert data["tool_name"] == "fetch"


@pytest.mark.asyncio
async def test_observe_llm_timeout_returns_none(mock_llm_client, tmp_path):
    """If LLM times out, observer returns None gracefully."""
    from safeclaw.llm.classification_observer import ClassificationObserver

    mock_llm_client.chat_json.return_value = None
    suggestions_file = tmp_path / "suggestions.jsonl"
    observer = ClassificationObserver(mock_llm_client, suggestions_file)

    action = ClassifiedAction(
        ontology_class="Action",
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="unknown",
        params={},
    )
    suggestion = await observer.observe("unknown", {}, action)
    assert suggestion is None
