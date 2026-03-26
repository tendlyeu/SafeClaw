"""CLI commands for LLM layer features."""

import json

import typer
from rich.console import Console
from rich.table import Table

llm_app = typer.Typer(
    help=(
        "Inspect the passive LLM layer — security findings and classification suggestions.\n\n"
        "The LLM layer observes tool calls and reviews them for security issues.\n"
        "It also suggests action classification improvements. All features require\n"
        "SAFECLAW_MISTRAL_API_KEY to be set."
    ),
)
console = Console()


@llm_app.command("findings")
def findings():
    """Show where to find security findings from the LLM reviewer.

    The LLM security reviewer runs passively on each tool call and logs
    findings to the safeclaw.llm.security logger. Findings are also
    available via the API.
    """
    console.print(
        "[yellow]Security findings are logged to the safeclaw.llm.security logger.[/yellow]"
    )
    console.print("")
    console.print("To view findings:")
    console.print("  - API:  GET /api/v1/llm/findings")
    console.print("  - Logs: check your log aggregation system for 'safeclaw.llm.security'")
    console.print("")
    console.print("To enable: set SAFECLAW_MISTRAL_API_KEY and ensure llm_security_review_enabled=true")


@llm_app.command("suggestions")
def suggestions():
    """Display LLM-generated classification improvement suggestions.

    The LLM observer compares the symbolic classifier's output with its own
    assessment and records disagreements as suggestions. These are stored
    in ~/.safeclaw/llm/classification_suggestions.jsonl.
    """
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
