"""API key management page."""

import hashlib
import secrets
from datetime import datetime, timezone

from fasthtml.common import *
from monsterui.all import *

from db import api_keys


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key. Returns (raw_key, key_id)."""
    raw_key = "sc_" + secrets.token_urlsafe(32)
    key_id = raw_key[:12]
    return raw_key, key_id


def hash_key(raw_key: str) -> str:
    """SHA256 hash of the raw key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def KeyTable(user_id: int):
    """Table of existing API keys for this user."""
    keys = api_keys(where="user_id = ?", where_args=[user_id], order_by="-id")
    if not keys:
        return P("No API keys yet. Create one to get started.", cls=TextPresets.muted_sm)

    rows = []
    for k in keys:
        status = Label("Active", cls=LabelT.primary) if k.is_active else Label("Revoked", cls=LabelT.destructive)
        revoke_btn = (
            Button("Revoke", cls=ButtonT.destructive + " " + ButtonT.xs,
                   hx_post=f"/dashboard/keys/{k.id}/revoke",
                   hx_target="#key-list", hx_swap="innerHTML",
                   hx_confirm="Revoke this key? This cannot be undone.")
            if k.is_active else Span("—", cls=TextPresets.muted_sm)
        )
        rows.append(Tr(
            Td(k.label),
            Td(Code(k.key_id + "…")),
            Td(k.scope),
            Td(k.created_at[:10]),
            Td(status),
            Td(revoke_btn),
        ))

    return Table(
        Thead(Tr(Th("Label"), Th("Key ID"), Th("Scope"), Th("Created"), Th("Status"), Th(""))),
        Tbody(*rows),
        cls=(TableT.divider, TableT.hover, TableT.sm),
    )


def CreateKeyForm():
    """Form to create a new API key."""
    return Card(
        H3("Create New Key"),
        Form(
            LabelInput("Label", id="label", placeholder="e.g. My dev key", required=True),
            LabelSelect(
                Option("Full access", value="full"),
                Option("Evaluate only", value="evaluate_only"),
                label="Scope", id="scope",
            ),
            Button("Create Key", cls=ButtonT.primary, type="submit"),
            hx_post="/dashboard/keys/create",
            hx_target="#key-list",
            hx_swap="innerHTML",
            cls="space-y-4",
        ),
    )


def NewKeyModal(raw_key: str):
    """Alert showing the raw key once (not a browser dialog -- an inline card)."""
    return Card(
        H3("Key Created"),
        P("Copy this key now — it won't be shown again:", cls=TextPresets.muted_sm),
        Div(
            Pre(Code(raw_key), style="word-break:break-all;"),
            cls="space-y-2",
        ),
        P("Store it securely. Use it as your SAFECLAW_API_KEY.", cls=TextPresets.muted_sm),
        id="new-key-alert",
        cls="uk-alert-success",
    )


def KeysContent(user_id: int):
    """Full keys page content."""
    return (
        Div(id="new-key-alert"),
        CreateKeyForm(),
        Card(
            H3("Your API Keys"),
            Div(KeyTable(user_id), id="key-list"),
        ),
    )
