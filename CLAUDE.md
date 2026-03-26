# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SafeClaw is a neurosymbolic governance layer for autonomous AI agents. It validates tool calls, messages, and actions against OWL ontologies and SHACL constraints before execution. The repo is a monorepo with two components:

- **`safeclaw-service/`** — Python FastAPI service (the brain). All governance logic lives here.
- **`openclaw-safeclaw-plugin/`** — TypeScript plugin that bridges OpenClaw agents to the SafeClaw service via HTTP. It's a thin client (~480 lines) with no governance logic of its own.

## Build & Development Commands

### Python service (safeclaw-service/)

```bash
cd safeclaw-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_engine.py -v

# Run a single test
python -m pytest tests/test_engine.py::test_function_name -v

# Lint
ruff check safeclaw/ tests/
ruff format --check safeclaw/ tests/

# Start the service (port 8420)
safeclaw serve

# Initialize config
safeclaw init --user-id yourname
```

### TypeScript plugin (openclaw-safeclaw-plugin/)

```bash
cd openclaw-safeclaw-plugin
npm install
npm run build        # tsc
npm run typecheck    # tsc --noEmit
```

### Docker

```bash
cd safeclaw-service
docker compose up --build   # runs on port 8420
```

## Architecture

### Constraint Pipeline

The core of SafeClaw is a multi-step validation pipeline in `FullEngine.evaluate_tool_call()` (`safeclaw-service/safeclaw/engine/full_engine.py`). Every tool call passes through these steps in order, blocking at the first violation. Steps use named constants (`STEP_*`) for machine-readable identification:

0. **Agent governance** (`agent_governance`) — token auth, kill switch, delegation bypass detection
1. **Action classification** (`action_classification`) — maps tool name + params to an ontology class with risk level
2. **Role-based access** (`role_check`) — checks if the agent's role allows the action class and resource path
3. **SHACL validation** (`shacl_validation`) — validates the action's RDF graph against shape constraints
4. **Policy check** (`policy_check`) — evaluates against policy rules from the knowledge graph
5. **Preference check** (`preference_check`) — user-specific preferences like "confirm before delete"
6. **Dependency check** (`dependency_check`) — e.g., tests must pass before git push
7. **Temporal check** (`temporal_check`) — time-based constraints (notBefore/notAfter)
8. **Rate limit check** (`rate_limit_check`) — per-session rate limiting
9. **Derived rules** (`derived_rules`) — combined rules that may require user confirmation
10. **Hierarchy rate limit** (`hierarchy_rate_limit`) — multi-agent hierarchy-wide rate limiting

### Engine Abstraction

`SafeClawEngine` (`engine/core.py`) is the abstract base class defining the interface: `evaluate_tool_call`, `evaluate_message`, `build_context`, `record_action_result`, `log_llm_io`. `FullEngine` is the concrete implementation using owlready2 + pySHACL + RDFLib.

### Knowledge Graph & Ontologies

Ontologies are Turtle (.ttl) files in `safeclaw/ontologies/`:
- `safeclaw-agent.ttl` — agent action class hierarchy
- `safeclaw-policy.ttl` — policy rules
- `safeclaw-channels.ttl` — channel trust level definitions (DM, public, webhook)
- `safeclaw-sandbox.ttl` — sandbox policy classes and properties
- `nemoclaw-policy.ttl` — NemoClaw network and filesystem rule classes
- `shapes/` — SHACL shape constraints (action, command, file, message, sandbox shapes)
- `roles/` — role definitions (admin, developer, researcher)
- `users/` — per-user preference triples

The `KnowledgeGraph` class (`engine/knowledge_graph.py`) wraps RDFLib and loads all .ttl files. The `OWLReasoner` (`engine/reasoner.py`) uses owlready2 and requires Java (HermiT reasoner).

### Multi-Agent Governance

SafeClaw supports governing hierarchical multi-agent systems:
- `AgentRegistry` — tracks registered agents, kill switches, tokens
- `RoleManager` — role-based permissions with allowed/denied action classes and resource paths
- `DelegationDetector` — detects when a blocked parent delegates to a child agent
- `TempPermissionManager` — time-limited or task-scoped permission grants

