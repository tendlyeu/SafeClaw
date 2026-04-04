"""Tests for the full SafeClaw engine."""

import pytest
from pathlib import Path

from safeclaw.config import SafeClawConfig
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.engine.core import ToolCallEvent, AgentStartEvent
from safeclaw.engine.full_engine import FullEngine
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP


@pytest.fixture
def engine(tmp_path):
    """Create a test engine with ontologies from the project."""
    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
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
async def test_delete_blocked_by_shacl_missing_filepath(engine):
    """rm -rf /tmp/old is blocked by SHACL: DeleteFile (subclass of FileAction) requires
    a filePath property, but shell commands only set commandText in the RDF graph."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="default",
        tool_name="exec",
        params={"command": "rm -rf /tmp/old"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert (
        "file path" in decision.reason.lower()
    ), f"Expected SHACL file path violation but got: {decision.reason}"


@pytest.mark.asyncio
async def test_delete_non_root_blocked_by_shacl_missing_filepath(engine):
    """rm -rf old_dir is blocked by SHACL: DeleteFile (subclass of FileAction) requires
    a filePath property, but shell commands only set commandText in the RDF graph.
    If SHACL did not fire, the confirmBeforeDelete preference would block it instead."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="default",
        tool_name="exec",
        params={"command": "rm -rf old_dir"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert (
        "file path" in decision.reason.lower()
    ), f"Expected SHACL file path violation but got: {decision.reason}"


@pytest.mark.asyncio
async def test_git_push_blocked_by_preference(engine):
    """git push is blocked by the confirmBeforePush preference (which fires before
    the dependency checker). Default user preferences have confirmBeforePush=true."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="test-user",
        tool_name="exec",
        params={"command": "git push origin main"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert (
        "confirmation before pushing" in decision.reason.lower()
    ), f"Expected confirmBeforePush preference violation but got: {decision.reason}"


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


@pytest.mark.asyncio
async def test_engine_blocks_rm_rf_root(engine):
    """rm -rf / is blocked by SHACL: DeleteFile (subclass of FileAction) requires
    a filePath property, but shell commands only set commandText in the RDF graph."""
    event = ToolCallEvent(
        session_id="test-session",
        user_id="default",
        tool_name="exec",
        params={"command": "rm -rf /"},
    )
    decision = await engine.evaluate_tool_call(event)
    assert decision.block is True
    assert (
        "file path" in decision.reason.lower()
    ), f"Expected SHACL file path violation but got: {decision.reason}"


def test_policy_checker_safe_match_malformed_regex():
    """PolicyChecker._safe_match handles invalid regex without crashing."""
    from rdflib import Literal, Namespace
    from safeclaw.constraints.action_classifier import ClassifiedAction

    kg = KnowledgeGraph()
    # Add a policy with an invalid regex pattern (unclosed bracket)
    sp = Namespace("http://safeclaw.uku.ai/ontology/policy#")
    policy_node = sp["BadRegexPolicy"]
    kg.graph.add((policy_node, SP["forbiddenCommandPattern"], Literal("[unclosed")))
    kg.graph.add((policy_node, SP["reason"], Literal("Bad regex test")))
    from rdflib import RDF

    kg.graph.add((policy_node, RDF.type, sp["Prohibition"]))

    checker = PolicyChecker(kg)

    # Classify a normal command and check -- should not crash and should not block
    action = ClassifiedAction(
        ontology_class="ExecuteCommand",
        risk_level="HighRisk",
        is_reversible=True,
        affects_scope="LocalOnly",
        tool_name="exec",
        params={"command": "echo hello"},
    )
    result = checker.check(action)
    assert result.violated is False
