"""API route tests using FastAPI TestClient (F-06)."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

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


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["engine_ready"] is True


def test_evaluate_tool_call_allowed(client):
    resp = client.post("/api/v1/evaluate/tool-call", json={
        "toolName": "read",
        "params": {"file_path": "/src/main.py"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["block"] is False


def test_evaluate_tool_call_blocked(client):
    resp = client.post("/api/v1/evaluate/tool-call", json={
        "toolName": "exec",
        "params": {"command": "git push --force origin main"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["block"] is True
    assert data["reason"]


def test_evaluate_message_blocked_by_confirm_preference(client):
    resp = client.post("/api/v1/evaluate/message", json={
        "to": "colleague@example.com",
        "content": "Hello, how are you?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["block"], bool)
    # Default user prefs have confirm_before_send=True, so it should be blocked
    assert data["block"] is True
    assert "confirm" in data["reason"].lower() or "send" in data["reason"].lower()


def test_build_context(client):
    resp = client.post("/api/v1/context/build", json={
        "sessionId": "api-test-session",
        "userId": "default",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "prependContext" in data
    assert "SafeClaw" in data["prependContext"]


def test_session_end(client):
    resp = client.post("/api/v1/session/end", json={
        "sessionId": "api-test-session",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["sessionId"] == "api-test-session"


def test_record_tool_result(client):
    resp = client.post("/api/v1/record/tool-result", json={
        "sessionId": "api-test-session",
        "toolName": "read",
        "params": {"file_path": "/src/main.py"},
        "result": "file contents here",
        "success": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


def test_audit_query(client):
    # First create an audit record via an evaluation
    client.post("/api/v1/evaluate/tool-call", json={
        "sessionId": "audit-api-test",
        "toolName": "read",
        "params": {"file_path": "/src/main.py"},
    })
    resp = client.get("/api/v1/audit", params={"sessionId": "audit-api-test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "decisions" in data
    assert len(data["decisions"]) >= 1


def test_register_agent(client):
    resp = client.post("/api/v1/agents/register", json={
        "agentId": "test-agent-1",
        "role": "developer",
        "sessionId": "reg-session",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["agentId"] == "test-agent-1"
    assert data["token"]
    assert data["role"] == "developer"


def test_reload(client):
    resp = client.post("/api/v1/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "triples" in data


def test_list_agents(client):
    """GET /agents returns agent list."""
    # Register an agent first
    client.post("/api/v1/agents/register", json={
        "agentId": "list-agent-1",
        "role": "developer",
        "sessionId": "list-sess",
    })
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    agent_ids = [a["agentId"] for a in data["agents"]]
    assert "list-agent-1" in agent_ids


def test_kill_agent_api(client):
    """POST /agents/{id}/kill sets killed flag."""
    client.post("/api/v1/agents/register", json={
        "agentId": "kill-agent-1",
        "role": "developer",
        "sessionId": "kill-sess",
    })
    resp = client.post("/api/v1/agents/kill-agent-1/kill")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["killed"] is True


def test_revive_agent_api(client):
    """POST /agents/{id}/revive clears killed flag."""
    client.post("/api/v1/agents/register", json={
        "agentId": "revive-agent-1",
        "role": "developer",
        "sessionId": "revive-sess",
    })
    client.post("/api/v1/agents/revive-agent-1/kill")
    resp = client.post("/api/v1/agents/revive-agent-1/revive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["killed"] is False


def test_audit_statistics(client):
    """GET /audit/statistics returns statistics dict."""
    # Create an audit record first
    client.post("/api/v1/evaluate/tool-call", json={
        "toolName": "read",
        "params": {"file_path": "/src/main.py"},
    })
    resp = client.get("/api/v1/audit/statistics")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_temp_grant_api(client):
    """POST /agents/{id}/temp-grant creates a temporary permission."""
    client.post("/api/v1/agents/register", json={
        "agentId": "grant-agent-1",
        "role": "researcher",
        "sessionId": "grant-sess",
    })
    resp = client.post("/api/v1/agents/grant-agent-1/temp-grant", json={
        "agentId": "grant-agent-1",
        "permission": "WriteFile",
        "durationSeconds": 60,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "grantId" in data
    assert data["grantId"]
