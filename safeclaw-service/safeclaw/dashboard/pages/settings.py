"""Dashboard settings page — API key management, LLM status, and config view."""

import json
import os
import re

import safeclaw.dashboard.components as _comp

from fasthtml.common import (
    Button,
    Div,
    Form,
    H2,
    H3,
    Input,
    Label,
    Option,
    P,
    RedirectResponse,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

from starlette.responses import Response

from safeclaw.dashboard.components import Page


def _write_config_safe(path, content: str) -> None:
    """Write a file with owner-only permissions (0o600).

    Uses ``os.open`` with explicit mode bits so the file is never
    world-readable, even momentarily.  This is important because config
    and preference files may contain API keys or other secrets.

    When overwriting an existing file, the mode parameter of ``os.open``
    is ignored (POSIX behavior), so we explicitly ``fchmod`` to ensure
    permissions are always tightened.
    """
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)


def _mask_key(key: str) -> str:
    """Mask an API key, showing first 4 and last 4 chars."""
    if not key:
        return "Not set"
    if len(key) <= 8:
        return key[:2] + "..." + key[-2:]
    return key[:4] + "..." + key[-4:]


def register(rt, get_engine, csrf_field=None, verify_csrf=None, get_csrf_token=None):
    @rt("/settings")
    def settings(sess):
        engine = get_engine()
        config = engine.config

        # ── Flash message ────────────────────────────────────────
        flash_msg = sess.pop("settings_flash", None) if sess else None
        flash_el = Div(flash_msg, cls="flash flash-success") if flash_msg else ""

        # ── LLM Provider panel ───────────────────────────────────
        from safeclaw.llm.providers import PROVIDERS

        current_provider = config.llm_provider or ("mistral" if config.mistral_api_key else "")
        current_key = config.llm_api_key or config.mistral_api_key
        key_configured = bool(current_key)
        status_text = "Configured" if key_configured else "Not configured"
        status_cls = "text-green" if key_configured else "text-red"
        masked = _mask_key(current_key)
        provider_name = PROVIDERS[current_provider].name if current_provider in PROVIDERS else "None"

        csrf = csrf_field(sess) if csrf_field else ""

        provider_options = [
            Option(
                info.name,
                value=pid,
                selected=(pid == current_provider),
            )
            for pid, info in PROVIDERS.items()
            if pid != "custom"
        ]
        provider_options.append(
            Option("Custom (OpenAI-compatible)", value="custom", selected=(current_provider == "custom"))
        )

        api_key_panel = Div(
            H2("LLM Provider"),
            Div(
                Div(
                    Span("Status: ", cls="text-muted"),
                    Span(status_text, cls=status_cls),
                    cls="mb-1",
                ),
                Div(
                    Span("Provider: ", cls="text-muted"),
                    Span(provider_name, cls="text-mono"),
                    cls="mb-1",
                ),
                Div(
                    Span("Current key: ", cls="text-muted"),
                    Span(masked, cls="text-mono"),
                    cls="mb-2",
                ),
                Form(
                    csrf,
                    Div(
                        Label("Provider", _for="provider"),
                        Select(
                            *provider_options,
                            name="provider",
                            id="provider",
                        ),
                        style="margin-bottom: 0.75rem;",
                    ),
                    Div(
                        Input(
                            type="password",
                            name="api_key",
                            placeholder="Enter new API key",
                        ),
                        style="margin-bottom: 0.75rem;",
                    ),
                    Button("Update", type="submit", cls="btn btn-primary"),
                    method="post",
                    action=f"{_comp.MOUNT_PREFIX}/settings/api-key",
                ),
                P(
                    "Changes take effect after service restart.",
                    cls="text-muted text-sm mt-1",
                ),
            ),
            cls="panel",
        )

        # ── LLM Features panel ───────────────────────────────────
        features = [
            ("Security Reviewer", engine.security_reviewer),
            ("Classification Observer", engine.classification_observer),
            ("Decision Explainer", engine.explainer),
            ("LLM Client", engine.llm_client),
        ]

        feature_rows = []
        for name, obj in features:
            if obj is not None:
                status_badge = Span("Active", cls="text-green")
            else:
                status_badge = Span("Inactive", cls="text-muted")
            feature_rows.append(Tr(Td(name), Td(status_badge)))

        llm_panel = Div(
            H2("LLM Features"),
            Table(
                Thead(Tr(Th("Feature"), Th("Status"))),
                Tbody(*feature_rows),
            ),
            cls="panel",
        )

        # ── Ontology Management panel ────────────────────────────
        triple_count = len(engine.kg)

        ontology_panel = Div(
            H2("Ontology Management"),
            Div(
                Span("Loaded triples: ", cls="text-muted"),
                Span(f"{triple_count:,}", cls="text-mono"),
                cls="mb-2",
            ),
            Form(
                csrf,
                Button("Reload Ontologies", type="submit", cls="btn btn-primary"),
                method="post",
                action=f"{_comp.MOUNT_PREFIX}/settings/reload",
            ),
            cls="panel",
        )

        # ── Current Configuration panel ──────────────────────────
        config_fields = [
            ("host", config.host),
            ("port", config.port),
            ("data_dir", str(config.data_dir)),
            ("ontology_dir", str(config.ontology_dir) if config.ontology_dir else "bundled"),
            ("audit_dir", str(config.audit_dir) if config.audit_dir else "default"),
            ("require_auth", config.require_auth),
            ("llm_provider", config.llm_provider or ("mistral (legacy)" if config.mistral_api_key else "none")),
            ("llm_model", config.llm_model or config.mistral_model),
            ("llm_timeout_ms", config.llm_timeout_ms if config.llm_provider else config.mistral_timeout_ms),
            ("llm_security_review_enabled", config.llm_security_review_enabled),
            ("llm_classification_observe", config.llm_classification_observe),
            ("log_level", config.log_level),
        ]

        config_items = []
        for key, value in config_fields:
            config_items.append(
                Div(
                    Div(key, cls="text-muted text-mono text-sm"),
                    Div(str(value), cls="text-mono"),
                )
            )

        config_panel = Div(
            H2("Current Configuration"),
            Div(*config_items, cls="config-grid"),
            cls="panel",
        )

        # ── User Preferences panel ─────────────────────────────────
        preferences_panel = Div(
            H2("User Preferences"),
            Div(
                id="preferences-content",
                hx_get=f"{_comp.MOUNT_PREFIX}/settings/preferences",
                hx_trigger="load",
                hx_swap="innerHTML",
            ),
            cls="panel",
        )

        token = get_csrf_token(sess) if get_csrf_token else ""
        return Page(
            "Settings",
            flash_el,
            api_key_panel,
            llm_panel,
            ontology_panel,
            preferences_panel,
            config_panel,
            active="settings",
            csrf_token=token,
        )

    @rt("/settings/api-key", methods=["post"])
    def update_api_key(api_key: str, provider: str = "", sess=None, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()

        if provider:
            engine.config.llm_provider = provider
            engine.config.llm_api_key = api_key
            os.environ["SAFECLAW_LLM_PROVIDER"] = provider
            os.environ["SAFECLAW_LLM_API_KEY"] = api_key
        else:
            engine.config.mistral_api_key = api_key
            os.environ["SAFECLAW_MISTRAL_API_KEY"] = api_key

        config_path = engine.config.data_dir / "config.json"
        try:
            cfg_data = json.loads(config_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            cfg_data = {}

        if provider:
            cfg_data["llm_provider"] = provider
            cfg_data["llm_api_key"] = api_key
        else:
            cfg_data["mistral_api_key"] = api_key

        config_path.parent.mkdir(parents=True, exist_ok=True)
        _write_config_safe(config_path, json.dumps(cfg_data, indent=2))

        sess["settings_flash"] = "LLM provider settings saved and applied."
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/settings", status_code=303)

    @rt("/settings/reload", methods=["post"])
    async def reload_ontologies(sess, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        await engine.reload()
        new_count = len(engine.kg)
        sess["settings_flash"] = f"Ontologies reloaded successfully — {new_count:,} triples loaded."
        return RedirectResponse(f"{_comp.MOUNT_PREFIX}/settings", status_code=303)

    # ── User Preferences routes ─────────────────────────────────

    @rt("/settings/preferences")
    def preferences_panel(sess):
        """Return the preference loader form (HTMX partial)."""
        return Div(
            H3("Load Preferences"),
            Form(
                Div(
                    Label("User ID", _for="pref_user_id"),
                    Input(
                        type="text",
                        name="user_id",
                        id="pref_user_id",
                        value="default",
                    ),
                    style="margin-bottom: 0.75rem;",
                ),
                Button(
                    "Load",
                    type="submit",
                    cls="btn btn-primary",
                ),
                hx_get=f"{_comp.MOUNT_PREFIX}/settings/preferences/load",
                hx_target="#pref-form-container",
                hx_swap="innerHTML",
                hx_include="[name='user_id']",
            ),
            Div(id="pref-form-container"),
        )

    @rt("/settings/preferences/load")
    def preferences_load(user_id: str, sess):
        """Return the preference editing form for a given user (HTMX partial)."""
        engine = get_engine()
        prefs = engine.preference_checker.get_preferences(user_id)
        csrf = csrf_field(sess) if csrf_field else ""

        return Form(
            csrf,
            Input(type="hidden", name="user_id", value=user_id),
            Div(
                Label("Autonomy Level", _for="autonomy_level"),
                Select(
                    Option(
                        "cautious",
                        value="cautious",
                        selected=(prefs.autonomy_level == "cautious"),
                    ),
                    Option(
                        "moderate",
                        value="moderate",
                        selected=(prefs.autonomy_level == "moderate"),
                    ),
                    Option(
                        "autonomous",
                        value="autonomous",
                        selected=(prefs.autonomy_level == "autonomous"),
                    ),
                    name="autonomy_level",
                    id="autonomy_level",
                ),
                style="margin-bottom: 0.75rem;",
            ),
            Div(
                Label(
                    Input(
                        type="checkbox",
                        name="confirm_before_delete",
                        checked=prefs.confirm_before_delete,
                    ),
                    " Confirm before delete",
                ),
                style="margin-bottom: 0.5rem;",
            ),
            Div(
                Label(
                    Input(
                        type="checkbox",
                        name="confirm_before_push",
                        checked=prefs.confirm_before_push,
                    ),
                    " Confirm before push",
                ),
                style="margin-bottom: 0.5rem;",
            ),
            Div(
                Label(
                    Input(
                        type="checkbox",
                        name="confirm_before_send",
                        checked=prefs.confirm_before_send,
                    ),
                    " Confirm before send",
                ),
                style="margin-bottom: 0.5rem;",
            ),
            Div(
                Label("Max files per commit", _for="max_files_per_commit"),
                Input(
                    type="number",
                    name="max_files_per_commit",
                    id="max_files_per_commit",
                    value=str(prefs.max_files_per_commit),
                    min="1",
                ),
                style="margin-bottom: 0.75rem;",
            ),
            Button("Save Preferences", type="submit", cls="btn btn-primary"),
            method="post",
            action=f"{_comp.MOUNT_PREFIX}/settings/preferences/save",
            hx_post=f"{_comp.MOUNT_PREFIX}/settings/preferences/save",
            hx_target="#pref-save-result",
            hx_swap="innerHTML",
        ), Div(id="pref-save-result", style="margin-top: 0.75rem;")

    @rt("/settings/preferences/save", methods=["post"])
    async def preferences_save(
        sess,
        user_id: str = "default",
        autonomy_level: str = "moderate",
        confirm_before_delete: str = "",
        confirm_before_push: str = "",
        confirm_before_send: str = "",
        max_files_per_commit: int = 10,
        _csrf: str = "",
    ):
        """Save user preferences — writes Turtle file and reloads ontologies."""
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)

        engine = get_engine()
        safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "", user_id)

        # Validate autonomy_level against allowlist to prevent Turtle injection
        VALID_AUTONOMY_LEVELS = {
            "autonomous",
            "moderate",
            "supervised",
            "conservative",
            "locked",
            "cautious",
        }
        if autonomy_level not in VALID_AUTONOMY_LEVELS:
            return Response("Invalid autonomy level", status_code=400)

        prefs_dict = {
            "autonomy_level": autonomy_level,
            "confirm_before_delete": confirm_before_delete == "on",
            "confirm_before_push": confirm_before_push == "on",
            "confirm_before_send": confirm_before_send == "on",
            "max_files_per_commit": int(max_files_per_commit),
        }

        # Write Turtle file for user preferences
        users_dir = engine.config.data_dir / "ontologies" / "users"
        users_dir.mkdir(parents=True, exist_ok=True)
        ttl_path = users_dir / f"user-{safe_user_id}.ttl"

        su = "http://safeclaw.uku.ai/ontology/user#"
        turtle = f"""@prefix su: <{su}> .

su:user-{safe_user_id} a su:User ;
    su:hasPreference su:pref-{safe_user_id} .

su:pref-{safe_user_id} a su:UserPreferences ;
    su:autonomyLevel "{prefs_dict["autonomy_level"]}" ;
    su:confirmBeforeDelete "{str(prefs_dict["confirm_before_delete"]).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:confirmBeforePush "{str(prefs_dict["confirm_before_push"]).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:confirmBeforeSend "{str(prefs_dict["confirm_before_send"]).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> ;
    su:maxFilesPerCommit "{prefs_dict["max_files_per_commit"]}"^^<http://www.w3.org/2001/XMLSchema#integer> .
"""
        _write_config_safe(ttl_path, turtle)

        # Reload ontologies so the new preferences take effect
        await engine.reload()

        return Div(
            f"Preferences saved for user '{safe_user_id}'.",
            cls="flash flash-success",
        )
