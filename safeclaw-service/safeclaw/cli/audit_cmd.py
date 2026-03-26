"""CLI audit commands - view and query audit logs."""

from enum import Enum

import typer
from rich.console import Console
from rich.table import Table

from safeclaw.audit.logger import AuditLogger
from safeclaw.config import SafeClawConfig

audit_app = typer.Typer(
    help="View, query, and report on the append-only audit log. Every governance decision (allow/block) is recorded with full justification.",
)
console = Console()


@audit_app.command("show")
def show(
    last: int = typer.Option(20, help="Max number of decisions to display"),
    blocked: bool = typer.Option(False, help="Show only blocked decisions (combinable with --session)"),
    session: str = typer.Option(None, help="Filter to a specific session ID"),
):
    """Display recent governance decisions in a table.

    Shows time, decision (allowed/blocked), tool name, action class, risk level,
    and the reason for any block. Filters can be combined:

      safeclaw audit show --session abc123 --blocked --last 10
    """
    config = SafeClawConfig()
    logger = AuditLogger(config.get_audit_dir())

    if session:
        records = logger.get_session_records(session)
        if blocked:
            records = [r for r in records if r.decision == "blocked"]
        records = records[-last:]
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


class ReportFormat(str, Enum):
    """Valid output formats for audit reports."""

    markdown = "markdown"
    json = "json"
    csv = "csv"


@audit_app.command("report")
def report(
    session: str = typer.Argument(help="Session ID to generate report for (from 'audit show')"),
    report_format: ReportFormat = typer.Option(
        ReportFormat.markdown, "--format", "-f", help="Output format"
    ),
    output: str = typer.Option(None, "--output", "-o", help="Write report to file instead of stdout"),
):
    """Generate a detailed audit report for a single session.

    Includes all decisions, constraint checks, and preference effects.
    Use --format to choose between markdown, json, or csv output.
    """
    from safeclaw.audit.reporter import AuditReporter

    config = SafeClawConfig()
    logger = AuditLogger(config.get_audit_dir())
    reporter = AuditReporter(logger)

    content = reporter.generate_session_report(session, format=report_format.value)

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
    """Show aggregate statistics: allow/block counts, block rate, latency, risk distribution."""
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
    output: str = typer.Option(None, "--output", "-o", help="Write report to file instead of stdout"),
):
    """Generate a compliance report suitable for SOC 2 / ISO 27001 review."""
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
    audit_id: str = typer.Argument(help="Audit record ID (shown in 'audit show' output)"),
):
    """Use the LLM to explain a governance decision in plain English.

    Requires SAFECLAW_MISTRAL_API_KEY to be set. The record ID can be
    found in the audit show output or JSONL files in ~/.safeclaw/audit/.
    """
    import asyncio
    from safeclaw.llm.client import create_client

    config = SafeClawConfig()
    client = create_client(config)
    if client is None:
        console.print(
            "[red]Error: LLM not configured.[/red]\n"
            "Set the SAFECLAW_MISTRAL_API_KEY environment variable:\n"
            "  export SAFECLAW_MISTRAL_API_KEY=your-key-here\n\n"
            "This feature uses Mistral to generate human-readable explanations."
        )
        raise typer.Exit(1)

    audit_logger = AuditLogger(config.get_audit_dir())
    record = audit_logger.get_record_by_id(audit_id)

    if record is None:
        console.print(f"[red]Error: Audit record '{audit_id}' not found.[/red]")
        console.print("Use [bold]safeclaw audit show[/bold] to find valid record IDs.")
        raise typer.Exit(1)

    from safeclaw.llm.explainer import DecisionExplainer

    explainer = DecisionExplainer(client)
    explanation = asyncio.run(explainer.explain(record))
    console.print(f"\n{explanation}\n")
