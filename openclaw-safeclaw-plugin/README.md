# openclaw-safeclaw-plugin

Neurosymbolic governance plugin for OpenClaw AI agents. Validates every tool call, message, and action against OWL ontologies and SHACL constraints before execution.

## Install

```bash
npm install openclaw-safeclaw-plugin
```

## Quick Start

Install and go — the plugin connects to SafeClaw's hosted service by default:

```bash
npm install openclaw-safeclaw-plugin
```

No configuration needed. The default service URL is `https://api.safeclaw.eu/api/v1`.

## Self-Hosted

To run your own SafeClaw service, override the URL:

```bash
export SAFECLAW_URL="http://localhost:8420/api/v1"

# Start the SafeClaw service
git clone https://github.com/tendlyeu/SafeClaw.git
cd SafeClaw/safeclaw-service
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
safeclaw init --user-id yourname
safeclaw serve
# Engine ready on http://localhost:8420
```

## What It Does

- **Blocks dangerous actions** — force push, deleting root, exposing secrets
- **Enforces dependencies** — tests must pass before git push
- **Checks user preferences** — confirmation for irreversible actions
- **Governs messages** — blocks sensitive data leaks
- **Full audit trail** — every decision logged with ontological justification

## How It Works

The plugin registers hooks on OpenClaw events:

1. **before_tool_call** — validates against SHACL shapes, policies, preferences, dependencies
2. **before_agent_start** — injects governance context into the agent's system prompt
3. **message_sending** — checks outbound messages for sensitive data
4. **after_tool_call** — records action outcomes for dependency tracking
5. **llm_input/output** — logs LLM interactions for audit

## Configuration

Set via environment variables or `~/.safeclaw/config.json`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SAFECLAW_URL` | `https://api.safeclaw.eu/api/v1` | SafeClaw service URL |
| `SAFECLAW_API_KEY` | *(empty)* | API key for cloud mode |
| `SAFECLAW_TIMEOUT_MS` | `500` | Request timeout in ms |
| `SAFECLAW_ENABLED` | `true` | Set `false` to disable |
| `SAFECLAW_ENFORCEMENT` | `enforce` | `enforce`, `warn-only`, `audit-only`, or `disabled` |
| `SAFECLAW_FAIL_MODE` | `closed` | `open` (allow on failure) or `closed` (block on failure) |

## Enforcement Modes

- **`enforce`** — block actions that violate constraints (recommended)
- **`warn-only`** — log warnings but allow all actions
- **`audit-only`** — server-side logging only, no client-side action
- **`disabled`** — plugin is completely inactive

## License

MIT
