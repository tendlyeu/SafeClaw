"""safeclaw connect — write API key to ~/.safeclaw/config.json."""

import json
import os
from pathlib import Path

import typer


def get_config_path() -> Path:
    """Return the default config path. Extracted for testability."""
    return Path.home() / ".safeclaw" / "config.json"


def connect_cmd(
    api_key: str = typer.Argument(help="Your SafeClaw API key (starts with sc_)"),
    service_url: str = typer.Option(
        "https://api.safeclaw.eu/api/v1",
        help="SafeClaw service URL",
    ),
):
    """Connect your plugin to SafeClaw by saving your API key to ~/.safeclaw/config.json."""
    config_path = get_config_path()

    # Load existing config or start fresh
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # Start fresh

    # Set remote config
    if "remote" not in config or not isinstance(config["remote"], dict):
        config["remote"] = {}
    config["remote"]["apiKey"] = api_key
    config["remote"]["serviceUrl"] = service_url

    # Write config with owner-only permissions (contains API key)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    os.chmod(config_path, 0o600)

    typer.echo(f"Connected! Your API key has been saved to {config_path}")
