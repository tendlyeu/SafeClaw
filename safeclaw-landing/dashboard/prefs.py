"""User preferences page."""

import json

from fasthtml.common import *
from monsterui.all import *


def _get_providers():
    from safeclaw.llm.providers import PROVIDERS
    return PROVIDERS


def _field_group(*children):
    """Wrap a form field and its helper text together."""
    return Div(*children, cls="space-y-1")


def _parse_llm_config(raw: str) -> dict:
    """Parse the llm_config JSON string, returning a safe default."""
    if not raw:
        return {"active_provider": "", "keys": {}}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"active_provider": "", "keys": {}}
        return data
    except (json.JSONDecodeError, TypeError):
        return {"active_provider": "", "keys": {}}


def _mask_key(key: str) -> str:
    if not key or len(key) < 5:
        return ""
    return "\u2022\u2022\u2022\u2022" + key[-4:]


def _provider_card(pid, info, llm_config, is_active):
    """Render a single provider card."""
    keys = llm_config.get("keys", {})
    has_key = bool(keys.get(pid, ""))
    masked = _mask_key(keys.get(pid, ""))

    badges = []
    if info.free_tier and info.free_tier != "No":
        color = "#065f46" if "free" in info.free_tier.lower() or info.free_tier == "Yes" else "#422006"
        text_color = "#6ee7b7" if color == "#065f46" else "#fbbf24"
        badges.append(
            Span(info.free_tier, style=f"font-size:0.7rem; background:{color}; color:{text_color}; padding:1px 6px; border-radius:8px;")
        )
    if has_key:
        badges.append(
            Span("\u2713 Key saved", style="font-size:0.7rem; color:#4ade80;")
        )

    border = "2px solid #4ade80" if is_active else "1px solid #333"
    active_badge = Span("Active", style="font-size:0.65rem; background:#4ade80; color:#000; padding:2px 8px; border-radius:12px; font-weight:600;") if is_active else ""
    button_text = "Using this" if is_active else "Use this"
    button_cls = ButtonT.primary if is_active else ButtonT.default

    return Div(
        DivLAligned(
            H4(info.name, style="margin:0;"),
            active_badge,
            style="justify-content:space-between; width:100%;",
        ),
        Div(*badges, style="display:flex; gap:0.4rem; margin:0.4rem 0;") if badges else "",
        Input(
            type="password",
            name=f"llm_key_{pid}",
            value=masked,
            placeholder=info.key_placeholder,
            style="width:100%; font-size:0.85rem;",
        ),
        DivLAligned(
            A(info.console_url.replace("https://", ""), href=info.console_url, target="_blank",
              style="font-size:0.75rem;") if info.console_url else "",
            Button(
                button_text,
                cls=button_cls,
                type="button",
                hx_post="/dashboard/prefs/set-llm-provider",
                hx_vals=json.dumps({"provider": pid}),
                hx_target="#llm-cards",
                hx_swap="outerHTML",
                style="font-size:0.75rem; padding:2px 10px;",
            ),
            style="justify-content:space-between; width:100%; margin-top:0.4rem;",
        ),
        style=f"border:{border}; border-radius:8px; padding:0.85rem; background:var(--card, #16213e);",
    )


def _custom_card(llm_config, is_active):
    """Render the Custom provider card (full width)."""
    border = "2px solid #4ade80" if is_active else "1px dashed #555"
    active_badge = Span("Active", style="font-size:0.65rem; background:#4ade80; color:#000; padding:2px 8px; border-radius:12px; font-weight:600;") if is_active else ""
    button_text = "Using this" if is_active else "Use this"
    button_cls = ButtonT.primary if is_active else ButtonT.default

    return Div(
        DivLAligned(
            H4("Custom (OpenAI-compatible)", style="margin:0;"),
            active_badge,
            style="justify-content:space-between; width:100%;",
        ),
        P("For Ollama, LM Studio, vLLM, or any OpenAI-compatible endpoint",
          cls=TextPresets.muted_sm),
        Grid(
            _field_group(
                LabelInput("Base URL", id="custom_base_url", value=llm_config.get("custom_base_url", ""),
                           placeholder="http://localhost:11434/v1"),
            ),
            _field_group(
                LabelInput("API Key (if needed)", id="custom_api_key", type="password",
                           value=_mask_key(llm_config.get("keys", {}).get("custom", "")),
                           placeholder="Optional"),
            ),
            cols=2,
        ),
        _field_group(
            LabelInput("Model name", id="custom_model", value=llm_config.get("custom_model", ""),
                       placeholder="e.g. llama3"),
        ),
        DivLAligned(
            Button(
                button_text,
                cls=button_cls,
                type="button",
                hx_post="/dashboard/prefs/set-llm-provider",
                hx_vals=json.dumps({"provider": "custom"}),
                hx_target="#llm-cards",
                hx_swap="outerHTML",
                style="font-size:0.75rem; padding:2px 10px;",
            ),
            style="justify-content:flex-end; width:100%; margin-top:0.4rem;",
        ),
        style=f"border:{border}; border-radius:8px; padding:0.85rem; background:var(--card, #111827); grid-column:1/-1;",
    )


def _llm_cards_section(llm_config):
    """Render all provider cards in a grid."""
    providers = _get_providers()
    active = llm_config.get("active_provider", "")

    cards = []
    for pid, info in providers.items():
        if pid == "custom":
            continue
        cards.append(_provider_card(pid, info, llm_config, is_active=(pid == active)))
    cards.append(_custom_card(llm_config, is_active=(active == "custom")))

    return Div(
        Grid(*cards, cols=2, cls="gap-3"),
        id="llm-cards",
    )


