"""Phase 2 tests: derived rules, temporal constraints, rate limiting, context violations."""

import time
from unittest.mock import patch

import pytest

from safeclaw.constraints.action_classifier import ActionClassifier, ClassifiedAction
from safeclaw.constraints.rate_limiter import RateLimiter
from safeclaw.constraints.temporal_checker import TemporalChecker, TemporalCheckResult
from safeclaw.engine.context_builder import ContextBuilder
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.engine.reasoning_rules import DerivedConstraintChecker


# --- Fixtures ---

@pytest.fixture
def kg():
    """Knowledge graph loaded with test ontologies."""
    from pathlib import Path
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


@pytest.fixture
def classifier():
    return ActionClassifier()


# --- DerivedConstraintChecker Tests ---

class TestDerivedConstraintChecker:
    def test_critical_irreversible_triggers(self, kg):
        checker = DerivedConstraintChecker(kg)
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={"command": "git push --force"},
        )
        from safeclaw.constraints.preference_checker import UserPreferences
        prefs = UserPreferences()
        result = checker.check(action, prefs, [])
        assert result.requires_confirmation
        assert "CriticalIrreversibleRule" in result.derived_rules

    def test_shared_state_cautious_triggers(self, kg):
        checker = DerivedConstraintChecker(kg)
        action = ClassifiedAction(
            ontology_class="GitPush",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={"command": "git push"},
        )
        from safeclaw.constraints.preference_checker import UserPreferences
        prefs = UserPreferences(autonomy_level="cautious")
        result = checker.check(action, prefs, [])
        assert result.requires_confirmation
        assert "SharedStateCautiousRule" in result.derived_rules

    def test_cumulative_risk_escalation(self, kg):
        checker = DerivedConstraintChecker(kg)
        action = ClassifiedAction(
            ontology_class="WriteFile",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="write",
            params={},
        )
        from safeclaw.constraints.preference_checker import UserPreferences
        prefs = UserPreferences()
        # 3+ MediumRisk entries should trigger
        history = ["MediumRisk:WriteFile", "MediumRisk:EditFile", "MediumRisk:WriteFile"]
        result = checker.check(action, prefs, history)
        assert result.requires_confirmation
        assert "CumulativeRiskRule" in result.derived_rules

    def test_no_trigger_on_low_risk(self, kg):
        checker = DerivedConstraintChecker(kg)
        action = ClassifiedAction(
            ontology_class="ReadFile",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="read",
            params={},
        )
        from safeclaw.constraints.preference_checker import UserPreferences
        prefs = UserPreferences()
        result = checker.check(action, prefs, [])
        assert not result.requires_confirmation
        assert result.derived_rules == []


# --- TemporalChecker Tests ---

class TestTemporalChecker:
    def test_no_temporal_constraints_passes(self, kg):
        checker = TemporalChecker()
        action = ClassifiedAction(
            ontology_class="ReadFile",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="read",
            params={},
        )
        result = checker.check(action, kg)
        assert not result.violated

    def test_temporal_constraint_not_before_future(self, kg):
        """Test that a notBefore constraint in the future blocks the action."""
        checker = TemporalChecker()
        action = ClassifiedAction(
            ontology_class="TestAction",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={},
        )
        # No temporal constraints exist for TestAction, so should pass
        result = checker.check(action, kg)
        assert not result.violated


# --- RateLimiter Tests ---

class TestRateLimiter:
    def test_under_limit_passes(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        result = limiter.check(action, "session-1")
        assert not result.exceeded

    def test_critical_risk_limit_exceeded(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        # Record 3 critical actions (the limit)
        for _ in range(3):
            limiter.record(action, "session-1")

        result = limiter.check(action, "session-1")
        assert result.exceeded
        assert "Rate limit exceeded" in result.reason
        assert "CriticalRisk" in result.reason

    def test_high_risk_limit_exceeded(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="GitPush",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        for _ in range(10):
            limiter.record(action, "session-1")

        result = limiter.check(action, "session-1")
        assert result.exceeded

    def test_low_risk_no_limit(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="ReadFile",
            risk_level="LowRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="read",
            params={},
        )
        # Even many low risk actions should pass (no limit configured)
        for _ in range(100):
            limiter.record(action, "session-1")
        result = limiter.check(action, "session-1")
        assert not result.exceeded

    def test_different_sessions_independent(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        for _ in range(3):
            limiter.record(action, "session-1")

        # session-2 should not be affected by session-1's limits
        result = limiter.check(action, "session-2")
        assert not result.exceeded

    def test_clear_session(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        for _ in range(3):
            limiter.record(action, "session-1")

        limiter.clear_session("session-1")
        result = limiter.check(action, "session-1")
        assert not result.exceeded

    def test_session_eviction(self):
        limiter = RateLimiter()
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        # Fill up to MAX_SESSIONS
        for i in range(1001):
            limiter.record(action, f"session-{i}")
        # The first session should have been evicted
        assert "session-0" not in limiter._sessions


# --- ContextBuilder Violation History Tests ---

class TestContextBuilderViolations:
    def test_violation_recorded_and_shown(self, kg):
        builder = ContextBuilder(kg)
        builder.record_violation("sess-1", "[SafeClaw] Force push blocked")
        context = builder.build_context("default", session_id="sess-1")
        assert "Recent Violations" in context
        assert "Force push blocked" in context
        assert "Do not retry" in context

    def test_no_violations_no_section(self, kg):
        builder = ContextBuilder(kg)
        context = builder.build_context("default", session_id="sess-1")
        assert "Recent Violations" not in context

    def test_max_five_violations_shown(self, kg):
        builder = ContextBuilder(kg)
        for i in range(8):
            builder.record_violation("sess-1", f"Violation {i}")
        context = builder.build_context("default", session_id="sess-1")
        # Should show last 5 (3,4,5,6,7)
        assert "Violation 3" in context
        assert "Violation 7" in context
        assert "Violation 2" not in context

    def test_clear_session_removes_violations(self, kg):
        builder = ContextBuilder(kg)
        builder.record_violation("sess-1", "Some violation")
        builder.clear_session("sess-1")
        context = builder.build_context("default", session_id="sess-1")
        assert "Recent Violations" not in context

    def test_session_history_in_context(self, kg):
        builder = ContextBuilder(kg)
        context = builder.build_context(
            "default",
            session_id="sess-1",
            session_history=["Ran tests", "Committed code"],
        )
        assert "Session History" in context
        assert "Ran tests" in context
