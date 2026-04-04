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
        "@prefix su: <http://safeclaw.uku.ai/ontology/user#> .\nsu:confirmBeforeDelete false .\n"
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
    # confirmBeforeDelete is a bare boolean in Turtle (not quoted)
    assert "su:confirmBeforeDelete true" in user_file.read_text()


def test_pref_set_max_files_per_commit_rejects_zero():
    """maxFilesPerCommit must be a positive integer."""
    result = runner.invoke(app, ["pref", "set", "maxFilesPerCommit", "0"])
    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_pref_set_max_files_per_commit_rejects_negative():
    """maxFilesPerCommit must be a positive integer."""
    # Use -- to prevent Typer from interpreting -5 as a flag
    result = runner.invoke(app, ["pref", "set", "--", "maxFilesPerCommit", "-5"])
    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_pref_set_max_files_per_commit_rejects_non_numeric():
    """maxFilesPerCommit must be a positive integer."""
    result = runner.invoke(app, ["pref", "set", "maxFilesPerCommit", "abc"])
    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_pref_set_max_files_per_commit_accepts_valid(tmp_path):
    """maxFilesPerCommit should accept a valid positive integer."""
    mock_cfg = MagicMock()
    mock_cfg.data_dir = tmp_path
    bundled_users = tmp_path / "bundled" / "users"
    bundled_users.mkdir(parents=True)
    default_ttl = bundled_users / "user-default.ttl"
    default_ttl.write_text(
        "@prefix su: <http://safeclaw.uku.ai/ontology/user#> .\nsu:maxFilesPerCommit 10 .\n"
    )
    mock_cfg.get_ontology_dir.return_value = tmp_path / "bundled"

    with patch("safeclaw.config.SafeClawConfig", return_value=mock_cfg):
        result = runner.invoke(
            app,
            ["pref", "set", "maxFilesPerCommit", "25", "--user-id", "testuser"],
        )
    assert result.exit_code == 0

    user_file = tmp_path / "ontologies" / "users" / "user-testuser.ttl"
    assert "su:maxFilesPerCommit 25" in user_file.read_text()


def test_pref_set_never_modify_paths_rejects_empty():
    """neverModifyPaths should reject empty strings."""
    result = runner.invoke(app, ["pref", "set", "neverModifyPaths", "   "])
    assert result.exit_code != 0
    assert "cannot be empty" in result.output


def test_pref_set_never_modify_paths_accepts_valid(tmp_path):
    """neverModifyPaths should accept comma-separated paths."""
    mock_cfg = MagicMock()
    mock_cfg.data_dir = tmp_path
    bundled_users = tmp_path / "bundled" / "users"
    bundled_users.mkdir(parents=True)
    default_ttl = bundled_users / "user-default.ttl"
    default_ttl.write_text(
        '@prefix su: <http://safeclaw.uku.ai/ontology/user#> .\nsu:neverModifyPaths "old/path" .\n'
    )
    mock_cfg.get_ontology_dir.return_value = tmp_path / "bundled"

    with patch("safeclaw.config.SafeClawConfig", return_value=mock_cfg):
        result = runner.invoke(
            app,
            ["pref", "set", "neverModifyPaths", "/etc,/prod", "--user-id", "testuser"],
        )
    assert result.exit_code == 0

    user_file = tmp_path / "ontologies" / "users" / "user-testuser.ttl"
    assert 'su:neverModifyPaths "/etc,/prod"' in user_file.read_text()
