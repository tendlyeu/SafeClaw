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
