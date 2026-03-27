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


def AuditTable(rows, show_user_column=False, disabled_logins=None):
    """Render audit log rows as a table."""
    if disabled_logins is None:
        disabled_logins = set()
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

    header = ["Time"]
    if show_user_column:
        header.append("User")
    header.extend(["Tool", "Decision", "Risk", "Reason", "Latency"])

    body = []
    for r in rows:
        ts = r.timestamp[:19].replace("T", " ") if r.timestamp else ""
        latency = f"{r.elapsed_ms:.0f}ms" if r.elapsed_ms else ""
        reason = (r.reason[:80] + "...") if r.reason and len(r.reason) > 80 else (r.reason or "")
        row_data = [ts]
        if show_user_column:
            login = getattr(r, "_github_login", "")
            style = "text-decoration:line-through;color:#888;" if login in disabled_logins else ""
            row_data.append(Span(login, style=style) if login else "—")
        row_data.extend([r.tool_name, _decision_badge(r.decision),
                         _risk_badge(r.risk_level), reason, latency])
        body.append(row_data)

    return Table(
        Thead(Tr(*[Th(h) for h in header])),
        Tbody(*[Tr(*[Td(c) for c in row]) for row in body]),
        cls=(TableT.hover, TableT.sm, TableT.striped),
    )


def AuditFilters(current_filter="all", session_id="", is_admin=False,
                 all_logins=None, current_user_filter=""):
    """Filter bar for the audit log."""
    admin_section = ""
    if is_admin and all_logins:
        options = [Option("All users", value="", selected=not current_user_filter)]
        for login in sorted(all_logins):
            options.append(Option(login, value=login, selected=current_user_filter == login))
        admin_section = Div(
            Div(
                FormLabel("User", _for="user_filter"),
                RawSelect(*options, name="user_filter", id="user_filter", cls="uk-select"),
                cls="space-y-2",
            ),
            style="border-left:1px solid #2a2a2a; padding-left:12px;",
        )

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
            admin_section,
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


def AuditContent(rows, current_filter="all", session_id="",
                 is_admin=False, all_logins=None, current_user_filter="",
                 show_user_column=False, disabled_logins=None):
    """Full audit page content."""
    return (
        Card(
            H3("Governance Audit Log"),
            P("All governance decisions made by SafeClaw for your API keys. ",
              "Toggle logging in ",
              A("Preferences", href="/dashboard/prefs"), ".",
              cls=TextPresets.muted_sm),
            AuditFilters(current_filter, session_id, is_admin=is_admin,
                         all_logins=all_logins, current_user_filter=current_user_filter),
        ),
        Div(AuditTable(rows, show_user_column=show_user_column,
                        disabled_logins=disabled_logins), id="audit-results"),
    )
