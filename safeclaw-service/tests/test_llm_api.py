"""Tests for LLM-related API routes."""

import pytest
from pathlib import Path

from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine


@pytest.fixture
def client(tmp_path):
    import safeclaw.main as main_module

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


def test_policy_compile_no_llm(client):
    """POST /policies/compile returns 503 when LLM is not configured."""
    resp = client.post(
        "/api/v1/policies/compile",
        json={"description": "Never delete production files"},
    )
    assert resp.status_code == 503


def test_audit_explain_no_llm(client):
    """GET /audit/{id}/explain returns 503 when LLM is not configured."""
    resp = client.get("/api/v1/audit/fake-id/explain")
    assert resp.status_code == 503


def test_llm_findings_empty(client):
    """GET /llm/findings returns empty list when no findings exist."""
    resp = client.get("/api/v1/llm/findings")
    assert resp.status_code == 200
    assert resp.json()["findings"] == []


def test_llm_suggestions_empty(client):
    """GET /llm/suggestions returns empty list when no suggestions exist."""
    resp = client.get("/api/v1/llm/suggestions")
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []
