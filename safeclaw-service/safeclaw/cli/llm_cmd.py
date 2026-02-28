"""CLI commands for LLM layer features."""

import json

import typer
from rich.console import Console
from rich.table import Table

llm_app = typer.Typer(help="LLM layer commands")
console = Console()


@llm_app.command("findings")
def findings(
    last: int = typer.Option(20, help="Number of recent findings to show"),
):
    """Show recent security findings from the LLM reviewer."""
    console.print("[yellow]Security findings are currently logged to the safeclaw.llm.security logger.[/yellow]")
    console.print("Use log aggregation to review findings, or check the API: GET /api/v1/llm/findings")


@llm_app.command("suggestions")
def suggestions():
    """Show classification improvement suggestions from the LLM observer."""
    from safeclaw.config import SafeClawConfig

    config = SafeClawConfig()
    suggestions_file = config.data_dir / "llm" / "classification_suggestions.jsonl"

    if not suggestions_file.exists():
        console.print("[yellow]No classification suggestions yet[/yellow]")
        return

    table = Table(title="Classification Suggestions")
    table.add_column("Tool", style="cyan")
    table.add_column("Current", style="dim")
    table.add_column("Suggested", style="green")
    table.add_column("Risk", style="yellow")
    table.add_column("Reasoning")

    for line in suggestions_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            s = json.loads(line)
            table.add_row(
                s.get("tool_name", ""),
                s.get("symbolic_class", ""),
                s.get("suggested_class", ""),
                s.get("suggested_risk", ""),
                s.get("reasoning", "")[:60],
            )
        except json.JSONDecodeError:
            continue

    console.print(table)
