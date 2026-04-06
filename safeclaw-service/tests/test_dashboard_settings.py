"""Tests for settings dashboard page."""

import json
import stat

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.dashboard.app import create_dashboard
from safeclaw.dashboard.pages.settings import _write_config_safe


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
    assert "LLM Provider" in resp.text


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


# ── Permission tests for _write_config_safe (#133) ──────────────────


def test_write_config_safe_creates_file_with_0600(tmp_path):
    """_write_config_safe must create files with owner-only permissions (0o600)."""
    target = tmp_path / "config.json"
    _write_config_safe(target, '{"key": "secret"}')

    assert target.exists()
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, f"Expected 0o600 but got {oct(mode)}"
    assert target.read_text() == '{"key": "secret"}'


def test_write_config_safe_overwrites_existing_file(tmp_path):
    """_write_config_safe must overwrite an existing file and keep 0o600."""
    target = tmp_path / "config.json"
    target.write_text("old content")
    # Default permissions are typically 0o644; verify write_config_safe tightens them
    _write_config_safe(target, "new content")

    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, f"Expected 0o600 but got {oct(mode)}"
    assert target.read_text() == "new content"


def test_api_key_save_writes_config_with_0600(tmp_path, settings_client):
    """POST /settings/api-key must write config.json with 0o600 permissions."""
    client, engine = settings_client
    engine.config.data_dir = tmp_path

    page = client.get("/settings")
    csrf = _extract_csrf(page.text)

    resp = client.post(
        "/settings/api-key",
        data={"api_key": "sk-new-key-12345678", "provider": "openai", "_csrf": csrf},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303)

    config_path = tmp_path / "config.json"
    assert config_path.exists()
    mode = stat.S_IMODE(config_path.stat().st_mode)
    assert mode == 0o600, f"config.json has permissions {oct(mode)}, expected 0o600"

    data = json.loads(config_path.read_text())
    assert data["llm_provider"] == "openai"
    assert data["llm_api_key"] == "sk-new-key-12345678"


def test_preferences_save_writes_ttl_with_0600(tmp_path, settings_client):
    """POST /settings/preferences/save must write TTL with 0o600 permissions."""
    client, engine = settings_client
    engine.config.data_dir = tmp_path

    page = client.get("/settings")
    csrf = _extract_csrf(page.text)

    resp = client.post(
        "/settings/preferences/save",
        data={
            "user_id": "testuser",
            "autonomy_level": "cautious",
            "confirm_before_delete": "on",
            "confirm_before_push": "",
            "confirm_before_send": "on",
            "max_files_per_commit": "5",
            "_csrf": csrf,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 200

    ttl_path = tmp_path / "ontologies" / "users" / "user-testuser.ttl"
    assert ttl_path.exists()
    mode = stat.S_IMODE(ttl_path.stat().st_mode)
    assert mode == 0o600, f"TTL file has permissions {oct(mode)}, expected 0o600"
