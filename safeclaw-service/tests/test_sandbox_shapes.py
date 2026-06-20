"""Tests for sandbox ontology, SHACL shapes, and validation endpoint (#193)."""

from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF, XSD

from safeclaw.engine.shacl_validator import SHACLValidator

SC = Namespace("http://safeclaw.uku.ai/ontology/agent#")

_ontology_dir = Path(__file__).parent.parent / "safeclaw" / "ontologies"
_shapes_dir = _ontology_dir / "shapes"
_sandbox_ttl = _ontology_dir / "safeclaw-sandbox.ttl"
_sandbox_shapes_ttl = _shapes_dir / "sandbox-shapes.ttl"

_has_sandbox = _sandbox_ttl.exists() and _sandbox_shapes_ttl.exists()
requires_sandbox = pytest.mark.skipif(not _has_sandbox, reason="Sandbox ontology not available")


# ── Ontology loading tests ──


@requires_sandbox
def test_sandbox_ontology_loads():
    """Verify the sandbox ontology parses without errors."""
    g = Graph()
    g.parse(str(_sandbox_ttl), format="turtle")
    assert len(g) > 0


@requires_sandbox
def test_sandbox_ontology_classes_queryable():
    """Verify key classes are queryable from the sandbox ontology."""
    g = Graph()
    g.bind("sc", SC)
    g.parse(str(_sandbox_ttl), format="turtle")

    # Query for SandboxPolicy class
    results = list(g.triples((SC.SandboxPolicy, RDF.type, None)))
    assert len(results) > 0, "SandboxPolicy class not found"

    # Query for ToolPolicy class
    results = list(g.triples((SC.ToolPolicy, RDF.type, None)))
    assert len(results) > 0, "ToolPolicy class not found"

    # Query for MountPoint class
    results = list(g.triples((SC.MountPoint, RDF.type, None)))
    assert len(results) > 0, "MountPoint class not found"


@requires_sandbox
def test_sandbox_ontology_properties_queryable():
    """Verify key properties are queryable."""
    g = Graph()
    g.bind("sc", SC)
    g.parse(str(_sandbox_ttl), format="turtle")

    for prop in [
        SC.hasToolPolicy,
        SC.hasFilesystemPolicy,
        SC.hasNetworkPolicy,
        SC.toolName,
        SC.mountPath,
        SC.mountMode,
        SC.allowedHost,
        SC.allowedPort,
    ]:
        results = list(g.triples((prop, RDF.type, None)))
        assert len(results) > 0, f"Property {prop} not found"


# ── SHACL validation tests ──


@requires_sandbox
def test_shacl_shapes_load():
    """Verify sandbox SHACL shapes load into the validator."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    assert len(validator.shapes_graph) > 0


@requires_sandbox
def test_conformant_sandbox_policy():
    """A valid sandbox policy with all required fields should conform."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)

    # Also load the sandbox ontology so class hierarchy is available
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)

    # Build a conformant SandboxPolicy
    policy = SC["test_sandbox_policy"]
    tool_policy = SC["test_tool_policy"]
    fs_policy = SC["test_fs_policy"]
    mount = SC["test_mount"]
    denied = SC["test_denied_tool"]

    # SandboxPolicy with required sub-policies
    g.add((policy, RDF.type, SC.SandboxPolicy))
    g.add((policy, SC.hasToolPolicy, tool_policy))
    g.add((policy, SC.hasFilesystemPolicy, fs_policy))

    # ToolPolicy (AllowedToolShape now requires toolName)
    g.add((tool_policy, RDF.type, SC.AllowedTool))
    g.add((tool_policy, SC.toolName, Literal("read_file", datatype=XSD.string)))

    # FilesystemPolicy (MountPoint is subClassOf FilesystemPolicy)
    g.add((fs_policy, RDF.type, SC.FilesystemPolicy))

    # A valid MountPoint
    g.add((mount, RDF.type, SC.MountPoint))
    g.add((mount, SC.mountPath, Literal("/workspace", datatype=XSD.string)))
    g.add((mount, SC.mountMode, Literal("read-write")))

    # A valid DeniedTool
    g.add((denied, RDF.type, SC.DeniedTool))
    g.add((denied, SC.toolName, Literal("rm", datatype=XSD.string)))

    result = validator.validate(g)
    assert result.conforms is True, f"Expected conformant, got violations: {result.violations}"


