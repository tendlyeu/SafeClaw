"""Tests for the full SafeClaw engine."""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import ToolCallEvent, MessageEvent, AgentStartEvent
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine(tmp_path):
    """Create a test engine with ontologies from the project."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
    )
    return FullEngine(config)


@pytest.mark.asyncio
async def test_read_file_allowed(engine):
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is False


@pytest.mark.asyncio
async def test_force_push_blocked_by_policy(engine):
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="exec",
        params={"command": "git push --force origin main"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert "force push" in decision.reason.lower() or "Force push" in decision.reason


@pytest.mark.asyncio
async def test_env_file_blocked_by_policy(engine):
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="read",
        params={"file_path": "/project/.env"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert "secret" in decision.reason.lower() or "env" in decision.reason.lower()


@pytest.mark.asyncio
async def test_delete_blocked_by_policy_or_preference(engine):
    """rm -rf /tmp/old is blocked — either by root deletion policy or delete confirmation pref."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="default",
        tool_name="exec",
        params={"command": "rm -rf /tmp/old"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert "SafeClaw" in decision.reason


@pytest.mark.asyncio
async def test_delete_non_root_blocked_by_preference(engine):
    """rm on a non-root path should still be blocked by confirmBeforeDelete preference."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="default",
        tool_name="exec",
        params={"command": "rm -rf old_dir"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert "confirm" in decision.reason.lower() or "delete" in decision.reason.lower()


@pytest.mark.asyncio
async def test_git_push_blocked_without_tests(engine):
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="exec",
        params={"command": "git push origin main"},
    )
    decision = await engine.evaluate_tool_call(event)
    # Should be blocked either by preference (confirmBeforePush) or dependency (tests first)
    assert decision.block is True


@pytest.mark.asyncio
async def test_build_context(engine):
    event = AgentStartEvent(
        session_id="test-session",
        user_id="default",
    )
    result = await engine.build_context(event)
    assert "SafeClaw Governance Context" in result.prepend_context


@pytest.mark.asyncio
async def test_audit_records_written(engine, tmp_path):
    event = ToolCallEvent(
        session_id="audit-test",
        user_id="test-user",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    await engine.evaluate_tool_call(event)

    records = engine.audit.get_session_records("audit-test")
    assert len(records) == 1
    assert records[0].action.tool_name == "read"
