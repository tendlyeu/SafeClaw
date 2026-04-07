"""Dashboard overview page."""

import subprocess
from pathlib import Path

from fasthtml.common import *
from monsterui.all import *

# Cache version info at module load
_VERSION_SHA = "unknown"
_VERSION_TS = ""

# Try .version file first (Docker builds bake this via ARG)
_version_file = Path(__file__).resolve().parent.parent / ".version"
if _version_file.exists():
    _parts = _version_file.read_text().strip().split(" ", 1)
    _sha = _parts[0] if _parts else "unknown"
    _VERSION_SHA = _sha[:7] if len(_sha) > 7 else _sha  # Short hash
    _VERSION_TS = _parts[1] if len(_parts) > 1 else ""
else:
    # Fall back to git (works in dev, not in Docker)
    try:
        _VERSION_SHA = subprocess.check_output(
            ["git", "log", "-1", "--format=%h"], text=True, timeout=2,
            stderr=subprocess.DEVNULL,
        ).strip()
        _VERSION_TS = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci"], text=True, timeout=2,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        pass


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


def LLMNudge():
    """Banner shown when user has no AI provider key configured."""
    return Card(
        DivLAligned(
            UkIcon("alert-triangle", height=20),
            Div(
                P(Strong("AI features disabled")),
                P("SafeClaw is running in rule-based mode only. "
                  "Add an AI provider key in ",
                  A("Preferences", href="/dashboard/prefs"),
                  " to unlock smart classification, security review, "
                  "and plain-English decision explanations. "
                  "Several providers offer free tiers.",
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


def OverviewContent(user, key_count: int, has_llm_key: bool = True):
    """Main overview page content."""
    commit_sha, commit_ts = _VERSION_SHA, _VERSION_TS
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
        Card(
            DivLAligned(UkIcon("git-commit", height=20), H4("Version")),
            P(Code(commit_sha), "  ", Span(commit_ts, cls=TextPresets.muted_sm)),
        ),
    ]
    if not has_llm_key:
        content.append(LLMNudge())
    if user.self_hosted:
        content.append(SelfHostedHealthCard())
    else:
        content.append(HostedStatusCard())
    content.append(GettingStartedCard())
    return tuple(content)
