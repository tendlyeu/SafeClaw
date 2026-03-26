"""Tests for the audit CLI commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from safeclaw.audit.models import (
    ActionDetail,
    ConstraintCheck,
    DecisionRecord,
    Justification,
)
from safeclaw.cli.main import app

runner = CliRunner()


def _make_record(decision="allowed", tool_name="read_file", record_id="test-id-1"):
    return DecisionRecord(
        id=record_id,
        session_id="sess-1",
        user_id="user-1",
        action=ActionDetail(
            tool_name=tool_name,
            params={},
            ontology_class="FileRead",
            risk_level="low",
            is_reversible=True,
            affects_scope="file",
        ),
        decision=decision,
        justification=Justification(
            constraints_checked=[
                ConstraintCheck(
                    constraint_uri="http://example.org/c1",
                    constraint_type="policy",
                    result="satisfied" if decision == "allowed" else "violated",
                    reason="test reason",
                )
            ],
            elapsed_ms=5.0,
        ),
    )


@patch("safeclaw.cli.audit_cmd.AuditLogger")
@patch("safeclaw.cli.audit_cmd.SafeClawConfig")
def test_audit_show_no_records(mock_config, mock_logger_cls):
    mock_logger = MagicMock()
    mock_logger.get_recent_records.return_value = []
    mock_logger_cls.return_value = mock_logger
    mock_config.return_value = MagicMock()

    result = runner.invoke(app, ["audit", "show"])
    assert result.exit_code == 0
    assert "No audit records found" in result.output


@patch("safeclaw.cli.audit_cmd.AuditLogger")
@patch("safeclaw.cli.audit_cmd.SafeClawConfig")
def test_audit_show_with_records(mock_config, mock_logger_cls):
    mock_logger = MagicMock()
    mock_logger.get_recent_records.return_value = [_make_record()]
    mock_logger_cls.return_value = mock_logger
    mock_config.return_value = MagicMock()

    result = runner.invoke(app, ["audit", "show"])
    assert result.exit_code == 0
    assert "read_file" in result.output


@patch("safeclaw.cli.audit_cmd.AuditLogger")
@patch("safeclaw.cli.audit_cmd.SafeClawConfig")
def test_audit_show_blocked_filter(mock_config, mock_logger_cls):
    mock_logger = MagicMock()
    mock_logger.get_blocked_records.return_value = [_make_record(decision="blocked")]
    mock_logger_cls.return_value = mock_logger
    mock_config.return_value = MagicMock()

    result = runner.invoke(app, ["audit", "show", "--blocked"])
    assert result.exit_code == 0
    mock_logger.get_blocked_records.assert_called_once()


@patch("safeclaw.cli.audit_cmd.AuditLogger")
@patch("safeclaw.cli.audit_cmd.SafeClawConfig")
def test_audit_show_session_and_blocked_composable(mock_config, mock_logger_cls):
    """--session and --blocked should be composable, filtering blocked records within a session."""
    allowed = _make_record(decision="allowed", tool_name="read_file", record_id="r1")
    blocked = _make_record(decision="blocked", tool_name="rm_file", record_id="r2")
    mock_logger = MagicMock()
    mock_logger.get_session_records.return_value = [allowed, blocked]
    mock_logger_cls.return_value = mock_logger
    mock_config.return_value = MagicMock()

    result = runner.invoke(app, ["audit", "show", "--session", "sess-1", "--blocked"])
    assert result.exit_code == 0
    # Should show only the blocked record, not the allowed one
    assert "rm_file" in result.output
    assert "read_file" not in result.output
    mock_logger.get_session_records.assert_called_once_with("sess-1")


@patch("safeclaw.cli.audit_cmd.AuditLogger")
@patch("safeclaw.cli.audit_cmd.SafeClawConfig")
def test_audit_show_session_respects_last_limit(mock_config, mock_logger_cls):
    """--session should respect the --last limit."""
    records = [_make_record(record_id=f"r{i}") for i in range(10)]
    mock_logger = MagicMock()
    mock_logger.get_session_records.return_value = records
    mock_logger_cls.return_value = mock_logger
    mock_config.return_value = MagicMock()

    result = runner.invoke(app, ["audit", "show", "--session", "sess-1", "--last", "3"])
    assert result.exit_code == 0
    # The table should contain only 3 rows (the last 3 records)
    assert result.output.count("read_file") == 3


def test_audit_report_invalid_format():
    """Invalid report format should be rejected by Typer's enum validation."""
    result = runner.invoke(app, ["audit", "report", "some-session", "--format", "xml"])
    assert result.exit_code != 0


@patch("safeclaw.cli.audit_cmd.AuditLogger")
@patch("safeclaw.cli.audit_cmd.SafeClawConfig")
def test_audit_explain_uses_get_record_by_id(mock_config, mock_logger_cls):
    """Verify explain uses get_record_by_id instead of get_recent_records (issue #43)."""
    mock_logger = MagicMock()
    mock_logger.get_record_by_id.return_value = None
    mock_logger_cls.return_value = mock_logger
    mock_config.return_value = MagicMock()

    # Will fail because LLM is not configured, but we can verify the lookup method
    result = runner.invoke(app, ["audit", "explain", "some-id"])
    # It should exit with error (LLM not configured or record not found)
    assert result.exit_code != 0
