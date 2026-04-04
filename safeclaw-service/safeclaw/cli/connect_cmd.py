"""safeclaw connect — write API key to ~/.safeclaw/config.json."""

import json
import os
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def get_config_path() -> Path:
    """Return the default config path. Extracted for testability."""
    return Path.home() / ".safeclaw" / "config.json"


def connect_cmd(
    api_key: str = typer.Argument(
        help="Your SafeClaw API key (starts with sc_). Get one at https://safeclaw.eu/dashboard"
    ),
    service_url: str = typer.Option(
        "https://api.safeclaw.eu/api/v1",
        help="SafeClaw remote service URL",
    ),
):
    """Save your API key for remote SafeClaw service connections.

    Writes the key to ~/.safeclaw/config.json with owner-only permissions.
    For plugin-side setup (OpenClaw registration, handshake validation),
    use 'safeclaw-plugin connect' instead.
    """
    if not api_key.startswith("sc_"):
        console.print("[red]Error: Invalid API key. Keys must start with 'sc_'.[/red]")
        console.print("Get your key at https://safeclaw.eu/dashboard")
        raise typer.Exit(1)

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

    # Write config with owner-only permissions atomically (contains API key)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_content = json.dumps(config, indent=2) + "\n"
    fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, config_content.encode("utf-8"))
    finally:
        os.close(fd)

    console.print(f"[green]Connected![/green] Your API key has been saved to {config_path}")
