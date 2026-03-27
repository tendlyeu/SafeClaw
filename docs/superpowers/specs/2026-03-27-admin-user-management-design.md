# Admin User Management — Design Spec

**Date:** 2026-03-27
**Status:** Approved

## Overview

Add multi-user admin capabilities to the SafeClaw landing dashboard. Admins can view, manage, and configure other users. Non-admin users see no changes to their experience.

## Requirements

### Admin Determination

Three sources determine admin status, checked in this order:

1. **`SAFECLAW_ADMINS` env var** — comma-separated GitHub logins (e.g., `henrikaavik,marekkask`). These users are always admin. On login, `is_admin` is synced to `True`. Cannot be demoted via UI. Displayed with an "env" badge in the user list.

2. **`is_admin` database field** — any admin can promote/demote other users via the UI. UI-promoted admins can be demoted by any other admin.

3. **First-user fallback** — if no env var admins are configured and no users with `is_admin=True` exist in the database, the first user to register (lowest `id`) is automatically promoted to admin. This ensures there is always at least one admin without requiring env var configuration.

### User States

Each user has two boolean flags:

- **`is_admin`** — grants access to user management features
- **`is_disabled`** — blocks login and API key usage, preserves all data

State rules:
- An admin cannot disable or demote themselves (UI hides the buttons, server rejects the request)
- An env var admin cannot be demoted via UI (server rejects the request)
- Disabling a user automatically revokes all their active API keys (sets `is_active=False`)
- A disabled user who tries to log in sees a "Your account has been disabled" page
- Re-enabling a user restores login access but does not restore revoked keys — new keys must be created

### Dashboard Pages

#### Users Page (`/dashboard/users`) — admin only

- **Stats bar**: total users, admin count, disabled count
- **User table** with columns: User (avatar + name + GitHub login), Role (Admin/User badges, "env" badge for env var admins), Status (Active/Disabled), Last Login, Keys (count), Actions
- **Actions per row**:
  - "View →" — navigates to user detail page
  - "Promote" / "Demote" — toggles admin status (hidden for env var admins, hidden for self)
  - "Disable" / "Enable" — toggles disabled status (hidden for self)
- Disabled users shown with reduced opacity

#### User Detail Page (`/dashboard/users/{id}`) — admin only

- **Breadcrumb**: "← All Users" link back to user list
- **Header card**: avatar, name, GitHub login, join date, last login, action buttons (Promote/Demote, Disable/Enable)
- **Quick stats**: API key count, decisions in last 30 days, blocks in last 30 days
- **Tabbed sub-views** (HTMX-loaded):
  - **Preferences tab**: editable form showing the user's governance preferences (autonomy level, confirmation rules, limits, deployment mode, audit logging). Admin can save changes on behalf of the user.
  - **API Keys tab**: the user's key table with revoke buttons. Admin can revoke keys but not create new ones (keys are user-owned secrets).
  - **Audit Log tab**: the user's audit entries with the standard filter controls (decision filter, session ID).

#### Audit Log Enhancement (`/dashboard/audit`)

- **Non-admins**: no changes — see their own audit data as before
- **Admins**: an additional "User" filter dropdown appears in the filter bar, visually separated with a divider and "Admin" label. Options: "All users" (default), or individual usernames. When "All users" is selected, a "User" column is added to the audit table.

### Sidebar Navigation

- Non-admins: unchanged — Overview, API Keys, Agents, Audit Log, Preferences
- Admins: "Users" nav item inserted between "Audit Log" and "Preferences"

## Data Model Changes

### User table — new columns

```python
is_admin: bool = False
is_disabled: bool = False
```

Added via fastlite's `transform=True` (auto-migration).

### No new tables

All admin state lives on the existing User model. No separate roles table needed.

## Routes

### New routes (all admin-only)

