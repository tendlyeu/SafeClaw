"""CLI status and diagnostic commands."""

from pathlib import Path

import typer

status_app = typer.Typer(help="Service status and diagnostics")


@status_app.command("check")
def status_check(
    url: str = typer.Option(
        "http://localhost:8420/api/v1", help="SafeClaw service URL"
    ),
):
    """Check the running SafeClaw service status."""
    import httpx
    from rich.console import Console
    from rich.table import Table

    console = Console()

    try:
        r = httpx.get(f"{url}/health", timeout=5)
        r.raise_for_status()
        data = r.json()
    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to {url}[/red]")
        console.print("Is the service running? Try: [bold]safeclaw serve[/bold]")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Service returned HTTP {e.response.status_code}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    status = data.get("status", "unknown")
    color = "green" if status == "ok" else "red"
    console.print(f"Service: [{color}]{status}[/{color}]")
    console.print(f"Version: {data.get('version', '?')}")
    console.print(f"Engine ready: {data.get('engine_ready', False)}")
    console.print(f"Uptime: {data.get('uptime_seconds', 0)}s")

    components = data.get("components")
    if components:
        table = Table(title="Components")
        table.add_column("Component", style="bold")
        table.add_column("Detail")

        kg = components.get("knowledge_graph", {})
        table.add_row("Knowledge Graph", f"{kg.get('triples', 0):,} triples")

        llm = components.get("llm", {})
        llm_status = "[green]configured[/green]" if llm.get("configured") else "[dim]not configured[/dim]"
        table.add_row("LLM", llm_status)

        sessions = components.get("sessions", {})
        table.add_row("Sessions", f"{sessions.get('active', 0)} active")

        agents = components.get("agents", {})
        table.add_row("Agents", f"{agents.get('registered', 0)} registered, {agents.get('active', 0)} active")

        console.print(table)


@status_app.command("diagnose")
def status_diagnose():
    """Run offline diagnostic checks (no service needed)."""
    from rich.console import Console

    console = Console()
    console.print("[bold]SafeClaw Diagnostics[/bold]\n")

    all_ok = True

    # 1. Config file
    config_path = Path.home() / ".safeclaw" / "config.json"
    if config_path.exists():
        console.print(f"[green]OK[/green]  Config file: {config_path}")
    else:
        console.print(f"[red]ISSUE[/red]  No config file at {config_path}")
        console.print("       Run: [bold]safeclaw init --user-id yourname[/bold]")
        all_ok = False

    # 2. Ontology files
    bundled_dir = Path(__file__).parent.parent / "ontologies"
    ttl_files = list(bundled_dir.glob("*.ttl")) if bundled_dir.exists() else []
    if ttl_files:
        console.print(f"[green]OK[/green]  Ontology files: {len(ttl_files)} .ttl files in {bundled_dir}")
    else:
        console.print(f"[red]ISSUE[/red]  No .ttl files found in {bundled_dir}")
        all_ok = False

    # 3. Audit directory
    audit_dir = Path.home() / ".safeclaw" / "audit"
    if audit_dir.exists():
        console.print(f"[green]OK[/green]  Audit directory: {audit_dir}")
    else:
        console.print(f"[yellow]ISSUE[/yellow]  Audit directory missing: {audit_dir} (will be created on first run)")

    # 4. Mistral API key
    import os

    if os.environ.get("SAFECLAW_MISTRAL_API_KEY"):
        console.print("[green]OK[/green]  Mistral API key: set via environment")
    else:
        console.print("[dim]INFO[/dim]  Mistral API key: not set (LLM features disabled, optional)")

    console.print()
    if all_ok:
        console.print("[green]All checks passed.[/green]")
    else:
        console.print("[yellow]Some issues found. See above.[/yellow]")
