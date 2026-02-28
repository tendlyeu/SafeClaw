"""Dashboard settings page — API key management, LLM status, and config view."""

import os

from fasthtml.common import (
    Button,
    Div,
    Form,
    H2,
    Input,
    P,
    RedirectResponse,
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


def _mask_key(key: str) -> str:
    """Mask an API key, showing first 4 and last 4 chars."""
    if not key:
        return "Not set"
    if len(key) <= 8:
        return key[:2] + "..." + key[-2:]
    return key[:4] + "..." + key[-4:]


def register(rt, get_engine, csrf_field=None, verify_csrf=None):
    @rt("/settings")
    def settings(sess):
        engine = get_engine()
        config = engine.config

        # ── Flash message ────────────────────────────────────────
        flash_msg = sess.pop("settings_flash", None) if sess else None
        flash_el = Div(flash_msg, cls="flash flash-success") if flash_msg else ""

        # ── Mistral API Key panel ────────────────────────────────
        key_configured = bool(config.mistral_api_key)
        status_text = "Configured" if key_configured else "Not configured"
        status_cls = "text-green" if key_configured else "text-red"
        masked = _mask_key(config.mistral_api_key)

        csrf = csrf_field(sess) if csrf_field else ""

        api_key_panel = Div(
            H2("Mistral API Key"),
            Div(
                Div(
                    Span("Status: ", cls="text-muted"),
                    Span(status_text, cls=status_cls),
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
                        Input(
                            type="password",
                            name="api_key",
                            placeholder="Enter new API key",
                        ),
                        style="margin-bottom: 0.75rem;",
                    ),
                    Button("Update", type="submit", cls="btn btn-primary"),
                    method="post",
                    action="/settings/api-key",
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
                action="/settings/reload",
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
            ("run_reasoner_on_startup", config.run_reasoner_on_startup),
            ("mistral_model", config.mistral_model),
            ("mistral_model_large", config.mistral_model_large),
            ("mistral_timeout_ms", config.mistral_timeout_ms),
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

        return Page(
            "Settings",
            flash_el,
            api_key_panel,
            llm_panel,
            ontology_panel,
            config_panel,
            active="settings",
        )

    @rt("/settings/api-key", methods=["post"])
    def update_api_key(api_key: str, sess, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        engine.config.mistral_api_key = api_key
        os.environ["SAFECLAW_MISTRAL_API_KEY"] = api_key
        sess["settings_flash"] = (
            "API key updated (runtime). Restart the service to reinitialise LLM features."
        )
        return RedirectResponse("/settings", status_code=303)

    @rt("/settings/reload", methods=["post"])
    def reload_ontologies(sess, _csrf: str = ""):
        if verify_csrf and not verify_csrf(sess, _csrf):
            return Response("CSRF token invalid", status_code=403)
        engine = get_engine()
        engine.reload()
        sess["settings_flash"] = "Ontologies reloaded successfully."
        return RedirectResponse("/settings", status_code=303)