| Route | Method | Description |
|-------|--------|-------------|
| `/dashboard/users` | GET | User list page |
| `/dashboard/users/{id}` | GET | User detail page |
| `/dashboard/users/{id}/promote` | POST | Set `is_admin=True` |
| `/dashboard/users/{id}/demote` | POST | Set `is_admin=False` (rejects env var admins) |
| `/dashboard/users/{id}/disable` | POST | Set `is_disabled=True` (rejects self) |
| `/dashboard/users/{id}/enable` | POST | Set `is_disabled=False` |
| `/dashboard/users/{id}/prefs` | POST | Save preferences for target user |
| `/dashboard/users/{id}/keys` | GET | HTMX partial — target user's key table |
| `/dashboard/users/{id}/keys/{kid}/revoke` | POST | Revoke a key belonging to target user |
| `/dashboard/users/{id}/audit` | GET | HTMX partial — target user's audit entries |

### Modified routes

| Route | Change |
|-------|--------|
| `/dashboard/audit/results` | Accepts optional `user_filter` query param. Admins: filters by github_login or shows all. Non-admins: param ignored. |

## Auth Changes

### `user_auth_before` (existing beforeware)

Add disabled check after successful user lookup:
```
if user.is_disabled:
    return disabled account page (HTML, not redirect)
```

### `require_admin` (new helper)

Used by all `/dashboard/users/*` routes:
```
def require_admin(user):
    if not is_user_admin(user):
        return Response("Admin access required.", status_code=403)
```

### `is_user_admin` (new helper)

Checks both env var and DB field:
```
def is_user_admin(user) -> bool:
    if user.is_admin:
        return True
    admins_env = os.environ.get("SAFECLAW_ADMINS", "")
    return user.github_login in [a.strip() for a in admins_env.split(",") if a.strip()]
```

### `is_env_admin` (new helper)

Checks only env var (for demote protection):
```
def is_env_admin(user) -> bool:
    admins_env = os.environ.get("SAFECLAW_ADMINS", "")
    return user.github_login in [a.strip() for a in admins_env.split(",") if a.strip()]
```

### Login flow change

In `auth_callback`, after `upsert_user`, sync env var admin status:
```
if is_env_admin(user) and not user.is_admin:
    user.is_admin = True
    users.update(user)
```

Also apply first-user fallback here if no admins exist.

### Disabled user key revocation

When a user is disabled, all their active API keys are automatically set to `is_active=False`. This prevents their agents from authenticating against the SafeClaw service. When re-enabled, keys remain revoked — the admin or user must create new keys. This is safer than silently restoring access.

## Security

- All admin routes protected by `require_admin` check
- CSRF tokens on all POST forms (existing pattern — `_csrf_token` hidden input)
- User IDs in routes are integer primary keys (no path traversal risk)
- Self-protection: cannot disable or demote yourself (checked server-side, not just UI)
- Env var protection: cannot demote env var admins (checked server-side)
- Admin actions are not audited in the governance audit log (they are dashboard-level actions, not agent governance decisions)

## File Structure

### New files

| File | Purpose |
|------|---------|
| `safeclaw-landing/dashboard/users.py` | User list and user detail UI components |

### Modified files

| File | Change |
|------|--------|
| `safeclaw-landing/db.py` | Add `is_admin`, `is_disabled` to User model |
| `safeclaw-landing/auth.py` | Add `is_user_admin`, `is_env_admin`, `require_admin`, disabled check, env admin sync on login, first-user fallback |
| `safeclaw-landing/main.py` | Add user management routes, modify audit route for user filter |
| `safeclaw-landing/dashboard/layout.py` | Conditionally show "Users" nav item for admins |
| `safeclaw-landing/dashboard/audit.py` | Add user filter dropdown and user column for admins |

## Out of Scope

- User invitation or creation from admin panel (users self-register via GitHub OAuth)
- Custom dashboard roles beyond admin/user
- Email notifications on admin actions
- Hard delete of users (soft disable only, for audit trail preservation)
- Admin action audit logging (governance audit tracks agent decisions, not dashboard admin actions)
