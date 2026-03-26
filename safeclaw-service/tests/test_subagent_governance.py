"""Tests for subagent governance endpoints (#188)."""

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


class TestSubagentSpawn:
    def test_spawn_allowed_by_default(self, client):
        """Spawn is allowed when no delegation bypass is detected."""
        resp = client.post(
            "/api/v1/evaluate/subagent-spawn",
            json={
                "sessionId": "s1",
                "parentAgentId": "parent-1",
                "childConfig": {"tools": ["read", "write"]},
                "reason": "Need help with file editing",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True
        assert data["block"] is False

    def test_spawn_allowed_empty_parent(self, client):
        """Spawn is allowed when parentAgentId is empty."""
        resp = client.post(
            "/api/v1/evaluate/subagent-spawn",
            json={"sessionId": "s1", "parentAgentId": "", "childConfig": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_spawn_blocked_killed_parent(self, client):
        """Spawn is blocked when parent agent is killed."""
        import safeclaw.main as main_module

        engine = main_module.engine
        # Register and kill the parent agent
        engine.agent_registry.register_agent("parent-killed", role="developer", session_id="s1")
        engine.agent_registry.kill_agent("parent-killed")

        resp = client.post(
            "/api/v1/evaluate/subagent-spawn",
            json={
                "sessionId": "s1",
                "parentAgentId": "parent-killed",
                "childConfig": {"tools": ["exec"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False
        assert data["block"] is True
        assert "killed" in data["reason"]

    def test_spawn_delegation_bypass_detected(self, client):
        """Spawn is blocked when delegation bypass is detected."""
        import safeclaw.main as main_module

        engine = main_module.engine
        # Record a block for the parent agent
        engine.delegation_detector.record_block(
            session_id="s1",
            agent_id="parent-bypass",
            tool_name="exec",
            params_signature="sig123",
            params={"command": "rm -rf /"},
        )

        resp = client.post(
            "/api/v1/evaluate/subagent-spawn",
            json={
                "sessionId": "s1",
                "parentAgentId": "parent-bypass",
                "childConfig": {"tools": ["exec", "read"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False
        assert data["block"] is True
        assert "bypass" in data["reason"].lower()

    def test_spawn_default_fields(self, client):
        """All default fields are present in response."""
        resp = client.post("/api/v1/evaluate/subagent-spawn", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed" in data
        assert "block" in data
        assert "reason" in data

    def test_spawn_response_model(self, client):
        """Response matches SubagentSpawnResponse schema."""
        resp = client.post(
            "/api/v1/evaluate/subagent-spawn",
            json={"sessionId": "s1", "parentAgentId": "p1", "childConfig": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["allowed"], bool)
        assert isinstance(data["block"], bool)
        assert isinstance(data["reason"], str)


class TestSubagentEnded:
    def test_record_subagent_ended(self, client):
        """Recording subagent end returns ok."""
        resp = client.post(
            "/api/v1/record/subagent-ended",
            json={
                "sessionId": "s1",
                "parentAgentId": "parent-1",
                "childAgentId": "child-1",
                "result": "completed successfully",
                "success": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_record_subagent_ended_failure(self, client):
        """Recording a failed subagent end returns ok (audit only)."""
        resp = client.post(
            "/api/v1/record/subagent-ended",
            json={
                "sessionId": "s1",
                "parentAgentId": "parent-1",
                "childAgentId": "child-1",
                "result": "error occurred",
                "success": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_record_subagent_ended_tracks_session(self, client):
        """Subagent ended event is recorded in session tracker."""
        import safeclaw.main as main_module

        resp = client.post(
            "/api/v1/record/subagent-ended",
            json={
                "sessionId": "s-track",
                "parentAgentId": "parent-1",
                "childAgentId": "child-1",
                "success": True,
            },
        )
        assert resp.status_code == 200

        engine = main_module.engine
        state = engine.session_tracker.get_state("s-track")
        assert state is not None
        assert len(state.facts) == 1
        assert state.facts[0].action_class == "SubagentEnded"

    def test_record_subagent_ended_default_fields(self, client):
        """All default fields are accepted."""
        resp = client.post("/api/v1/record/subagent-ended", json={})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_record_subagent_ended_response_model(self, client):
        """Response matches SubagentEndedResponse schema."""
        resp = client.post(
            "/api/v1/record/subagent-ended",
            json={"sessionId": "s1", "childAgentId": "c1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["ok"], bool)
