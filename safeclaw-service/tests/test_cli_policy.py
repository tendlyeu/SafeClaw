"""Tests for the policy CLI commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from safeclaw.cli.main import app

runner = CliRunner()


def test_policy_add_invalid_name_rejected():
    """Policy names with path traversal characters should be rejected."""
    result = runner.invoke(
        app,
        ["policy", "add", "../../evil", "--reason", "test"],
    )
    assert result.exit_code != 0
    assert "Invalid policy name" in result.output


def test_policy_add_valid_name_accepted(tmp_path):
    """Valid policy names should be accepted."""
    mock_cfg = MagicMock()
    policy_file = tmp_path / "safeclaw-policy.ttl"
    policy_file.write_text("# test policy file\n")
    mock_cfg.get_ontology_dir.return_value = tmp_path

    with patch("safeclaw.config.SafeClawConfig", return_value=mock_cfg):
        result = runner.invoke(
            app,
            [
                "policy",
                "add",
                "TestPolicy",
                "--reason",
                "test reason",
                "--type",
                "prohibition",
            ],
        )
    assert result.exit_code == 0
    assert "added successfully" in result.output

    # Verify the policy was appended
    content = policy_file.read_text()
    assert "sp:TestPolicy" in content


def test_policy_remove_not_found(tmp_path):
    """Removing a nonexistent policy should report not found."""
    mock_cfg = MagicMock()
    policy_file = tmp_path / "safeclaw-policy.ttl"
    policy_file.write_text("# empty policy file\n")
    mock_cfg.get_ontology_dir.return_value = tmp_path

    with patch("safeclaw.config.SafeClawConfig", return_value=mock_cfg):
        result = runner.invoke(app, ["policy", "remove", "NonExistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_policy_add_unknown_type():
    """Unknown policy type should be rejected."""
    result = runner.invoke(
        app,
        ["policy", "add", "TestPolicy", "--reason", "test", "--type", "unknown"],
    )
    assert result.exit_code != 0
