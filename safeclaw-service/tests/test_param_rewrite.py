"""#316: tool-call param rewrite — the service returns control-char-sanitized
params for an allowed call so the tool executes what the service governed."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def client(tmp_path):
    import safeclaw.main as main_module

    main_module.engine = FullEngine(
        SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
            audit_dir=tmp_path / "audit",
            dev_mode=True,
        )
    )
    yield TestClient(main_module.app), main_module.engine
    main_module.engine = None


def _eval(c, params):
    return c.post(
        "/api/v1/evaluate/tool-call",
        json={"sessionId": "s", "toolName": "read", "params": params},
    )


def test_sanitized_params_returned_for_allowed_call(client):
    c, _ = client
    r = _eval(c, {"file_path": "/src/a\x00\x07b.py"})
    body = r.json()
    assert body["block"] is False
    # The control chars are stripped and returned as the rewrite.
    assert body["params"] == {"file_path": "/src/ab.py"}


def test_clean_params_no_rewrite(client):
    c, _ = client
    r = _eval(c, {"file_path": "/src/main.py"})
    body = r.json()
    assert body["block"] is False
    # Nothing changed -> no rewrite (None), tool uses the original.
    assert body["params"] is None


def test_rewrite_disabled_by_config(tmp_path):
    import safeclaw.main as main_module

    main_module.engine = FullEngine(
        SafeClawConfig(
            data_dir=tmp_path,
            ontology_dir=Path(__file__).parent.parent / "safeclaw" / "ontologies",
            audit_dir=tmp_path / "audit",
            dev_mode=True,
            tool_param_rewrite_enabled=False,
        )
    )
    try:
        c = TestClient(main_module.app)
        r = _eval(c, {"file_path": "/src/a\x00b.py"})
        assert r.json()["params"] is None
    finally:
        main_module.engine = None


def test_confirmation_required_call_gets_rewrite(client):
    # SafeClaw models confirmation as block=True + confirmationRequired=True. The
    # call MAY still execute after approval, so the sanitized params must be
    # returned (the plugin carries them onto the approval result, which OpenClaw
    # applies post-approval). A `delete` requires confirmation.
    c, _ = client
    r = c.post(
        "/api/v1/evaluate/tool-call",
        json={"sessionId": "s", "toolName": "delete", "params": {"file_path": "/tmp/a\x00b.txt"}},
    )
    body = r.json()
    assert body["confirmationRequired"] is True
    assert body["params"] == {"file_path": "/tmp/ab.txt"}


def test_hard_blocked_call_has_no_rewrite(client):
    # A genuine hard block (block=True, confirmationRequired=False) never
    # executes, so no rewrite even with control chars. `git push --force` is a
    # policy hard-block.
    c, _ = client
    r = c.post(
        "/api/v1/evaluate/tool-call",
        json={"sessionId": "s", "toolName": "exec", "params": {"command": "git push --force\x00"}},
    )
    body = r.json()
    assert body["block"] is True
    assert body["confirmationRequired"] is False
    assert body["params"] is None
