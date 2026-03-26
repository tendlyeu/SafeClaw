# openclaw-safeclaw-plugin

Neurosymbolic governance plugin for OpenClaw AI agents. Validates every tool call, message, and action against OWL ontologies and SHACL constraints before execution.

## Installation

### Via ClawHub (recommended)

```bash
openclaw plugins install safeclaw
```

### Manual install

```bash
npm install -g openclaw-safeclaw-plugin
safeclaw-plugin setup
safeclaw-plugin restart-openclaw
```

The `setup` command copies the plugin manifest to `~/.openclaw/extensions/safeclaw/` and enables it in `~/.openclaw/openclaw.json`. After install, restart OpenClaw to activate the plugin.

## Quick Start

1. Install the plugin (see above)
2. Connect to SafeClaw (cloud or self-hosted):

```bash
# Cloud
safeclaw-plugin connect <your-api-key>

# Self-hosted
safeclaw-plugin config set serviceUrl http://localhost:8420/api/v1
```

3. Restart OpenClaw:

```bash
safeclaw-plugin restart-openclaw
```

Every tool call your AI agent makes is now governed by SafeClaw.

## Configuration

Configuration is resolved in this order (later sources override earlier ones):

1. **Defaults** -- hardcoded in the plugin
2. **Config file** -- `~/.safeclaw/config.json`
3. **Environment variables** -- `SAFECLAW_*` prefixed vars
4. **OpenClaw plugin config** -- values from `api.pluginConfig` (set via OpenClaw settings UI or `openclaw.json`)

### Config file

Created automatically by `safeclaw-plugin connect`. Structure:

```json
{
  "enabled": true,
  "remote": {
    "serviceUrl": "http://localhost:8420/api/v1",
    "apiKey": "sc_live_..."
  },
  "enforcement": {
    "mode": "enforce",
    "failMode": "open"
  }
}
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SAFECLAW_URL` | `http://localhost:8420/api/v1` | SafeClaw service URL |
| `SAFECLAW_API_KEY` | *(empty)* | API key for authentication |
| `SAFECLAW_TIMEOUT_MS` | `5000` | HTTP request timeout in milliseconds |
| `SAFECLAW_ENABLED` | `true` | Set `false` to disable the plugin entirely |
| `SAFECLAW_ENFORCEMENT` | `enforce` | Enforcement mode (see below) |
| `SAFECLAW_FAIL_MODE` | `open` | Fail mode (see below) |
| `SAFECLAW_AGENT_ID` | *(empty)* | Agent identifier for multi-agent governance |
| `SAFECLAW_AGENT_TOKEN` | *(empty)* | Agent authentication token |

### OpenClaw plugin config