@requires_sandbox
def test_sandbox_policy_missing_tool_policy():
    """A SandboxPolicy without hasToolPolicy should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)

    policy = SC["test_sandbox_no_tools"]
    fs_policy = SC["test_fs"]
    g.add((policy, RDF.type, SC.SandboxPolicy))
    # Only filesystem policy, no tool policy
    g.add((policy, SC.hasFilesystemPolicy, fs_policy))
    g.add((fs_policy, RDF.type, SC.FilesystemPolicy))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"] for v in result.violations]
    assert any("tool policy" in m.lower() for m in messages)


@requires_sandbox
def test_sandbox_policy_missing_filesystem_policy():
    """A SandboxPolicy without hasFilesystemPolicy should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)

    policy = SC["test_sandbox_no_fs"]
    tool_policy = SC["test_tool"]
    g.add((policy, RDF.type, SC.SandboxPolicy))
    # Only tool policy, no filesystem policy
    g.add((policy, SC.hasToolPolicy, tool_policy))
    g.add((tool_policy, RDF.type, SC.ToolPolicy))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"] for v in result.violations]
    assert any("filesystem" in m.lower() for m in messages)


@requires_sandbox
def test_mount_point_missing_path():
    """A MountPoint without mountPath should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)

    mount = SC["test_mount_no_path"]
    g.add((mount, RDF.type, SC.MountPoint))
    g.add((mount, SC.mountMode, Literal("read-only")))
    # No mountPath

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"] for v in result.violations]
    assert any("path" in m.lower() for m in messages)


@requires_sandbox
def test_mount_point_invalid_mode():
    """A MountPoint with an invalid mountMode should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)

    mount = SC["test_mount_bad_mode"]
    g.add((mount, RDF.type, SC.MountPoint))
    g.add((mount, SC.mountPath, Literal("/data", datatype=XSD.string)))
    g.add((mount, SC.mountMode, Literal("execute")))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"] for v in result.violations]
    assert any("mount mode" in m.lower() or "read-only" in m.lower() for m in messages)


@requires_sandbox
def test_denied_tool_missing_name():
    """A DeniedTool without toolName should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)

    denied = SC["test_denied_no_name"]
    g.add((denied, RDF.type, SC.DeniedTool))
    # No toolName

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"] for v in result.violations]
    assert any("name" in m.lower() or "tool" in m.lower() for m in messages)


# ── Hardening ontology tests (OpenClaw 2026.6.x dimensions, #323) ──


@requires_sandbox
def test_sandbox_hardening_properties_queryable():
    """Verify the new hardening properties are present in the ontology."""
    g = Graph()
    g.bind("sc", SC)
    g.parse(str(_sandbox_ttl), format="turtle")

    for prop in [
        SC.seccompProfile,
        SC.inheritsHostEnv,
        SC.bindSource,
        SC.egressAllowlist,
    ]:
        results = list(g.triples((prop, RDF.type, None)))
        assert len(results) > 0, f"Property {prop} not found"


@requires_sandbox
def test_sandbox_hardening_classes_queryable():
    """Verify the new hardening classes are present in the ontology."""
    g = Graph()
    g.bind("sc", SC)
    g.parse(str(_sandbox_ttl), format="turtle")

    for cls in [SC.SeccompPolicy, SC.EnvironmentPolicy, SC.BindMount, SC.EgressPolicy]:
        results = list(g.triples((cls, RDF.type, None)))
        assert len(results) > 0, f"Class {cls} not found"


@requires_sandbox
def test_seccomp_unconfined_rejected():
    """A seccomp profile set to 'unconfined' should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_seccomp_unconfined"]
    g.add((node, RDF.type, SC.SeccompPolicy))
    g.add((node, SC.seccompProfile, Literal("unconfined", datatype=XSD.string)))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"].lower() for v in result.violations]
    assert any("unconfined" in m or "seccomp" in m for m in messages)


