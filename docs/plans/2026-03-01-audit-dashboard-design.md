# Audit Dashboard Design

## Goal

Show all governance decisions (blocked + allowed) in the user's safeclaw.eu dashboard, with a preference toggle to disable logging.

## Architecture

The SafeClaw service already builds `DecisionRecord` objects and logs them to local JSONL files. This feature adds a second write path: after each evaluation, the service inserts a summary row into an `audit_log` table in the shared SQLite database. The landing site dashboard reads from this table to display decisions to the user.

Logging is controlled per-user via an `audit_logging` column on the `users` table. The service checks this preference before writing.

## Data Model

### New table: `audit_log`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| user_id | INTEGER | FK to users table |
| timestamp | TEXT | ISO 8601 |
| session_id | TEXT | Agent session |
| tool_name | TEXT | e.g. "bash", "read" |
| params_summary | TEXT | Truncated params (max 500 chars) |
| decision | TEXT | "allowed" or "blocked" |
| risk_level | TEXT | "safe", "low", "medium", "high", "critical" |
| reason | TEXT | Block reason or "passed all checks" |
| elapsed_ms | REAL | Validation latency |

### Modified table: `users`

New column: `audit_logging INTEGER DEFAULT 1` (1 = enabled, 0 = disabled).

## Data Flow

1. User toggles "Audit Logging" on/off in preferences page -> saved to `users.audit_logging`
2. `FullEngine.evaluate_tool_call()` completes -> checks if audit logging is enabled for the user via `SQLiteAPIKeyManager`
3. If enabled, inserts row into `audit_log` in shared DB
4. Landing dashboard reads from `audit_log` filtered by `user_id`

The service already has the user's `org_id` (= `user_id`) from API key validation and a connection to the shared DB via `SQLiteAPIKeyManager`.

## Dashboard Page

New page at `/dashboard/audit` in the landing site sidebar nav.

- **Filter bar**: Dropdown for "All" / "Blocked only" / "Allowed only" + session ID search
- **Table**: Timestamp, Tool, Decision (color-coded badge), Risk Level (badge), Reason, Latency
- **Pagination**: Last 50 by default, "Load more" button
- **Empty state**: Explanation of audit logging with link to prefs page

## Preferences Toggle

Checkbox on `/dashboard/prefs`: "Log all governance decisions to your dashboard" — enabled by default.

## Components Modified

- `safeclaw-service/safeclaw/auth/api_key.py` — add `audit_log` table creation, `audit_logging` column, insert method, preference check method
- `safeclaw-service/safeclaw/engine/full_engine.py` — call audit DB insert after evaluation
- `safeclaw-landing/db.py` — add `audit_logging` field to User class, `audit_log` table
- `safeclaw-landing/dashboard/audit.py` — new dashboard page
- `safeclaw-landing/dashboard/layout.py` — add "Audit Log" nav item
- `safeclaw-landing/dashboard/prefs.py` — add audit logging toggle
- `safeclaw-landing/main.py` — register audit routes
