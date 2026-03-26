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


def test_kill_switch_never_auto_executes_ast_inspection():
    """Regression test for #130: SecurityReviewer must never call kill_agent directly.

    The LLM security reviewer may *recommend* a kill_switch action, but it must
    never auto-execute it. Executing a kill based solely on LLM output is dangerous
    because LLM responses can be hallucinated or manipulated via prompt injection.
    Instead, kill_switch findings must only be escalated (logged) for human review.

    This test uses AST inspection to verify that the SecurityReviewer class source
    code never contains calls to kill_agent, registry.kill, or agent_registry.kill.
    """
    import ast
    import inspect
    from safeclaw.llm.security_reviewer import SecurityReviewer

    source = inspect.getsource(SecurityReviewer)
    tree = ast.parse(source)

    # Patterns that would indicate auto-execution of kill_switch:
    # - kill_agent(...)
    # - *.kill_agent(...)
    # - registry.kill(...)
    # - agent_registry.kill(...)
    # - agent_registry.kill_agent(...)
    forbidden_patterns = {"kill_agent", "kill"}

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Direct call: kill_agent(...)
            if isinstance(func, ast.Name) and func.id in forbidden_patterns:
                violations.append(f"Direct call to {func.id}() at line {node.lineno}")
            # Attribute call: something.kill_agent(...) or something.kill(...)
            elif isinstance(func, ast.Attribute) and func.attr in forbidden_patterns:
                # Reconstruct the dotted name for the error message
                parts = []
                obj = func.value
                while isinstance(obj, ast.Attribute):
                    parts.append(obj.attr)
                    obj = obj.value
                if isinstance(obj, ast.Name):
                    parts.append(obj.id)
                parts.reverse()
                dotted = ".".join(parts) + f".{func.attr}"
                violations.append(f"Call to {dotted}() at line {node.lineno}")

    assert violations == [], (
        "SecurityReviewer must never auto-execute kill_switch. "
        f"Found forbidden calls: {violations}. "
        "Kill switch findings should only be escalated for human review "
        "(see issue #130)."
    )


@pytest.mark.asyncio
async def test_kill_switch_recommendation_only_logs(mock_llm_client, mock_engine):
    """Regression test for #130: kill_switch recommendation must log, not execute.

    When the LLM recommends kill_switch with high confidence, the SecurityReviewer
    must only log a CRITICAL message and optionally publish an event — it must NOT
    call any kill method on the agent registry.
    """
    from safeclaw.llm.security_reviewer import SecurityReviewer, ReviewEvent

    mock_llm_client.chat_json.return_value = {
        "suspicious": True,
        "severity": "critical",
        "category": "evasion",
        "description": "Agent attempting to bypass constraints via delegation",
        "recommended_action": "kill_switch",
        "confidence": 0.95,
    }

    reviewer = SecurityReviewer(mock_llm_client, mock_engine)
    event = ReviewEvent(
        tool_name="exec",
        params={"command": "rm -rf /"},
        classified_action=ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="SystemWide",
            tool_name="exec",
            params={"command": "rm -rf /"},
        ),
        symbolic_decision="allowed",
        session_history=["ReadFile", "ExecuteCommand", "ExecuteCommand"],
        constraints_checked=[{"type": "SHACL", "result": "satisfied"}],
        agent_id="agent-123",
    )
    finding = await reviewer.review(event)

    # The finding should be returned for upstream handling
    assert finding is not None
    assert finding.recommended_action == "kill_switch"
    assert finding.confidence == 0.95

    # The agent registry's kill method must NOT have been called
    mock_engine.agent_registry.kill.assert_not_called()
    mock_engine.agent_registry.kill_agent.assert_not_called()
