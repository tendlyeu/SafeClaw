# SafeClaw -- Neurosymbolic Governance for OpenClaw

SafeClaw validates every tool call, message, and agent action against OWL ontologies and SHACL constraints before execution. It acts as a governance gate between your AI agent and the tools it uses.

## What it does

- **Blocks dangerous actions** -- force push, deleting root, exposing secrets
- **Enforces dependencies** -- tests must pass before git push
- **Checks user preferences** -- confirmation for irreversible actions based on autonomy level
- **Governs messages** -- blocks sensitive data leaks, enforces contact rules
- **Controls subagent delegation** -- prevents blocked parents from spawning unrestricted children
- **Full audit trail** -- every decision logged with ontological justification

## Hooks

11 hooks covering the full agent lifecycle:

- `before_tool_call` -- constraint gate for every tool invocation
- `before_prompt_build` -- injects governance context into system prompt
- `message_sending` -- outbound message governance
- `message_received` -- inbound message evaluation
- `llm_input` / `llm_output` -- LLM interaction audit logging
- `after_tool_call` -- records outcomes for dependency tracking
- `subagent_spawning` / `subagent_ended` -- multi-agent governance
- `session_start` / `session_end` -- session lifecycle tracking

## Agent tools

- `safeclaw_status` -- check governance service status and active enforcement mode
- `safeclaw_check_action` -- dry-run check if a specific tool call would be allowed

## Configuration

Set via OpenClaw plugin settings, `~/.safeclaw/config.json`, or `SAFECLAW_*` environment variables. Supports four enforcement modes (`enforce`, `warn-only`, `audit-only`, `disabled`) and two fail modes (`open`, `closed`).

### NemoClaw sandbox

Automatically detects NemoClaw sandboxes and rewrites `localhost` to `host.containers.internal`. Includes a bundled egress policy at `policies/safeclaw.yaml`.

### Self-hosted

Run the SafeClaw service locally:

```bash
pip install safeclaw
safeclaw serve
```

The plugin connects to `http://localhost:8420/api/v1` by default.
