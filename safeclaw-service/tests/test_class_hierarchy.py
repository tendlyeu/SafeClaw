"""Tests for ClassHierarchy, hierarchy-aware policy/role checking, ontology validation,
and ontology-enriched classification."""

from pathlib import Path

import pytest

from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.engine.class_hierarchy import ClassHierarchy
from safeclaw.engine.ontology_validator import OntologyValidator
from safeclaw.constraints.action_classifier import ActionClassifier
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.engine.roles import Role, RoleManager
from safeclaw.engine.reasoning_rules import DerivedConstraintChecker
from safeclaw.constraints.preference_checker import UserPreferences


@pytest.fixture
def kg():
    """Load the real ontology files."""
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


@pytest.fixture
def hierarchy(kg):
    return ClassHierarchy(kg)


# ── ClassHierarchy Tests ──


class TestClassHierarchy:
    def test_superclasses_of_git_push(self, hierarchy):
        supers = hierarchy.get_superclasses("GitPush")
        assert "GitPush" in supers
        assert "ShellAction" in supers
        assert "Action" in supers

    def test_subclasses_of_shell_action(self, hierarchy):
        subs = hierarchy.get_subclasses("ShellAction")
        assert "ShellAction" in subs
        assert "GitPush" in subs
        assert "ForcePush" in subs
        assert "ExecuteCommand" in subs

    def test_subclasses_of_file_action(self, hierarchy):
        subs = hierarchy.get_subclasses("FileAction")
        assert "ReadFile" in subs
        assert "WriteFile" in subs
        assert "EditFile" in subs
        assert "DeleteFile" in subs

    def test_is_subclass_of(self, hierarchy):
        assert hierarchy.is_subclass_of("GitPush", "ShellAction")
        assert hierarchy.is_subclass_of("GitPush", "Action")
        assert hierarchy.is_subclass_of("GitPush", "GitPush")  # reflexive
        assert not hierarchy.is_subclass_of("GitPush", "FileAction")

    def test_defaults_for_known_class(self, hierarchy):
        defaults = hierarchy.get_defaults("ForcePush")
        assert defaults is not None
        assert defaults["risk_level"] == "CriticalRisk"
        assert defaults["is_reversible"] is False
        assert defaults["affects_scope"] == "SharedState"

    def test_defaults_for_read_file(self, hierarchy):
        defaults = hierarchy.get_defaults("ReadFile")
        assert defaults is not None
        assert defaults["risk_level"] == "LowRisk"
        assert defaults["is_reversible"] is True

    def test_defaults_none_for_unknown(self, hierarchy):
        assert hierarchy.get_defaults("NonexistentClass") is None

    def test_unknown_class_returns_self(self, hierarchy):
        supers = hierarchy.get_superclasses("UnknownThing")
        assert supers == {"UnknownThing"}


# ── Ontology-Enriched Classification Tests ──


class TestOntologyEnrichedClassification:
    def test_unknown_tool_gets_ontology_defaults(self, hierarchy):
        """Unknown tools classified as 'Action' should NOT get enriched (no defaults for 'Action' base)."""
        classifier = ActionClassifier(hierarchy=hierarchy)
        action = classifier.classify("some_unknown_tool", {})
        # "Action" base class has no defaults in the ontology, so stays at Python defaults
        assert action.ontology_class == "Action"

    def test_known_tool_keeps_hardcoded_classification(self, hierarchy):
        """Known tools should keep their hardcoded classification."""
        classifier = ActionClassifier(hierarchy=hierarchy)
        action = classifier.classify("read", {})
        assert action.ontology_class == "ReadFile"
        assert action.risk_level == "LowRisk"

    def test_shell_classification_unchanged(self, hierarchy):
        """Shell commands should still use pattern matching."""
        classifier = ActionClassifier(hierarchy=hierarchy)
        action = classifier.classify("bash", {"command": "git push --force"})
        assert action.ontology_class == "ForcePush"
        assert action.risk_level == "CriticalRisk"

    def test_classifier_works_without_hierarchy(self):
        """Classifier still works with no hierarchy (backward compat)."""
        classifier = ActionClassifier()
        action = classifier.classify("read", {})
        assert action.ontology_class == "ReadFile"


# ── Hierarchy-Aware Policy Checking Tests ──


class TestHierarchyAwarePolicyChecking:
    def test_policy_blocks_force_push_via_class_prohibition(self, kg, hierarchy):
        """sp:NoForcePush has sp:appliesTo sc:ForcePush — should block ForcePush."""
        checker = PolicyChecker(kg, hierarchy=hierarchy)
        classifier = ActionClassifier(hierarchy=hierarchy)
        action = classifier.classify("bash", {"command": "git push --force"})
        result = checker.check(action)
        assert result.violated
        assert "Force push" in result.reason or "force" in result.reason.lower()

    def test_policy_blocks_git_reset_hard_via_class(self, kg, hierarchy):
        """sp:NoResetHard appliesTo sc:GitResetHard."""
        checker = PolicyChecker(kg, hierarchy=hierarchy)
        classifier = ActionClassifier(hierarchy=hierarchy)
        action = classifier.classify("bash", {"command": "git reset --hard"})
        result = checker.check(action)
        assert result.violated

    def test_safe_action_not_blocked(self, kg, hierarchy):
        """ReadFile should not be blocked by any policy."""
        checker = PolicyChecker(kg, hierarchy=hierarchy)
        classifier = ActionClassifier(hierarchy=hierarchy)
        action = classifier.classify("read", {})
        result = checker.check(action)
        assert not result.violated


