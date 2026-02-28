"""SafeClaw admin dashboard — FastHTML application factory."""

from fasthtml.common import (
    Beforeware,
    Button,
    Div,
    Form,
    H1,
    Input,
    P,
    RedirectResponse,
    fast_app,
)

from safeclaw.dashboard.components import DashboardCSS
from safeclaw.dashboard.pages import agents, audit, home, settings


def create_dashboard(get_engine_fn):
    """Create the FastHTML dashboard app.

    Args:
        get_engine_fn: callable that returns the current FullEngine instance.

    Returns:
        A FastHTML app ready to be mounted at ``/admin``.
    """

    _engine = get_engine_fn

    def _get_config():
        try:
            eng = _engine()
            return eng.config
        except Exception:
            from safeclaw.config import SafeClawConfig

            return SafeClawConfig()

    def auth_before(req, sess):
        cfg = _get_config()
        # Dev mode: no password configured -> skip auth
        if not cfg.admin_password:
            return
        if not sess.get("admin_auth"):
            return RedirectResponse("/login", status_code=303)

    bware = Beforeware(
        auth_before,
        skip=["/login", "/favicon.ico", "/css", "/js"],
    )

    app, rt = fast_app(
        pico=False,
        before=bware,
        secret_key="safeclaw-admin-session-key",
    )

    # Store engine accessor on app for external use
    app.get_engine = _engine

    # ── Auth routes ──────────────────────────────────────────────

    @rt("/login", methods=["get"])
    def login_page(req, error: str = ""):
        error_flash = (
            Div("Invalid password. Please try again.", cls="flash flash-error")
            if error
            else ""
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
                        action="/login",
                    ),
                    cls="login-card",
                ),
                cls="login-container",
            ),
        )

    @rt("/login", methods=["post"])
    def login_submit(password: str, sess):
        cfg = _get_config()
        if password == cfg.admin_password:
            sess["admin_auth"] = True
            return RedirectResponse("/", status_code=303)
        return RedirectResponse("/login?error=1", status_code=303)

    @rt("/logout")
    def logout(sess):
        sess.clear()
        return RedirectResponse("/login", status_code=303)

    # ── Register page modules ───────────────────────────────────

    home.register(rt, _engine)
    audit.register(rt, _engine)
    agents.register(rt, _engine)
    settings.register(rt, _engine)

    return app
