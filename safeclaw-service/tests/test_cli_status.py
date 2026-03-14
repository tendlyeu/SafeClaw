"""Tests for the status CLI commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from safeclaw.cli.main import app

runner = CliRunner()


def test_status_diagnose_runs():
    """Diagnose should run without requiring a live service."""
    result = runner.invoke(app, ["status", "diagnose"])
    assert result.exit_code == 0
    assert "Diagnostics" in result.output


def test_status_check_connection_error():
    """status check should handle connection errors gracefully."""
    import httpx

    mock_httpx = MagicMock()
    mock_httpx.ConnectError = httpx.ConnectError
    mock_httpx.HTTPStatusError = httpx.HTTPStatusError
    mock_httpx.get.side_effect = httpx.ConnectError("Connection refused")

    # httpx is imported inside the function body, so we patch it in the module's imports
    with patch.dict("sys.modules", {"httpx": mock_httpx}):
        result = runner.invoke(app, ["status", "check"])
    assert result.exit_code != 0
    assert "Cannot connect" in result.output
