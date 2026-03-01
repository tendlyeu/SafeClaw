"""Onboarding wizard — shown to first-time users after GitHub OAuth."""

from monsterui.all import *


def OnboardStep1():
    """Step 1: Choose autonomy level."""
    levels = [
        ("cautious", "Cautious",
         "Confirms before any write, delete, or external action. "
         "Best for production environments."),
        ("moderate", "Moderate",
         "Confirms before deletes and irreversible actions. "
         "Allows reads and safe writes automatically."),
        ("autonomous", "Autonomous",
         "Minimal confirmations. Only blocks policy violations "
         "and critical-risk actions."),
    ]
    cards = []
    for value, label, desc in levels:
        checked = "checked" if value == "moderate" else ""
        cards.append(
            Label(
                Card(
                    DivLAligned(
                        Input(type="radio", name="autonomy_level", value=value,
                              cls="uk-radio", **({checked: True} if checked else {})),
                        H4(label),
                    ),
                    P(desc, cls=TextPresets.muted_sm),
                ),
                style="cursor:pointer; display:block;",
            )
        )
    return Div(
        H2("Welcome to SafeClaw"),
        P("Choose how much control SafeClaw should have over your AI agent's actions.",
          cls=TextPresets.muted_sm),
        Form(
            Div(*cards, cls="space-y-3"),
            Button("Next", cls=ButtonT.primary, type="submit"),
            hx_post="/dashboard/onboard/step1",
            hx_target="#onboard-content",
            hx_swap="innerHTML",
            cls="space-y-6",
        ),
        id="onboard-content",
    )


def OnboardStep2(raw_key: str):
    """Step 2: Show generated API key + install instructions."""
    return Div(
        H2("Your API Key"),
        P("Copy this key now — it won't be shown again.",
          cls=TextPresets.muted_sm),
        Card(
            Pre(Code(raw_key), style="word-break:break-all; font-size:1.1em;"),
            cls="uk-alert-success",
        ),
        H3("Connect your OpenClaw agent"),
        Div(
            P("1. Install the SafeClaw plugin:"),
            Pre(Code("openclaw plugins install openclaw-safeclaw-plugin")),
            P("2. Set your API key:"),
            Pre(Code(f"export SAFECLAW_API_KEY={raw_key}")),
            P("That's it — SafeClaw will govern your agent's actions automatically.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
        Form(
            Button("Go to Dashboard", cls=ButtonT.primary, type="submit"),
            action="/dashboard/onboard/done",
            method="post",
        ),
        id="onboard-content",
    )