# ── Hierarchy-Aware Role Checking Tests ──


class TestHierarchyAwareRoleChecking:
    def test_deny_parent_blocks_child(self, hierarchy):
        """Denying ShellAction should also deny GitPush (child)."""
        role = Role(
            name="restricted",
            enforcement_mode="enforce",
            autonomy_level="supervised",
            denied_action_classes={"ShellAction"},
        )
        rm = RoleManager(hierarchy=hierarchy)
        assert not rm.is_action_allowed(role, "GitPush")
        assert not rm.is_action_allowed(role, "ForcePush")
        assert not rm.is_action_allowed(role, "ExecuteCommand")

    def test_allow_parent_allows_children(self, hierarchy):
        """Allowing FileAction should also allow ReadFile, WriteFile, etc."""
        role = Role(
            name="file-reader",
            enforcement_mode="enforce",
            autonomy_level="moderate",
            allowed_action_classes={"FileAction"},
        )
        rm = RoleManager(hierarchy=hierarchy)
        assert rm.is_action_allowed(role, "ReadFile")
        assert rm.is_action_allowed(role, "WriteFile")
        assert rm.is_action_allowed(role, "EditFile")
        assert rm.is_action_allowed(role, "DeleteFile")

    def test_deny_specific_overrides_parent_allow(self, hierarchy):
        """Denying ForcePush specifically should block it even if ShellAction is allowed."""
        role = Role(
            name="dev",
            enforcement_mode="enforce",
            autonomy_level="moderate",
            denied_action_classes={"ForcePush"},
        )
        rm = RoleManager(hierarchy=hierarchy)
        assert not rm.is_action_allowed(role, "ForcePush")
        # GitPush is NOT denied (ForcePush is not a parent of GitPush)
        assert rm.is_action_allowed(role, "GitPush")

    def test_no_hierarchy_fallback(self):
        """Without hierarchy, exact match behavior is preserved."""
        role = Role(
            name="dev",
            enforcement_mode="enforce",
            autonomy_level="moderate",
            denied_action_classes={"ShellAction"},
        )
        rm = RoleManager()
        # Without hierarchy, GitPush is NOT blocked by denying ShellAction (exact match only)
        assert rm.is_action_allowed(role, "GitPush")
        assert not rm.is_action_allowed(role, "ShellAction")


# ── Hierarchy-Aware Derived Constraint Tests ──


class TestHierarchyAwareDerivedConstraints:
    def test_transitive_prohibition_uses_hierarchy(self, kg, hierarchy):
        """ForcePush should inherit prohibition from sp:appliesTo sc:ForcePush."""
        checker = DerivedConstraintChecker(kg, hierarchy=hierarchy)
        prefs = UserPreferences()
        from safeclaw.constraints.action_classifier import ClassifiedAction

        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="bash",
            params={"command": "git push --force"},
        )
        result = checker.check(action, prefs, [])
        # Should trigger at least TransitiveProhibitionRule and CriticalIrreversibleRule
        assert result.requires_confirmation
        assert "TransitiveProhibitionRule" in result.derived_rules


# ── Ontology Validator Tests ──


class TestOntologyValidator:
    def test_validate_returns_list(self, kg, hierarchy):
        """Validate should return a list (possibly empty) of warnings."""
        validator = OntologyValidator(kg, hierarchy)
        warnings = validator.validate()
        assert isinstance(warnings, list)

    def test_no_dangling_references_in_default_ontology(self, kg, hierarchy):
        """Default ontology should have no dangling references."""
        validator = OntologyValidator(kg, hierarchy)
        warnings = validator.validate()
        dangling = [w for w in warnings if "Dangling reference" in w]
        assert len(dangling) == 0

    def test_detects_missing_defaults(self, kg, hierarchy):
        """Some classes may not have defaults — validator should detect them."""
        validator = OntologyValidator(kg, hierarchy)
        warnings = validator.validate()
        missing = [w for w in warnings if "Missing defaults" in w]
        # Classes like AllActions, FileAction, ShellAction, NetworkAction, MessageAction
        # don't have explicit risk defaults in the ontology
        assert len(missing) > 0

    def test_detects_dangling_reference_with_bad_policy(self, hierarchy):
        """Adding a policy that references a nonexistent class should trigger warning."""
        from rdflib import Namespace, RDF, Literal

        kg = KnowledgeGraph()
        ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
        kg.load_directory(ontology_dir)
        # Add a policy referencing a nonexistent class
        SP = Namespace("http://safeclaw.uku.ai/ontology/policy#")
        SC = Namespace("http://safeclaw.uku.ai/ontology/agent#")
        kg.add_triple(SP["BadPolicy"], RDF.type, SP["Prohibition"])
        kg.add_triple(SP["BadPolicy"], SP["appliesTo"], SC["NonexistentAction"])
        kg.add_triple(SP["BadPolicy"], SP["reason"], Literal("test"))

        # Need to rebuild hierarchy with the updated kg
        new_hierarchy = ClassHierarchy(kg)
        validator = OntologyValidator(kg, new_hierarchy)
        warnings = validator.validate()
        dangling = [w for w in warnings if "NonexistentAction" in w]
        assert len(dangling) == 1
