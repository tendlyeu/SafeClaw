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
# Legacy network allowlist tests
# ======================================================================


class TestLegacyNemoNetworkRules:
    def test_allowed_host_passes(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://github.com/repo")
        result = checker.check(action)
        assert result.violated is False

    def test_disallowed_host_blocked(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
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
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=False)
        action = _make_action("WebFetch", url="https://evil.com/data")
        result = checker.check(action)
        assert result.violated is False

    def test_port_default_https(self, kg, tmp_path):
        """URL without explicit port defaults to 443 for https."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    port: 443
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://example.com/page")
        result = checker.check(action)
        assert result.violated is False

    def test_port_default_http(self, kg, tmp_path):
        """URL without explicit port defaults to 80 for http."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    port: 80
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="http://example.com/page")
        result = checker.check(action)
        assert result.violated is False

    def test_wrong_port_blocked(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="http://example.com/page")
        result = checker.check(action)
        assert result.violated is True

    def test_wildcard_host(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: github-all
    host: "*.github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://api.github.com/repos")
        result = checker.check(action)
        assert result.violated is False

    def test_wildcard_host_base_domain(self, kg, tmp_path):
        """*.github.com should also match github.com itself."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: github-all
    host: "*.github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://github.com/repo")
        result = checker.check(action)
        assert result.violated is False

    def test_rule_without_port_matches_any_port(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: any-port
    host: "example.com"
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://example.com:8080/api")
        result = checker.check(action)
        assert result.violated is False

    def test_rule_without_protocol_matches_any(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: any-proto
    host: "example.com"
    port: 443
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://example.com/page")
        result = checker.check(action)
        assert result.violated is False

    def test_exec_curl_triggers_network_check(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""",
        )
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
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""",
        )
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
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/src/main.py")
        result = checker.check(action)
        assert result.violated is False

    def test_endpoint_param_used(self, kg, tmp_path):
        """WebSearch may use 'endpoint' instead of 'url'."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: search
    host: "search.example.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WebSearch",
            tool_name="web_search",
            endpoint="https://search.example.com/q?query=test",
        )
        result = checker.check(action)
        assert result.violated is False


# ======================================================================
# Real NemoClaw format network tests
# ======================================================================


