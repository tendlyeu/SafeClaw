"""Tests for agents dashboard page."""

import pytest
from unittest.mock import MagicMock
from starlette.testclient import TestClient
from time import monotonic

from safeclaw.config import SafeClawConfig
from safeclaw.engine.agent_registry import AgentRecord
from safeclaw.dashboard.app import create_dashboard


def _make_agent(agent_id="agent-1", role="developer", killed=False):
    return AgentRecord(
        agent_id=agent_id,
        role=role,
        parent_id=None,
        session_id="sess-1",
        token_hash="fake",
        created_at=monotonic(),
        killed=killed,
    )


@pytest.fixture
def agents_client():
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password="")
    engine.audit = MagicMock()
    engine.audit.get_recent_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = [
        _make_agent("agent-1", "developer"),
        _make_agent("agent-2", "researcher", killed=True),
    ]
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = None
    engine.security_reviewer = None
    engine.classification_observer = None
    engine.explainer = None
    engine.temp_permissions = MagicMock()
    engine.temp_permissions.list_grants.return_value = []

    def get_engine():
        return engine

    app = create_dashboard(get_engine)
    return TestClient(app), engine


def test_agents_page_renders(agents_client):
    """Agents page shows registered agents."""
    client, _ = agents_client
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert "agent-1" in resp.text
    assert "agent-2" in resp.text
    assert "developer" in resp.text


def test_agents_page_shows_status(agents_client):
    """Agents page shows active/killed status badges."""
    client, _ = agents_client
    resp = client.get("/agents")
    assert "ACTIVE" in resp.text or "active" in resp.text.lower()
    assert "KILLED" in resp.text or "killed" in resp.text.lower()


def _extract_csrf(html: str) -> str:
    """Extract CSRF token from a hidden input in the page HTML."""
    import re

    match = re.search(r'value="([^"]+)"\s+name="_csrf"', html)
    return match.group(1) if match else ""


def test_kill_agent(agents_client):
    """POST to kill endpoint kills an agent."""
    client, engine = agents_client
    engine.agent_registry.kill_agent.return_value = True
    page = client.get("/agents")
    csrf = _extract_csrf(page.text)
    resp = client.post("/agents/agent-1/kill", data={"_csrf": csrf}, follow_redirects=False)
    assert resp.status_code in (200, 303)
    engine.agent_registry.kill_agent.assert_called_with("agent-1")


def test_revive_agent(agents_client):
    """POST to revive endpoint revives an agent."""
    client, engine = agents_client
    engine.agent_registry.revive_agent.return_value = True
    page = client.get("/agents")
    csrf = _extract_csrf(page.text)
    resp = client.post("/agents/agent-2/revive", data={"_csrf": csrf}, follow_redirects=False)
    assert resp.status_code in (200, 303)
    engine.agent_registry.revive_agent.assert_called_with("agent-2")
