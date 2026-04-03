"""Tests for NemoClaw YAML policy loader."""

import pytest
from pathlib import Path

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP
from safeclaw.nemoclaw.policy_loader import NemoClawPolicyLoader


@pytest.fixture
def kg():
    """Create a knowledge graph with the NemoClaw ontology loaded."""
    graph = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    graph.load_directory(ontology_dir)
    return graph


@pytest.fixture
def policy_dir(tmp_path):
    """Create a temporary policy directory."""
    return tmp_path / "policies"


def _write_yaml(policy_dir: Path, filename: str, content: str) -> None:
    """Helper to write a YAML file to the policy directory."""
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / filename).write_text(content, encoding="utf-8")


# ======================================================================
# Legacy format tests (backward compatibility)
# ======================================================================


class TestLegacyNetworkRules:
    def test_network_rule_generates_triples(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: github-https
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host ?port ?protocol WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host ;
                      sp:allowsPort ?port ;
                      sp:allowsProtocol ?protocol .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "github.com"
        assert int(results[0]["port"]) == 443
        assert str(results[0]["protocol"]) == "https"

    def test_network_rule_without_port(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: any-port
    host: "example.com"
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
                FILTER NOT EXISTS {{ ?rule sp:allowsPort ?port }}
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "example.com"

    def test_deny_rule_skipped(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: denied
    host: "evil.com"
    allow: false
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 0

    def test_binary_restriction(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: git-only
    host: "github.com"
    port: 443
    protocol: https
    allow: true
    binary: "/usr/bin/git"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?binary WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:binaryRestriction ?binary .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["binary"]) == "/usr/bin/git"

    def test_multiple_rules(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
  - name: pypi
    host: "pypi.org"
    port: 443
    protocol: https
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{
                ?rule a sp:NemoNetworkRule ; sp:allowsHost ?host .
            }}
        """)
        hosts = {str(r["host"]) for r in results}
        assert hosts == {"github.com", "pypi.org"}


class TestLegacyFilesystemRules:
    def test_filesystem_rule_generates_triples(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
  - path: "/usr"
    mode: "read-only"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/sandbox"] == "read-write"
        assert rules["/usr"] == "read-only"

    def test_denied_path(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/etc/shadow"
    mode: "denied"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/etc/shadow"] == "denied"

    def test_alternative_mode_key(self, kg, policy_dir):
        """fs_rules with 'access' key instead of 'mode'."""
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
fs_rules:
  - path: "/tmp"
    access: "read-write"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/tmp"] == "read-write"


# ======================================================================
# Real NemoClaw format tests
# ======================================================================


class TestRealNetworkPolicies:
    def test_endpoint_generates_triples(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
    binaries:
      - { path: /usr/local/bin/claude }
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host ?port ?protocol WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host ;
                      sp:allowsPort ?port ;
                      sp:allowsProtocol ?protocol .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "api.anthropic.com"
        assert int(results[0]["port"]) == 443
        assert str(results[0]["protocol"]) == "rest"

    def test_enforcement_and_tls_stored(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  my_group:
    name: my_group
    endpoints:
      - host: example.com
        port: 443
        protocol: rest
        enforcement: audit
        tls: passthrough
    binaries: []
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?enforcement ?tls WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:enforcement ?enforcement ;
                      sp:tlsMode ?tls .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["enforcement"]) == "audit"
        assert str(results[0]["tls"]) == "passthrough"

    def test_policy_group_stored(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
    binaries: []
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?group WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:policyGroup ?group .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["group"]) == "claude_code"

    def test_binary_restrictions_from_group(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/local/bin/claude }
      - { path: /usr/bin/node }
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?binary WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:binaryRestriction ?binary .
            }}
        """)
        binaries = {str(r["binary"]) for r in results}
        assert binaries == {"/usr/local/bin/claude", "/usr/bin/node"}

    def test_multiple_groups(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
    binaries: []
  package_manager:
    name: package_manager
    endpoints:
      - host: pypi.org
        port: 443
        protocol: rest
      - host: registry.npmjs.org
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/bin/pip }
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
            }}
        """)
        hosts = {str(r["host"]) for r in results}
        assert hosts == {
            "api.anthropic.com",
            "pypi.org",
            "registry.npmjs.org",
        }

    def test_multiple_endpoints_share_binaries(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  git_group:
    name: git_group
    endpoints:
      - host: github.com
        port: 443
        protocol: rest
      - host: gitlab.com
        port: 443
        protocol: rest
    binaries:
      - { path: /usr/bin/git }
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host ?binary WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host ;
                      sp:binaryRestriction ?binary .
            }}
        """)
        assert len(results) == 2
        hosts = {str(r["host"]) for r in results}
        assert hosts == {"github.com", "gitlab.com"}
        for r in results:
            assert str(r["binary"]) == "/usr/bin/git"

    def test_endpoint_without_optional_fields(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  minimal:
    name: minimal
    endpoints:
      - host: example.com
    binaries: []
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
                FILTER NOT EXISTS {{ ?rule sp:allowsPort ?p }}
                FILTER NOT EXISTS {{ ?rule sp:allowsProtocol ?proto }}
                FILTER NOT EXISTS {{ ?rule sp:enforcement ?e }}
                FILTER NOT EXISTS {{ ?rule sp:tlsMode ?t }}
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "example.com"


class TestRealFilesystemPolicy:
    def test_read_only_paths(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
filesystem_policy:
  read_only:
    - /usr
    - /lib
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/usr"] == "read-only"
        assert rules["/lib"] == "read-only"

    def test_read_write_paths(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
filesystem_policy:
  read_write:
    - /sandbox
    - /tmp
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/sandbox"] == "read-write"
        assert rules["/tmp"] == "read-write"

    def test_mixed_read_only_and_read_write(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
filesystem_policy:
  include_workdir: true
  read_only:
    - /usr
    - /lib
  read_write:
    - /sandbox
    - /tmp
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/usr"] == "read-only"
        assert rules["/lib"] == "read-only"
        assert rules["/sandbox"] == "read-write"
        assert rules["/tmp"] == "read-write"
        assert len(rules) == 4

    def test_include_workdir_ignored(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
filesystem_policy:
  include_workdir: true
  read_only:
    - /usr
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) == 1

    def test_empty_filesystem_policy(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
filesystem_policy:
  include_workdir: false
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) == 0


class TestRealCombinedPolicy:
    def test_full_real_format_document(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
        rules:
          - allow: { method: GET, path: "/**" }
          - allow: { method: POST, path: "/**" }
    binaries:
      - { path: /usr/local/bin/claude }

filesystem_policy:
  include_workdir: true
  read_only:
    - /usr
    - /lib
  read_write:
    - /sandbox
    - /tmp
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        net_results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
            }}
        """)
        assert len(net_results) == 1
        assert str(net_results[0]["host"]) == "api.anthropic.com"

        fs_results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path .
            }}
        """)
        paths = {str(r["path"]) for r in fs_results}
        assert paths == {"/usr", "/lib", "/sandbox", "/tmp"}


# ======================================================================
# Provenance and reason tests (format-agnostic)
# ======================================================================


class TestProvenance:
    def test_network_rule_has_nemoclaw_source(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: test
    host: "example.com"
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?source WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:source ?source .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["source"]) == "nemoclaw"

    def test_filesystem_rule_has_nemoclaw_source(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/data"
    mode: "read-write"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?source WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:source ?source .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["source"]) == "nemoclaw"

    def test_real_format_has_nemoclaw_source(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  test_group:
    name: test_group
    endpoints:
      - host: example.com
        port: 443
        protocol: rest
    binaries: []
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?source WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:source ?source .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["source"]) == "nemoclaw"


class TestReasonGeneration:
    def test_network_reason_with_port_and_protocol(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: test
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?reason WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:reason ?reason .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["reason"]) == "NemoClaw: host github.com allowed on port 443 (https)"

    def test_network_reason_without_port(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: test
    host: "example.com"
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?reason WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:reason ?reason .
            }}
        """)
        assert str(results[0]["reason"]) == "NemoClaw: host example.com allowed"

    def test_filesystem_read_only_reason(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/usr"
    mode: "read-only"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?reason WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:reason ?reason .
            }}
        """)
        assert (
            str(results[0]["reason"]) == "NemoClaw: /usr is read-only (Landlock filesystem policy)"
        )

    def test_filesystem_read_write_reason(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?reason WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:reason ?reason .
            }}
        """)
        assert str(results[0]["reason"]) == "NemoClaw: /sandbox is read-write"


# ======================================================================
# Error handling tests
# ======================================================================


class TestErrorHandling:
    def test_malformed_yaml_skipped(self, kg, policy_dir, caplog):
        _write_yaml(policy_dir, "bad.yaml", "{{{{not valid yaml: [")
        _write_yaml(
            policy_dir,
            "good.yaml",
            """
