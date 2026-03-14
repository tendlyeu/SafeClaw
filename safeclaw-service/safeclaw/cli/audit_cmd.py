"""CLI audit commands - view and query audit logs."""

import typer
from rich.console import Console
from rich.table import Table

from safeclaw.audit.logger import AuditLogger
from safeclaw.config import SafeClawConfig

audit_app = typer.Typer(help="Audit log commands")
console = Console()


@audit_app.command("show")
def show(
    last: int = typer.Option(20, help="Number of recent decisions to show"),
    blocked: bool = typer.Option(False, help="Show only blocked decisions"),
    session: str = typer.Option(None, help="Filter by session ID"),
):
    """Show recent audit decisions."""
    config = SafeClawConfig()
    logger = AuditLogger(config.get_audit_dir())

    if session:
        records = logger.get_session_records(session)
    elif blocked:
        records = logger.get_blocked_records(last)
    else:
        records = logger.get_recent_records(last)

    if not records:
        console.print("[yellow]No audit records found[/yellow]")
        return

    table = Table(title="SafeClaw Audit Log")
    table.add_column("Time", style="dim")
    table.add_column("Decision", style="bold")
    table.add_column("Tool")
    table.add_column("Action Class")
    table.add_column("Risk")
    table.add_column("Reason")

    for record in records:
        decision_style = "green" if record.decision == "allowed" else "red"
        reason = ""
        if record.decision == "blocked":
            for check in record.justification.constraints_checked:
                if check.result == "violated":
                    reason = check.reason
                    break
            if not reason:
                for pref in record.justification.preferences_applied:
                    reason = pref.effect
                    break

        table.add_row(
            record.timestamp[:19],
            f"[{decision_style}]{record.decision}[/{decision_style}]",
            record.action.tool_name,
            record.action.ontology_class,
            record.action.risk_level,
            reason[:60],
        )

    console.print(table)


@audit_app.command("report")
def report(
    session: str = typer.Argument(help="Session ID to generate report for"),
    format: str = typer.Option(
        "markdown", "--format", "-f", help="Output format: markdown, json, csv"
    ),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Generate an audit report for a session."""
    from safeclaw.audit.reporter import AuditReporter

    config = SafeClawConfig()
    logger = AuditLogger(config.get_audit_dir())
    reporter = AuditReporter(logger)

    content = reporter.generate_session_report(session, format=format)

    if output:
        with open(output, "w") as f:
            f.write(content)
        console.print(f"[green]Report written to {output}[/green]")
    else:
        console.print(content)


@audit_app.command("stats")
def stats(
    last: int = typer.Option(100, help="Number of recent records to analyze"),
):
    """Show aggregate audit statistics."""
    from safeclaw.audit.reporter import AuditReporter

    config = SafeClawConfig()
    logger = AuditLogger(config.get_audit_dir())
    reporter = AuditReporter(logger)
    records = logger.get_recent_records(last)

    if not records:
        console.print("[yellow]No audit records found[/yellow]")
        return

    s = reporter.get_statistics(records)

    console.print(f"[bold]SafeClaw Audit Statistics[/bold] (last {s['total']} decisions)")
    console.print(f"  Allowed: [green]{s['allowed']}[/green]")
    console.print(f"  Blocked: [red]{s['blocked']}[/red]")
    console.print(f"  Block rate: {s['block_rate']}%")
    console.print(f"  Avg latency: {s['avg_latency_ms']}ms")

    if s.get("risk_distribution"):
        console.print("\n[bold]Risk Distribution:[/bold]")
        for risk, count in sorted(s["risk_distribution"].items()):
            console.print(f"  {risk}: {count}")

    if s.get("top_violated_constraints"):
        console.print("\n[bold]Top Violated Constraints:[/bold]")
        for uri, count in s["top_violated_constraints"].items():
            console.print(f"  {uri}: {count}")


@audit_app.command("compliance")
def compliance(
    last: int = typer.Option(100, help="Number of recent records to include"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Generate a compliance report."""
    from safeclaw.audit.reporter import AuditReporter

    config = SafeClawConfig()
    logger = AuditLogger(config.get_audit_dir())
    reporter = AuditReporter(logger)
    records = logger.get_recent_records(last)

    content = reporter.generate_compliance_report(records)

    if output:
        with open(output, "w") as f:
            f.write(content)
        console.print(f"[green]Compliance report written to {output}[/green]")
    else:
        console.print(content)


@audit_app.command("explain")
def explain(
    audit_id: str = typer.Argument(help="Audit record ID to explain"),
):
    """Explain a decision in plain English (requires LLM)."""
    import asyncio
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    if client is None:
        console.print(
            "[red]LLM not configured. Set SAFECLAW_MISTRAL_API_KEY environment variable.[/red]"
        )
        raise typer.Exit(1)

    audit_logger = AuditLogger(config.get_audit_dir())
    record = audit_logger.get_record_by_id(audit_id)

    if record is None:
        console.print(f"[red]Audit record '{audit_id}' not found[/red]")
        raise typer.Exit(1)

    from safeclaw.llm.explainer import DecisionExplainer

    explainer = DecisionExplainer(client)
    explanation = asyncio.run(explainer.explain(record))
    console.print(f"\n{explanation}\n")
