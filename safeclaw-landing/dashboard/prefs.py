"""User preferences page."""

from fasthtml.common import *
from monsterui.all import *


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
          Strong("Cautious"), " asks for confirmation on almost everything. ",
          Strong("Moderate"), " only confirms destructive or irreversible actions. ",
          Strong("Autonomous"), " only blocks outright policy violations.",
          cls=TextPresets.muted_sm),

        # ── Confirmation Rules ──
        H4("Confirmation Rules"),
        P("When enabled, SafeClaw will pause the agent and ask for your "
          "confirmation before allowing these action types. The agent receives "
          "a 'confirm required' response instead of a block or allow.",
          cls=TextPresets.muted_sm),
        LabelCheckboxX(
            "Confirm before deleting files",
            id="confirm_before_delete",
            checked=prefs.get("confirm_before_delete", True),
        ),
        P("Applies to file deletion, directory removal, and similar destructive "
          "file system operations.",
          cls=TextPresets.muted_sm, style="margin-top:-0.5rem;"),
        LabelCheckboxX(
            "Confirm before pushing code",
            id="confirm_before_push",
            checked=prefs.get("confirm_before_push", True),
        ),
        P("Applies to git push, force push, and publishing to remote repositories.",
          cls=TextPresets.muted_sm, style="margin-top:-0.5rem;"),
        LabelCheckboxX(
            "Confirm before sending messages",
            id="confirm_before_send",
            checked=prefs.get("confirm_before_send", True),
        ),
        P("Applies to sending emails, Slack messages, or any outbound communication.",
          cls=TextPresets.muted_sm, style="margin-top:-0.5rem;"),

        # ── Limits ──
        H4("Limits"),
        LabelInput(
            "Max files per commit",
            id="max_files_per_commit",
            type="number",
            value=str(prefs.get("max_files_per_commit", 10)),
            min="1",
            max="100",
        ),
        P("SafeClaw will block commits that touch more files than this limit. "
          "Large commits are harder to review and more likely to introduce issues. "
          "Set to 100 to effectively disable this check.",
          cls=TextPresets.muted_sm),

        # ── LLM Integration ──
        H4("LLM Integration"),
        P("SafeClaw can use Mistral AI to enhance its governance capabilities. "
          "Without a key, SafeClaw still works using rule-based classification — "
          "but adding a key unlocks smarter analysis.",
          cls=TextPresets.muted_sm),
        Ul(
            Li(Strong("Smart classification"), " — understands what a tool call "
               "actually does, even for tools SafeClaw hasn't seen before"),
            Li(Strong("Security review"), " — scans parameters for hidden risks "
               "like command injection or sensitive data exposure"),
            Li(Strong("Plain-English explanations"), " — tells you why an action "
               "was blocked in clear language"),
            cls="uk-list uk-list-disc",
            style="font-size:0.9em; color:var(--muted-foreground, #888);",
        ),
        LabelInput(
            "Mistral API Key",
            id="mistral_api_key",
            type="password",
            value=mistral_api_key,
            placeholder="Enter your Mistral API key",
        ),
        P("Get a free key at ",
          A("console.mistral.ai", href="https://console.mistral.ai", target="_blank"),
          ". Your key is stored in our database and used only for your "
          "governance requests. Clear this field and save to remove it.",
          cls=TextPresets.muted_sm),

        Button("Save Preferences", cls=ButtonT.primary, type="submit"),
        hx_post="/dashboard/prefs/save",
        hx_target="#prefs-status",
        hx_swap="innerHTML",
        cls="space-y-4",
    )


def PrefsContent(prefs: dict | None = None, mistral_api_key: str = ""):
    """Full preferences page content."""
    return (
        Card(
            H3("Governance Preferences"),
            P(
                "These settings control how SafeClaw governs your AI agent's actions. "
                "They apply to all agents connected with your API keys. "
                "Changes take effect immediately — no restart needed.",
                cls=TextPresets.muted_sm,
            ),
            PrefsForm(prefs, mistral_api_key=mistral_api_key),
        ),
        Div(id="prefs-status"),
    )
