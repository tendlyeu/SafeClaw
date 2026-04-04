"""Phase 2 tests: derived rules, temporal constraints, rate limiting, context violations."""

import pytest

from safeclaw.constraints.action_classifier import ActionClassifier, ClassifiedAction
from safeclaw.constraints.rate_limiter import RateLimiter, MAX_SESSIONS
from safeclaw.constraints.temporal_checker import TemporalChecker
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

    def test_temporal_no_constraint_also_passes(self, kg):
        """Test that an action with no temporal constraints passes temporal check."""
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

    def test_temporal_violation_not_before(self, kg):
        """Temporal constraint with notBefore in the future should flag a violation (R3-71)."""
        from rdflib import Literal, Namespace, RDF, XSD
        from safeclaw.engine.knowledge_graph import SP, SC

        sp = Namespace(str(SP))
        sc = Namespace(str(SC))

        # Insert a temporal constraint: DeployAction not allowed before year 2099
        constraint = sp["FutureDeployConstraint"]
        kg.graph.add((constraint, RDF.type, sp["TemporalConstraint"]))
        kg.graph.add((constraint, sp["appliesTo"], sc["DeployAction"]))
        kg.graph.add(
            (
                constraint,
                sp["notBefore"],
                Literal("2099-01-01T00:00:00+00:00", datatype=XSD.dateTime),
            )
        )

        # Also add DeployAction as an OWL class so rdfs:subClassOf* can match
        from rdflib import RDFS

        kg.graph.add((sc["DeployAction"], RDF.type, RDFS.Class))

        checker = TemporalChecker()
        action = ClassifiedAction(
            ontology_class="DeployAction",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={},
        )
        result = checker.check(action, kg)
        assert result.violated
        assert "not allowed before" in result.reason.lower() or "DeployAction" in result.reason


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
        # Fill beyond MAX_SESSIONS so oldest sessions get evicted
        for i in range(MAX_SESSIONS + 1):
            limiter.record(action, f"session-{i}")
        # The first session should have been evicted; check via public API
        result = limiter.check(action, "session-0")
        # After eviction, session-0 has no records, so it should not be exceeded
        assert result.exceeded is False
        # The latest session should still have its record
        result_latest = limiter.check(action, f"session-{MAX_SESSIONS}")
        # It has 1 CriticalRisk action (limit is 3), so not exceeded
        assert result_latest.exceeded is False


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
