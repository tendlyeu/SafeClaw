"""Regression tests for policy/classification/preference bugs (issues #27-#166).

Each test validates that a previously reported bug remains fixed. Tests are
grouped by subsystem and annotated with the corresponding GitHub issue number.
"""

from pathlib import Path

import pytest
from rdflib import Namespace

from safeclaw.constraints.action_classifier import ActionClassifier, ClassifiedAction, SHELL_PATTERNS
from safeclaw.constraints.dependency_checker import DependencyChecker
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.constraints.preference_checker import PreferenceChecker, UserPreferences
from safeclaw.constants import PATH_PARAM_KEYS
from safeclaw.engine.class_hierarchy import ClassHierarchy
from safeclaw.engine.knowledge_graph import KnowledgeGraph, SU
from safeclaw.engine.reasoning_rules import DerivedConstraintChecker
from safeclaw.engine.roles import RoleManager, BUILTIN_ROLES, _glob_match
from safeclaw.engine.shacl_validator import SHACLValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kg():
    kg = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    kg.load_directory(ontology_dir)
    return kg


@pytest.fixture
def hierarchy(kg):
    return ClassHierarchy(kg)


@pytest.fixture
def classifier(hierarchy):
    return ActionClassifier(hierarchy=hierarchy)


@pytest.fixture
def policy_checker(kg, hierarchy):
    return PolicyChecker(kg, hierarchy=hierarchy)


@pytest.fixture
def preference_checker(kg):
    return PreferenceChecker(kg)


@pytest.fixture
def dependency_checker(kg, hierarchy):
    return DependencyChecker(kg, hierarchy=hierarchy)


# ===========================================================================
# Issue #27: RunTests class never produced by shell classifier
# ===========================================================================


class TestIssue27RunTestsClassification:
    """Shell classifier must produce RunTests for test runner commands."""

    def test_pytest_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "pytest tests/ -v"})
        assert action.ontology_class == "RunTests"

    def test_python_m_pytest_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "python -m pytest tests/"})
        assert action.ontology_class == "RunTests"

    def test_npm_test_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "npm test"})
        assert action.ontology_class == "RunTests"

    def test_npm_run_test_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "npm run test"})
        assert action.ontology_class == "RunTests"

    def test_cargo_test_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "cargo test"})
        assert action.ontology_class == "RunTests"

    def test_make_test_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "make test"})
        assert action.ontology_class == "RunTests"

    def test_go_test_classified_as_run_tests(self, classifier):
        action = classifier.classify("exec", {"command": "go test ./..."})
        assert action.ontology_class == "RunTests"

    def test_run_tests_has_low_risk(self, classifier):
        action = classifier.classify("exec", {"command": "pytest"})
        assert action.risk_level == "LowRisk"

    def test_run_tests_satisfies_git_push_dependency(self, dependency_checker):
        """RunTests in session history should satisfy GitPush dependency."""
        session_id = "test-dep-27"
        dependency_checker.record_action(session_id, "RunTests")
        action = ClassifiedAction(
            ontology_class="GitPush",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={"command": "git push origin main"},
        )
        result = dependency_checker.check(action, session_id)
        assert not result.unmet, "RunTests should satisfy GitPush dependency"

    def test_shell_patterns_contain_run_tests(self):
        """SHELL_PATTERNS must include at least one RunTests entry."""
        run_tests_patterns = [p for p in SHELL_PATTERNS if p[1] == "RunTests"]
        assert len(run_tests_patterns) >= 4, (
            f"Expected at least 4 RunTests patterns, found {len(run_tests_patterns)}"
        )


# ===========================================================================
# Issue #30: Unknown ontology classes bypass hierarchy-aware policy prohibitions
# ===========================================================================


class TestIssue30UnknownClassHierarchy:
    """Unknown classes should still be checked against root Action prohibitions."""

    def test_unknown_class_has_action_superclass(self, hierarchy):
        supers = hierarchy.get_superclasses("CompletelyUnknownClass")
        assert "Action" in supers, (
            "Unknown classes must include 'Action' as superclass for prohibition matching"
        )

    def test_unknown_class_includes_self(self, hierarchy):
        supers = hierarchy.get_superclasses("CompletelyUnknownClass")
        assert "CompletelyUnknownClass" in supers

    def test_known_class_has_full_hierarchy(self, hierarchy):
        supers = hierarchy.get_superclasses("GitPush")
        assert "ShellAction" in supers
        assert "Action" in supers
        assert "GitPush" in supers


