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


def MistralNudge():
    """Banner shown when user has no Mistral API key configured."""
    return Card(
        DivLAligned(
            UkIcon("alert-triangle", height=20),
            Div(
                P(Strong("LLM features disabled")),
                P("Add your Mistral API key in ",
                  A("Preferences", href="/dashboard/prefs"),
                  " to enable security review and smart classification.",
                  cls=TextPresets.muted_sm),
            ),
        ),
        cls="uk-alert-warning",
    )


def GettingStartedCard():
    """Setup instructions for new users."""
    return Card(
        H3("Getting Started"),
        Div(
            P("1. Create an API key in the ", A("Keys", href="/dashboard/keys"), " tab"),
            P("2. Install the OpenClaw plugin:"),
            Pre(Code("openclaw plugins install openclaw-safeclaw-plugin")),
            P("3. Connect your plugin:"),
            Pre(Code("safeclaw connect sc_your_key_here")),
            cls="space-y-2",
        ),
    )


def OverviewContent(user, key_count: int, has_mistral_key: bool = True):
    """Main overview page content."""
    content = [
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
    ]
    if not has_mistral_key:
        content.append(MistralNudge())
    content.append(ServiceHealthCard())
    content.append(GettingStartedCard())
    return tuple(content)
