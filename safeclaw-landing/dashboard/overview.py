"""Dashboard overview page."""

from fasthtml.common import *
from monsterui.all import *


def HostedStatusCard():
    """Card showing hosted service status for SaaS users."""
    return Card(
        H3("Service Status"),
        DivLAligned(
            Span("●", style="color:#4ade80; font-size:20px;"),
            Span("Connected to SafeClaw hosted service"),
        ),
        P("Your agents are governed by the SafeClaw cloud at ",
          Code("api.safeclaw.eu"), ". No setup required.",
          cls=TextPresets.muted_sm),
    )


def SelfHostedHealthCard():
    """Card showing service health status for self-hosted users, refreshes via HTMX."""
    return Card(
        H3("Service Health"),
        P("Checking your self-hosted SafeClaw service.",
          cls=TextPresets.muted_sm),
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
                P("SafeClaw is running in rule-based mode only. "
                  "Add your Mistral API key in ",
                  A("Preferences", href="/dashboard/prefs"),
                  " to unlock smart classification, security review, "
                  "and plain-English decision explanations.",
                  cls=TextPresets.muted_sm),
            ),
        ),
        cls="uk-alert-warning",
    )


def GettingStartedCard():
    """Setup instructions for new users."""
    return Card(
        H3("Getting Started"),
        P("Follow these steps to connect your AI agent to SafeClaw. "
          "This only needs to be done once per machine.",
          cls=TextPresets.muted_sm),
        Div(
            P(Strong("1."), " Create an API key in the ", A("Keys", href="/dashboard/keys"), " tab"),
            P(Strong("2."), " Install the plugin:"),
            Pre(Code("npm install -g openclaw-safeclaw-plugin")),
            P(Strong("3."), " Connect (saves key + registers with OpenClaw):"),
            Pre(Code("safeclaw connect sc_your_key_here")),
            P(Strong("4."), " Restart OpenClaw to activate:"),
            Pre(Code("safeclaw restart-openclaw")),
            P("After restarting, every tool call your AI agent makes will be "
              "validated against your governance rules before execution.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
    )


def OverviewContent(user, key_count: int, has_mistral_key: bool = True):
    """Main overview page content."""
    content = [
        Grid(
            Card(
                DivLAligned(UkIcon("key", height=20), H4("API Keys")),
                P(f"{key_count} key{'s' if key_count != 1 else ''} created", cls=TextPresets.muted_sm),
                footer=A("Manage keys ->", href="/dashboard/keys"),
            ),
            Card(
                DivLAligned(UkIcon("settings", height=20), H4("Preferences")),
                P(f"Autonomy: {user.autonomy_level}", cls=TextPresets.muted_sm),
                footer=A("Edit preferences ->", href="/dashboard/prefs"),
            ),
            cols=2,
        ),
    ]
    if not has_mistral_key:
        content.append(MistralNudge())
    if user.self_hosted:
        content.append(SelfHostedHealthCard())
    else:
        content.append(HostedStatusCard())
    content.append(GettingStartedCard())
    return tuple(content)
