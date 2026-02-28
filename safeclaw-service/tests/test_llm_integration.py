"""Integration tests for LLM layer in FullEngine."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine_no_llm(tmp_path):
    """Engine without LLM (no API key)."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="",
    )
    return FullEngine(config)


@pytest.fixture
def engine_with_llm(tmp_path):
    """Engine with LLM (mocked client)."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="test-key",
    )
    mock_client = MagicMock()
    with patch("safeclaw.llm.client.create_client", return_value=mock_client):
        # We need to patch where create_client is looked up by full_engine
        with patch(
            "safeclaw.engine.full_engine.create_client", return_value=mock_client, create=True
        ):
            engine = FullEngine(config)
    return engine


@pytest.mark.asyncio
async def test_engine_works_without_llm(engine_no_llm):
    """Engine works exactly as before when no API key is set."""
    event = ToolCallEvent(
        session_id="test",
        user_id="test",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    decision = await engine_no_llm.evaluate_tool_call(event)
    assert decision.block is False
    assert engine_no_llm.llm_client is None
    assert engine_no_llm.security_reviewer is None


@pytest.mark.asyncio
async def test_engine_initializes_llm_with_api_key(tmp_path):
    """Engine initializes LLM components when API key is provided."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="test-key-for-init",
    )

    mock_client = MagicMock()
    with patch("safeclaw.llm.client.create_client", return_value=mock_client):
        engine = FullEngine(config)

    assert engine.llm_client is not None
    assert engine.security_reviewer is not None
    assert engine.classification_observer is not None
    assert engine.explainer is not None


@pytest.mark.asyncio
async def test_security_review_fires_after_allow(tmp_path):
    """Security review task is created after a tool call is allowed."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
        mistral_api_key="test-key",
    )

    mock_client = MagicMock()
    with patch("safeclaw.llm.client.create_client", return_value=mock_client):
        engine = FullEngine(config)

    # Mock the security reviewer to track if it's called
    engine.security_reviewer.review = AsyncMock(return_value=None)

    event = ToolCallEvent(
        session_id="test",
        user_id="test",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is False

    # Give background tasks a moment to fire
    await asyncio.sleep(0.1)

    engine.security_reviewer.review.assert_called_once()


@pytest.mark.asyncio
async def test_symbolic_decision_not_delayed_by_llm(engine_no_llm):
    """Verify symbolic pipeline returns immediately regardless of LLM."""
    import time

    event = ToolCallEvent(
        session_id="test",
        user_id="test",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )

    start = time.monotonic()
    decision = await engine_no_llm.evaluate_tool_call(event)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert decision.block is False
    assert elapsed_ms < 500  # Symbolic pipeline should be fast
