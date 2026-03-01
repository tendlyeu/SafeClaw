"""GitHub OAuth authentication for safeclaw-landing."""

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


def get_current_user(sess):
    """Get the currently logged-in user from session, or None."""
    user_id = sess.get("auth")
    if not user_id:
        return None
    try:
        return users[user_id]
    except Exception:
        return None


def user_auth_before(req, sess):
    """Beforeware: protect /dashboard/* routes."""
    path = req.url.path
    if not path.startswith("/dashboard"):
        return  # Public routes — allow
    user = get_current_user(sess)
    if not user:
        return RedirectResponse("/login", status_code=303)
    req.scope["user"] = user
