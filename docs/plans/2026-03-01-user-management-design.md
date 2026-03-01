# User Management & Dashboard Design

## Goal

Add GitHub OAuth login and a user-facing dashboard to the safeclaw-landing app, enabling users to manage API keys, view registered agents, and edit governance preferences. Works for both SaaS (safeclaw.eu) and self-hosted deployments.

## Architecture

The `safeclaw-landing` FastHTML app is extended with authentication, a SQLite database, and dashboard routes. It acts as a client of the SafeClaw service API — never accessing the engine directly.

```
Browser → safeclaw-landing (FastHTML + MonsterUI)
  ├── Public routes: /, /docs (no auth)
  ├── Auth routes: /login/github, /auth/callback, /logout
  └── Dashboard routes (auth required):
      ├── /dashboard         → overview + service health
      ├── /dashboard/keys    → API key management
      ├── /dashboard/agents  → agent list + kill switches
      └── /dashboard/prefs   → preference editing

Dashboard → safeclaw-service API (api.safeclaw.eu/api/v1)
  └── Uses user's API key to proxy requests
```

## Database Schema

SQLite via fastlite at `safeclaw-landing/data/safeclaw.db`.

### User

| Field        | Type         | Notes                |
|-------------|-------------|----------------------|
| id          | int (pk)    | Auto-increment       |
| github_id   | int         | Unique, from GitHub  |
| github_login| str         | GitHub username       |
| name        | str         | Display name          |
| avatar_url  | str         | GitHub avatar         |
| email       | str | None  | Optional              |
| created_at  | str         | ISO timestamp         |
| last_login  | str         | ISO timestamp         |

### APIKey

| Field      | Type         | Notes                     |
|-----------|-------------|---------------------------|
| id        | int (pk)    | Auto-increment            |
| user_id   | int         | FK → User                 |
| key_id    | str         | Unique, first 12 chars    |
| key_hash  | str         | SHA256 of full key        |
| label     | str         | User-given name           |
| scope     | str         | "full" or "evaluate_only" |
| created_at| str         | ISO timestamp             |
| is_active | bool        | Revocable                 |

Agents, preferences, and audit logs are NOT stored locally — they're queried live from the service API.

## Authentication

GitHub OAuth via FastHTML's built-in `GitHubAppClient`.

1. User clicks "Sign In with GitHub" in nav
2. Redirect to GitHub OAuth authorize URL
3. GitHub redirects to `/auth/callback` with code
4. Exchange code for token, fetch user info (id, login, name, avatar)
5. Upsert user in SQLite
6. Store `user_id` in signed session cookie
7. Redirect to `/dashboard`

Beforeware `user_auth_before` protects `/dashboard/*` routes, skips public routes.

Environment variables: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`.

## Dashboard Pages

All pages use MonsterUI blue theme. Shared layout: sidebar nav + content area.

### /dashboard — Overview

- Service health card (polls `/health`)
- Quick stats: API key count, active agents
- Getting Started card for new users

### /dashboard/keys — API Key Management

- Table: label, key_id (masked), scope, created date, status
- Create Key: form with label + scope → shows raw key once (modal with copy)
- Revoke button per key

### /dashboard/agents — Agent Management

- Agent list from service API (`GET /api/v1/agents`)
- Per agent: ID, role, status, last heartbeat
- Kill/Revive toggle (calls service API)
- Requires service URL + admin password in session

### /dashboard/prefs — Preferences

- Form with current preference values from service API
- Dropdowns for enums, checkboxes for booleans, text inputs for strings
- Save POSTs to service API

## Service Integration

The dashboard proxies to the SafeClaw service API. Service URL is configurable (defaults to `https://api.safeclaw.eu/api/v1`).

- **Keys:** Fully local (SQLite), no service call
- **Agents:** Proxied to service, requires admin password
- **Prefs:** Proxied to service via new endpoints

### New service endpoint

```
GET  /api/v1/preferences/{user_id}  → current prefs as JSON
POST /api/v1/preferences/{user_id}  → update prefs
```

Thin wrapper around existing `PreferenceChecker` / Turtle file I/O.

## Self-Host Mode

Same app, different service URL (`localhost:8420` instead of `api.safeclaw.eu`). No code changes.

## Separation from TUI

The web dashboard manages **service-side** settings (autonomy, confirmation rules, governance preferences). The TUI manages **plugin-local** settings (enforcement mode, fail mode, service URL). These are different concerns and stay separate.

## File Structure

### safeclaw-landing/ (new/modified)

```
main.py              -- modify: OAuth, Beforeware, MonsterUI headers
requirements.txt     -- modify: add monsterui, httpx
auth.py              -- new: GitHub OAuth flow
db.py                -- new: database setup
dashboard/
  __init__.py
  layout.py          -- new: shared sidebar layout
  overview.py        -- new: /dashboard
  keys.py            -- new: /dashboard/keys
  agents.py          -- new: /dashboard/agents
  prefs.py           -- new: /dashboard/prefs
data/
  safeclaw.db        -- created at runtime
```

### safeclaw-service/ (modified)

```
safeclaw/api/routes.py  -- add GET/POST /preferences/{user_id}
```

## Dependencies

Added to `safeclaw-landing/requirements.txt`:
- `monsterui` — dashboard UI components
- `httpx` — async HTTP client for service proxy
