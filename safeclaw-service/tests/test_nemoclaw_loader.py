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


class TestNetworkRules:
    def test_network_rule_generates_triples(self, kg, policy_dir):
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: github-https
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
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
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: any-port
    host: "example.com"
    allow: true
""")
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
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: denied
    host: "evil.com"
    allow: false
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 0

    def test_binary_restriction(self, kg, policy_dir):
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: git-only
    host: "github.com"
    port: 443
    protocol: https
    allow: true
    binary: "/usr/bin/git"
""")
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
        _write_yaml(policy_dir, "net.yaml", """
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
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{ ?rule a sp:NemoNetworkRule ; sp:allowsHost ?host . }}
        """)
        hosts = {str(r["host"]) for r in results}
        assert hosts == {"github.com", "pypi.org"}


class TestFilesystemRules:
    def test_filesystem_rule_generates_triples(self, kg, policy_dir):
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
  - path: "/usr"
    mode: "read-only"
""")
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
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/etc/shadow"
    mode: "denied"
""")
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
        _write_yaml(policy_dir, "fs.yaml", """
fs_rules:
  - path: "/tmp"
    access: "read-write"
""")
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


class TestProvenance:
    def test_network_rule_has_nemoclaw_source(self, kg, policy_dir):
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: test
    host: "example.com"
    allow: true
""")
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
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/data"
    mode: "read-write"
""")
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


class TestReasonGeneration:
    def test_network_reason_with_port_and_protocol(self, kg, policy_dir):
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: test
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
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
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: test
    host: "example.com"
    allow: true
""")
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
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/usr"
    mode: "read-only"
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?reason WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:reason ?reason .
            }}
        """)
        assert str(results[0]["reason"]) == "NemoClaw: /usr is read-only (Landlock filesystem policy)"

    def test_filesystem_read_write_reason(self, kg, policy_dir):
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
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


class TestErrorHandling:
    def test_malformed_yaml_skipped(self, kg, policy_dir, caplog):
        _write_yaml(policy_dir, "bad.yaml", "{{{{not valid yaml: [")
        _write_yaml(policy_dir, "good.yaml", """
rules:
  - name: test
    host: "example.com"
    allow: true
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        # Good file should still be loaded
        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 1

    def test_missing_directory_returns_silently(self, kg, tmp_path):
        missing_dir = tmp_path / "nonexistent"
        loader = NemoClawPolicyLoader(missing_dir)
        loader.load(kg)
        # No exception raised, no triples added

    def test_empty_directory(self, kg, policy_dir):
        policy_dir.mkdir(parents=True, exist_ok=True)
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)
        # No exception raised

    def test_non_dict_yaml(self, kg, policy_dir, caplog):
        _write_yaml(policy_dir, "list.yaml", "- item1\n- item2\n")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)
        # Should log warning and continue

    def test_unknown_access_mode_skipped(self, kg, policy_dir, caplog):
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/data"
    mode: "execute-only"
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoFilesystemRule . }}
        """)
        assert len(results) == 0

    def test_rule_missing_host_skipped(self, kg, policy_dir):
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: no-host
    port: 443
    allow: true
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
        """)
        assert len(results) == 0
