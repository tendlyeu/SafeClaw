"""Tests for the safeclaw connect CLI command."""

import json

from typer.testing import CliRunner

from safeclaw.cli.main import app

runner = CliRunner()


class TestConnectCommand:
    def test_connect_creates_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / ".safeclaw" / "config.json"
        monkeypatch.setattr("safeclaw.cli.connect_cmd.get_config_path", lambda: config_path)

        result = runner.invoke(app, ["connect", "sc_test_key_12345"])
        assert result.exit_code == 0
        assert "Connected" in result.output

        config = json.loads(config_path.read_text())
        assert config["remote"]["apiKey"] == "sc_test_key_12345"
        assert "safeclaw.eu" in config["remote"]["serviceUrl"]

    def test_connect_custom_service_url(self, tmp_path, monkeypatch):
        config_path = tmp_path / ".safeclaw" / "config.json"
        monkeypatch.setattr("safeclaw.cli.connect_cmd.get_config_path", lambda: config_path)

        result = runner.invoke(app, [
            "connect", "sc_test_key_12345",
            "--service-url", "http://localhost:8420/api/v1",
        ])
        assert result.exit_code == 0

        config = json.loads(config_path.read_text())
        assert config["remote"]["serviceUrl"] == "http://localhost:8420/api/v1"

    def test_connect_merges_existing_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / ".safeclaw" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({
            "enabled": True,
            "userId": "existing-user",
            "remote": {"serviceUrl": "http://old.example.com", "apiKey": "old_key"},
        }))
        monkeypatch.setattr("safeclaw.cli.connect_cmd.get_config_path", lambda: config_path)

        result = runner.invoke(app, ["connect", "sc_new_key_67890"])
        assert result.exit_code == 0

        config = json.loads(config_path.read_text())
        assert config["remote"]["apiKey"] == "sc_new_key_67890"
        assert config["userId"] == "existing-user"  # preserved