### API Layer

FastAPI routes in `api/routes.py`, all under `/api/v1`. Key endpoints:
- `POST /evaluate/tool-call` — the main gate (supports `dryRun` mode)
- `POST /evaluate/message` — message governance
- `POST /evaluate/inbound-message` — inbound message prompt injection risk assessment
- `POST /evaluate/subagent-spawn` — subagent spawn governance (delegation bypass detection)
- `POST /evaluate/sandbox-policy` — sandbox policy validation (admin)
- `POST /session/start` — initialize session-scoped governance state
- `POST /session/end` — clean up per-session state
- `POST /context/build` — context injection for agent system prompts
- `POST /record/tool-result` — feedback loop for session tracking
- `POST /record/subagent-ended` — record subagent completion for audit trail
- `POST /reload` — hot-reload ontologies (admin)
- `POST /handshake` — plugin handshake / API key validation
- `POST /heartbeat` — plugin heartbeat with agent token verification
- Agent management: `/agents/register`, `/agents/{id}/kill`, `/agents/{id}/revive`, `/agents/{id}/temp-grant`
- Audit: `/audit`, `/audit/statistics`, `/audit/report/{session_id}`, `/audit/compliance`, `/audit/{audit_id}/explain`
- LLM: `/policies/compile`, `/llm/findings`, `/llm/suggestions`

### NemoClaw Integration

The `safeclaw/nemoclaw/` module converts NemoClaw YAML sandbox policies into RDF triples that integrate with the knowledge graph. When enabled (via config or auto-detection of `~/.nemoclaw/` YAML files), the `PolicyChecker` gains network allowlist and filesystem prefix enforcement. Policies are re-ingested on hot-reload.

### State Persistence

The `StateStore` (`engine/state_store.py`) is a SQLite-backed persistence layer at `~/.safeclaw/governance_state.db`. It persists agent kills, rate-limit counters, and temporary permission grants across service restarts. In-memory structures remain the fast path for reads.

### Plugin ↔ Service Communication

The TypeScript plugin registers OpenClaw event hooks (`before_tool_call`, `message_sending`, `before_agent_start`, etc.) that make HTTP POST calls to the service. It supports enforcement modes: `enforce`, `warn-only`, `audit-only`, `disabled`. Fail mode can be `open` (allow on service failure) or `closed` (block on service failure).

### Security

- Admin passwords use bcrypt (`$2b$` prefix) with plaintext legacy fallback via constant-time comparison
- API keys use bcrypt hashing with SHA-256 legacy fallback for unmigrated keys
- Agent tokens are verified on every tool call, message evaluation, and heartbeat
- Input sanitization at both API route and engine level (control character stripping, params depth/size limits)

### Configuration

- Python config: `SafeClawConfig` uses pydantic-settings with `SAFECLAW_` env prefix
- Runtime config: `~/.safeclaw/config.json` (generated by `safeclaw init`)
- Plugin config: reads from `~/.safeclaw/config.json` and `SAFECLAW_*` env vars
- NemoClaw config: `nemoclaw_enabled`, `nemoclaw_policy_dir` fields with auto-detection fallback
- See `docs/configuration.md` for full field reference

### Audit

`AuditLogger` writes append-only JSONL to `~/.safeclaw/audit/`. Every decision (block/allow) is recorded as a `DecisionRecord` with full justification including which constraints were checked.

## Key Conventions

- Python: ruff for linting/formatting, line length 100, target Python 3.11+
- Tests: pytest with `asyncio_mode = "auto"`, test files match `test_*.py`
- Ontology namespace: `http://safeclaw.uku.ai/ontology/agent#` (prefix `sc:`)
- All API request/response models use camelCase field names (Pydantic aliases)
- The OWL reasoner requires Java — tests use `run_reasoner_on_startup=False` to skip it
- The service runs on port 8420
