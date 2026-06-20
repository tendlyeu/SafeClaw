"""Schema-validated coverage against the real NemoClaw v0.0.65 example policies.

These fixtures are vendored verbatim from NVIDIA/NemoClaw@v0.0.65:

  - ``sandbox-policy.schema.json``  (schemas/sandbox-policy.schema.json)
  - ``policy-permissive.yaml``      (agents/openclaw/policy-permissive.yaml)
  - ``openclaw-sandbox.yaml``       (nemoclaw-blueprint/policies/openclaw-sandbox.yaml)

This replaces the fictional ``protocol: https`` / ``protocol: full`` real-format
fixtures (#330) with real, schema-validated documents. The legacy *flat*-format
tests (``rules:`` lists) are intentionally kept elsewhere — they exercise
SafeClaw's own backward-compat path, not the NemoClaw schema.
"""

import json
from pathlib import Path

import pytest
import yaml

from safeclaw.engine.knowledge_graph import KnowledgeGraph, SP
from safeclaw.nemoclaw.policy_loader import NemoClawPolicyLoader

jsonschema = pytest.importorskip("jsonschema")

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nemoclaw"
REAL_POLICY_FILES = ["policy-permissive.yaml", "openclaw-sandbox.yaml"]


@pytest.fixture(scope="module")
def schema():
    return json.loads((FIXTURE_DIR / "sandbox-policy.schema.json").read_text())


@pytest.fixture
def kg():
    graph = KnowledgeGraph()
    ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
    graph.load_directory(ontology_dir)
    return graph


@pytest.mark.parametrize("filename", REAL_POLICY_FILES)
def test_real_fixture_is_schema_valid(schema, filename):
    """The vendored fixtures must validate against the v0.0.65 schema."""
    data = yaml.safe_load((FIXTURE_DIR / filename).read_text())
    jsonschema.validate(instance=data, schema=schema)


@pytest.mark.parametrize("filename", REAL_POLICY_FILES)
def test_real_fixture_loads_without_error(kg, tmp_path, filename):
    """Loading the real fixture must produce network rules without warnings/errors."""
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / filename).write_text((FIXTURE_DIR / filename).read_text())

    NemoClawPolicyLoader(policy_dir, workdir="/sandbox").load(kg)

    results = kg.query(f"""
        PREFIX sp: <{SP}>
        SELECT ?rule WHERE {{ ?rule a sp:NemoNetworkRule . }}
    """)
    assert len(results) > 0


def test_permissive_only_uses_schema_protocols(kg, tmp_path):
    """Every loaded protocol from the real permissive policy is rest|websocket."""
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy-permissive.yaml").write_text(
        (FIXTURE_DIR / "policy-permissive.yaml").read_text()
    )
    NemoClawPolicyLoader(policy_dir, workdir="/sandbox").load(kg)

    results = kg.query(f"""
        PREFIX sp: <{SP}>
        SELECT DISTINCT ?protocol WHERE {{
            ?rule a sp:NemoNetworkRule ;
                  sp:allowsProtocol ?protocol .
        }}
    """)
    protocols = {str(r["protocol"]) for r in results}
    assert protocols <= {"rest", "websocket"}
    assert protocols  # non-empty


def test_blueprint_raw_tunnel_flagged(kg, tmp_path):
    """The blueprint's gateway dial-back (access: full + tls: skip) is flagged."""
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "openclaw-sandbox.yaml").write_text(
        (FIXTURE_DIR / "openclaw-sandbox.yaml").read_text()
    )
    NemoClawPolicyLoader(policy_dir, workdir="/sandbox").load(kg)

    results = kg.query(f"""
        PREFIX sp: <{SP}>
        SELECT ?host WHERE {{
            ?rule a sp:NemoNetworkRule ;
                  sp:rawTunnel true ;
                  sp:allowsHost ?host .
        }}
    """)
    hosts = {str(r["host"]) for r in results}
    # Both dial-back ports (18789, 18790) target the same host.
    assert hosts == {"10.200.0.2"}


def test_blueprint_allowed_ips_loaded(kg, tmp_path):
    """allowed_ips from the blueprint dial-back endpoints are ingested."""
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "openclaw-sandbox.yaml").write_text(
        (FIXTURE_DIR / "openclaw-sandbox.yaml").read_text()
    )
    NemoClawPolicyLoader(policy_dir, workdir="/sandbox").load(kg)

    results = kg.query(f"""
        PREFIX sp: <{SP}>
        SELECT DISTINCT ?ip WHERE {{
            ?rule a sp:NemoNetworkRule ;
                  sp:allowedIp ?ip .
        }}
    """)
    ips = {str(r["ip"]) for r in results}
    assert "10.200.0.2" in ips


def test_permissive_include_workdir_emits_read_write(kg, tmp_path):
    """The permissive policy sets include_workdir: true -> workdir is read-write."""
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy-permissive.yaml").write_text(
        (FIXTURE_DIR / "policy-permissive.yaml").read_text()
    )
    NemoClawPolicyLoader(policy_dir, workdir="/sandbox").load(kg)

    results = kg.query(f"""
        PREFIX sp: <{SP}>
        SELECT ?path ?mode WHERE {{
            ?rule a sp:NemoFilesystemRule ;
                  sp:path ?path ;
                  sp:accessMode ?mode .
        }}
    """)
    rules = {str(r["path"]): str(r["mode"]) for r in results}
    assert rules.get("/sandbox") == "read-write"