When running inside OpenClaw, the plugin reads `api.pluginConfig` which maps to the `configSchema` in `openclaw.plugin.json`. These values take priority over the config file. Set them via the OpenClaw settings UI or directly in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "safeclaw": {
        "enabled": true,
        "config": {
          "enforcement": "enforce",
          "failMode": "open",
          "serviceUrl": "http://localhost:8420/api/v1"
        }
      }
    }
  }
}
```

## Enforcement Modes

| Mode | Behavior |
|------|----------|
| `enforce` | Block tool calls and messages that violate constraints. Recommended for production. |
| `warn-only` | Log warnings but allow all actions through. Useful during initial rollout. |
| `audit-only` | Server-side logging only, no client-side warnings or blocks. |
| `disabled` | Plugin is completely inactive. No HTTP calls to the service. |

## Fail Modes

Controls what happens when the SafeClaw service is unreachable:

| Mode | Behavior |
|------|----------|
| `open` | Allow all actions when the service is unavailable. Default. |
| `closed` | Block all actions when the service is unavailable. Use when safety is critical. |

## Hooks

The plugin registers 11 hooks on OpenClaw events. Each hook communicates with the SafeClaw service via HTTP.

### Blocking hooks (can prevent actions)

| Hook | Priority | Description |
|------|----------|-------------|
| `before_tool_call` | 100 | The main gate. Evaluates every tool call against SHACL shapes, policies, preferences, and dependencies. Returns `{ block: true }` if the action violates constraints. |
| `message_sending` | 100 | Checks outbound messages for sensitive data leaks, contact rule violations, and content policy. Returns `{ cancel: true }` to block. |
| `subagent_spawning` | 100 | Evaluates child agent spawn requests. Detects delegation bypass attempts where a blocked parent tries to spawn an unrestricted child. |

### Context hooks (modify agent behavior)

| Hook | Priority | Description |
|------|----------|-------------|
| `before_prompt_build` | 100 | Injects governance context into the agent system prompt via `prependSystemContext`. Tells the agent what constraints are active. |

### Recording hooks (fire-and-forget)

| Hook | Description |
|------|-------------|
| `after_tool_call` | Records tool execution results (success/failure, duration, errors) for dependency tracking and audit. |
| `llm_input` | Logs the prompt sent to the LLM, including provider and model name. |
| `llm_output` | Logs the LLM response, including token usage. |
| `subagent_ended` | Records child agent lifecycle completion. |
| `session_start` | Notifies the service when a new session begins. |
| `session_end` | Notifies the service when a session ends. |
| `message_received` | Evaluates inbound messages for governance (sender, channel, content). |

## Agent Tools

The plugin registers two tools that agents can call to introspect governance state.

### `safeclaw_status`

Returns the current governance status. No parameters.

```json
{
  "status": "ok",
  "enforcement": "enforce",
  "failMode": "open",
  "serviceUrl": "http://localhost:8420/api/v1",
  "handshakeCompleted": true
}
```

### `safeclaw_check_action`

Dry-run check of whether a tool call would be allowed. No side effects.

**Parameters:**
- `toolName` (string, required) -- tool name to check
- `params` (object, optional) -- tool parameters to validate

```json
{
  "block": false,
  "reason": null,
  "constraints": ["shacl:ActionShape", "policy:NoForceOnMain"]
}
```

## CLI Commands

The plugin ships a standalone CLI (`safeclaw-plugin`) and registers a `safeclaw` subcommand in the OpenClaw CLI via `api.registerCli`.

### Standalone CLI

```
safeclaw-plugin connect <api-key>    Save API key, validate via handshake, register with OpenClaw
safeclaw-plugin setup                Register plugin with OpenClaw (no key needed)
safeclaw-plugin restart-openclaw     Restart the OpenClaw daemon
safeclaw-plugin status               Run diagnostics (config, service, handshake, OpenClaw, NemoClaw)
safeclaw-plugin config show          Show current configuration
safeclaw-plugin config set <k> <v>   Set a config value (enforcement, failMode, enabled, serviceUrl)
safeclaw-plugin tui                  Open interactive settings TUI
```

### OpenClaw CLI extension

When loaded by OpenClaw, the plugin adds:

```
openclaw safeclaw status    Show SafeClaw service status and enforcement mode
```

## NemoClaw Sandbox

When running inside a NemoClaw sandbox (detected via the `OPENSHELL_SANDBOX` environment variable), the plugin automatically adjusts:

- **Service URL**: `localhost` is rewritten to `host.containers.internal` since the sandbox runs in a container and cannot reach the host's loopback interface directly.
- **Egress policy**: The bundled `policies/safeclaw.yaml` defines the network rules NemoClaw needs to allow SafeClaw traffic.

### Setup

1. Copy the egress policy into your NemoClaw configuration:

```bash
nemoclaw policy-add safeclaw
```

Or manually copy `policies/safeclaw.yaml` to your NemoClaw policy directory.

2. The policy allows two destinations:
   - `api.safeclaw.eu:443` (HTTPS) -- cloud service
   - `host.containers.internal:8420` (HTTP) -- self-hosted service on the host machine

3. No additional configuration is needed. The plugin detects the sandbox automatically and adjusts the service URL.

## Architecture

This plugin is a thin HTTP bridge (~450 lines). All governance logic lives in the SafeClaw Python service. The plugin:

1. Registers hooks on OpenClaw events
2. Forwards event data to the SafeClaw service via HTTP POST
3. Acts on the service response (block, warn, or allow)
4. Sends a heartbeat every 30 seconds with config hash
5. Registers as an OpenClaw service for clean lifecycle management (no `process.exit()`)

The plugin performs a handshake with the service on startup to validate the API key and confirm the engine is ready. If the handshake fails and `failMode` is `closed`, all tool calls are blocked until the service becomes reachable.

## License

MIT