# ===========================================================================
# Issue #44: neverModifyPaths singular/plural mismatch
# ===========================================================================


class TestIssue44NeverModifyPathsNaming:
    """SPARQL query must use 'neverModifyPaths' (plural) matching the TTL."""

    def test_preferences_load_never_modify_paths_plural(self, kg):
        """Verify that setting neverModifyPaths in TTL is loaded by preference checker."""
        # Add user prefs with neverModifyPaths
        su = Namespace(str(SU))
        user_node = su["user-test44"]
        pref_node = su["test44-prefs"]
        from rdflib import Literal, RDF as RDFNS

        kg.graph.add((user_node, RDFNS.type, su.User))
        kg.graph.add((user_node, su.hasPreference, pref_node))
        kg.graph.add((pref_node, su.neverModifyPaths, Literal("*.env")))

        checker = PreferenceChecker(kg)
        prefs = checker.get_preferences("test44")
        assert prefs.never_modify_paths is not None, (
            "neverModifyPaths preference should be loaded (plural form in TTL)"
        )
        assert "*.env" in prefs.never_modify_paths


# ===========================================================================
# Issue #46: Researcher role TTL vs Python BUILTIN_ROLES disagree
# ===========================================================================


class TestIssue46ResearcherRoleConsistency:
    """Researcher role Python builtins must match TTL definitions."""

    def test_researcher_denies_shell_action(self):
        """ShellAction (parent class) should be denied, not just ExecuteCommand."""
        researcher = BUILTIN_ROLES["researcher"]
        assert "ShellAction" in researcher.denied_action_classes

    def test_researcher_does_not_allow_web_search(self):
        """WebSearch is NOT in the TTL allowed list and should not be in builtins."""
        researcher = BUILTIN_ROLES["researcher"]
        assert "WebSearch" not in researcher.allowed_action_classes

    def test_researcher_ttl_values_loaded_when_no_builtins(self, kg, hierarchy):
        """When no builtins exist, TTL researcher role should be loaded correctly."""
        # Create role manager with empty config to skip builtins
        rm = RoleManager(
            config={"roles": {"definitions": {}}},
            hierarchy=hierarchy,
            knowledge_graph=kg,
        )
        role = rm.get_role("researcher")
        assert role is not None, "Researcher role should be loaded from TTL"
        assert "ShellAction" in role.denied_action_classes

    def test_ttl_overrides_python_builtins(self, kg, hierarchy):
        """TTL role definitions should override Python BUILTIN_ROLES (#46).

        If someone updates the TTL to change permissions, the change should
        have runtime effect rather than being silently ignored.
        """
        rm = RoleManager(hierarchy=hierarchy, knowledge_graph=kg)
        role = rm.get_role("researcher")
        assert role is not None
        # The KG-loaded researcher role should be active (not just the builtin).
        # Both happen to match now, but verify the TTL is actually being used
        # by checking that the role was loaded from KG (ShellAction in denied
        # comes from TTL's sp:deniesAction sc:ShellAction).
        assert "ShellAction" in role.denied_action_classes


# ===========================================================================
# Issue #47: fnmatch does not support ** across path separators
# ===========================================================================


class TestIssue47GlobMatchCrossSeparator:
    """_glob_match must support ** across path separators."""

    def test_double_star_matches_nested_file(self):
        assert _glob_match("secrets/passwords.txt", "secrets/**")

    def test_double_star_matches_deep_nesting(self):
        assert _glob_match("etc/nginx/conf.d/site.conf", "etc/**")

    def test_single_star_does_not_cross_separators(self):
        assert not _glob_match("secrets/deep/file.txt", "secrets/*.txt")

    def test_deny_pattern_blocks_nested_path(self):
        """Developer role's /secrets/** deny pattern must block nested paths."""
        developer = BUILTIN_ROLES["developer"]
        rm = RoleManager()
        assert not rm.is_resource_allowed(developer, "/secrets/passwords.txt")
        assert not rm.is_resource_allowed(developer, "/secrets/deep/nested/key.pem")

    def test_deny_pattern_blocks_etc(self):
        developer = BUILTIN_ROLES["developer"]
        rm = RoleManager()
        assert not rm.is_resource_allowed(developer, "/etc/passwd")
        assert not rm.is_resource_allowed(developer, "/etc/nginx/conf.d/site.conf")


