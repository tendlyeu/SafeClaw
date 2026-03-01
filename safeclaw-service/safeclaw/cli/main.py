"""SafeClaw CLI - command line interface."""

from pathlib import Path

import typer

from safeclaw.cli.connect_cmd import connect_cmd
from safeclaw.cli.serve import serve_cmd
from safeclaw.cli.audit_cmd import audit_app
from safeclaw.cli.llm_cmd import llm_app
from safeclaw.cli.policy_cmd import policy_app
from safeclaw.cli.pref_cmd import pref_app
from safeclaw.cli.status_cmd import status_app

app = typer.Typer(name="safeclaw", help="SafeClaw - Neurosymbolic governance for AI agents")

app.command("connect")(connect_cmd)
app.command("serve")(serve_cmd)
app.add_typer(audit_app, name="audit")
app.add_typer(llm_app, name="llm")
app.add_typer(policy_app, name="policy")
app.add_typer(pref_app, name="pref")
app.add_typer(status_app, name="status")


@app.command()
def init(
    user_id: str = typer.Option("", help="User ID for the config"),
    mode: str = typer.Option("embedded", help="Operating mode: embedded, remote, or hybrid"),
    service_url: str = typer.Option(
        "http://localhost:8420/api/v1", help="Remote service URL"
    ),
):
    """Generate default ~/.safeclaw/config.json."""
    from safeclaw.config_template import generate_config, write_config

    config_path = Path.home() / ".safeclaw" / "config.json"
    if config_path.exists():
        typer.echo(f"Config already exists at {config_path}")
        typer.echo("Delete it first if you want to regenerate.")
        raise typer.Exit(code=1)

    config = generate_config(user_id=user_id, mode=mode, service_url=service_url)
    write_config(config_path, config)
    typer.echo(f"SafeClaw config written to {config_path}")


if __name__ == "__main__":
    app()