@requires_sandbox
def test_seccomp_profile_conformant():
    """A non-unconfined seccomp profile should conform."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_seccomp_ok"]
    g.add((node, RDF.type, SC.SeccompPolicy))
    g.add((node, SC.seccompProfile, Literal("default", datatype=XSD.string)))

    result = validator.validate(g)
    assert result.conforms is True, f"Expected conformant, got: {result.violations}"


@requires_sandbox
def test_host_env_inheritance_rejected():
    """A sandbox inheriting host env vars should fail validation (credential leak)."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_env_inherit"]
    g.add((node, RDF.type, SC.EnvironmentPolicy))
    g.add((node, SC.inheritsHostEnv, Literal(True)))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"].lower() for v in result.violations]
    assert any("host environment" in m or "credential" in m for m in messages)


@requires_sandbox
def test_bind_source_unvalidated_rejected():
    """A bind mount with an unvalidated source should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_bind_unvalidated"]
    g.add((node, RDF.type, SC.BindMount))
    g.add((node, SC.mountPath, Literal("/workspace", datatype=XSD.string)))
    g.add((node, SC.mountMode, Literal("read-write")))
    g.add((node, SC.bindSource, Literal("/host/secrets", datatype=XSD.string)))
    g.add((node, SC.bindSourceValidated, Literal(False)))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"].lower() for v in result.violations]
    assert any("source" in m and "validat" in m for m in messages)


@requires_sandbox
def test_bind_source_omitted_flag_rejected():
    """A bind mount with a source but NO validation flag must fail (fail-closed)."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_bind_omitted_flag"]
    g.add((node, RDF.type, SC.BindMount))
    g.add((node, SC.mountPath, Literal("/workspace", datatype=XSD.string)))
    g.add((node, SC.mountMode, Literal("read-write")))
    g.add((node, SC.bindSource, Literal("/host/secrets", datatype=XSD.string)))
    # NOTE: no bindSourceValidated triple at all -> must be treated as unvalidated.

    result = validator.validate(g)
    assert result.conforms is False, "Omitted validation flag must be non-conformant (fail-closed)"
    messages = [v["message"].lower() for v in result.violations]
    assert any("source" in m and "validat" in m for m in messages)


@requires_sandbox
def test_bind_source_validated_true_conformant():
    """A bind mount explicitly proven validated (true) must still conform."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_bind_validated"]
    g.add((node, RDF.type, SC.BindMount))
    g.add((node, SC.mountPath, Literal("/workspace", datatype=XSD.string)))
    g.add((node, SC.mountMode, Literal("read-write")))
    g.add((node, SC.bindSource, Literal("/srv/workspace", datatype=XSD.string)))
    g.add((node, SC.bindSourceValidated, Literal(True)))

    result = validator.validate(g)
    assert result.conforms is True, f"Expected conformant, got: {result.violations}"


@requires_sandbox
def test_bind_source_missing_rejected():
    """A bind mount without a source path should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_bind_no_source"]
    g.add((node, RDF.type, SC.BindMount))
    g.add((node, SC.mountPath, Literal("/workspace", datatype=XSD.string)))
    g.add((node, SC.mountMode, Literal("read-write")))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"].lower() for v in result.violations]
    assert any("source" in m for m in messages)


