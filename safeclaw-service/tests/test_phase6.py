"""Phase 6 tests: plan reasoner, knowledge store, multi-agent governor."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.constraints.preference_checker import UserPreferences
from safeclaw.engine.plan_reasoner import PlanReasoner, PlanStep, PlanAssessment
from safeclaw.engine.knowledge_store import KnowledgeStore, MAX_ENTRIES


# --- Helpers ---

def _make_action(
    ontology_class: str = "ReadFile",
    risk_level: str = "LowRisk",
    is_reversible: bool = True,
    affects_scope: str = "LocalOnly",
    tool_name: str = "read",
    params: dict | None = None,
) -> ClassifiedAction:
    return ClassifiedAction(
        ontology_class=ontology_class,
        risk_level=risk_level,
        is_reversible=is_reversible,
        affects_scope=affects_scope,
        tool_name=tool_name,
        params=params or {},
    )


def _make_policy_result(violated: bool = False, reason: str = ""):
    result = MagicMock()
    result.violated = violated
    result.reason = reason
    return result


def _make_derived_result(requires_confirmation: bool = False, reason: str = ""):
    result = MagicMock()
    result.requires_confirmation = requires_confirmation
    result.reason = reason
    return result


# --- Fixtures ---

@pytest.fixture
def mock_classifier():
    return MagicMock()


@pytest.fixture
def mock_policy_checker():
    return MagicMock()


@pytest.fixture
def mock_derived_checker():
    return MagicMock()


@pytest.fixture
def reasoner(mock_classifier, mock_policy_checker, mock_derived_checker):
    return PlanReasoner(
        classifier=mock_classifier,
        policy_checker=mock_policy_checker,
        derived_checker=mock_derived_checker,
    )


@pytest.fixture
def user_prefs():
    return UserPreferences(autonomy_level="moderate")


# --- PlanReasoner Tests ---

class TestPlanReasoner:
    def test_all_safe_steps_no_errors(self, reasoner, mock_classifier, mock_policy_checker, mock_derived_checker, user_prefs):
        """assess_plan with all-safe steps returns no errors."""
        safe_action = _make_action("ReadFile", "LowRisk")
        mock_classifier.classify.return_value = safe_action
        mock_policy_checker.check.return_value = _make_policy_result(violated=False)
        mock_derived_checker.check.return_value = _make_derived_result(requires_confirmation=False)

        steps = [
            PlanStep(tool_name="read", params={"file_path": "/a.py"}, description="Read a"),
            PlanStep(tool_name="read", params={"file_path": "/b.py"}, description="Read b"),
        ]
        assessment = reasoner.assess_plan(steps, user_prefs)

        assert not assessment.has_errors
        assert not assessment.has_warnings
        assert assessment.total_risk_score == 2  # 1 + 1

    def test_detects_policy_violation(self, reasoner, mock_classifier, mock_policy_checker, mock_derived_checker, user_prefs):
        """assess_plan detects policy violations."""
        action = _make_action("DeleteFile", "CriticalRisk", is_reversible=False)
        mock_classifier.classify.return_value = action
        mock_policy_checker.check.return_value = _make_policy_result(
            violated=True, reason="Deleting protected file"
        )
        mock_derived_checker.check.return_value = _make_derived_result(requires_confirmation=False)

        steps = [PlanStep(tool_name="exec", params={"command": "rm -rf /etc"}, description="Delete")]
        assessment = reasoner.assess_plan(steps, user_prefs)

        assert assessment.has_errors
        policy_issues = [i for i in assessment.issues if i.issue_type == "policy_violation"]
        assert len(policy_issues) == 1
        assert policy_issues[0].severity == "error"
        assert "Deleting protected file" in policy_issues[0].message

    def test_detects_irreversible_action(self, reasoner, mock_classifier, mock_policy_checker, mock_derived_checker, user_prefs):
        """assess_plan detects irreversible actions requiring confirmation."""
        action = _make_action("ForcePush", "CriticalRisk", is_reversible=False, affects_scope="SharedState")
        mock_classifier.classify.return_value = action
        mock_policy_checker.check.return_value = _make_policy_result(violated=False)
        mock_derived_checker.check.return_value = _make_derived_result(
            requires_confirmation=True, reason="CriticalRisk and irreversible"
        )

        steps = [PlanStep(tool_name="exec", params={"command": "git push --force"}, description="Force push")]
        assessment = reasoner.assess_plan(steps, user_prefs)

        assert assessment.has_warnings
        irreversible_issues = [i for i in assessment.issues if i.issue_type == "irreversible"]
        assert len(irreversible_issues) == 1
        assert irreversible_issues[0].severity == "warning"

    def test_detects_cumulative_risk_above_threshold(self, reasoner, mock_classifier, mock_policy_checker, mock_derived_checker, user_prefs):
        """assess_plan detects cumulative risk above threshold (>30)."""
        # CriticalRisk score is 15, so 3 steps = 45 > 30
        action = _make_action("DeleteFile", "CriticalRisk", is_reversible=False)
        mock_classifier.classify.return_value = action
        mock_policy_checker.check.return_value = _make_policy_result(violated=False)
        mock_derived_checker.check.return_value = _make_derived_result(requires_confirmation=False)

        steps = [
            PlanStep(tool_name="exec", params={"command": "rm a"}, description="Del a"),
            PlanStep(tool_name="exec", params={"command": "rm b"}, description="Del b"),
            PlanStep(tool_name="exec", params={"command": "rm c"}, description="Del c"),
        ]
        assessment = reasoner.assess_plan(steps, user_prefs)

        assert assessment.total_risk_score == 45
        cumulative_issues = [i for i in assessment.issues if i.issue_type == "cumulative_risk"]
        assert len(cumulative_issues) == 1
        assert "45" in cumulative_issues[0].message

    def test_detects_dependency_ordering_later(self, reasoner, mock_classifier, mock_policy_checker, mock_derived_checker, user_prefs):
        """assess_plan detects dependency ordering issues when requirement appears later."""
        # GitPush requires RunTests. Put GitPush first, RunTests second.
        actions = [
            _make_action("GitPush", "HighRisk", is_reversible=False, affects_scope="SharedState"),
            _make_action("RunTests", "LowRisk"),
        ]
        mock_classifier.classify.side_effect = actions
        mock_policy_checker.check.return_value = _make_policy_result(violated=False)
        mock_derived_checker.check.return_value = _make_derived_result(requires_confirmation=False)

        steps = [
            PlanStep(tool_name="exec", params={"command": "git push"}, description="Push"),
            PlanStep(tool_name="exec", params={"command": "pytest"}, description="Test"),
        ]
        assessment = reasoner.assess_plan(steps, user_prefs)

        dep_issues = [i for i in assessment.issues if i.issue_type == "dependency_order"]
        error_deps = [i for i in dep_issues if i.severity == "error"]
        assert len(error_deps) >= 1
        assert "RunTests" in error_deps[0].message
        assert "later" in error_deps[0].message

    def test_detects_missing_dependency(self, reasoner, mock_classifier, mock_policy_checker, mock_derived_checker, user_prefs):
        """assess_plan detects missing dependencies not present in plan."""
        # GitPush requires RunTests, but RunTests is not in the plan at all
        actions = [
            _make_action("GitPush", "HighRisk", is_reversible=False, affects_scope="SharedState"),
        ]
        mock_classifier.classify.side_effect = actions
        mock_policy_checker.check.return_value = _make_policy_result(violated=False)
        mock_derived_checker.check.return_value = _make_derived_result(requires_confirmation=False)

        steps = [
            PlanStep(tool_name="exec", params={"command": "git push"}, description="Push"),
        ]
        assessment = reasoner.assess_plan(steps, user_prefs)

        dep_issues = [i for i in assessment.issues if i.issue_type == "dependency_order"]
        warning_deps = [i for i in dep_issues if i.severity == "warning"]
        assert len(warning_deps) >= 1
        assert "RunTests" in warning_deps[0].message
        assert "not in the plan" in warning_deps[0].message

    def test_assessment_properties(self):
        """PlanAssessment has_errors and has_warnings properties work correctly."""
        empty = PlanAssessment()
        assert not empty.has_errors
        assert not empty.has_warnings

        from safeclaw.engine.plan_reasoner import PlanIssue
        with_error = PlanAssessment(issues=[
            PlanIssue(step_index=0, severity="error", issue_type="policy_violation", message="bad"),
        ])
        assert with_error.has_errors
        assert not with_error.has_warnings

        with_warning = PlanAssessment(issues=[
            PlanIssue(step_index=0, severity="warning", issue_type="irreversible", message="careful"),
        ])
        assert not with_warning.has_errors
        assert with_warning.has_warnings


# --- KnowledgeStore Tests ---

class TestKnowledgeStore:
    def test_record_and_get_fact(self, tmp_path):
        """record_fact and retrieve by get_fact."""
        store = KnowledgeStore(tmp_path / "kb")
        fact_id = store.record_fact("file_structure", "main.py", "entry point")
        fact = store.get_fact(fact_id)
        assert fact is not None
        assert fact["type"] == "file_structure"
        assert fact["subject"] == "main.py"
        assert fact["detail"] == "entry point"

    def test_get_facts_with_type_filter(self, tmp_path):
        """get_facts with type filter returns only matching type."""
        store = KnowledgeStore(tmp_path / "kb")
        store.record_fact("file_structure", "a.py", "module a")
        store.record_fact("decision_pattern", "always test", "run tests before push")
        store.record_fact("file_structure", "b.py", "module b")

        file_facts = store.get_facts(fact_type="file_structure")
        assert len(file_facts) == 2
        assert all(f["type"] == "file_structure" for f in file_facts)

        decision_facts = store.get_facts(fact_type="decision_pattern")
        assert len(decision_facts) == 1

    def test_get_facts_respects_limit(self, tmp_path):
        """get_facts respects the limit parameter."""
        store = KnowledgeStore(tmp_path / "kb")
        for i in range(10):
            store.record_fact("file_structure", f"file{i}.py", f"module {i}")

        facts = store.get_facts(limit=3)
        assert len(facts) == 3
        # Should return the last 3 (most recent)
        assert facts[-1]["subject"] == "file9.py"

    def test_get_project_context(self, tmp_path):
        """get_project_context returns file structure and decision patterns."""
        store = KnowledgeStore(tmp_path / "kb")
        store.record_fact("file_structure", "src/main.py", "entry point")
        store.record_fact("file_structure", "src/utils.py", "helpers")
        store.record_fact("decision_pattern", "testing", "always run tests before push")

        context = store.get_project_context()
        assert any("Known project files" in line for line in context)
        assert any("main.py" in line for line in context)
        assert any("Known decision patterns" in line for line in context)
        assert any("always run tests before push" in line for line in context)

    def test_persistence_save_and_reload(self, tmp_path):
        """Facts persist to disk and are reloaded on new instance."""
        store_dir = tmp_path / "kb"
        store1 = KnowledgeStore(store_dir)
        store1.record_fact("file_structure", "main.py", "entry point")
        store1.record_fact("decision_pattern", "testing", "test first")

        # Create a new instance pointing to the same directory
        store2 = KnowledgeStore(store_dir)
        assert store2.get_fact("file_structure:main.py") is not None
        assert store2.get_fact("decision_pattern:testing") is not None
        assert len(store2.get_facts()) == 2

    def test_eviction_when_max_entries_exceeded(self, tmp_path, monkeypatch):
        """Eviction when MAX_ENTRIES exceeded removes oldest entries."""
        import safeclaw.engine.knowledge_store as ks_mod
        monkeypatch.setattr(ks_mod, "MAX_ENTRIES", 20)

        store = KnowledgeStore(tmp_path / "kb")

        # Record 25 facts (over the patched limit of 20)
        for i in range(25):
            store.record_fact("test", f"item_{i}", f"detail {i}")

        # Total should be capped at 20
        all_facts = store.get_facts(limit=100)
        assert len(all_facts) <= 20

        # The oldest entries should have been evicted
        assert store.get_fact("test:item_0") is None
        assert store.get_fact("test:item_4") is None
        # The newest should still exist
        assert store.get_fact("test:item_24") is not None

    def test_clear_removes_all_facts_and_file(self, tmp_path):
        """clear removes all facts and the storage file."""
        store_dir = tmp_path / "kb"
        store = KnowledgeStore(store_dir)
        store.record_fact("file_structure", "a.py", "module a")
        store.record_fact("file_structure", "b.py", "module b")

        store_file = store_dir / "knowledge.jsonl"
        assert store_file.exists()

        store.clear()

        assert len(store.get_facts()) == 0
        assert store.get_fact("file_structure:a.py") is None
        assert not store_file.exists()


