# SaaS User Flow Design

**Date**: 2026-03-01

## Overview

Design the end-to-end SaaS user flow for SafeClaw: account creation via GitHub OAuth, onboarding wizard, API key generation, and plugin connection.

## User Flow

1. User visits safeclaw.eu → clicks "Get Started" → GitHub OAuth login
2. GitHub callback → account created/updated in shared SQLite → first-time users redirect to onboarding wizard
3. Wizard Step 1: Choose autonomy level (cautious / moderate / autonomous)
4. Wizard Step 2: API key auto-generated, shown with copy button + pre-filled install commands
5. User installs plugin → plugin defaults to `https://api.safeclaw.eu/api/v1` → uses API key → governance active
6. Dashboard → user manages keys, preferences, views audit

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | Shared SQLite | Landing site + service read from same DB. Migrate to Postgres later when scale demands it. |
| Deployment | Single process | FastAPI service mounted inside FastHTML app. One container, one port, shared SQLite. |
| Onboarding | Guided wizard | Two-step wizard after first GitHub login. Best first experience. |
| Wizard scope | Autonomy level only | General policy template as default. Keep wizard fast. |
| Multi-tenancy | Shared ontologies + DB prefs | All users share base ontologies. Per-user differences stored in SQLite. |
| Auth | GitHub OAuth | Extensible to Google and others later. |

## Database Schema Changes

### Users table — new columns

- `onboarded: bool` (default `False`) — tracks whether user completed the wizard
- `autonomy_level: str` (default `"moderate"`) — user's chosen autonomy level

### API keys table

No changes needed. Existing schema: `user_id`, `key_id`, `key_hash`, `label`, `scope`, `created_at`, `is_active`.

The SafeClaw service reads keys from this table instead of its in-memory dict.

## Single-Process Deployment

The FastHTML app mounts the FastAPI service at `/api/v1`:

- `safeclaw.eu/` → landing page (FastHTML)
- `safeclaw.eu/dashboard/*` → user dashboard (FastHTML)
- `safeclaw.eu/api/v1/*` → SafeClaw service API (FastAPI, mounted)

Both share the same process and SQLite file. The plugin's default URL (`https://api.safeclaw.eu/api/v1`) points to the same host.

Self-hosted users continue using `safeclaw serve` on port 8420 — no change to the self-hosted path.

## Onboarding Wizard

**Route**: `/dashboard/onboard`

**Trigger**: After GitHub OAuth callback, if `user.onboarded is False`, redirect to `/dashboard/onboard`.

### Step 1 — Choose Autonomy Level

- Three cards: Cautious / Moderate (pre-selected) / Autonomous
- Each with a short description
- "Next" button saves the choice to `users.autonomy_level`

### Step 2 — Your API Key

- Auto-generates a key with label "Default" and scope "full"
- Shows the raw key in a prominent box with copy button
- Below it, pre-filled install commands:
  ```
  openclaw plugins install openclaw-safeclaw-plugin
  export SAFECLAW_API_KEY=sc_abc123...
  ```
- Warning: "This key is shown only once. Copy it now."
- "Done" button sets `user.onboarded = True`, redirects to `/dashboard`

### Returning users

If `user.onboarded is True`, OAuth callback redirects straight to `/dashboard`.

## Files Changed

| File | Change |
|------|--------|
| `safeclaw-landing/db.py` | Add `onboarded` and `autonomy_level` columns to User model |
| `safeclaw-landing/dashboard/onboard.py` | **New** — wizard page with 2 steps (HTMX-driven) |
| `safeclaw-landing/dashboard/layout.py` | Conditionally show onboarding state in nav |
| `safeclaw-landing/main.py` | Mount FastAPI app at `/api/v1`, update auth callback for first-time vs returning users, add onboard routes |
| `safeclaw-landing/auth.py` | Update redirect logic in `auth_callback` |
| `safeclaw-service/safeclaw/auth/api_key.py` | Add `SQLiteAPIKeyManager` that reads from shared SQLite |
| `safeclaw-service/safeclaw/auth/middleware.py` | Use `SQLiteAPIKeyManager` when DB path is configured |
| `safeclaw-landing/main.py` (QuickStart) | Update SaaS instructions to mention API key step |
| `safeclaw-landing/main.py` (docs) | Update /docs to describe SaaS signup + onboarding flow |
