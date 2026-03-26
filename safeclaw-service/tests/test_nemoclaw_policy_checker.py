"""Tests for PolicyChecker NemoClaw extensions."""

import pytest
from pathlib import Path

from safeclaw.constraints.action_classifier import ClassifiedAction
from safeclaw.constraints.policy_checker import PolicyChecker
from safeclaw.engine.knowledge_graph import KnowledgeGraph
from safeclaw.nemoclaw.policy_loader import NemoClawPolicyLoader


@pytest.fixture
def kg():
    """Knowledge graph with NemoClaw ontology."""
    graph = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    graph.load_directory(ontology_dir)
    return graph


def _load_network_policy(kg, policy_dir, yaml_content):
    """Helper to write YAML and load into KG."""
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy.yaml").write_text(yaml_content, encoding="utf-8")
    NemoClawPolicyLoader(policy_dir).load(kg)


def _make_action(ontology_class, tool_name="web_fetch", **params):
    """Helper to create a ClassifiedAction."""
    return ClassifiedAction(
        ontology_class=ontology_class,
        risk_level="MediumRisk",
        is_reversible=True,
        affects_scope="ExternalWorld",
        tool_name=tool_name,
        params=params,
    )


# ======================================================================
# Network allowlist tests
# ======================================================================

class TestNemoNetworkRules:
    def test_allowed_host_passes(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://github.com/repo")
        result = checker.check(action)
        assert result.violated is False

    def test_disallowed_host_blocked(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://evil.com/data")
        result = checker.check(action)
        assert result.violated is True
        assert "Not in NemoClaw network allowlist" in result.reason
        assert "evil.com" in result.reason

    def test_no_network_rules_skips(self, kg):
        """When no NemoClaw network rules exist, skip the check entirely."""
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://anything.com/")
        result = checker.check(action)
        assert result.violated is False

    def test_nemoclaw_disabled_skips(self, kg, tmp_path):
        """When nemoclaw_enabled is False, NemoClaw checks are skipped."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=False)
        action = _make_action("WebFetch", url="https://evil.com/data")
        result = checker.check(action)
        assert result.violated is False

    def test_port_default_https(self, kg, tmp_path):
        """URL without explicit port defaults to 443 for https."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    port: 443
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://example.com/page")
        result = checker.check(action)
        assert result.violated is False

    def test_port_default_http(self, kg, tmp_path):
        """URL without explicit port defaults to 80 for http."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    port: 80
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="http://example.com/page")
        result = checker.check(action)
        assert result.violated is False

    def test_wrong_port_blocked(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="http://example.com/page")
        result = checker.check(action)
        assert result.violated is True

    def test_wildcard_host(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: github-all
    host: "*.github.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://api.github.com/repos")
        result = checker.check(action)
        assert result.violated is False

    def test_wildcard_host_base_domain(self, kg, tmp_path):
        """*.github.com should also match github.com itself."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: github-all
    host: "*.github.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://github.com/repo")
        result = checker.check(action)
        assert result.violated is False

    def test_rule_without_port_matches_any_port(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: any-port
    host: "example.com"
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://example.com:8080/api")
        result = checker.check(action)
        assert result.violated is False

    def test_rule_without_protocol_matches_any(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: any-proto
    host: "example.com"
    port: 443
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        # https scheme but no protocol restriction on rule
        action = _make_action("WebFetch", url="https://example.com/page")
        result = checker.check(action)
        assert result.violated is False

    def test_exec_curl_triggers_network_check(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="curl https://evil.com/api",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "evil.com" in result.reason

    def test_exec_curl_allowed_host(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="curl https://example.com/api",
        )
        result = checker.check(action)
        assert result.violated is False

    def test_non_network_action_skipped(self, kg, tmp_path):
        """ReadFile should not trigger network checks."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/src/main.py")
        result = checker.check(action)
        assert result.violated is False

    def test_endpoint_param_used(self, kg, tmp_path):
        """WebSearch may use 'endpoint' instead of 'url'."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: search
    host: "search.example.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WebSearch",
            tool_name="web_search",
            endpoint="https://search.example.com/q?query=test",
        )
        result = checker.check(action)
        assert result.violated is False


# ======================================================================
# Filesystem policy tests
# ======================================================================

class TestNemoFilesystemRules:
    def test_read_write_allows_write(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WriteFile", tool_name="write", file_path="/sandbox/output.txt")
        result = checker.check(action)
        assert result.violated is False

    def test_read_write_allows_read(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/sandbox/data.txt")
        result = checker.check(action)
        assert result.violated is False

    def test_read_only_blocks_write(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/usr"
    mode: "read-only"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WriteFile", tool_name="write", file_path="/usr/bin/evil")
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_read_only_allows_read(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/usr"
    mode: "read-only"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/usr/bin/ls")
        result = checker.check(action)
        assert result.violated is False

    def test_denied_blocks_all(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/etc/shadow"
    mode: "denied"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/etc/shadow")
        result = checker.check(action)
        assert result.violated is True
        assert "denied" in result.reason

    def test_denied_blocks_write(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/etc/shadow"
    mode: "denied"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WriteFile", tool_name="write", file_path="/etc/shadow")
        result = checker.check(action)
        assert result.violated is True

    def test_most_specific_wins(self, kg, tmp_path):
        """More specific path rule takes precedence."""
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
  - path: "/sandbox/secrets"
    mode: "read-only"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        # Write to /sandbox/secrets should be blocked (read-only wins)
        action = _make_action("WriteFile", tool_name="write", file_path="/sandbox/secrets/config.txt")
        result = checker.check(action)
        assert result.violated is True
        nemo_violations = [
            v for v in result.all_violations if v["policy_type"] == "NemoFilesystemRule"
        ]
        assert len(nemo_violations) == 1
        assert "read-only" in nemo_violations[0]["reason"]

        # Write to /sandbox/output should be allowed (read-write wins)
        action2 = _make_action("WriteFile", tool_name="write", file_path="/sandbox/output/data.txt")
        result2 = checker.check(action2)
        assert result2.violated is False

    def test_outside_sandbox_blocked(self, kg, tmp_path):
        """Path not covered by any rule is blocked."""
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WriteFile", tool_name="write", file_path="/home/user/.ssh/id_rsa")
        result = checker.check(action)
        assert result.violated is True
        assert "outside NemoClaw sandbox" in result.reason

    def test_no_fs_rules_skips(self, kg):
        """When no NemoClaw filesystem rules exist, skip."""
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WriteFile", tool_name="write", file_path="/any/path")
        result = checker.check(action)
        assert result.violated is False

    def test_non_file_action_skipped(self, kg, tmp_path):
        """WebFetch should not trigger filesystem checks."""
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        # WebFetch with no NemoClaw network rules should pass (both checks skip)
        action = _make_action("WebFetch", url="https://example.com")
        result = checker.check(action)
        assert result.violated is False

    def test_delete_on_read_only_blocked(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/data"
    mode: "read-only"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("DeleteFile", tool_name="delete", file_path="/data/important.db")
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_exact_path_match(self, kg, tmp_path):
        """A file path that exactly matches the rule path should be governed."""
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "denied"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/sandbox")
        result = checker.check(action)
        assert result.violated is True
        assert "denied" in result.reason


class TestNemoPathTraversal:
    """Verify path traversal via '..' is blocked by os.path.normpath."""

    def test_path_traversal_blocked(self, kg, tmp_path):
        """Path with .. must be normalized before matching."""
        # /sandbox/../etc/shadow should NOT match /sandbox read-write
        # After normpath it becomes /etc/shadow, which is outside the sandbox
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile", tool_name="write", file_path="/sandbox/../etc/shadow"
        )
        result = checker.check(action)
        assert result.violated is True
        assert "outside NemoClaw sandbox" in result.reason

    def test_path_traversal_within_sandbox_allowed(self, kg, tmp_path):
        """Path with .. that stays within sandbox should be allowed."""
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        # /sandbox/sub/../file.txt normalizes to /sandbox/file.txt — still in sandbox
        action = _make_action(
            "WriteFile", tool_name="write", file_path="/sandbox/sub/../file.txt"
        )
        result = checker.check(action)
        assert result.violated is False


class TestNemoNetworkFailClosed:
    """Verify that network checks fail-closed when URL cannot be extracted."""

    def test_network_curl_without_scheme_blocked(self, kg, tmp_path):
        """curl with bare IP (no http://) should be blocked when network rules exist."""
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        # curl 10.0.0.1 has no http:// scheme, so _extract_url returns None
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="curl 10.0.0.1/sensitive-data",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "could not be extracted" in result.reason

    def test_network_no_url_no_rules_allows(self, kg):
        """If no NemoClaw network rules exist, missing URL should not block."""
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="curl 10.0.0.1/data",
        )
        result = checker.check(action)
        assert result.violated is False


class TestNemoClawDisabled:
    """Verify NemoClaw checks are completely gated."""

    def test_network_check_skipped_when_disabled(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
rules:
  - name: only-github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=False)
        action = _make_action("WebFetch", url="https://evil.com")
        result = checker.check(action)
        assert result.violated is False

    def test_filesystem_check_skipped_when_disabled(self, kg, tmp_path):
        _load_network_policy(kg, tmp_path / "policies", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        checker = PolicyChecker(kg, nemoclaw_enabled=False)
        action = _make_action("WriteFile", tool_name="write", file_path="/outside/sandbox")
        result = checker.check(action)
        assert result.violated is False
