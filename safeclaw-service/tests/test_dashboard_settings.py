"""Tests for settings dashboard page."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.dashboard.app import create_dashboard


@pytest.fixture
def settings_client():
    engine = MagicMock()
    engine.reload = AsyncMock()
    engine.config = SafeClawConfig(admin_password="", mistral_api_key="sk-test-123")
    engine.audit = MagicMock()
    engine.audit.get_recent_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = []
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = MagicMock()
    engine.security_reviewer = MagicMock()
    engine.classification_observer = MagicMock()
    engine.explainer = MagicMock()

    def get_engine():
        return engine

    app = create_dashboard(get_engine)
    return TestClient(app), engine


def test_settings_page_renders(settings_client):
    """Settings page shows configuration."""
    client, _ = settings_client
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Mistral API Key" in resp.text or "API Key" in resp.text


def test_settings_shows_llm_status(settings_client):
    """Settings page shows LLM feature status."""
    client, _ = settings_client
    resp = client.get("/settings")
    assert "Security Reviewer" in resp.text


def test_settings_shows_config_values(settings_client):
    """Settings page shows current config values."""
    client, _ = settings_client
    resp = client.get("/settings")
    assert "8420" in resp.text  # port


def _extract_csrf(html: str) -> str:
    """Extract CSRF token from a hidden input in the page HTML."""
    import re

    match = re.search(r'value="([^"]+)"\s+name="_csrf"', html)
    return match.group(1) if match else ""


def test_reload_ontologies(settings_client):
    """Reload button triggers engine reload."""
    client, engine = settings_client
    page = client.get("/settings")
    csrf = _extract_csrf(page.text)
    resp = client.post("/settings/reload", data={"_csrf": csrf}, follow_redirects=False)
    assert resp.status_code in (200, 303)
    engine.reload.assert_called_once()
