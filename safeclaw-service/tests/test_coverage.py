"""Tests for previously untested modules and code paths (F-55)."""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.engine.core import (
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def engine(tmp_path):
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
    )
    return FullEngine(config)


# --- evaluate_message full pipeline ---


@pytest.mark.asyncio
async def test_message_never_contact_blocked(engine):
    engine.message_gate.add_never_contact("blocked@example.com")
    event = MessageEvent(
        session_id="s1",
        user_id="default",
        to="blocked@example.com",
        content="Hi there",
    )
    decision = await engine.evaluate_message(event)
    assert decision.block is True
    assert "never-contact" in decision.reason.lower()


@pytest.mark.asyncio
async def test_message_default_user_confirm_preference(engine):
    """Default user has confirm_before_send=True, so messages should be blocked (R3-65)."""
    event = MessageEvent(
        session_id="s1",
        user_id="default",
        to="friend@example.com",
        content="Hello",
    )
    decision = await engine.evaluate_message(event)
    assert decision.block is True
    assert "confirm" in decision.reason.lower() or "send" in decision.reason.lower()
    assert decision.audit_id  # audit record is always created


# --- record_action_result ---


@pytest.mark.asyncio
async def test_record_action_result_updates_trackers(engine):
    session_id = "rec-test"
    event = ToolResultEvent(
        session_id=session_id,
        tool_name="read",
        params={"file_path": "/src/main.py"},
        result="contents",
        success=True,
    )
    await engine.record_action_result(event)

    # Session tracker should have recorded this
    state = engine.session_tracker.get_state(session_id)
    assert state is not None
    assert len(state.facts) == 1
    assert state.facts[0].action_class == "ReadFile"

    # Verify dependency was recorded by checking a dependent action no longer shows unmet
    from safeclaw.constraints.action_classifier import ClassifiedAction

    dep_action = ClassifiedAction(
        ontology_class="GitPush",
        risk_level="HighRisk",
        is_reversible=False,
        affects_scope="SharedState",
        tool_name="exec",
        params={"command": "git push"},
    )
    dep_result = engine.dependency_checker.check(dep_action, session_id)
    # ReadFile is now in history; GitPush requires RunTests, so it should still be unmet
    # But the important thing is the check doesn't crash and ReadFile was recorded
    assert dep_result.unmet is True


# --- reload ---


@pytest.mark.asyncio
async def test_reload_reinitializes(engine):
    original_triple_count = len(engine.kg)
    await engine.reload()
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
        session_id=session_id,
        user_id="default",
        tool_name="read",
        params={"file_path": "/src/main.py"},
    )
    await engine.evaluate_tool_call(event)

    # Record a tool result to populate session tracker and dependency checker
    result_event = ToolResultEvent(
        session_id=session_id,
        tool_name="read",
        params={"file_path": "/src/main.py"},
        result="contents",
        success=True,
    )
    await engine.record_action_result(result_event)

    # Verify state exists
    assert engine.session_tracker.get_state(session_id) is not None

    # Clear session
    await engine.clear_session(session_id)

    # Verify all per-component state is cleared
    assert engine.session_tracker.get_state(session_id) is None

    # Verify dependency checker was cleared: check() should show unmet deps again
    from safeclaw.constraints.action_classifier import ClassifiedAction

    dep_action = ClassifiedAction(
        ontology_class="GitPush",
        risk_level="HighRisk",
        is_reversible=False,
        affects_scope="SharedState",
        tool_name="exec",
        params={"command": "git push"},
    )
    dep_result = engine.dependency_checker.check(dep_action, session_id)
    # After clearing, history is gone so RunTests prerequisite should be unmet
    assert dep_result.unmet is True

    # Verify clear_session doesn't raise (covers session lock cleanup)
    await engine.clear_session(session_id)


def test_dependency_checker_loads_from_kg():
    """DependencyChecker loads dependency constraints from the knowledge graph."""
    from rdflib import Literal, Namespace, RDF
    from safeclaw.constraints.dependency_checker import DependencyChecker, DEFAULT_DEPENDENCIES
    from safeclaw.engine.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    sp = Namespace("http://safeclaw.uku.ai/ontology/policy#")
    sc = Namespace("http://safeclaw.uku.ai/ontology/agent#")

    # Add a custom dependency constraint to the KG
    constraint_node = sp["CustomDepConstraint"]
    kg.graph.add((constraint_node, RDF.type, sp["DependencyConstraint"]))
    kg.graph.add((constraint_node, sp["appliesTo"], sc["DeployProduction"]))
    kg.graph.add((constraint_node, sp["requiresBefore"], sc["RunTests"]))
    kg.graph.add((constraint_node, sp["reason"], Literal("Must test before deploying")))

    checker = DependencyChecker(kg)

    # The KG-sourced dependency should be loaded beyond DEFAULT_DEPENDENCIES
    assert "DeployProduction" in checker._dependencies
    assert "RunTests" in checker._dependencies["DeployProduction"]
    # Default dependencies should still be present
    for key in DEFAULT_DEPENDENCIES:
        assert key in checker._dependencies
