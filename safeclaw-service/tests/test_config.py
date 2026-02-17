"""Tests for config template generation and loading."""

import json

import pytest

from safeclaw.config_template import (
    DEFAULT_CONFIG,
    generate_config,
    load_config,
    write_config,
)


class TestGenerateConfig:
    def test_defaults(self):
        config = generate_config()
        assert config["enabled"] is True
        assert config["userId"] == ""
        assert config["mode"] == "embedded"
        assert config["remote"]["serviceUrl"] == "http://localhost:8420/api/v1"

    def test_custom_user_id(self):
        config = generate_config(user_id="henrik")
        assert config["userId"] == "henrik"

    def test_custom_mode(self):
        config = generate_config(mode="remote")
        assert config["mode"] == "remote"

    def test_custom_service_url(self):
        config = generate_config(service_url="https://api.safeclaw.uku.ai/api/v1")
        assert config["remote"]["serviceUrl"] == "https://api.safeclaw.uku.ai/api/v1"

    def test_does_not_mutate_defaults(self):
        original_user = DEFAULT_CONFIG["userId"]
        generate_config(user_id="someone")
        assert DEFAULT_CONFIG["userId"] == original_user


class TestWriteConfig:
    def test_writes_json_file(self, tmp_path):
        config_path = tmp_path / "safeclaw" / "config.json"
        config = generate_config(user_id="test")
        write_config(config_path, config)

        assert config_path.exists()
        loaded = json.loads(config_path.read_text())
        assert loaded["userId"] == "test"

    def test_creates_parent_directories(self, tmp_path):
        config_path = tmp_path / "deep" / "nested" / "config.json"
        write_config(config_path, {"enabled": True})
        assert config_path.exists()


class TestLoadConfig:
    def test_load_nonexistent_returns_defaults(self, tmp_path):
        config = load_config(tmp_path / "missing.json")
        assert config["enabled"] is True
        assert config["mode"] == "embedded"

    def test_load_existing_config(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"userId": "loaded", "mode": "remote"}))
        config = load_config(config_path)
        assert config["userId"] == "loaded"
        assert config["mode"] == "remote"
        # Defaults should be filled in for missing keys
        assert config["enforcement"]["mode"] == "enforce"

    def test_deep_merge_preserves_nested_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        # Only override one nested key
        config_path.write_text(json.dumps({
            "audit": {"retentionDays": 30}
        }))
        config = load_config(config_path)
        # Override applied
        assert config["audit"]["retentionDays"] == 30
        # Other nested defaults preserved
        assert config["audit"]["enabled"] is True
        assert config["audit"]["logLlmIO"] is True
        assert config["audit"]["format"] == "jsonl"

    def test_roundtrip(self, tmp_path):
        config_path = tmp_path / "config.json"
        original = generate_config(user_id="roundtrip", mode="hybrid")
        write_config(config_path, original)
        loaded = load_config(config_path)
        assert loaded == original
