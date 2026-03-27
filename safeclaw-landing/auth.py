"""GitHub OAuth authentication for safeclaw-landing."""

import hmac
import os

from fasthtml.common import *
from fasthtml.oauth import GitHubAppClient

from db import users

# GitHub OAuth config — set these env vars
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Only create client if credentials are configured
github_client = (
    GitHubAppClient(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)
    if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET
    else None
)


def _get_env_admins() -> set[str]:
    """Parse SAFECLAW_ADMINS env var into a set of GitHub logins."""
    raw = os.environ.get("SAFECLAW_ADMINS", "")
    return {a.strip() for a in raw.split(",") if a.strip()}


def is_env_admin(user) -> bool:
    """Check if user is an admin via the SAFECLAW_ADMINS env var."""
    return user.github_login in _get_env_admins()


def is_user_admin(user) -> bool:
    """Check if user is an admin (env var or DB field)."""
    return bool(user.is_admin) or is_env_admin(user)


def require_admin(user):
    """Return a 403 Response if user is not an admin, else None."""
    if not is_user_admin(user):
        return Response("Admin access required.", status_code=403)
    return None


def sync_admin_on_login(user) -> None:
    """Sync env var admin status to DB on login. Apply first-user fallback."""
    changed = False
    # Env var admins always get is_admin=True in DB
    if is_env_admin(user) and not user.is_admin:
        user.is_admin = True
        changed = True
    # First-user fallback: if no admins exist, first user becomes admin
    if not user.is_admin:
        env_admins = _get_env_admins()
        if not env_admins:
            existing_admins = users(where="is_admin = 1")
            if not existing_admins:
                user.is_admin = True
                changed = True
    if changed:
        users.update(user)


def get_current_user(sess):
    """Get the currently logged-in user from session, or None."""
    user_id = sess.get("auth")
    if not user_id:
        return None
    try:
        return users[user_id]
    except Exception:
        return None


async def user_auth_before(req, sess):
    """Beforeware: protect /dashboard/* routes and verify CSRF on POST (#39)."""
    path = req.url.path
    if not path.startswith("/dashboard"):
        return  # Public routes — allow
    user = get_current_user(sess)
    if not user:
        return RedirectResponse("/login", status_code=303)

    # Disabled users cannot access the dashboard
    if user.is_disabled:
        from monsterui.all import Theme as MUITheme
        return (
            Title("Account Disabled — SafeClaw"),
            *MUITheme.blue.headers(mode='dark'),
            Div(
                Div(
                    H2("Account Disabled"),
                    P("Your account has been disabled by an administrator. "
                      "Contact your team admin to regain access."),
                    A("Back to home", href="/"),
                    cls="space-y-4",
                    style="max-width:400px; margin:100px auto; text-align:center; color:#e5e5e5;",
                ),
                style="background:#0a0a0a; min-height:100vh;",
            ),
        )

    req.scope["user"] = user

    # CSRF verification for all dashboard POST requests (#39)
    if req.method == "POST":
        form = await req.form()
        token = form.get("_csrf_token", "")
        expected = sess.get("_csrf_token", "")
        if not expected or not token or not hmac.compare_digest(expected, token):
            return Response("CSRF token missing or invalid.", status_code=403)