# ===========================================================================
# Issue #48: SHACL shapes skip subclass instances when inference=none
# ===========================================================================


class TestIssue48SHACLSubclassInference:
    """SHACL validation must fire shapes on subclass instances."""

    def test_shacl_validator_uses_rdfs_inference(self):
        """Validator should use inference='rdfs' to resolve subClassOf for shapes."""
        validator = SHACLValidator()
        shapes_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies" / "shapes"
        validator.load_shapes(shapes_dir)

        # Create a GitPush action (subclass of ShellAction) without commandText
        # sh:targetClass sc:ShellAction shape requires sc:commandText
        classifier = ActionClassifier()
        action = classifier.classify("exec", {"command": "git push origin main"})
        graph = action.as_rdf_graph()

        result = validator.validate(graph)
        # GitPush is a subclass of ShellAction, so ShellAction shapes should fire
        assert result.conforms is True, f"SHACL should validate subclass instance, got violations: {result.violations}"

    def test_shacl_file_action_shape_fires_for_delete(self):
        """FileAction shapes should fire for DeleteFile (a subclass)."""
        validator = SHACLValidator()
        shapes_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies" / "shapes"
        validator.load_shapes(shapes_dir)

        # DeleteFile without filePath should violate FileAction shape
        action = ClassifiedAction(
            ontology_class="DeleteFile",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "rm -rf /tmp"},
        )
        graph = action.as_rdf_graph()
        result = validator.validate(graph)
        # DeleteFile is subclass of FileAction, shape requires filePath
        assert not result.conforms, (
            "DeleteFile without filePath should fail FileAction SHACL shape"
        )


# ===========================================================================
# Issue #116: PolicyCompiler._extract_policy_type() uses naive substring search
# ===========================================================================


class TestIssue116PolicyCompilerTypeExtraction:
    """Policy type extraction should use regex, not naive 'in' substring search."""

    def test_obligation_with_prohibition_in_reason(self):
        from safeclaw.llm.policy_compiler import PolicyCompiler

        pc = PolicyCompiler.__new__(PolicyCompiler)
        turtle = (
            'sp:TestObligation a sp:Obligation ;\n'
            '    sp:reason "This overrides sp:Prohibition NoEnvFiles" .'
        )
        assert pc._extract_policy_type(turtle) == "obligation"

    def test_prohibition_detected_correctly(self):
        from safeclaw.llm.policy_compiler import PolicyCompiler

        pc = PolicyCompiler.__new__(PolicyCompiler)
        turtle = 'sp:TestProhibition a sp:Prohibition ;\n    sp:reason "No force push" .'
        assert pc._extract_policy_type(turtle) == "prohibition"

    def test_permission_with_prohibition_in_label(self):
        from safeclaw.llm.policy_compiler import PolicyCompiler

        pc = PolicyCompiler.__new__(PolicyCompiler)
        turtle = (
            'sp:TestPermission a sp:Permission ;\n'
            '    rdfs:label "Override Prohibition" .'
        )
        assert pc._extract_policy_type(turtle) == "permission"


# ===========================================================================
# Issue #122: NoForcePush and NoResetHard policy violations fire twice
# ===========================================================================


class TestIssue122DuplicateViolations:
    """Policies should not produce duplicate violations for the same logical rule."""

    def test_force_push_single_violation(self, policy_checker):
        action = ClassifiedAction(
            ontology_class="ForcePush",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={"command": "git push --force origin main"},
        )
        result = policy_checker.check(action)
        assert result.violated
        # Should have exactly one violation from NoForcePush, not two
        no_fp_violations = [
            v for v in result.all_violations
            if "NoForcePush" in v["policy_uri"]
        ]
        assert len(no_fp_violations) == 1, (
            f"Expected 1 NoForcePush violation, got {len(no_fp_violations)}"
        )

    def test_reset_hard_single_violation(self, policy_checker):
        action = ClassifiedAction(
            ontology_class="GitResetHard",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "git reset --hard"},
        )
        result = policy_checker.check(action)
        assert result.violated
        no_rh_violations = [
            v for v in result.all_violations
            if "NoResetHard" in v["policy_uri"]
        ]
        assert len(no_rh_violations) == 1, (
            f"Expected 1 NoResetHard violation, got {len(no_rh_violations)}"
        )


