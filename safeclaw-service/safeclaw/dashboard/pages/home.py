"""Dashboard home page — system health stats and recent activity."""

from fasthtml.common import Div, H2, P, Span, Table, Tbody, Td, Th, Thead, Tr

from safeclaw.audit.reporter import AuditReporter
import safeclaw.dashboard.components as _comp
from safeclaw.dashboard.components import DecisionBadge, Page, RiskBadge, StatCard


def _build_home_content(engine):
    """Build the home page stats + activity content (reused by page and partial)."""
    prefix = _comp.MOUNT_PREFIX

    # ── Gather data ─────────────────────────────────────────
    recent = engine.audit.get_recent_records(limit=50)
    stats = AuditReporter(engine.audit).get_statistics(recent)

    triple_count = len(engine.kg)
    llm_configured = engine.llm_client is not None

    total = stats.get("total", 0)
    allowed = stats.get("allowed", 0)
    blocked = stats.get("blocked", 0)
    block_rate = stats.get("block_rate", 0)

    # Agent counts
    all_agents = engine.agent_registry.list_agents()
    registered_count = len(all_agents)
    active_count = sum(1 for a in all_agents if not a.killed)

    # ── Status cards row ────────────────────────────────────
    status_row = Div(
        StatCard("Engine Status", "Running", color="green"),
        StatCard(
            "LLM Status",
            "Configured" if llm_configured else "Not configured",
            color="purple" if llm_configured else "",
        ),
        StatCard("Ontology Triples", f"{triple_count:,}", color="blue"),
        StatCard("Registered Agents", registered_count, color="blue"),
        StatCard("Active Agents", active_count, color="green"),
        cls="stat-grid",
    )

    # ── Quick stats row ─────────────────────────────────────
    quick_row = Div(
        StatCard("Total Decisions", total),
        StatCard("Allowed", allowed, color="green"),
        StatCard("Blocked", blocked, color="red"),
        StatCard("Block Rate %", f"{block_rate}%", color="orange"),
        cls="stat-grid",
    )

    # ── Recent activity table ───────────────────────────────
    last_10 = recent[:10]
    if last_10:
        rows = []
        for r in last_10:
            ts = r.timestamp[:19].replace("T", " ")
            rows.append(
                Tr(
                    Td(Span(ts, cls="mono text-xs")),
                    Td(Span(r.session_id[:8], cls="mono text-xs")),
                    Td(r.action.tool_name),
                    Td(r.action.ontology_class),
                    Td(RiskBadge(r.action.risk_level)),
                    Td(DecisionBadge(r.decision)),
                    Td(
                        Span(
                            f"{r.justification.elapsed_ms:.0f}ms",
                            cls="text-muted text-xs mono",
                        )
                    ),
                )
            )
        activity_table = Table(
            Thead(
                Tr(
                    Th("Time"),
                    Th("Session"),
                    Th("Tool"),
                    Th("Action"),
                    Th("Risk"),
                    Th("Decision"),
                    Th("Latency"),
                )
            ),
            Tbody(*rows),
        )
    else:
        activity_table = Div(P("No recent decisions recorded."), cls="empty-state")

    activity_panel = Div(H2("Recent Activity"), activity_table, cls="panel")

    return Div(
        status_row,
        quick_row,
        activity_panel,
        id="home-stats",
        hx_get=f"{prefix}/partials/home-stats",
        hx_trigger="every 5s",
        hx_swap="outerHTML",
    )


def register(rt, get_engine):
    @rt("/")
    def home():
        engine = get_engine()
        content = _build_home_content(engine)
        return Page("Home", content, active="home")

    @rt("/partials/home-stats")
    def home_stats_partial():
        engine = get_engine()
        return _build_home_content(engine)
