"""Regression tests for CSRF token stability within sessions (#129).

The bug was that get_csrf_token() regenerated a new token on every call,
which broke CSRF validation for multi-form pages.  The fix added an
``if "csrf_token" not in sess`` guard so the token is created once per
session and reused on subsequent calls.
"""

from safeclaw.dashboard.app import get_csrf_token, verify_csrf


def test_csrf_token_stable_within_session():
    """Same session dict, two calls to get_csrf_token -> same token."""
    sess: dict = {}
    token_a = get_csrf_token(sess)
    token_b = get_csrf_token(sess)

    assert token_a == token_b, "CSRF token must not change within the same session"
    assert isinstance(token_a, str)
    assert len(token_a) == 64  # secrets.token_hex(32) produces 64 hex chars


def test_csrf_token_different_across_sessions():
    """Different session dicts must produce different tokens."""
    sess_1: dict = {}
    sess_2: dict = {}

    token_1 = get_csrf_token(sess_1)
    token_2 = get_csrf_token(sess_2)

    assert token_1 != token_2, "Independent sessions should get unique CSRF tokens"


def test_csrf_token_persists_in_session_dict():
    """get_csrf_token stores the token under the 'csrf_token' key."""
    sess: dict = {}
    token = get_csrf_token(sess)

    assert "csrf_token" in sess
    assert sess["csrf_token"] == token


def test_verify_csrf_accepts_matching_token():
    """verify_csrf returns True when the submitted token matches the session."""
    sess: dict = {}
    token = get_csrf_token(sess)

    assert verify_csrf(sess, token) is True


def test_verify_csrf_rejects_wrong_token():
    """verify_csrf returns False for a token that doesn't match."""
    sess: dict = {}
    get_csrf_token(sess)

    assert verify_csrf(sess, "wrong-token-value") is False


def test_verify_csrf_rejects_empty_session():
    """verify_csrf returns False when the session has no CSRF token at all."""
    sess: dict = {}

    assert verify_csrf(sess, "any-token") is False