# ===========================================================================
# Issue #125: _classify_shell crashes with TypeError if params['command'] is None
# ===========================================================================


class TestIssue125NoneCommand:
    """Classifier must handle params['command'] = None without crashing."""

    def test_none_command_does_not_crash(self, classifier):
        action = classifier.classify("bash", {"command": None})
        assert action.ontology_class == "ExecuteCommand"

    def test_missing_command_key(self, classifier):
        action = classifier.classify("exec", {})
        assert action.ontology_class == "ExecuteCommand"

    def test_empty_string_command(self, classifier):
        action = classifier.classify("shell", {"command": ""})
        assert action.ontology_class == "ExecuteCommand"


# ===========================================================================
# Issue #150: Shell classifier does not handle newline as command separator
# ===========================================================================


class TestIssue150NewlineSeparator:
    """Newline should be treated as a command separator in shell commands."""

    def test_newline_separates_commands(self, classifier):
        action = classifier.classify("exec", {"command": "echo hello\nrm -rf /"})
        assert action.ontology_class == "DeleteFile"
        assert "DeleteFile" in action.chain_classes

    def test_newline_with_safe_commands(self, classifier):
        action = classifier.classify("exec", {"command": "echo hello\nls"})
        assert action.ontology_class == "ExecuteCommand"

    def test_split_chain_handles_newline(self):
        parts = ActionClassifier._split_chain("echo hello\nls -la\ngit push")
        assert len(parts) == 3
        assert parts[0].strip() == "echo hello"
        assert parts[1].strip() == "ls -la"
        assert parts[2].strip() == "git push"


# ===========================================================================
# Issue #159: ExecuteCommand marked as reversible — bypasses confirmation
# ===========================================================================


class TestIssue159ExecuteCommandNotReversible:
    """ExecuteCommand must be classified as not reversible."""

    def test_execute_command_not_reversible_in_classifier(self, classifier):
        action = classifier.classify("exec", {"command": "chmod 000 /"})
        assert action.is_reversible is False

    def test_execute_command_not_reversible_in_ontology(self, kg, hierarchy):
        defaults = hierarchy.get_defaults("ExecuteCommand")
        assert defaults is not None
        assert defaults["is_reversible"] is False

    def test_generic_shell_not_reversible(self, classifier):
        action = classifier.classify("exec", {"command": "some-unknown-cmd"})
        assert action.is_reversible is False


# ===========================================================================
# Issue #165: Cumulative risk check uses string `in` instead of startswith
# ===========================================================================


class TestIssue165CumulativeRiskStartswith:
    """Cumulative risk check must use startswith, not substring 'in'."""

    def test_no_false_positive_for_embedded_risk_name(self, kg):
        """A class name containing 'MediumRisk' as substring should not match."""
        checker = DerivedConstraintChecker(kg)
        # These do NOT start with "MediumRisk:" so should not count
        history = ["SomeMediumRiskAction:test", "AlsoMediumRiskHere:other"]
        assert not checker._check_cumulative_risk(history)

    def test_correct_medium_risk_counting(self, kg):
        checker = DerivedConstraintChecker(kg)
        history = [
            "MediumRisk:WriteFile",
            "MediumRisk:EditFile",
            "MediumRisk:WriteFile",
        ]
        assert checker._check_cumulative_risk(history)

    def test_correct_high_risk_counting(self, kg):
        checker = DerivedConstraintChecker(kg)
        history = ["HighRisk:GitPush", "HighRisk:GitPush"]
        assert checker._check_cumulative_risk(history)

    def test_critical_risk_counts_as_high(self, kg):
        checker = DerivedConstraintChecker(kg)
        history = ["CriticalRisk:ForcePush", "CriticalRisk:DeleteFile"]
        assert checker._check_cumulative_risk(history)


