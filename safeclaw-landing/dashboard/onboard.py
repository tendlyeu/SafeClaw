"""Onboarding wizard — shown to first-time users after GitHub OAuth."""

from fasthtml.common import *
from monsterui.all import *


def OnboardStep1(csrf_token=""):
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
        Div(
            H2("Welcome to SafeClaw"),
            P("SafeClaw sits between your AI agent and the tools it uses. "
              "Every action — file edits, git pushes, shell commands — is checked "
              "against safety rules before it runs.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
        Divider(),
        Div(
            P("Choose how strictly SafeClaw should govern your agent. "
              "You can change this anytime from the Preferences page.",
              cls=TextPresets.muted_sm),
            Form(
                Input(type="hidden", name="_csrf_token", value=csrf_token),
                Div(*cards, cls="space-y-4"),
                Button("Next", cls=ButtonT.primary, type="submit"),
                hx_post="/dashboard/onboard/step1",
                hx_target="#onboard-content",
                hx_swap="innerHTML",
                cls="space-y-6",
            ),
            cls="space-y-4",
        ),
        id="onboard-content",
        cls="space-y-6",
    )


def OnboardStep2LLM(csrf_token=""):
    """Step 2: Optional AI provider key for LLM features."""
    from providers import PROVIDERS

    free_providers = [
        ("mistral", PROVIDERS["mistral"]),
        ("gemini", PROVIDERS["gemini"]),
        ("groq", PROVIDERS["groq"]),
        ("qwen", PROVIDERS["qwen"]),
    ]

    provider_options = []
    for pid, info in free_providers:
        provider_options.append(
            Card(
                DivLAligned(
                    Input(type="radio", name="llm_provider", value=pid, cls="uk-radio"),
                    H4(info.name),
                    Span(info.free_tier, style="font-size:0.7rem; background:#065f46; color:#6ee7b7; padding:1px 6px; border-radius:8px; margin-left:auto;"),
                ),
                P("Get a key at ",
                  A(info.console_url.replace("https://", ""), href=info.console_url, target="_blank"),
                  cls=TextPresets.muted_sm),
            )
        )

    return Div(
        Div(
            H2("Enable AI Features"),
            P("Without an AI key, SafeClaw uses rule-based classification only — "
              "it maps tool names to action categories using exact matches. "
              "This works for common tools but can miss unusual or custom ones.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
        Divider(),
        Div(
            P("With an AI provider key, SafeClaw adds:", cls=TextPresets.muted_sm),
            Ul(
                Li(Strong("Smart classification"), " — understands what a tool call "
                   "actually does, even for unfamiliar tools"),
                Li(Strong("Security review"), " — scans parameters for hidden risks "
                   "like command injection or data exposure"),
                Li(Strong("Plain-English explanations"), " — tells you why an action "
                   "was blocked in clear language"),
                cls="uk-list uk-list-disc",
                style="font-size:0.875rem; color:var(--muted-foreground, #888);",
            ),
            P("API keys are separate from consumer subscriptions (ChatGPT Plus, etc.). "
              "These providers all offer free tiers:",
              style="font-size:0.8rem; color:var(--muted-foreground, #888); margin-top:0.5rem;"),
            cls="space-y-2",
        ),
        Divider(),
        Form(
            Input(type="hidden", name="_csrf_token", value=csrf_token),
            Div(*provider_options, cls="space-y-3"),
            Div(
                LabelInput(
                    "API Key",
                    id="llm_api_key",
                    type="password",
                    placeholder="Paste your API key here",
                ),
                P("You can add more providers or change this later in Preferences.",
                  cls=TextPresets.muted_sm),
                cls="space-y-1",
                style="margin-top:1rem;",
            ),
            DivLAligned(
                Button("Next", cls=ButtonT.primary, type="submit"),
                Button("Skip for now", type="submit",
                       cls="uk-link-muted",
                       style="margin-left:1rem; background:none; border:none; cursor:pointer; text-decoration:underline;"),
            ),
            hx_post="/dashboard/onboard/step2",
            hx_target="#onboard-content",
            hx_swap="innerHTML",
            cls="space-y-6",
        ),
        id="onboard-content",
        cls="space-y-6",
    )


def OnboardStep3(raw_key: str, csrf_token=""):
    """Step 3: Show generated API key + connection instructions."""
    return Div(
        Div(
            H2("Your API Key"),
            P("This key authenticates your agent's plugin against SafeClaw. "
              "It starts with ", Code("sc_"), " and is shown only this once — "
              "we store a hash, so we can't recover it for you.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
        Card(
            Pre(Code(raw_key), style="word-break:break-all; font-size:1.1em;"),
            cls="uk-alert-success",
        ),
        Divider(),
        Div(
            H3("Connect your OpenClaw agent"),
            P("Run these commands in your terminal. This only needs to be done once per machine.",
              cls=TextPresets.muted_sm),
            cls="space-y-2",
        ),
        Div(
            Div(
                P(Strong("Step 1"), " — Install the plugin globally:"),
                Pre(Code("npm install -g openclaw-safeclaw-plugin")),
                cls="space-y-2",
            ),
            Divider(),
            Div(
                P(Strong("Step 2"), " — Connect with your key:"),
                Pre(Code(f"safeclaw connect {raw_key}")),
                P("This saves your key to ", Code("~/.safeclaw/config.json"),
                  " and automatically registers the SafeClaw plugin with OpenClaw.",
                  cls=TextPresets.muted_sm),
                cls="space-y-2",
            ),
            Divider(),
            Div(
                P(Strong("Step 3"), " — Restart OpenClaw to activate:"),
                Pre(Code("safeclaw restart-openclaw")),
                cls="space-y-2",
            ),
            cls="space-y-4",
        ),
        Divider(),
        Div(
            P("After connecting, every tool call your AI agent makes will be "
              "validated by SafeClaw before execution.",
              cls=TextPresets.muted_sm),
            Form(
                Input(type="hidden", name="_csrf_token", value=csrf_token),
                Button("Go to Dashboard", cls=ButtonT.primary, type="submit"),
                action="/dashboard/onboard/done",
                method="post",
            ),
            cls="space-y-4",
        ),
        id="onboard-content",
        cls="space-y-6",
    )
