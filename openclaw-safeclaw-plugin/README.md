# openclaw-safeclaw-plugin

Neurosymbolic governance plugin for OpenClaw AI agents. Validates every tool call, message, and action against safety constraints before execution.

## Install

```bash
npm install -g openclaw-safeclaw-plugin
```

## Quick Start

1. Sign up at [safeclaw.eu](https://safeclaw.eu) and create an API key
2. Install and connect:

```bash
npm install -g openclaw-safeclaw-plugin
safeclaw connect <your-api-key>
safeclaw restart-openclaw
```

That's it. Every tool call your AI agent makes is now governed by SafeClaw.

## Commands

```
safeclaw connect <api-key>  Connect to SafeClaw and register with OpenClaw
safeclaw setup              Register plugin with OpenClaw (no key needed)
safeclaw tui                Open the interactive settings TUI
safeclaw restart-openclaw   Restart the OpenClaw daemon
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
| `SAFECLAW_API_KEY` | *(empty)* | API key (set automatically by `safeclaw connect`) |
| `SAFECLAW_TIMEOUT_MS` | `5000` | Request timeout in ms |
| `SAFECLAW_ENABLED` | `true` | Set `false` to disable |
| `SAFECLAW_ENFORCEMENT` | `enforce` | `enforce`, `warn-only`, `audit-only`, or `disabled` |
| `SAFECLAW_FAIL_MODE` | `open` | `open` (allow on failure) or `closed` (block on failure) |

## Enforcement Modes

- **`enforce`** — block actions that violate constraints (recommended)
- **`warn-only`** — log warnings but allow all actions
- **`audit-only`** — server-side logging only, no client-side action
- **`disabled`** — plugin is completely inactive

## License

MIT
