# SafeClaw TUI Design

## Goal

Add an interactive terminal UI to the OpenClaw SafeClaw plugin, invoked via `safeclaw tui`, that lets users view connection status and manage settings. Also add a heartbeat watchdog to detect plugin tampering.

## Architecture

The TUI is built with Ink (React for CLI) and lives alongside the existing plugin code. The plugin remains a thin HTTP bridge — the TUI is additive only.

### File Structure

```
openclaw-safeclaw-plugin/
  index.ts          # existing plugin + heartbeat interval
  cli.tsx           # bin entry point: renders <App />
  tui/
    App.tsx         # root Ink component — tab navigation
    Settings.tsx    # settings screen with toggles/selects
    Status.tsx      # live connection + heartbeat status
    About.tsx       # version and links
    config.ts       # shared config read/write for ~/.safeclaw/config.json
```

Service-side additions (in `safeclaw-service/`):
- `safeclaw/engine/heartbeat_monitor.py` — tracks agent heartbeats, detects staleness and config drift
- `POST /api/v1/heartbeat` route in `api/routes.py`

## TUI Screens

### Screen 1: Status (default)

Live-updating view showing:
- Service connection state (connected/disconnected, URL)
- Heartbeat status (active/stale, last seen)
- Current enforcement mode and fail mode
- Plugin and service versions

Green/red indicators. Fetches `/health` on load, refreshes periodically.

### Screen 2: Settings

Keyboard-driven settings editor:
- **Enabled** — toggle ON/OFF
- **Enforcement** — cycle: enforce / warn-only / audit-only / disabled
- **Fail Mode** — cycle: closed / open
- **Service URL** — text input

Arrow keys navigate, left/right cycles options, changes save immediately to `~/.safeclaw/config.json`.

### Screen 3: About

Static info: project name, website, docs URL, version. `q` to quit.

## Heartbeat Watchdog

### Plugin Side

- After successful `checkConnection()`, start `setInterval` every 30 seconds
- `POST /api/v1/heartbeat` with `{agentId, configHash, timestamp}`
- `configHash` = SHA-256 of `JSON.stringify({enabled, enforcement, failMode, serviceUrl})` — the security-relevant fields
- On process exit, send final heartbeat with `{status: "shutdown"}` for intentional shutdown
- Fire-and-forget, non-blocking

### Service Side

`HeartbeatMonitor` class:
- `record(agent_id, config_hash)` — stores last heartbeat time and hash
- `check_stale(threshold=90)` — returns agents with no heartbeat for >90s (3 missed beats)
- `check_config_drift(agent_id)` — compares current hash vs first-seen hash

Detection triggers:
- Stale heartbeat → `SafeClawEvent(severity="critical", title="Agent heartbeat lost")`
- Config hash change → `SafeClawEvent(severity="critical", title="Agent config hash changed")`

### What it does NOT do

- Does not auto-block agents on missed heartbeat (too aggressive for network blips)
- Does not require heartbeat for service to function (backwards compatible)
- Does not encrypt heartbeat payload (already over HTTPS)

### Security Model

All tool calls (file edits, npm uninstall, process kill) go through SafeClaw's gate. The heartbeat is a safety net for the case where the plugin is already removed and can no longer intercept.

## Dependencies

### New runtime deps
- `ink` — React-based terminal UI renderer
- `react` — required by Ink
- `ink-select-input` — arrow-key menu selection
- `ink-text-input` — for editing service URL

### New dev deps
- `@types/react` — TypeScript types

### package.json changes
- `"bin": {"safeclaw": "dist/cli.js"}`
- jsx support in tsconfig

### Impact
- ~1.5MB added to node_modules
- Existing plugin export (`"main"`) unchanged
- `bin` entry is separate from plugin loading

## CLI Interface

Single command: `safeclaw tui`

No scripting subcommands. TUI only.

## Tech Stack

- Ink (React for CLI) for interactive terminal rendering
- TypeScript with JSX
- Node.js >= 18
