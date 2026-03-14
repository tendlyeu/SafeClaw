"""Tests for the pref CLI commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from safeclaw.cli.main import app

runner = CliRunner()


def test_pref_set_path_traversal_blocked():
    """User IDs with path traversal characters should be rejected."""
    result = runner.invoke(
        app,
        ["pref", "set", "confirmBeforeDelete", "true", "--user-id", "../../etc/evil"],
    )
    assert result.exit_code != 0
    assert "Invalid user_id" in result.output


def test_pref_set_invalid_key():
    """Unknown preference keys should be rejected."""
    result = runner.invoke(
        app,
        ["pref", "set", "nonExistentPref", "true"],
    )
    assert result.exit_code != 0
    assert "Unknown preference" in result.output


def test_pref_set_invalid_value():
    """Invalid preference values should be rejected."""
    result = runner.invoke(
        app,
        ["pref", "set", "confirmBeforeDelete", "maybe"],
    )
    assert result.exit_code != 0
    assert "Invalid value" in result.output


def test_pref_show_path_traversal_blocked():
    """User IDs with path traversal characters should be rejected in show too."""
    result = runner.invoke(
        app,
        ["pref", "show", "--user-id", "../../../etc/passwd"],
    )
    assert result.exit_code != 0
    assert "Invalid user_id" in result.output


def test_pref_set_writes_to_data_dir(tmp_path):
    """pref set should write to data_dir, not the bundled package directory."""
    mock_cfg = MagicMock()
    mock_cfg.data_dir = tmp_path
    # Create bundled ontology users dir with a default file
    bundled_users = tmp_path / "bundled" / "users"
    bundled_users.mkdir(parents=True)
    default_ttl = bundled_users / "user-default.ttl"
    default_ttl.write_text(
        '@prefix su: <http://safeclaw.uku.ai/ontology/user#> .\n'
        'su:confirmBeforeDelete "false" .\n'
    )
    mock_cfg.get_ontology_dir.return_value = tmp_path / "bundled"

    with patch("safeclaw.config.SafeClawConfig", return_value=mock_cfg):
        result = runner.invoke(
            app,
            ["pref", "set", "confirmBeforeDelete", "true", "--user-id", "testuser"],
        )
    assert result.exit_code == 0

    # Verify it wrote to data_dir/ontologies/users/, not bundled dir
    user_file = tmp_path / "ontologies" / "users" / "user-testuser.ttl"
    assert user_file.exists()
    assert '"true"' in user_file.read_text()
