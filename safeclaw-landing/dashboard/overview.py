"""Dashboard overview page."""

from monsterui.all import *


def ServiceHealthCard():
    """Card showing service health status, refreshes via HTMX."""
    return Card(
        H3("Service Health"),
        Div(
            P("Checking...", cls=TextPresets.muted_sm),
            id="health-status",
            hx_get="/dashboard/health-check",
            hx_trigger="load, every 30s",
            hx_swap="innerHTML",
        ),
    )


def GettingStartedCard():
    """Setup instructions for new users."""
    return Card(
        H3("Getting Started"),
        Div(
            P("1. Create an API key in the ", A("Keys", href="/dashboard/keys"), " tab"),
            P("2. Install the OpenClaw plugin:"),
            Pre(Code("openclaw plugins install openclaw-safeclaw-plugin")),
            P("3. Set your API key:"),
            Pre(Code("export SAFECLAW_API_KEY=sc_your_key_here")),
            cls="space-y-2",
        ),
    )


def OverviewContent(user, key_count: int):
    """Main overview page content."""
    return (
        Grid(
            Card(
                DivLAligned(UkIcon("key", height=20), H4("API Keys")),
                P(f"{key_count} keys", cls=TextPresets.muted_sm),
                footer=A("Manage keys ->", href="/dashboard/keys"),
            ),
            Card(
                DivLAligned(UkIcon("bot", height=20), H4("Agents")),
                P("View on service", cls=TextPresets.muted_sm),
                footer=A("View agents ->", href="/dashboard/agents"),
            ),
            cols=2,
        ),
        ServiceHealthCard(),
        GettingStartedCard(),
    )
