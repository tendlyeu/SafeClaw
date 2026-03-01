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


def OnboardStep2Mistral():
    """Step 2: Optional Mistral API key for LLM features."""
    return Div(
        H2("Enable LLM Features"),
        P("SafeClaw uses Mistral for security review, smart classification, "
          "and plain-English decision explanations.",
          cls=TextPresets.muted_sm),
        P("You can add this later from Preferences.",
          cls=TextPresets.muted_sm),
        Form(
            LabelInput(
                "Mistral API Key",
                id="mistral_api_key",
                type="password",
                placeholder="Enter your Mistral API key",
            ),
            DivLAligned(
                Button("Next", cls=ButtonT.primary, type="submit"),
                A("Skip for now", hx_post="/dashboard/onboard/step2",
                  hx_target="#onboard-content", hx_swap="innerHTML",
                  cls="uk-link-muted", style="margin-left:1rem;"),
            ),
            hx_post="/dashboard/onboard/step2",
            hx_target="#onboard-content",
            hx_swap="innerHTML",
            cls="space-y-4",
        ),
        id="onboard-content",
    )


def OnboardStep3(raw_key: str):
    """Step 3: Show generated API key + connection instructions."""
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
            P("2. Connect your plugin (choose one):"),
            P(Strong("Option A — CLI (recommended):")),
            Pre(Code(f"safeclaw connect {raw_key}")),
            P(Strong("Option B — Manual config file:")),
            Pre(Code(
                f'mkdir -p ~/.safeclaw && cat > ~/.safeclaw/config.json << \'EOF\'\n'
                f'{{\n'
                f'  "remote": {{\n'
                f'    "apiKey": "{raw_key}",\n'
                f'    "serviceUrl": "https://api.safeclaw.eu/api/v1"\n'
                f'  }}\n'
                f'}}\n'
                f'EOF'
            )),
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
