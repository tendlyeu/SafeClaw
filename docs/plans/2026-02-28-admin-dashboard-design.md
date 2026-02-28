# SafeClaw Admin Dashboard — Design Document

**Date:** 2026-02-28
**Status:** Approved

## Goal

Build an admin dashboard inside safeclaw-service that provides visibility into SafeClaw's operation and a place to configure settings like the Mistral API key.

## Architecture Decision

**Chosen approach:** FastHTML mounted as ASGI sub-app inside the existing FastAPI service at `/admin/`.

**Rationale:**
- Single deployment — no extra container or service
- Direct Python access to `FullEngine` instance (no HTTP calls, no CORS)
- Same tech stack as the landing page (FastHTML + HTMX)
- MonsterUI components for polished dark-theme UI

**Alternatives considered:**
1. Jinja2 templates inside FastAPI — verbose, no MonsterUI, no component reuse
2. Separate container — network hop, CORS, duplicated config, more deployment complexity

## Pages

### 1. Home / System Health (`/admin/`)

Quick overview dashboard:
- **Status cards**: Engine status, LLM status (configured/not), Ontology loaded (triple count), Reasoner status
- **Recent activity**: Last 10 decisions in a mini table with color-coded allow/block badges
- **Quick stats**: Total decisions today, block rate %, active agents count, active sessions

### 2. Audit Log (`/admin/audit`)

- Filterable table of `DecisionRecord`s: timestamp, session, tool name, decision badge, risk level, elapsed_ms
- Filters: session_id, decision type (allowed/blocked), date range
- Row click → expand to show full justification (constraints checked, preferences applied)
- Explain button (if LLM configured) → plain English explanation via `DecisionExplainer`

### 3. Agents (`/admin/agents`)

- Agent table: agent_id, role, status badge (active/killed), registered_at
- Per-agent actions: kill switch toggle, grant temp permission (modal: permission type + duration)
- Empty state messaging when no agents registered

### 4. Settings (`/admin/settings`)

- **Mistral API Key**: masked input showing current status, form to set new key (runtime + optional persist to config.json)
- **Current Config**: read-only display of all SafeClawConfig values
- **Ontology Reload**: button calling `engine.reload()`
- **LLM Status**: which features are active (security reviewer, classification observer, explainer)

## Authentication

- Session-based password auth via `SAFECLAW_ADMIN_PASSWORD` env var
- Login page at `/admin/login` with single password field
- If `SAFECLAW_ADMIN_PASSWORD` is not set: dashboard accessible without auth (dev mode)
- Session cookie set on successful login

## Navigation

Sticky top bar:
- SafeClaw logo/text (left)
- Page links: Home, Audit, Agents, Settings (center)
- Logout button (right)

## Visual Style

Dark theme matching safeclaw.eu landing page:
- Background: `#0a0a0a`, Surface: `#1a1a1a`, Border: `#2a2a2a`
- Text: `#e5e5e5`, Muted: `#888888`
- Success/Allowed: `#4ade80`, Error/Blocked: `#f87171`
- Primary: `#60a5fa`, Accent: `#a78bfa`, Warning: `#fb923c`
- MonsterUI slate theme in dark mode
- Font: Inter (sans), JetBrains Mono (mono)

## File Structure

```
safeclaw-service/safeclaw/dashboard/
├── __init__.py
├── app.py           # FastHTML app factory, auth beforeware, route registration
├── pages/
│   ├── __init__.py
│   ├── home.py      # System health overview
│   ├── audit.py     # Audit log viewer
│   ├── agents.py    # Agent management
│   └── settings.py  # Config & API key entry
└── components.py    # Shared UI components (nav, status badges, layout)
```

## Integration Point

Mount in `safeclaw/main.py`:
```python
from safeclaw.dashboard.app import create_dashboard
app.mount("/admin", create_dashboard(get_engine))
```

## Data Sources

| Data | Source | Method |
|------|--------|--------|
| Recent decisions | `engine.audit` | `.get_recent_records(limit)` |
| Session records | `engine.audit` | `.get_session_records(session_id)` |
| Blocked actions | `engine.audit` | `.get_blocked_records(limit)` |
| Statistics | `AuditReporter` | `.get_statistics(records)` |
| Agents | `engine.agent_registry` | `.list_agents()` |
| Agent status | `engine.agent_registry` | `.is_killed(agent_id)` |
| Config | `engine.config` | Direct attribute access |
| Sessions | `engine.session_tracker` | Direct access |
