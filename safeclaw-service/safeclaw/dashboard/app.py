"""SafeClaw admin dashboard — FastHTML application factory."""

import os
import secrets

from fasthtml.common import (
    Beforeware,
    Button,
    Div,
    Form,
    H1,
    Hidden,
    Input,
    P,
    RedirectResponse,
    fast_app,
)
import safeclaw.dashboard.components as _components
from safeclaw.dashboard.components import DashboardCSS
from safeclaw.dashboard.pages import agents, audit, home, settings


def _derive_secret(admin_password: str) -> str:
    """Generate a random session secret key."""
    return os.urandom(32).hex()


def get_csrf_token(sess) -> str:
    """Get or create a CSRF token stored in the session."""
    if "csrf_token" not in sess:
        sess["csrf_token"] = secrets.token_hex(32)
    return sess["csrf_token"]


def csrf_field(sess) -> Hidden:
    """Return a hidden input with the CSRF token."""
    return Hidden(name="_csrf", value=get_csrf_token(sess))


def verify_csrf(sess, token: str) -> bool:
    """Verify a submitted CSRF token matches the session token."""
    expected = sess.get("csrf_token", "")
    return secrets.compare_digest(expected, token) if expected else False


def create_dashboard(get_engine_fn, mount_prefix: str = ""):
    """Create the FastHTML dashboard app.

    Args:
        get_engine_fn: callable that returns the current FullEngine instance.
        mount_prefix: URL prefix where this app is mounted (e.g. "/admin").

    Returns:
        A FastHTML app ready to be mounted at ``/admin``.
    """

    _engine = get_engine_fn

    def _get_config():
        try:
            eng = _engine()
            return eng.config
        except (RuntimeError, Exception):
            # Engine not yet initialized (startup) — fall back to env-based config
            from safeclaw.config import SafeClawConfig

            return SafeClawConfig()

    # Resolve mount prefix so redirects work when app is mounted at /admin
    _prefix = mount_prefix.rstrip("/")
    _components.MOUNT_PREFIX = _prefix

    def auth_before(req, sess):
        cfg = _get_config()
        # Dev mode: no password configured -> skip auth
        if not cfg.admin_password:
            return
        if not sess.get("admin_auth"):
            return RedirectResponse(f"{_prefix}/login", status_code=303)

    bware = Beforeware(
        auth_before,
        skip=[
            f"{_prefix}/login",
            f"{_prefix}/favicon.ico",
            f"{_prefix}/css.*",
            f"{_prefix}/js.*",
        ],
    )

    cfg = _get_config()
    secret = _derive_secret(cfg.admin_password)

    app, rt = fast_app(
        pico=False,
        before=bware,
        secret_key=secret,
        same_site="strict",
    )

    # Store engine accessor on app for external use
    app.get_engine = _engine

    # ── Auth routes ──────────────────────────────────────────────

    @rt("/login", methods=["get"])
    def login_page(req, error: str = ""):
        error_flash = (
            Div("Invalid password. Please try again.", cls="flash flash-error") if error else ""
        )
        return (
            DashboardCSS(),
            Div(
                Div(
                    H1("SafeClaw Admin"),
                    P("Enter the admin password to continue."),
                    error_flash,
                    Form(
                        Input(
                            type="password",
                            name="password",
                            placeholder="Admin password",
                            required=True,
                        ),
                        Button("Sign in", type="submit", cls="btn btn-primary"),
                        method="post",
                        action=f"{_prefix}/login",
                    ),
                    cls="login-card",
                ),
                cls="login-container",
            ),
        )

    @rt("/login", methods=["post"])
    def login_submit(password: str, sess):
        cfg = _get_config()
        if secrets.compare_digest(password, cfg.admin_password):
            sess["admin_auth"] = True
            return RedirectResponse(f"{_prefix}/", status_code=303)
        return RedirectResponse(f"{_prefix}/login?error=1", status_code=303)

    @rt("/logout")
    def logout(sess):
        sess.clear()
        return RedirectResponse(f"{_prefix}/login", status_code=303)

    # ── Register page modules ───────────────────────────────────

    home.register(rt, _engine)
    audit.register(rt, _engine)
    agents.register(rt, _engine, csrf_field, verify_csrf)
    settings.register(rt, _engine, csrf_field, verify_csrf)

    return app