rules:
  - name: test
    host: "example.com"
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 1

    def test_missing_directory_returns_silently(self, kg, tmp_path):
        missing_dir = tmp_path / "nonexistent"
        loader = NemoClawPolicyLoader(missing_dir)
        loader.load(kg)

    def test_empty_directory(self, kg, policy_dir):
        policy_dir.mkdir(parents=True, exist_ok=True)
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

    def test_non_dict_yaml(self, kg, policy_dir, caplog):
        _write_yaml(policy_dir, "list.yaml", "- item1\n- item2\n")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

    def test_unknown_access_mode_skipped(self, kg, policy_dir, caplog):
        _write_yaml(
            policy_dir,
            "fs.yaml",
            """
filesystem:
  - path: "/data"
    mode: "execute-only"
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) == 0

    def test_rule_missing_host_skipped(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "net.yaml",
            """
rules:
  - name: no-host
    port: 443
    allow: true
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 0

    def test_real_format_endpoint_missing_host_skipped(self, kg, policy_dir):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  bad_group:
    name: bad_group
    endpoints:
      - port: 443
        protocol: rest
    binaries: []
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 0

    def test_real_format_non_dict_group_skipped(self, kg, policy_dir, caplog):
        _write_yaml(
            policy_dir,
            "policy.yaml",
            """
network_policies:
  bad_group: "not a dict"
  good_group:
    name: good_group
    endpoints:
      - host: example.com
        port: 443
    binaries: []
""",
        )
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "example.com"
