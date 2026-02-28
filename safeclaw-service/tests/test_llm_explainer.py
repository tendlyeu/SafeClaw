"""Tests for the Decision Explainer."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
)


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def sample_record():
    return DecisionRecord(
        session_id="test-session",
        user_id="test-user",
        agent_id="",
        action=ActionDetail(
            tool_name="exec",
            params={"command": "git push --force"},
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
        ),
        decision="blocked",
        justification=Justification(
            constraints_checked=[
                ConstraintCheck(
                    constraint_uri="sp:NoForcePush",
                    constraint_type="Policy",
                    result="violated",
                    reason="Force push can destroy shared history",
                )
            ],
            elapsed_ms=12.5,
        ),
    )


@pytest.mark.asyncio
async def test_explain_returns_llm_text(mock_llm_client, sample_record):
    """explain() returns the LLM's plain-English explanation."""
    from safeclaw.llm.explainer import DecisionExplainer

    mock_llm_client.chat.return_value = (
        "The agent tried to force-push to git. SafeClaw blocked this because "
        "force pushing can overwrite shared history. The NoForcePush policy was violated."
    )

    explainer = DecisionExplainer(mock_llm_client)
    result = await explainer.explain(sample_record)
    assert "force" in result.lower()
    assert len(result) > 20


@pytest.mark.asyncio
async def test_explain_fallback_on_timeout(mock_llm_client, sample_record):
    """If LLM times out, explain() returns the raw reason from the record."""
    from safeclaw.llm.explainer import DecisionExplainer

    mock_llm_client.chat.return_value = None

    explainer = DecisionExplainer(mock_llm_client)
    result = await explainer.explain(sample_record)
    assert "Force push" in result  # Falls back to constraint reason


@pytest.mark.asyncio
async def test_explain_session_summarizes(mock_llm_client, sample_record):
    """explain_session() summarizes multiple records."""
    from safeclaw.llm.explainer import DecisionExplainer

    mock_llm_client.chat.return_value = "In this session, 1 action was blocked."

    explainer = DecisionExplainer(mock_llm_client)
    result = await explainer.explain_session([sample_record])
    assert "blocked" in result.lower()
