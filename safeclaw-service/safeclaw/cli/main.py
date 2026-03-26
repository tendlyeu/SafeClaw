"""SafeClaw CLI - command line interface."""

from enum import Enum
from pathlib import Path

import typer

from safeclaw.cli.connect_cmd import connect_cmd
from safeclaw.cli.serve import serve_cmd
from safeclaw.cli.audit_cmd import audit_app
from safeclaw.cli.llm_cmd import llm_app
from safeclaw.cli.policy_cmd import policy_app
from safeclaw.cli.pref_cmd import pref_app
from safeclaw.cli.status_cmd import status_app

app = typer.Typer(
    name="safeclaw",
    help=(
        "SafeClaw — Neurosymbolic governance for AI agents.\n\n"
        "Validates tool calls, messages, and actions against OWL ontologies\n"
        "and SHACL constraints before execution. This is the service CLI.\n\n"
        "Quick start:\n\n"
        "  safeclaw init --user-id yourname   Create config\n\n"
        "  safeclaw serve                     Start the governance service\n\n"
        "  safeclaw status check              Verify the service is running\n\n"
        "For the OpenClaw plugin CLI, use safeclaw-plugin."
    ),
)

app.command("connect")(connect_cmd)
app.command("serve")(serve_cmd)
app.add_typer(audit_app, name="audit")
app.add_typer(llm_app, name="llm")
app.add_typer(policy_app, name="policy")
app.add_typer(pref_app, name="pref")
app.add_typer(status_app, name="status")


class OperatingMode(str, Enum):
    """Valid operating modes for SafeClaw."""

    embedded = "embedded"
    remote = "remote"


@app.command()
def init(
    user_id: str = typer.Option(
        "", help="Your user ID, used to load per-user preferences (e.g., 'alice')"
    ),
    mode: OperatingMode = typer.Option(
        OperatingMode.embedded,
        help="'embedded' runs the engine locally; 'remote' connects to a hosted service",
    ),
    service_url: str = typer.Option(
        "http://localhost:8420/api/v1",
        help="Service URL (only used in 'remote' mode)",
    ),
):
    """Create the initial SafeClaw config at ~/.safeclaw/config.json.

    Sets up roles, enforcement mode, audit settings, and context injection
    defaults. Run this once before starting the service.
    """
    from safeclaw.config_template import generate_config, write_config

    config_path = Path.home() / ".safeclaw" / "config.json"
    if config_path.exists():
        typer.echo(f"Error: Config already exists at {config_path}")
        typer.echo("To regenerate, delete the existing file first:")
        typer.echo(f"  rm {config_path}")
        raise typer.Exit(code=1)

    config = generate_config(user_id=user_id, mode=mode.value, service_url=service_url)
    write_config(config_path, config)
    typer.echo(f"SafeClaw config written to {config_path}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  safeclaw serve           Start the governance service")
    typer.echo("  safeclaw status check    Verify the service is running")


if __name__ == "__main__":
    app()
