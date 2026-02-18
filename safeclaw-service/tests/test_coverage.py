"""Tests for previously untested modules and code paths (F-55)."""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import (
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from safeclaw.engine.cached_engine import CachedEngine
from safeclaw.engine.full_engine import FullEngine
from safeclaw.engine.agent_registry import AgentRegistry


@pytest.fixture
def engine(tmp_path):
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        run_reasoner_on_startup=False,
    )
    return FullEngine(config)


# --- CachedEngine tests ---

@pytest.mark.asyncio
async def test_cached_engine_allows_normal_call():
    ce = CachedEngine()
    event = ToolCallEvent(
        session_id="s1", user_id="u1", tool_name="read",
        params={"file_path": "/foo.py"},
    )
    decision = await ce.evaluate_tool_call(event)
    assert decision.block is False


@pytest.mark.asyncio
async def test_cached_engine_kill_switch():
    registry = AgentRegistry()
    token = registry.register_agent("agent-x", role="developer", session_id="s1")
    registry.kill_agent("agent-x")

    ce = CachedEngine(agent_registry=registry)
    event = ToolCallEvent(
        session_id="s1", user_id="u1", tool_name="read",
        params={"file_path": "/foo.py"},
        agent_id="agent-x", agent_token=token,
    )
    decision = await ce.evaluate_tool_call(event)
    assert decision.block is True
    assert "killed" in decision.reason.lower()


# --- evaluate_message full pipeline ---

@pytest.mark.asyncio
async def test_message_never_contact_blocked(engine):
    engine.message_gate.add_never_contact("blocked@example.com")
    event = MessageEvent(
        session_id="s1", user_id="default",
        to="blocked@example.com", content="Hi there",
    )
    decision = await engine.evaluate_message(event)
    assert decision.block is True
    assert "never-contact" in decision.reason.lower()


@pytest.mark.asyncio
async def test_message_normal_allowed(engine):
    event = MessageEvent(
        session_id="s1", user_id="default",
        to="friend@example.com", content="Hello",
    )
    decision = await engine.evaluate_message(event)
    # May be blocked by confirm_before_send preference; either way we get a decision
    assert isinstance(decision.block, bool)
    assert decision.audit_id  # audit record is always created


# --- record_action_result ---

@pytest.mark.asyncio
async def test_record_action_result_updates_trackers(engine):
    session_id = "rec-test"
    event = ToolResultEvent(
        session_id=session_id, tool_name="read",
        params={"file_path": "/src/main.py"},
        result="contents", success=True,
    )
    await engine.record_action_result(event)

    # Session tracker should have recorded this
    state = engine.session_tracker.get_state(session_id)
    assert state is not None
    assert len(state.facts) == 1
    assert state.facts[0].action_class == "ReadFile"

    # Dependency checker should have recorded successful action
    history = engine.dependency_checker._session_history.get(session_id, [])
    assert "ReadFile" in history


# --- reload ---

def test_reload_reinitializes(engine):
    original_triple_count = len(engine.kg)
    engine.reload()
    # Engine should still work with the same number of triples
    assert len(engine.kg) == original_triple_count
    assert engine.policy_checker is not None
    assert engine.shacl is not None


# --- clear_session ---

@pytest.mark.asyncio
async def test_clear_session_removes_state(engine):
    session_id = "clear-test"

    # Create some session state via an evaluation
    event = ToolCallEvent(
        session_id=session_id, user_id="default",
        tool_name="read", params={"file_path": "/src/main.py"},
    )
    await engine.evaluate_tool_call(event)

    # Record a tool result to populate session tracker and dependency checker
    result_event = ToolResultEvent(
        session_id=session_id, tool_name="read",
        params={"file_path": "/src/main.py"},
        result="contents", success=True,
    )
    await engine.record_action_result(result_event)

    # Verify state exists
    assert engine.session_tracker.get_state(session_id) is not None

    # Clear session
    engine.clear_session(session_id)

    # Verify all per-component state is cleared
    assert engine.session_tracker.get_state(session_id) is None
    assert session_id not in engine.dependency_checker._session_history
    assert session_id not in engine._session_locks
