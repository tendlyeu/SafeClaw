"""Dashboard audit log page — filterable audit log with detail expansion."""

from fasthtml.common import (
    Button,
    Div,
    Form,
    H2,
    Input,
    Option,
    P,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

from safeclaw.dashboard.components import DecisionBadge, Page, RiskBadge


def register(rt, get_engine):
    @rt("/audit")
    def audit(filter: str = "", session_id: str = "", limit: int = 50):
        engine = get_engine()

        # ── Fetch records based on filters ────────────────────────
        if filter == "blocked":
            records = engine.audit.get_blocked_records(limit=limit)
        elif session_id:
            records = engine.audit.get_session_records(session_id)
        else:
            records = engine.audit.get_recent_records(limit=limit)

        # ── Filter panel ──────────────────────────────────────────
        filter_panel = Div(
            H2("Filters"),
            Form(
                Div(
                    Div(
                        Select(
                            Option("All", value="", selected=(filter != "blocked")),
                            Option(
                                "Blocked only",
                                value="blocked",
                                selected=(filter == "blocked"),
                            ),
                            name="filter",
                        ),
                    ),
                    Div(
                        Input(
                            type="text",
                            name="session_id",
                            placeholder="Session ID",
                            value=session_id,
                        ),
                    ),
                    Div(
                        Button("Apply", type="submit", cls="btn btn-primary"),
                    ),
                    style="display: flex; gap: 1rem; align-items: end;",
                ),
                method="get",
                action="/audit",
            ),
            cls="panel",
        )

        # ── Results table ─────────────────────────────────────────
        if records:
            rows = []
            for r in records:
                ts = r.timestamp[:19].replace("T", " ")
                rows.append(
                    Tr(
                        Td(Span(ts, cls="mono text-xs")),
                        Td(Span(r.session_id[:8], cls="mono text-xs")),
                        Td(r.action.tool_name),
                        Td(Span(r.action.ontology_class, cls="text-sm")),
                        Td(RiskBadge(r.action.risk_level)),
                        Td(DecisionBadge(r.decision)),
                        Td(
                            Span(
                                f"{r.justification.elapsed_ms:.0f}ms",
                                cls="text-muted text-xs mono",
                            )
                        ),
                        Td(
                            Button(
                                "Details",
                                cls="btn btn-sm",
                                hx_get=f"/audit/detail/{r.id}",
                                hx_target=f"#detail-{r.id}",
                                hx_swap="innerHTML",
                            )
                        ),
                    )
                )
                # Detail expansion row (hidden until loaded via HTMX)
                rows.append(
                    Tr(
                        Td(
                            Div(id=f"detail-{r.id}"),
                            colspan="8",
                        )
                    )
                )

            results_table = Table(
                Thead(
                    Tr(
                        Th("Time"),
                        Th("Session"),
                        Th("Tool"),
                        Th("Action"),
                        Th("Risk"),
                        Th("Decision"),
                        Th("Latency"),
                        Th(""),
                    )
                ),
                Tbody(*rows),
            )
        else:
            results_table = Div(P("No audit records found."), cls="empty-state")

        results_panel = Div(H2("Results"), results_table, cls="panel")

        return Page("Audit Log", filter_panel, results_panel, active="audit")

    @rt("/audit/detail/{audit_id}")
    def audit_detail(audit_id: str):
        engine = get_engine()
        record = engine.audit.get_record_by_id(audit_id)

        if record is None:
            return Div(P("Record not found.", cls="text-muted"))

        # ── Constraints checked table ─────────────────────────────
        constraint_rows = []
        for c in record.justification.constraints_checked:
            constraint_rows.append(
                Tr(
                    Td(c.constraint_type),
                    Td(c.result),
                    Td(c.reason),
                )
            )

        constraints_table = (
            Table(
                Thead(
                    Tr(
                        Th("Type"),
                        Th("Result"),
                        Th("Reason"),
                    )
                ),
                Tbody(*constraint_rows),
            )
            if constraint_rows
            else P("No constraints checked.", cls="text-muted")
        )

        # ── Preferences applied ───────────────────────────────────
        pref_rows = []
        for p in record.justification.preferences_applied:
            pref_rows.append(
                Tr(
                    Td(p.preference_uri),
                    Td(p.value),
                    Td(p.effect),
                )
            )

        preferences_section = (
            Div(
                H2("Preferences Applied"),
                Table(
                    Thead(
                        Tr(
                            Th("Preference"),
                            Th("Value"),
                            Th("Effect"),
                        )
                    ),
                    Tbody(*pref_rows),
                ),
                cls="mt-2",
            )
            if pref_rows
            else ""
        )

        return Div(
            H2("Constraints Checked"),
            constraints_table,
            preferences_section,
            style="padding: 0.75rem 0;",
        )
