"""Audit log dashboard page."""

from fasthtml.common import *
from monsterui.all import *
from fasthtml.components import Select as RawSelect


def _decision_badge(decision: str):
    """Color-coded badge for allowed/blocked."""
    if decision == "blocked":
        return Label(decision, cls=LabelT.destructive)
    return Label(decision, cls=LabelT.secondary)


def _risk_badge(risk_level: str):
    """Color-coded badge for risk level."""
    colors = {
        "critical": LabelT.destructive,
        "high": LabelT.destructive,
        "medium": LabelT.primary,
    }
    return Label(risk_level, cls=colors.get(risk_level, LabelT.secondary))


def AuditTable(rows):
    """Render audit log rows as a table."""
    if not rows:
        return Card(
            DivCentered(
                UkIcon("file-search", height=32),
                H4("No audit log entries yet"),
                P("Governance decisions will appear here once SafeClaw evaluates tool calls.",
                  cls=TextPresets.muted_sm),
                P("Make sure audit logging is enabled in ",
                  A("Preferences", href="/dashboard/prefs"), ".",
                  cls=TextPresets.muted_sm),
                cls="space-y-2",
            ),
        )

    header = ["Time", "Tool", "Decision", "Risk", "Reason", "Latency"]
    body = []
    for r in rows:
        ts = r.timestamp[:19].replace("T", " ") if r.timestamp else ""
        latency = f"{r.elapsed_ms:.0f}ms" if r.elapsed_ms else ""
        reason = (r.reason[:80] + "...") if r.reason and len(r.reason) > 80 else (r.reason or "")
        body.append([ts, r.tool_name, _decision_badge(r.decision),
                      _risk_badge(r.risk_level), reason, latency])

    return Table(
        Thead(Tr(*[Th(h) for h in header])),
        Tbody(*[Tr(*[Td(c) for c in row]) for row in body]),
        cls=(TableT.hover, TableT.sm, TableT.striped),
    )


def AuditFilters(current_filter="all", session_id=""):
    """Filter bar for the audit log."""
    return Form(
        DivLAligned(
            Div(
                FormLabel("Filter", _for="filter"),
                RawSelect(
                    Option("All decisions", value="all", selected=current_filter == "all"),
                    Option("Blocked only", value="blocked", selected=current_filter == "blocked"),
                    Option("Allowed only", value="allowed", selected=current_filter == "allowed"),
                    name="filter", id="filter", cls="uk-select",
                ),
                cls="space-y-2",
            ),
            LabelInput(
                "Session ID",
                id="session_id",
                value=session_id,
                placeholder="Optional",
            ),
            Button("Apply", cls=ButtonT.primary, type="submit"),
            Span(Loading(cls=LoadingT.spinner), cls="htmx-indicator", id="audit-spinner"),
            cls="gap-4 items-end",
        ),
        hx_get="/dashboard/audit/results",
        hx_target="#audit-results",
        hx_swap="innerHTML",
        hx_indicator="#audit-spinner",
        cls="space-y-4",
    )


def AuditContent(rows, current_filter="all", session_id=""):
    """Full audit page content."""
    return (
        Card(
            H3("Governance Audit Log"),
            P("All governance decisions made by SafeClaw for your API keys. ",
              "Toggle logging in ",
              A("Preferences", href="/dashboard/prefs"), ".",
              cls=TextPresets.muted_sm),
            AuditFilters(current_filter, session_id),
        ),
        Div(AuditTable(rows), id="audit-results"),
    )
