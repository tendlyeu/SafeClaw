"""Tests for audit log dashboard page."""

import pytest
from unittest.mock import MagicMock
from starlette.testclient import TestClient

from safeclaw.config import SafeClawConfig
from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
)
from safeclaw.dashboard.app import create_dashboard


def _make_record(decision="allowed", tool="read", risk="LowRisk", session_id="sess-1"):
    return DecisionRecord(
        session_id=session_id,
        user_id="testuser",
        action=ActionDetail(
            tool_name=tool,
            params={"file_path": "/src/main.py"},
            ontology_class="ReadFile",
            risk_level=risk,
            is_reversible=True,
            affects_scope="Workspace",
        ),
        decision=decision,
        justification=Justification(
            constraints_checked=[
                ConstraintCheck(
                    constraint_uri="shacl:validation",
                    constraint_type="SHACL",
                    result="satisfied",
                    reason="All shapes conform",
                ),
            ],
            elapsed_ms=1.5,
        ),
    )


@pytest.fixture
def audit_client():
    engine = MagicMock()
    engine.config = SafeClawConfig(admin_password="")
    engine.audit.get_recent_records.return_value = [
        _make_record("allowed"),
        _make_record("blocked", "exec", "CriticalRisk"),
    ]
    engine.audit.get_blocked_records.return_value = [
        _make_record("blocked", "exec", "CriticalRisk"),
    ]
    engine.audit.get_session_records.return_value = []
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

    def get_engine():
        return engine

    app = create_dashboard(get_engine)
    return TestClient(app), engine


def test_audit_page_renders(audit_client):
    """Audit page renders with decision records."""
    client, _ = audit_client
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert "ReadFile" in resp.text
    assert "allowed" in resp.text.lower()
    assert "blocked" in resp.text.lower()


def test_audit_filter_blocked(audit_client):
    """Audit page can filter to blocked only."""
    client, engine = audit_client
    resp = client.get("/audit?filter=blocked")
    assert resp.status_code == 200
    engine.audit.get_blocked_records.assert_called()
