# SafeClaw — Neurosymbolic Governance for OpenClaw

SafeClaw adds ontology-based constraint checking to your OpenClaw agent. Every tool call, message, and action is validated against OWL ontologies and SHACL shapes before execution.

## What it does

- **Blocks dangerous actions** — force push, deleting root, exposing secrets
- **Enforces dependencies** — tests must pass before git push
- **Checks user preferences** — confirmation for irreversible actions based on autonomy level
- **Governs messages** — blocks sensitive data leaks, enforces never-contact lists
- **Full audit trail** — every decision logged with ontological justification

## Setup

The plugin connects to `https://api.safeclaw.eu/api/v1` by default — no configuration needed.

### Self-hosted mode

To run your own SafeClaw service, override the URL:

```bash
export SAFECLAW_URL="http://localhost:8420/api/v1"
export SAFECLAW_API_KEY="sc_live_your_key_here"  # optional
```

## Configuration

Set via environment variables or `~/.safeclaw/config.json`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SAFECLAW_URL` | `https://api.safeclaw.eu/api/v1` | SafeClaw service URL |
| `SAFECLAW_API_KEY` | (empty) | API key for remote/cloud mode |
| `SAFECLAW_TIMEOUT_MS` | `500` | Request timeout in milliseconds |
| `SAFECLAW_ENABLED` | `true` | Set to `false` to disable |
| `SAFECLAW_ENFORCEMENT` | `enforce` | `enforce`, `warn-only`, `audit-only`, or `disabled` |

## How it works

This plugin registers hooks on every OpenClaw event:

1. **before_tool_call** — validates against SHACL shapes, policies, preferences, dependencies
2. **before_agent_start** — injects governance context into the agent's system prompt
3. **message_sending** — checks outbound messages for sensitive data and contact rules
4. **after_tool_call** — records action outcomes for dependency tracking
5. **llm_input/output** — logs LLM interactions for audit

If the SafeClaw service is unavailable, the plugin degrades gracefully — no blocks, no crashes.
