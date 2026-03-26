"""Tests for session lifecycle endpoints (#189)."""

from pathlib import Path

import pytest
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
    )
    main_module.engine = FullEngine(config)
    client = TestClient(main_module.app)
    yield client
    main_module.engine = None


class TestSessionStart:
    def test_session_start_acknowledged(self, client):
        """Session start returns acknowledged."""
        resp = client.post(
            "/api/v1/session/start",
            json={"sessionId": "s1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["acknowledged"] is True

    def test_session_start_with_user(self, client):
        """Session start with userId pre-loads preferences."""
        resp = client.post(
            "/api/v1/session/start",
            json={"sessionId": "s2", "userId": "alice"},
        )
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True

    def test_session_start_with_agent(self, client):
        """Session start with agentId sets session owner."""
        import safeclaw.main as main_module

        resp = client.post(
            "/api/v1/session/start",
            json={"sessionId": "s3", "agentId": "agent-1"},
        )
        assert resp.status_code == 200

        engine = main_module.engine
        state = engine.session_tracker.get_state("s3")
        assert state is not None
        assert state.owner_id == "agent-1"

    def test_session_start_initializes_rate_limiter(self, client):
        """Session start initializes a rate limiter session bucket."""
        import safeclaw.main as main_module

        resp = client.post(
            "/api/v1/session/start",
            json={"sessionId": "s-rate"},
        )
        assert resp.status_code == 200

        engine = main_module.engine
        assert "s-rate" in engine.rate_limiter._sessions

    def test_session_start_with_metadata(self, client):
        """Session start accepts metadata dict."""
        resp = client.post(
            "/api/v1/session/start",
            json={
                "sessionId": "s-meta",
                "metadata": {"source": "cli", "version": "1.0"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True

    def test_session_start_requires_session_id(self, client):
        """Session start requires sessionId field."""
        resp = client.post(
            "/api/v1/session/start",
            json={},
        )
        assert resp.status_code == 422

    def test_session_start_response_model(self, client):
        """Response matches SessionStartResponse schema."""
        resp = client.post(
            "/api/v1/session/start",
            json={"sessionId": "s-model"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["acknowledged"], bool)


class TestSessionEnd:
    def test_session_end_basic(self, client):
        """Session end clears session state."""
        # Start a session first
        client.post("/api/v1/session/start", json={"sessionId": "s-end"})

        resp = client.post(
            "/api/v1/session/end",
            json={"sessionId": "s-end"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["sessionId"] == "s-end"

    def test_session_end_nonexistent(self, client):
        """Ending a nonexistent session succeeds (idempotent)."""
        resp = client.post(
            "/api/v1/session/end",
            json={"sessionId": "nonexistent-session"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_session_end_clears_tracker_state(self, client):
        """Session end removes state from session tracker."""
        import safeclaw.main as main_module

        # Start and populate session
        client.post(
            "/api/v1/session/start",
            json={"sessionId": "s-clear"},
        )

        engine = main_module.engine
        assert engine.session_tracker.get_state("s-clear") is not None

        # End session
        client.post("/api/v1/session/end", json={"sessionId": "s-clear"})
        assert engine.session_tracker.get_state("s-clear") is None

    def test_session_end_requires_session_id(self, client):
        """Session end requires sessionId field."""
        resp = client.post(
            "/api/v1/session/end",
            json={},
        )
        assert resp.status_code == 422

    def test_session_start_then_end_lifecycle(self, client):
        """Full session lifecycle: start -> use -> end."""
        import safeclaw.main as main_module

        # Start
        resp = client.post(
            "/api/v1/session/start",
            json={"sessionId": "lifecycle", "userId": "testuser", "agentId": "a1"},
        )
        assert resp.status_code == 200

        engine = main_module.engine
        state = engine.session_tracker.get_state("lifecycle")
        assert state is not None
        assert state.owner_id == "a1"

        # End
        resp = client.post(
            "/api/v1/session/end",
            json={"sessionId": "lifecycle"},
        )
        assert resp.status_code == 200
        assert engine.session_tracker.get_state("lifecycle") is None
