"""Tests for audit DB logging in SQLiteAPIKeyManager."""

import sqlite3
import pytest

from safeclaw.auth.api_key import SQLiteAPIKeyManager


@pytest.fixture
def db_with_user(tmp_path):
    """Create a writable SQLite DB with a user who has audit_logging enabled."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, mistral_api_key TEXT DEFAULT '', audit_logging INTEGER DEFAULT 1)")
    conn.execute("INSERT INTO user (id, audit_logging) VALUES (1, 1)")
    conn.execute("CREATE TABLE api_key (id INTEGER PRIMARY KEY, user_id INTEGER, key_id TEXT, key_hash TEXT, label TEXT, scope TEXT, created_at TEXT, is_active BOOLEAN)")
    conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, user_id INTEGER, timestamp TEXT, session_id TEXT, tool_name TEXT, params_summary TEXT, decision TEXT, risk_level TEXT, reason TEXT, elapsed_ms REAL)")
    conn.commit()
    conn.close()
    return db_path


def test_is_audit_logging_enabled_returns_true(db_with_user):
    mgr = SQLiteAPIKeyManager(db_with_user)
    assert mgr.is_audit_logging_enabled("1") is True


def test_is_audit_logging_enabled_returns_false(db_with_user):
    conn = sqlite3.connect(db_with_user)
    conn.execute("UPDATE user SET audit_logging = 0 WHERE id = 1")
    conn.commit()
    conn.close()
    mgr = SQLiteAPIKeyManager(db_with_user)
    assert mgr.is_audit_logging_enabled("1") is False


def test_is_audit_logging_enabled_missing_user(db_with_user):
    mgr = SQLiteAPIKeyManager(db_with_user)
    assert mgr.is_audit_logging_enabled("999") is True  # default: enabled


def test_log_audit_decision_inserts_row(db_with_user):
    mgr = SQLiteAPIKeyManager(db_with_user)
    mgr.log_audit_decision(
        user_id="1",
        timestamp="2026-03-01T23:00:00Z",
        session_id="sess-1",
        tool_name="bash",
        params_summary='{"command": "rm -rf /"}',
        decision="blocked",
        risk_level="critical",
        reason="Dangerous command",
        elapsed_ms=12.5,
    )
    conn = sqlite3.connect(db_with_user)
    rows = conn.execute("SELECT * FROM audit_log WHERE user_id = 1").fetchall()
    assert len(rows) == 1
    assert rows[0][4] == "bash"  # tool_name
    assert rows[0][6] == "blocked"  # decision


def test_log_audit_decision_skips_when_disabled(db_with_user):
    conn = sqlite3.connect(db_with_user)
    conn.execute("UPDATE user SET audit_logging = 0 WHERE id = 1")
    conn.commit()
    conn.close()
    mgr = SQLiteAPIKeyManager(db_with_user)
    mgr.log_audit_decision(
        user_id="1",
        timestamp="2026-03-01T23:00:00Z",
        session_id="sess-1",
        tool_name="bash",
        params_summary="{}",
        decision="allowed",
        risk_level="safe",
        reason="passed",
        elapsed_ms=1.0,
    )
    conn = sqlite3.connect(db_with_user)
    rows = conn.execute("SELECT * FROM audit_log WHERE user_id = 1").fetchall()
    assert len(rows) == 0