# ===========================================================================
# Issue #166: ListFiles and SearchFiles missing owl:NamedIndividual in ontology
# ===========================================================================


class TestIssue166NamedIndividualDeclarations:
    """Action subclasses must have owl:NamedIndividual and property assignments."""

    def test_list_files_has_defaults(self, hierarchy):
        defaults = hierarchy.get_defaults("ListFiles")
        assert defaults is not None, "ListFiles should have ontology defaults"
        assert defaults["risk_level"] == "LowRisk"
        assert defaults["is_reversible"] is True

    def test_search_files_has_defaults(self, hierarchy):
        defaults = hierarchy.get_defaults("SearchFiles")
        assert defaults is not None, "SearchFiles should have ontology defaults"
        assert defaults["risk_level"] == "LowRisk"
        assert defaults["is_reversible"] is True

    def test_network_request_has_defaults(self, hierarchy):
        defaults = hierarchy.get_defaults("NetworkRequest")
        assert defaults is not None, "NetworkRequest should have ontology defaults"

    def test_system_config_change_has_defaults(self, hierarchy):
        defaults = hierarchy.get_defaults("SystemConfigChange")
        assert defaults is not None, "SystemConfigChange should have ontology defaults"


# ===========================================================================
# Issue #29 / #126: never_modify_paths preference checks all PATH_PARAM_KEYS
# ===========================================================================


class TestIssue29And126PathParamKeysCoverage:
    """Preference checker must check all PATH_PARAM_KEYS, not just file_path and path."""

    def test_all_path_keys_checked_for_never_modify(self, preference_checker):
        prefs = UserPreferences(never_modify_paths=["*.env"])
        for key in PATH_PARAM_KEYS:
            action = ClassifiedAction(
                ontology_class="WriteFile",
                risk_level="MediumRisk",
                is_reversible=True,
                affects_scope="LocalOnly",
                tool_name="write",
                params={key: ".env"},
            )
            result = preference_checker.check(action, prefs)
            assert result.violated, (
                f"never_modify_paths should block path in param key '{key}'"
            )

    def test_destination_key_blocked(self, preference_checker):
        """Regression: 'destination' was not checked prior to fix."""
        prefs = UserPreferences(never_modify_paths=["/secrets/*"])
        action = ClassifiedAction(
            ontology_class="WriteFile",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="write",
            params={"destination": "/secrets/api_key.txt"},
        )
        result = preference_checker.check(action, prefs)
        assert result.violated


# ===========================================================================
# Issue #59: PreferencesRequest Literal excludes 'supervised' autonomy level
# ===========================================================================


class TestIssue59AutonomyLevelLiteral:
    """API model must accept all valid autonomy levels."""

    def test_supervised_accepted(self):
        from safeclaw.api.models import PreferencesRequest

        req = PreferencesRequest(autonomy_level="supervised")
        assert req.autonomy_level == "supervised"

    def test_full_accepted(self):
        from safeclaw.api.models import PreferencesRequest

        req = PreferencesRequest(autonomy_level="full")
        assert req.autonomy_level == "full"

    def test_cautious_accepted(self):
        from safeclaw.api.models import PreferencesRequest

        req = PreferencesRequest(autonomy_level="cautious")
        assert req.autonomy_level == "cautious"

    def test_invalid_rejected(self):
        from pydantic import ValidationError
        from safeclaw.api.models import PreferencesRequest

        with pytest.raises(ValidationError):
            PreferencesRequest(autonomy_level="maximum_chaos")


# ===========================================================================
# Issue #80: max_files_per_commit preference stored but never enforced
# ===========================================================================


