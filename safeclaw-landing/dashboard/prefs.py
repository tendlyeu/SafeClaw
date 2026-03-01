"""User preferences page."""

from fasthtml.common import *
from monsterui.all import *


def _field_group(*children):
    """Wrap a form field and its helper text together."""
    return Div(*children, cls="space-y-1")


def PrefsForm(prefs: dict | None = None, mistral_api_key: str = ""):
    """Preference editing form."""
    if prefs is None:
        prefs = {
            "autonomy_level": "moderate",
            "confirm_before_delete": True,
            "confirm_before_push": True,
            "confirm_before_send": True,
            "max_files_per_commit": 10,
        }

    return Form(
        # ── Autonomy Level ──
        _field_group(
            LabelSelect(
                Option("Cautious", value="cautious", selected=prefs.get("autonomy_level") == "cautious"),
                Option("Moderate", value="moderate", selected=prefs.get("autonomy_level") == "moderate"),
                Option(
                    "Autonomous",
                    value="autonomous",
                    selected=prefs.get("autonomy_level") == "autonomous",
                ),
                label="Autonomy Level",
                id="autonomy_level",
            ),
            P("Controls how strictly SafeClaw enforces constraints. ",
              Strong("Cautious"), " = confirms almost everything. ",
              Strong("Moderate"), " = confirms destructive actions only. ",
              Strong("Autonomous"), " = blocks policy violations only.",
              cls=TextPresets.muted_sm),
        ),

        Divider(),

        # ── Confirmation Rules ──
        Div(
            H4("Confirmation Rules"),
            P("When enabled, SafeClaw pauses the agent and asks for your "
              "confirmation before allowing these action types.",
              cls=TextPresets.muted_sm),
            cls="space-y-1",
        ),

        _field_group(
            LabelCheckboxX(
                "Confirm before deleting files",
                id="confirm_before_delete",
                checked=prefs.get("confirm_before_delete", True),
            ),
            P("File deletion, directory removal, destructive file system operations.",
              cls=TextPresets.muted_sm, style="padding-left:1.75rem;"),
        ),

        _field_group(
            LabelCheckboxX(
                "Confirm before pushing code",
                id="confirm_before_push",
                checked=prefs.get("confirm_before_push", True),
            ),
            P("Git push, force push, publishing to remote repositories.",
              cls=TextPresets.muted_sm, style="padding-left:1.75rem;"),
        ),

        _field_group(
            LabelCheckboxX(
                "Confirm before sending messages",
                id="confirm_before_send",
                checked=prefs.get("confirm_before_send", True),
            ),
            P("Emails, Slack messages, any outbound communication.",
              cls=TextPresets.muted_sm, style="padding-left:1.75rem;"),
        ),

        Divider(),

        # ── Limits ──
        _field_group(
            H4("Limits"),
            LabelInput(
                "Max files per commit",
                id="max_files_per_commit",
                type="number",
                value=str(prefs.get("max_files_per_commit", 10)),
                min="1",
                max="100",
            ),
            P("Blocks commits touching more files than this. Set to 100 to disable.",
              cls=TextPresets.muted_sm),
        ),

        Divider(),

        # ── LLM Integration ──
        Div(
            H4("LLM Integration"),
            P("SafeClaw can use Mistral AI to enhance governance. "
              "Without a key it still works using rule-based classification.",
              cls=TextPresets.muted_sm),
            Ul(
                Li(Strong("Smart classification"), " — understands unfamiliar tools"),
                Li(Strong("Security review"), " — detects hidden risks in parameters"),
                Li(Strong("Plain-English explanations"), " — clear block reasons"),
                cls="uk-list uk-list-disc",
                style="font-size:0.875rem; color:var(--muted-foreground, #888); margin-top:0.5rem;",
            ),
            cls="space-y-1",
        ),

        _field_group(
            LabelInput(
                "Mistral API Key",
                id="mistral_api_key",
                type="password",
                value=mistral_api_key,
                placeholder="Enter your Mistral API key",
            ),
            P("Get a free key at ",
              A("console.mistral.ai", href="https://console.mistral.ai", target="_blank"),
              ". Clear this field and save to remove it.",
              cls=TextPresets.muted_sm),
        ),

        Button("Save Preferences", cls=ButtonT.primary, type="submit"),
        hx_post="/dashboard/prefs/save",
        hx_target="#prefs-status",
        hx_swap="innerHTML",
        cls="space-y-6",
    )


def PrefsContent(prefs: dict | None = None, mistral_api_key: str = ""):
    """Full preferences page content."""
    return (
        Card(
            H3("Governance Preferences"),
            P(
                "These settings control how SafeClaw governs your AI agent's actions. "
                "Changes take effect immediately.",
                cls=TextPresets.muted_sm,
            ),
            PrefsForm(prefs, mistral_api_key=mistral_api_key),
        ),
        Div(id="prefs-status"),
    )
