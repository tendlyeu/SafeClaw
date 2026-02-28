"""Tests for the SafeClaw admin dashboard app skeleton and auth flow."""

from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.dashboard.app import create_dashboard


def _make_engine(admin_password: str = "testpass123"):
    """Build a mock engine with the given admin password."""
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password=admin_password)
    engine.audit = MagicMock()
    engine.audit.get_recent_records.return_value = []
    engine.audit.get_blocked_records.return_value = []
    engine.agent_registry = MagicMock()
    engine.agent_registry.list_agents.return_value = []
    engine.session_tracker = MagicMock()
    engine.session_tracker._sessions = {}
    engine.kg = MagicMock()
    engine.kg.__len__ = MagicMock(return_value=42)
    engine.llm_client = None
    engine.security_reviewer = None
    engine.classification_observer = None
    engine.explainer = None
    return engine


@pytest.fixture()
def auth_client():
    """Client for an app that requires a password."""
    engine = _make_engine(admin_password="testpass123")
    app = create_dashboard(lambda: engine)
    return TestClient(app, follow_redirects=False)


@pytest.fixture()
def open_client():
    """Client for an app with no password (dev mode)."""
    engine = _make_engine(admin_password="")
    app = create_dashboard(lambda: engine)
    return TestClient(app, follow_redirects=False)


def test_login_page_shown_when_not_authenticated(auth_client):
    """GET / without session returns 303 redirect to /login."""
    resp = auth_client.get("/")
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_login_page_renders(auth_client):
    """GET /login returns 200 with a password field."""
    resp = auth_client.get("/login")
    assert resp.status_code == 200
    assert "password" in resp.text.lower()


def test_login_with_correct_password(auth_client):
    """POST /login with the correct password redirects to /."""
    resp = auth_client.post("/login", data={"password": "testpass123"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_login_with_wrong_password(auth_client):
    """POST /login with a wrong password redirects back to /login."""
    resp = auth_client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_no_password_configured_allows_access(open_client):
    """When admin_password is empty, GET / returns 200 (dev mode)."""
    resp = open_client.get("/")
    assert resp.status_code == 200


def test_logout_clears_session(auth_client):
    """After logging in, GET /logout redirects to /login and clears the session."""
    # Log in first
    auth_client.post("/login", data={"password": "testpass123"})

    # Logout
    resp = auth_client.get("/logout")
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]

    # Verify session is cleared: accessing / should redirect back to login
    resp = auth_client.get("/")
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]
