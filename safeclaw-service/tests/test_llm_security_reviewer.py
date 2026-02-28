"""Tests for the Semantic Security Reviewer."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from safeclaw.constraints.action_classifier import ClassifiedAction


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat_json = AsyncMock()
    return client


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.agent_registry = MagicMock()
    engine.temp_permissions = MagicMock()
    return engine


@pytest.mark.asyncio
async def test_review_clean_action(mock_llm_client, mock_engine):
    """Clean actions should return None (no finding)."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = {
        "suspicious": False,
        "severity": "low",
        "category": "none",
        "description": "Simple read operation, no risk",
        "recommended_action": "log",
        "confidence": 1.0,
    }

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="read",
        params={"file_path": "/src/main.py"},
        classified_action=ClassifiedAction(
            ontology_class="ReadFile",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="read",
            params={"file_path": "/src/main.py"},
        ),
        symbolic_decision="allowed",
        session_history=[],
        constraints_checked=[],
    )
    finding = await reviewer.review(event)
    assert finding is None


@pytest.mark.asyncio
async def test_review_obfuscated_command(mock_llm_client, mock_engine):
    """Obfuscated base64 command should produce a finding."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = {
        "suspicious": True,
        "severity": "high",
        "category": "obfuscation",
        "description": "Base64-encoded destructive command detected",
        "recommended_action": "escalate_confirmation",
        "confidence": 0.95,
    }

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "echo cm0gLXJmIC8= | base64 -d | sh"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "echo cm0gLXJmIC8= | base64 -d | sh"},
        ),
        symbolic_decision="allowed",
        session_history=["ReadFile"],
        constraints_checked=[{"type": "SHACL", "result": "satisfied"}],
    )
    finding = await reviewer.review(event)
    assert finding is not None
    assert finding.severity == "high"
    assert finding.category == "obfuscation"


@pytest.mark.asyncio
async def test_review_llm_timeout_returns_none(mock_llm_client, mock_engine):
    """If LLM times out, review returns None."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = None
    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "ls"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "ls"},
        ),
        symbolic_decision="allowed",
        session_history=[],
        constraints_checked=[],
    )
    finding = await reviewer.review(event)
    assert finding is None


@pytest.mark.asyncio
async def test_review_invalid_json_returns_none(mock_llm_client, mock_engine):
    """If LLM returns invalid structure, review returns None."""
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = {"unexpected": "format"}
    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "ls"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "ls"},
        ),
        symbolic_decision="allowed",
        session_history=[],
        constraints_checked=[],
    )
    finding = await reviewer.review(event)
    assert finding is None