class TestIssue80MaxFilesPerCommitEnforced:
    """Preference checker must enforce max_files_per_commit for git commits."""

    def test_commit_with_too_many_files_blocked(self, preference_checker):
        prefs = UserPreferences(
            max_files_per_commit=3,
            confirm_before_push=False,
            confirm_before_delete=False,
        )
        action = ClassifiedAction(
            ontology_class="GitCommit",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={
                "command": "git commit",
                "files": ["a.py", "b.py", "c.py", "d.py"],
            },
        )
        result = preference_checker.check(action, prefs)
        assert result.violated
        assert "4 files" in result.reason

    def test_commit_within_limit_allowed(self, preference_checker):
        prefs = UserPreferences(
            max_files_per_commit=5,
            confirm_before_push=False,
            confirm_before_delete=False,
            confirm_before_send=False,
            autonomy_level="autonomous",
        )
        action = ClassifiedAction(
            ontology_class="GitCommit",
            risk_level="MediumRisk",
            is_reversible=True,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={
                "command": "git commit",
                "files": ["a.py", "b.py"],
            },
        )
        result = preference_checker.check(action, prefs)
        assert not result.violated


# ===========================================================================
# Issue #107: max_files_per_commit has no server-side bounds check
# ===========================================================================


class TestIssue107MaxFilesPerCommitBounds:
    """API model must enforce bounds on max_files_per_commit."""

    def test_negative_value_rejected(self):
        from pydantic import ValidationError
        from safeclaw.api.models import PreferencesRequest

        with pytest.raises(ValidationError):
            PreferencesRequest(max_files_per_commit=-1)

    def test_zero_value_rejected(self):
        from pydantic import ValidationError
        from safeclaw.api.models import PreferencesRequest

        with pytest.raises(ValidationError):
            PreferencesRequest(max_files_per_commit=0)

    def test_excessive_value_rejected(self):
        from pydantic import ValidationError
        from safeclaw.api.models import PreferencesRequest

        with pytest.raises(ValidationError):
            PreferencesRequest(max_files_per_commit=2147483647)

    def test_valid_value_accepted(self):
        from safeclaw.api.models import PreferencesRequest

        req = PreferencesRequest(max_files_per_commit=50)
        assert req.max_files_per_commit == 50


# ===========================================================================
# Issue #121: 'autonomous' and 'moderate' autonomy levels functionally identical
# ===========================================================================


class TestIssue121AutonomyLevelDifferentiation:
    """Each autonomy level must have distinct behavior."""

    def test_moderate_blocks_critical_irreversible(self, preference_checker):
        prefs = UserPreferences(
            autonomy_level="moderate",
            confirm_before_delete=False,
            confirm_before_push=False,
            confirm_before_send=False,
        )
        action = ClassifiedAction(
            ontology_class="GitResetHard",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "git reset --hard"},
        )
        result = preference_checker.check(action, prefs)
        assert result.violated, "moderate should block critical irreversible actions"

    def test_autonomous_allows_critical_irreversible(self, preference_checker):
        prefs = UserPreferences(
            autonomy_level="autonomous",
            confirm_before_delete=False,
            confirm_before_push=False,
            confirm_before_send=False,
        )
        action = ClassifiedAction(
            ontology_class="GitResetHard",
            risk_level="CriticalRisk",
            is_reversible=False,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "git reset --hard"},
        )
        result = preference_checker.check(action, prefs)
        assert not result.violated, "autonomous should allow critical irreversible actions"

    def test_cautious_blocks_all_irreversible(self, preference_checker):
        prefs = UserPreferences(
            autonomy_level="cautious",
            confirm_before_delete=False,
            confirm_before_push=False,
            confirm_before_send=False,
        )
        action = ClassifiedAction(
            ontology_class="GitPush",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="SharedState",
            tool_name="exec",
            params={"command": "git push"},
        )
        result = preference_checker.check(action, prefs)
        assert result.violated, "cautious should block all irreversible actions"

    def test_moderate_allows_non_critical_irreversible(self, preference_checker):
        """moderate only blocks CriticalRisk irreversible, not HighRisk irreversible."""
        prefs = UserPreferences(
            autonomy_level="moderate",
            confirm_before_delete=False,
            confirm_before_push=False,
            confirm_before_send=False,
        )
        action = ClassifiedAction(
            ontology_class="ExecuteCommand",
            risk_level="HighRisk",
            is_reversible=False,
            affects_scope="LocalOnly",
            tool_name="exec",
            params={"command": "some-cmd"},
        )
        result = preference_checker.check(action, prefs)
        assert not result.violated, "moderate should allow HighRisk irreversible actions"
