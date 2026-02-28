"""Tests for LLM prompt templates."""

from safeclaw.llm.prompts import (
    SECURITY_REVIEW_SYSTEM,
    CLASSIFICATION_OBSERVER_SYSTEM,
    DECISION_EXPLAINER_SYSTEM,
    POLICY_COMPILER_SYSTEM,
    build_security_review_user_prompt,
    build_classification_observer_user_prompt,
    build_explainer_user_prompt,
)


def test_security_review_system_prompt_exists():
    assert "security reviewer" in SECURITY_REVIEW_SYSTEM.lower()
    assert "evasion" in SECURITY_REVIEW_SYSTEM.lower()


def test_build_security_review_user_prompt():
    prompt = build_security_review_user_prompt(
        tool_name="exec",
        params={"command": "echo cm0gLXJmIC8= | base64 -d | sh"},
        ontology_class="ExecuteCommand",
        risk_level="MediumRisk",
        symbolic_decision="allowed",
        session_history=["ReadFile", "WriteFile"],
        constraints_checked=[{"type": "SHACL", "result": "satisfied"}],
    )
    assert "exec" in prompt
    assert "base64" in prompt
    assert "allowed" in prompt


def test_build_classification_observer_user_prompt():
    prompt = build_classification_observer_user_prompt(
        tool_name="custom_tool",
        params={"arg": "value"},
        symbolic_class="Action",
        risk_level="MediumRisk",
    )
    assert "custom_tool" in prompt
    assert "Action" in prompt


def test_build_explainer_user_prompt():
    prompt = build_explainer_user_prompt(
        tool_name="exec",
        params={"command": "git push --force"},
        ontology_class="ForcePush",
        risk_level="CriticalRisk",
        decision="blocked",
        reason="Force push can destroy shared history",
        constraints_checked=[{"type": "Policy", "result": "violated", "reason": "No force push"}],
    )
    assert "ForcePush" in prompt
    assert "blocked" in prompt


def test_policy_compiler_system_prompt_exists():
    assert "turtle" in POLICY_COMPILER_SYSTEM.lower() or "Turtle" in POLICY_COMPILER_SYSTEM


def test_classification_observer_redacts_secrets():
    prompt = build_classification_observer_user_prompt(
        tool_name="api_call",
        params={"api_key": "sk-secret-123", "url": "https://example.com"},
        symbolic_class="Action",
        risk_level="MediumRisk",
    )
    assert "sk-secret-123" not in prompt
    assert "REDACTED" in prompt