def PrefsForm(prefs: dict | None = None, llm_config: dict | None = None,
              mistral_api_key: str = "", csrf_token=""):
    """Preference editing form."""
    if prefs is None:
        prefs = {
            "autonomy_level": "moderate",
            "confirm_before_delete": True,
            "confirm_before_push": True,
            "confirm_before_send": True,
            "max_files_per_commit": 10,
            "self_hosted": False,
            "service_url": "",
            "admin_password": "",
            "audit_logging": True,
        }

    if llm_config is None:
        llm_config = {"active_provider": "", "keys": {}}
    if not llm_config.get("active_provider") and mistral_api_key:
        llm_config = {
            "active_provider": "mistral",
            "keys": {"mistral": mistral_api_key},
        }

    self_hosted = prefs.get("self_hosted", False)

    return Form(
        Input(type="hidden", name="_csrf_token", value=csrf_token),
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

        # ── Audit Logging ──
        Div(
            H4("Audit Logging"),
            P("When enabled, SafeClaw logs every governance decision "
              "(allowed and blocked) to your dashboard for review.",
              cls=TextPresets.muted_sm),
            cls="space-y-1",
        ),

        _field_group(
            LabelCheckboxX(
                "Log governance decisions to dashboard",
                id="audit_logging",
                checked=prefs.get("audit_logging", True),
            ),
            P("Disable to stop recording decisions. Existing logs are preserved.",
              cls=TextPresets.muted_sm, style="padding-left:1.75rem;"),
        ),

        Divider(),

        # ── AI Integration ──
        Div(
            H4("AI Integration"),
            Div(
                P(Strong("How SafeClaw uses AI"), style="margin-bottom:0.25rem;"),
                P("SafeClaw can use an AI model to enhance governance \u2014 classifying unfamiliar tools, "
                  "reviewing parameters for hidden security risks, and explaining blocked actions in "
                  "plain English. Without a key, SafeClaw still works using rule-based classification. "
                  "AI features are optional and passive \u2014 the AI never makes governance decisions, it only advises.",
                  cls=TextPresets.muted_sm),
                P("API keys are separate from consumer subscriptions (ChatGPT Plus, Google One, etc.). "
                  "Several providers offer free tiers that work well for SafeClaw's lightweight usage.",
                  style="font-size:0.75rem; color:var(--muted-foreground, #64748b); margin-top:0.5rem;"),
                style="background:var(--muted, #1e293b); border:1px solid var(--border, #334155); border-radius:8px; padding:1rem; margin-bottom:1rem;",
            ),
            Ul(
                Li(Strong("Smart classification"), " \u2014 understands unfamiliar tools"),
                Li(Strong("Security review"), " \u2014 detects hidden risks in parameters"),
                Li(Strong("Plain-English explanations"), " \u2014 clear block reasons"),
                cls="uk-list uk-list-disc",
                style="font-size:0.875rem; color:var(--muted-foreground, #888); margin-top:0.5rem;",
            ),
            cls="space-y-1",
        ),

        _llm_cards_section(llm_config),

        Divider(),

        # ── Deployment Mode ──
        Div(
            H4("Deployment Mode"),
            P("By default, SafeClaw uses the hosted service at ",
              Code("api.safeclaw.eu"),
              ". Enable self-hosted mode if you run your own SafeClaw engine.",
              cls=TextPresets.muted_sm),
            cls="space-y-1",
        ),

        _field_group(
            LabelCheckboxX(
                "I run my own SafeClaw service (self-hosted)",
                id="self_hosted",
                checked=self_hosted,
            ),
        ),

        Div(
            Divider(),
            _field_group(
                LabelInput(
                    "Service URL",
                    id="service_url",
                    value=prefs.get("service_url", ""),
                    placeholder="http://localhost:8420",
                ),
                P("The URL of your self-hosted SafeClaw service.",
                  cls=TextPresets.muted_sm),
            ),
            _field_group(
                LabelInput(
                    "Admin Password",
                    id="admin_password",
                    type="password",
                    value="",
                    placeholder="Enter new password or leave empty",
                ),
                P("Required if you set ", Code("SAFECLAW_ADMIN_PASSWORD"),
                  " on your service. Leave empty to keep current password.",
                  cls=TextPresets.muted_sm),
            ),
            id="self-hosted-fields",
            cls="space-y-6",
            style="" if self_hosted else "display:none;",
        ),

        Script("""
            document.getElementById('self_hosted').addEventListener('change', function() {
                document.getElementById('self-hosted-fields').style.display =
                    this.checked ? '' : 'none';
            });
        """),

        Divider(),

        Button("Save Preferences", cls=ButtonT.primary, type="submit"),
        hx_post="/dashboard/prefs/save",
        hx_target="#prefs-status",
        hx_swap="innerHTML",
        cls="space-y-6",
    )


def PrefsContent(prefs: dict | None = None, llm_config: dict | None = None,
                 mistral_api_key: str = "", csrf_token=""):
    """Full preferences page content."""
    return (
        Card(
            H3("Governance Preferences"),
            P(
                "These settings control how SafeClaw governs your AI agent's actions. "
                "Changes take effect immediately.",
                cls=TextPresets.muted_sm,
            ),
            PrefsForm(prefs, llm_config=llm_config, mistral_api_key=mistral_api_key,
                      csrf_token=csrf_token),
        ),
        Div(id="prefs-status"),
    )
