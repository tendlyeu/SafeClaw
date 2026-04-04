"""Dashboard audit log page — filterable audit log with detail expansion."""

from fasthtml.common import (
    A,
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

import safeclaw.dashboard.components as _comp
from safeclaw.dashboard.components import DecisionBadge, Page, RiskBadge


def register(rt, get_engine, get_csrf_token=None):
    @rt("/audit")
    def audit(
        sess,
        filter: str = "",
        session_id: str = "",
        tool_name: str = "",
        risk: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 50,
    ):
        engine = get_engine()

        # ── Fetch records based on filters ────────────────────────
        if filter == "blocked":
            records = engine.audit.get_blocked_records(limit=limit)
        elif session_id:
            records = engine.audit.get_session_records(session_id)
        else:
            records = engine.audit.get_recent_records(limit=limit)

        # ── Post-fetch filters ───────────────────────────────────
        if tool_name:
            records = [r for r in records if tool_name.lower() in r.action.tool_name.lower()]
        if risk:
            records = [r for r in records if r.action.risk_level.lower() == risk.lower()]
        if date_from:
            records = [r for r in records if r.timestamp[:10] >= date_from]
        if date_to:
            records = [r for r in records if r.timestamp[:10] <= date_to]

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
                        Input(
                            type="text",
                            name="tool_name",
                            placeholder="Tool name",
                            value=tool_name,
                        ),
                    ),
                    Div(
                        Select(
                            Option("All risks", value="", selected=(not risk)),
                            Option(
                                "critical",
                                value="critical",
                                selected=(risk == "critical"),
                            ),
                            Option(
                                "high",
                                value="high",
                                selected=(risk == "high"),
                            ),
                            Option(
                                "medium",
                                value="medium",
                                selected=(risk == "medium"),
                            ),
                            Option(
                                "low",
                                value="low",
                                selected=(risk == "low"),
                            ),
                            name="risk",
                        ),
                    ),
                    style="display: flex; gap: 1rem; align-items: end;",
                ),
                Div(
                    Div(
                        Span("From", cls="text-xs"),
                        Input(type="date", name="date_from", value=date_from),
                    ),
                    Div(
                        Span("To", cls="text-xs"),
                        Input(type="date", name="date_to", value=date_to),
                    ),
                    Div(
                        Button("Apply", type="submit", cls="btn btn-primary"),
                    ),
                    style="display: flex; gap: 1rem; align-items: end;",
                ),
                method="get",
                action=f"{_comp.MOUNT_PREFIX}/audit",
            ),
            cls="panel",
        )

        # ── Export buttons ───────────────────────────────────────
        export_links = []
        if session_id:
            export_links.append(
                A(
                    "Export Session Report",
                    href=f"/api/v1/audit/report/{session_id}?format=markdown",
                    cls="btn export-btn",
                    target="_blank",
                )
            )
        export_links.append(
            A(
                "Compliance Report",
                href="/api/v1/audit/compliance",
                cls="btn export-btn",
                target="_blank",
            )
        )
        export_row = Div(
            *export_links,
            style="display: flex; gap: 1rem; margin-bottom: 1rem;",
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
                                hx_get=f"{_comp.MOUNT_PREFIX}/audit/detail/{r.id}",
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

        token = get_csrf_token(sess) if get_csrf_token else ""
        return Page(
            "Audit Log",
            filter_panel,
            export_row,
            results_panel,
            active="audit",
            csrf_token=token,
        )

    @rt("/audit/detail/{audit_id}")
    def audit_detail(audit_id: str):
        engine = get_engine()
        record = engine.audit.get_record_by_id(audit_id)

        if record is None:
            return Div(P("Record not found.", cls="text-muted"))

        sections = []

        # ── Action params (truncated) ─────────────────────────────
        import json

        params_str = json.dumps(record.action.params, default=str)
        if len(params_str) > 500:
            params_str = params_str[:500] + "..."
        sections.append(
            Div(
                H2("Action Parameters"),
                P(Span(params_str, cls="mono text-xs"), style="word-break: break-all;"),
                cls="mt-1",
            )
        )

        # ── Decision reason (for early-exit blocks with no constraint checks) ──
        if record.decision == "blocked" and not record.justification.constraints_checked:
            # Early-exit block (agent governance, role check, etc.)
            sections.append(
                Div(
                    H2("Block Reason"),
                    P("Blocked before constraint pipeline (agent governance or role check)."),
                    cls="mt-1",
                )
            )

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
        sections.append(Div(H2("Constraints Checked"), constraints_table))

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

        if pref_rows:
            sections.append(
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
            )

        # ── Session action history (last 5) ───────────────────────
        history = getattr(record, "session_action_history", None) or []
        if history:
            last_5 = history[-5:]
            history_rows = [Tr(Td(Span(str(h), cls="mono text-xs"))) for h in last_5]
            sections.append(
                Div(
                    H2("Session History (last 5)"),
                    Table(Thead(Tr(Th("Action"))), Tbody(*history_rows)),
                    cls="mt-2",
                )
            )

        # ── LLM Explain button ───────────────────────────────────
        if engine.explainer is not None:
            sections.append(
                Div(
                    Button(
                        "Explain",
                        cls="btn btn-sm hx_indicator",
                        hx_get=f"{_comp.MOUNT_PREFIX}/audit/explain/{audit_id}",
                        hx_target=f"#explain-{audit_id}",
                        hx_swap="innerHTML",
                    ),
                    Div(id=f"explain-{audit_id}"),
                    cls="mt-2",
                )
            )

        return Div(*sections, style="padding: 0.75rem 0;")

    @rt("/audit/explain/{audit_id}")
    async def audit_explain(audit_id: str):
        engine = get_engine()

        if engine.explainer is None:
            return Div(P("Explainer not available.", cls="text-muted"))

        record = engine.audit.get_record_by_id(audit_id)
        if record is None:
            return Div(P("Record not found.", cls="text-muted"))

        explanation = await engine.explainer.explain(record)
        return Div(P(explanation), cls="explain-block")