class TestRealNemoNetworkRules:
    def test_rest_protocol_allows_https(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  api_group:
    name: api_group
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://api.anthropic.com/v1/messages")
        result = checker.check(action)
        assert result.violated is False

    def test_rest_protocol_allows_http(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  api_group:
    name: api_group
    endpoints:
      - host: internal.example.com
        port: 80
        protocol: rest
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="http://internal.example.com/api")
        result = checker.check(action)
        assert result.violated is False

    def test_rest_protocol_blocks_ws(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  api_group:
    name: api_group
    endpoints:
      - host: example.com
        port: 443
        protocol: rest
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="wss://example.com/socket")
        result = checker.check(action)
        assert result.violated is True

    def test_websocket_protocol_allows_wss(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  ws_group:
    name: ws_group
    endpoints:
      - host: stream.example.com
        port: 443
        protocol: websocket
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="wss://stream.example.com/events")
        result = checker.check(action)
        assert result.violated is False

    def test_full_protocol_matches_any_scheme(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  full_group:
    name: full_group
    endpoints:
      - host: anything.example.com
        port: 443
        protocol: full
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://anything.example.com/path")
        result = checker.check(action)
        assert result.violated is False

    def test_disallowed_host_blocked(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  api_group:
    name: api_group
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://evil.com/exfiltrate")
        result = checker.check(action)
        assert result.violated is True
        assert "evil.com" in result.reason

    def test_multiple_groups_allow_multiple_hosts(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  claude:
    name: claude
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
    binaries: []
  pypi:
    name: pypi
    endpoints:
      - host: pypi.org
        port: 443
        protocol: rest
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        assert (
            checker.check(
                _make_action(
                    "WebFetch",
                    url="https://api.anthropic.com/v1/messages",
                )
            ).violated
            is False
        )
        assert (
            checker.check(_make_action("WebFetch", url="https://pypi.org/simple/")).violated
            is False
        )
        assert checker.check(_make_action("WebFetch", url="https://evil.com/data")).violated is True


# ======================================================================
# Protocol mapping tests
# ======================================================================


class TestProtocolMapping:
    def test_rest_matches_https(self):
        assert PolicyChecker._protocol_matches("rest", "https") is True

    def test_rest_matches_http(self):
        assert PolicyChecker._protocol_matches("rest", "http") is True

    def test_rest_rejects_wss(self):
        assert PolicyChecker._protocol_matches("rest", "wss") is False

    def test_grpc_matches_https(self):
        assert PolicyChecker._protocol_matches("grpc", "https") is True

    def test_grpc_matches_http(self):
        assert PolicyChecker._protocol_matches("grpc", "http") is True

    def test_websocket_matches_wss(self):
        assert PolicyChecker._protocol_matches("websocket", "wss") is True

    def test_websocket_matches_ws(self):
        assert PolicyChecker._protocol_matches("websocket", "ws") is True

    def test_websocket_rejects_https(self):
        assert PolicyChecker._protocol_matches("websocket", "https") is False

    def test_full_matches_anything(self):
        assert PolicyChecker._protocol_matches("full", "https") is True
        assert PolicyChecker._protocol_matches("full", "http") is True
        assert PolicyChecker._protocol_matches("full", "wss") is True
        assert PolicyChecker._protocol_matches("full", "ftp") is True

    def test_exact_scheme_fallback(self):
        assert PolicyChecker._protocol_matches("https", "https") is True
        assert PolicyChecker._protocol_matches("http", "http") is True
        assert PolicyChecker._protocol_matches("https", "http") is False


# ======================================================================
# Binary restriction tests
# ======================================================================


class TestBinaryRestriction:
    def test_binary_match_allows_exec_command(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  git_group:
    name: git_group
    endpoints:
      - host: github.com
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/bin/git }
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="git clone https://github.com/repo.git",
        )
        result = checker.check(action)
        assert result.violated is False

    def test_binary_mismatch_blocks_exec_command(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  git_group:
    name: git_group
    endpoints:
      - host: github.com
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/bin/git }
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="curl https://github.com/repo",
        )
        result = checker.check(action)
        assert result.violated is True

    def test_binary_skipped_for_web_fetch(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  git_group:
    name: git_group
    endpoints:
      - host: github.com
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/bin/git }
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://github.com/api/repos")
        result = checker.check(action)
        assert result.violated is False

    def test_no_binaries_matches_any_command(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  open_group:
    name: open_group
    endpoints:
      - host: example.com
        port: 443
        protocol: rest
    binaries: []
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="curl https://example.com/api",
        )
        result = checker.check(action)
        assert result.violated is False

    def test_multiple_binaries_any_match(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  multi:
    name: multi
    endpoints:
      - host: github.com
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/bin/git }
      - { path: /usr/bin/ssh }
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ExecuteCommand",
            tool_name="exec",
            command="ssh git@github.com",
        )
        result = checker.check(action)
        assert result.violated is False


# ======================================================================
# Legacy filesystem policy tests
# ======================================================================


class TestLegacyNemoFilesystemRules:
    def test_read_write_allows_write(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/output.txt",
        )
        result = checker.check(action)
        assert result.violated is False

    def test_read_write_allows_read(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "ReadFile",
            tool_name="read",
            file_path="/sandbox/data.txt",
        )
        result = checker.check(action)
        assert result.violated is False

    def test_read_only_blocks_write(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/usr"
    mode: "read-only"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/usr/bin/evil",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_read_only_allows_read(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/usr"
    mode: "read-only"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/usr/bin/ls")
        result = checker.check(action)
        assert result.violated is False

    def test_denied_blocks_all(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/etc/shadow"
    mode: "denied"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/etc/shadow")
        result = checker.check(action)
        assert result.violated is True
        assert "denied" in result.reason

    def test_denied_blocks_write(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/etc/shadow"
    mode: "denied"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WriteFile", tool_name="write", file_path="/etc/shadow")
        result = checker.check(action)
        assert result.violated is True

    def test_most_specific_wins(self, kg, tmp_path):
        """More specific path rule takes precedence."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
  - path: "/sandbox/secrets"
    mode: "read-only"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/secrets/config.txt",
        )
        result = checker.check(action)
        assert result.violated is True
        nemo_violations = [
            v for v in result.all_violations if v["policy_type"] == "NemoFilesystemRule"
        ]
        assert len(nemo_violations) == 1
        assert "read-only" in nemo_violations[0]["reason"]

        action2 = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/output/data.txt",
        )
        result2 = checker.check(action2)
        assert result2.violated is False

    def test_outside_sandbox_blocked(self, kg, tmp_path):
        """Path not covered by any rule is blocked."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/home/user/.ssh/id_rsa",
        )
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
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://example.com")
        result = checker.check(action)
        assert result.violated is False

    def test_delete_on_read_only_blocked(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/data"
    mode: "read-only"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "DeleteFile",
            tool_name="delete",
            file_path="/data/important.db",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_exact_path_match(self, kg, tmp_path):
        """A file path that exactly matches the rule path should be governed."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "denied"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/sandbox")
        result = checker.check(action)
        assert result.violated is True
        assert "denied" in result.reason


# ======================================================================
# Real NemoClaw format filesystem tests
# ======================================================================


class TestRealNemoFilesystemRules:
    def test_read_write_allows_write(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem_policy:
  read_write:
    - /sandbox
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/output.txt",
        )
        result = checker.check(action)
        assert result.violated is False

    def test_read_only_blocks_write(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem_policy:
  read_only:
    - /usr
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/usr/local/bin/evil",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "read-only" in result.reason

    def test_read_only_allows_read(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem_policy:
  read_only:
    - /usr
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("ReadFile", tool_name="read", file_path="/usr/bin/ls")
        result = checker.check(action)
        assert result.violated is False

    def test_outside_policy_blocked(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem_policy:
  read_write:
    - /sandbox
  read_only:
    - /usr
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/home/user/.ssh/key",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "outside NemoClaw sandbox" in result.reason


class TestNemoPathTraversal:
    """Verify path traversal via '..' is blocked by os.path.normpath."""

    def test_path_traversal_blocked(self, kg, tmp_path):
        """Path with .. must be normalized before matching."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/../etc/shadow",
        )
        result = checker.check(action)
        assert result.violated is True
        assert "outside NemoClaw sandbox" in result.reason

    def test_path_traversal_within_sandbox_allowed(self, kg, tmp_path):
        """Path with .. that stays within sandbox should be allowed."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/sandbox/sub/../file.txt",
        )
        result = checker.check(action)
        assert result.violated is False


class TestNemoNetworkFailClosed:
    """Verify that network checks fail-closed when URL cannot be extracted."""

    def test_network_curl_without_scheme_blocked(self, kg, tmp_path):
        """curl with bare IP (no http://) should be blocked when rules exist."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: example
    host: "example.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
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
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
rules:
  - name: only-github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=False)
        action = _make_action("WebFetch", url="https://evil.com")
        result = checker.check(action)
        assert result.violated is False

    def test_filesystem_check_skipped_when_disabled(self, kg, tmp_path):
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=False)
        action = _make_action(
            "WriteFile",
            tool_name="write",
            file_path="/outside/sandbox",
        )
        result = checker.check(action)
        assert result.violated is False


# ======================================================================
# Enforcement field filtering tests
# ======================================================================


class TestEnforcementFiltering:
    def test_disabled_rule_skipped(self, kg, tmp_path):
        """Rule with enforcement=disabled should not count as an allowlist entry."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  disabled_api:
    endpoints:
      - host: api.example.com
        port: 443
        protocol: rest
        enforcement: disabled
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        # No enforce rules exist, so no allowlist -> skip (allow)
        action = _make_action("WebFetch", url="https://api.example.com/data")
        result = checker.check(action)
        assert result.violated is False

    def test_disabled_rule_does_not_allow_other_hosts(self, kg, tmp_path):
        """Disabled rules don't create an allowlist; other hosts should also pass."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  disabled_api:
    endpoints:
      - host: api.example.com
        port: 443
        enforcement: disabled
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://other.com/data")
        result = checker.check(action)
        assert result.violated is False

    def test_enforce_rule_blocks_unmatched(self, kg, tmp_path):
        """Enforce rule creates an allowlist that blocks unmatched hosts."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  api:
    endpoints:
      - host: api.example.com
        port: 443
        protocol: rest
        enforcement: enforce
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action = _make_action("WebFetch", url="https://evil.com/data")
        result = checker.check(action)
        assert result.violated is True

    def test_mixed_enforce_and_disabled(self, kg, tmp_path):
        """Only enforce rules count; disabled rules are ignored."""
        _load_network_policy(
            kg,
            tmp_path / "policies",
            """
network_policies:
  allowed:
    endpoints:
      - host: api.example.com
        port: 443
        protocol: rest
        enforcement: enforce
  ignored:
    endpoints:
      - host: evil.com
        port: 443
        enforcement: disabled
""",
        )
        checker = PolicyChecker(kg, nemoclaw_enabled=True)
        action1 = _make_action("WebFetch", url="https://api.example.com/data")
        result1 = checker.check(action1)
        assert result1.violated is False

        action2 = _make_action("WebFetch", url="https://evil.com/data")
        result2 = checker.check(action2)
        assert result2.violated is True
