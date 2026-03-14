"""Tests for the LLM CLI commands."""

from typer.testing import CliRunner

from safeclaw.cli.main import app

runner = CliRunner()


def test_llm_findings_runs():
    """llm findings should run and show guidance message."""
    result = runner.invoke(app, ["llm", "findings"])
    assert result.exit_code == 0
    assert "findings" in result.output.lower() or "logger" in result.output.lower()


def test_llm_suggestions_no_file():
    """llm suggestions should handle missing suggestions file gracefully."""
    result = runner.invoke(app, ["llm", "suggestions"])
    assert result.exit_code == 0
    # Should show "no suggestions" or the table
    assert "suggestion" in result.output.lower() or "No" in result.output