@requires_sandbox
def test_egress_without_allowlist_rejected():
    """Outbound egress without an allowlist should fail validation."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_egress_open"]
    g.add((node, RDF.type, SC.EgressPolicy))
    g.add((node, SC.allowsOutbound, Literal(True)))

    result = validator.validate(g)
    assert result.conforms is False
    messages = [v["message"].lower() for v in result.violations]
    assert any("egress" in m and "allowlist" in m for m in messages)


@requires_sandbox
def test_egress_with_allowlist_conformant():
    """Outbound egress with an allowlist should conform."""
    validator = SHACLValidator()
    validator.load_shapes(_shapes_dir)
    validator._ont_graph.parse(str(_sandbox_ttl), format="turtle")

    g = Graph()
    g.bind("sc", SC)
    node = SC["test_egress_allowlisted"]
    g.add((node, RDF.type, SC.EgressPolicy))
    g.add((node, SC.allowsOutbound, Literal(True)))
    g.add((node, SC.egressAllowlist, Literal("api.example.com", datatype=XSD.string)))

    result = validator.validate(g)
    assert result.conforms is True, f"Expected conformant, got: {result.violations}"


# ── API endpoint tests ──


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    import safeclaw.main as main_module
    from safeclaw.config import SafeClawConfig
    from safeclaw.engine.full_engine import FullEngine

    config = SafeClawConfig(
        data_dir=tmp_path,
        ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
        audit_dir=tmp_path / "audit",
        dev_mode=True,
    )
    main_module.engine = FullEngine(config)
    client = TestClient(main_module.app)
    yield client
    main_module.engine = None


def test_api_sandbox_policy_valid(client):
    """Valid sandbox policy should return conformant=True."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {
                "toolPolicy": {
                    "allowed": ["read", "write"],
                    "denied": [{"name": "exec"}],
                },
                "filesystemPolicy": {
                    "mounts": [
                        {"path": "/workspace", "mode": "read-write"},
                        {"path": "/etc", "mode": "read-only"},
                    ],
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is True
    assert data["violations"] == []


def test_api_sandbox_policy_missing_tool_policy(client):
    """Missing toolPolicy should return conformant=False."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {
                "filesystemPolicy": {
                    "mounts": [{"path": "/workspace", "mode": "read-write"}],
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any(v["field"] == "toolPolicy" for v in data["violations"])


def test_api_sandbox_policy_missing_filesystem_policy(client):
    """Missing filesystemPolicy should return conformant=False."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {
                "toolPolicy": {"allowed": ["read"]},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any(v["field"] == "filesystemPolicy" for v in data["violations"])


def test_api_sandbox_policy_missing_both(client):
    """Missing both required sections should return two violations."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    fields = {v["field"] for v in data["violations"]}
    assert "toolPolicy" in fields
    assert "filesystemPolicy" in fields


def test_api_sandbox_policy_invalid_mount_mode(client):
    """Invalid mount mode should produce a violation."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {
                "toolPolicy": {"allowed": ["read"]},
                "filesystemPolicy": {
                    "mounts": [{"path": "/data", "mode": "execute"}],
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("mode" in v["field"] for v in data["violations"])


def test_api_sandbox_policy_mount_missing_path(client):
    """Mount point without path should produce a violation."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {
                "toolPolicy": {"allowed": ["read"]},
                "filesystemPolicy": {
                    "mounts": [{"mode": "read-only"}],
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("path" in v["field"] for v in data["violations"])


def test_api_sandbox_policy_denied_tool_missing_name(client):
    """Denied tool without a name should produce a violation."""
    resp = client.post(
        "/api/v1/evaluate/sandbox-policy",
        json={
            "policy": {
                "toolPolicy": {
                    "allowed": ["read"],
                    "denied": [{"description": "dangerous tool"}],
                },
                "filesystemPolicy": {
                    "mounts": [{"path": "/workspace", "mode": "read-write"}],
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("denied" in v["field"] for v in data["violations"])


# ── API hardening tests (OpenClaw 2026.6.x dimensions, #323) ──


def _base_policy() -> dict:
    return {
        "toolPolicy": {"allowed": ["read"]},
        "filesystemPolicy": {"mounts": [{"path": "/workspace", "mode": "read-write"}]},
    }


def test_api_sandbox_seccomp_unconfined(client):
    """A seccomp profile of 'unconfined' should be flagged."""
    policy = _base_policy()
    policy["seccompPolicy"] = {"profile": "unconfined"}
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("seccomp" in v["field"].lower() for v in data["violations"])


def test_api_sandbox_seccomp_default_ok(client):
    """A non-unconfined seccomp profile should not be flagged."""
    policy = _base_policy()
    policy["seccompPolicy"] = {"profile": "default"}
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    assert resp.json()["conformant"] is True


def test_api_sandbox_host_env_inheritance(client):
    """Inheriting host env vars should be flagged as a credential leak."""
    policy = _base_policy()
    policy["environmentPolicy"] = {"inheritHostEnv": True}
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("inheritHostEnv" in v["field"] for v in data["violations"])


def test_api_sandbox_bind_source_missing(client):
    """A bind mount without a host source should be flagged."""
    policy = _base_policy()
    policy["filesystemPolicy"]["mounts"] = [
        {"path": "/workspace", "mode": "read-write", "type": "bind"}
    ]
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("source" in v["field"] for v in data["violations"])


def test_api_sandbox_bind_source_unvalidated(client):
    """A writable bind mount with an unvalidated source should be flagged."""
    policy = _base_policy()
    policy["filesystemPolicy"]["mounts"] = [
        {
            "path": "/workspace",
            "mode": "read-write",
            "type": "bind",
            "source": "/host/secrets",
            "sourceValidated": False,
        }
    ]
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("sourceValidated" in v["field"] for v in data["violations"])


def test_api_sandbox_bind_source_omitted_flag(client):
    """A bind mount with a source but NO sourceValidated flag must be flagged (fail-closed)."""
    policy = _base_policy()
    policy["filesystemPolicy"]["mounts"] = [
        {
            "path": "/workspace",
            "mode": "read-write",
            "type": "bind",
            "source": "/host/secrets",
            # NOTE: no sourceValidated key at all.
        }
    ]
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False, "Omitted sourceValidated must fail-closed"
    assert any("sourceValidated" in v["field"] for v in data["violations"])


def test_api_sandbox_bind_source_validated_true_ok(client):
    """A bind mount with sourceValidated=True must still conform (no over-blocking)."""
    policy = _base_policy()
    policy["filesystemPolicy"]["mounts"] = [
        {
            "path": "/workspace",
            "mode": "read-write",
            "type": "bind",
            "source": "/srv/workspace",
            "sourceValidated": True,
        }
    ]
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is True, data["violations"]


def test_api_sandbox_egress_without_allowlist(client):
    """Outbound egress without an allowlist should be flagged."""
    policy = _base_policy()
    policy["networkPolicy"] = {"allowOutbound": True}
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is False
    assert any("egressAllowlist" in v["field"] for v in data["violations"])


def test_api_sandbox_egress_with_allowlist_ok(client):
    """Outbound egress with an allowlist should pass."""
    policy = _base_policy()
    policy["networkPolicy"] = {
        "allowOutbound": True,
        "egressAllowlist": ["api.example.com"],
    }
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    assert resp.json()["conformant"] is True


def test_api_sandbox_fully_hardened_ok(client):
    """A fully hardened sandbox policy should conform."""
    policy = _base_policy()
    policy["filesystemPolicy"]["mounts"] = [
        {
            "path": "/workspace",
            "mode": "read-write",
            "type": "bind",
            "source": "/srv/workspace",
            "sourceValidated": True,
        }
    ]
    policy["seccompPolicy"] = {"profile": "default"}
    policy["environmentPolicy"] = {"inheritHostEnv": False}
    policy["networkPolicy"] = {"allowOutbound": True, "egressAllowlist": ["api.example.com"]}
    resp = client.post("/api/v1/evaluate/sandbox-policy", json={"policy": policy})
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformant"] is True, data["violations"]
