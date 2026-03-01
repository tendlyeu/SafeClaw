"""User preferences page — proxies to SafeClaw service API."""

from monsterui.all import *


def PrefsForm(prefs: dict | None = None):
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
        H4("Confirmation Rules"),
        LabelCheckboxX(
            "Confirm before deleting files",
            id="confirm_before_delete",
            checked=prefs.get("confirm_before_delete", True),
        ),
        LabelCheckboxX(
            "Confirm before pushing code",
            id="confirm_before_push",
            checked=prefs.get("confirm_before_push", True),
        ),
        LabelCheckboxX(
            "Confirm before sending messages",
            id="confirm_before_send",
            checked=prefs.get("confirm_before_send", True),
        ),
        H4("Limits"),
        LabelInput(
            "Max files per commit",
            id="max_files_per_commit",
            type="number",
            value=str(prefs.get("max_files_per_commit", 10)),
            min="1",
            max="100",
        ),
        Button("Save Preferences", cls=ButtonT.primary, type="submit"),
        hx_post="/dashboard/prefs/save",
        hx_target="#prefs-status",
        hx_swap="innerHTML",
        cls="space-y-4",
    )


def PrefsContent(prefs: dict | None = None):
    """Full preferences page content."""
    return (
        Card(
            H3("Governance Preferences"),
            P(
                "These settings control how strictly SafeClaw governs your agent's actions.",
                cls=TextPresets.muted_sm,
            ),
            PrefsForm(prefs),
        ),
        Div(id="prefs-status"),
    )
