# SafeClaw Service

Python FastAPI service that implements the SafeClaw neurosymbolic governance layer. Validates tool calls, messages, and actions against OWL ontologies and SHACL constraints before execution.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

safeclaw init --user-id yourname
safeclaw serve
# Listening on http://localhost:8420
```

### Docker

```bash
docker compose up --build   # runs on port 8420
```

## Constraint Pipeline

Every tool call passes through an 11-step validation pipeline (`FullEngine.evaluate_tool_call()` in `safeclaw/engine/full_engine.py`). Each step uses a named constant (`STEP_*`) for machine-readable identification. The pipeline blocks at the first violation.

| Step | Name                  | Constant              | Description                                                      |
|------|-----------------------|-----------------------|------------------------------------------------------------------|
| 0    | Agent governance      | `agent_governance`    | Token auth, kill switch, delegation bypass detection              |
| 1    | Action classification | `action_classification` | Maps tool name + params to an ontology class with risk level    |
| 2    | Role-based access     | `role_check`          | Checks if the agent's role allows the action class and resource  |
| 3    | SHACL validation      | `shacl_validation`    | Validates the action's RDF graph against shape constraints        |
| 4    | Policy check          | `policy_check`        | Evaluates against policy rules from the knowledge graph           |
| 5    | Preference check      | `preference_check`    | User-specific preferences (e.g., "confirm before delete")        |
| 6    | Dependency check      | `dependency_check`    | Prerequisite enforcement (e.g., tests must pass before git push) |
| 7    | Temporal check        | `temporal_check`      | Time-based constraints (notBefore / notAfter windows)            |
| 8    | Rate limit check      | `rate_limit_check`    | Per-session rate limiting                                        |
| 9    | Derived rules         | `derived_rules`       | Combined rules that may require user confirmation                |
| 10   | Hierarchy rate limit  | `hierarchy_rate_limit`| Multi-agent hierarchy-wide rate limiting                         |

## API Endpoints

All endpoints are under `/api/v1`.

### Evaluation (core gate)

| Method | Path                         | Auth     | Description                                        |
|--------|------------------------------|----------|----------------------------------------------------|
| POST   | `/evaluate/tool-call`        | Agent    | Main gate -- validates a tool call against all 11 pipeline steps. Supports `dryRun` mode. |
| POST   | `/evaluate/message`          | Agent    | Message governance (content policies, sensitive data, contact rules) |
| POST   | `/evaluate/inbound-message`  | Agent    | Evaluate inbound messages for prompt injection risk (channel trust, pattern detection) |
| POST   | `/evaluate/subagent-spawn`   | Agent    | Evaluate whether a subagent spawn should be allowed (delegation bypass detection) |
| POST   | `/evaluate/sandbox-policy`   | Admin    | Validate a sandbox policy configuration (toolPolicy, filesystemPolicy) |

### Session lifecycle

| Method | Path                         | Auth     | Description                                        |
|--------|------------------------------|----------|----------------------------------------------------|
| POST   | `/session/start`             | Agent    | Initialize session-scoped governance state (preferences, rate limits) |
| POST   | `/session/end`               | API key  | Clean up per-session state (with ownership verification) |

### Context and recording

| Method | Path                         | Auth     | Description                                        |
|--------|------------------------------|----------|----------------------------------------------------|
| POST   | `/context/build`             | Agent    | Build context injection for agent system prompts    |
| POST   | `/record/tool-result`        | Agent    | Record tool execution result (feedback loop for session tracking) |
| POST   | `/record/subagent-ended`     | Agent    | Record subagent completion for audit trail          |

### LLM I/O logging

| Method | Path                         | Auth     | Description                                        |
|--------|------------------------------|----------|----------------------------------------------------|
| POST   | `/log/llm-input`             | None     | Log LLM input for audit                            |
| POST   | `/log/llm-output`            | None     | Log LLM output for audit                           |

### Agent management (admin)

| Method | Path                                    | Auth  | Description                                   |
|--------|-----------------------------------------|-------|-----------------------------------------------|
| POST   | `/agents/register`                      | Admin | Register a new agent with a role              |
| POST   | `/agents/{agent_id}/kill`               | Admin | Kill switch -- immediately block all actions  |
| POST   | `/agents/{agent_id}/revive`             | Admin | Revive a killed agent (issues new token)      |
| GET    | `/agents`                               | Admin | List all registered agents                    |
| POST   | `/agents/{agent_id}/temp-grant`         | Admin | Grant a time-limited or task-scoped permission|
| DELETE | `/agents/{agent_id}/temp-grant/{grant_id}` | Admin | Revoke a temporary permission              |
| POST   | `/tasks/{task_id}/complete`             | Admin | Complete a task (revokes task-scoped grants)  |

### Audit and reporting (admin)

| Method | Path                                | Auth  | Description                                       |
|--------|-------------------------------------|-------|---------------------------------------------------|
| GET    | `/audit`                            | Admin | Query audit records (by session, blocked, recent) |
| GET    | `/audit/statistics`                 | Admin | Aggregate statistics from recent records          |
| GET    | `/audit/report/{session_id}`        | Admin | Session report (markdown, JSON, or CSV)           |
| GET    | `/audit/compliance`                 | Admin | Compliance report from recent records             |
| GET    | `/audit/{audit_id}/explain`         | Admin | LLM-powered explanation of an audit decision      |

### Ontology and preferences (admin)

| Method | Path                         | Auth  | Description                                        |
|--------|------------------------------|-------|----------------------------------------------------|
| GET    | `/ontology/graph`            | Admin | D3-compatible graph of the knowledge graph          |
| GET    | `/ontology/search`           | Admin | Fuzzy search for ontology nodes                     |
| GET    | `/preferences/{user_id}`     | Admin | Get user preferences as JSON                        |
| POST   | `/preferences/{user_id}`     | Admin | Update user preferences (writes Turtle file)        |

### Infrastructure

| Method | Path                         | Auth  | Description                                        |
|--------|------------------------------|-------|----------------------------------------------------|
| POST   | `/reload`                    | Admin | Hot-reload ontologies and reinitialize checkers     |
| POST   | `/heartbeat`                 | None  | Plugin heartbeat (agent token verified if registered)|
| POST   | `/handshake`                 | API key | Validate API key and log connection event         |
| GET    | `/events`                    | Admin | SSE endpoint for real-time SafeClaw events          |

### LLM layer (admin)

| Method | Path                         | Auth  | Description                                        |
|--------|------------------------------|-------|----------------------------------------------------|
| POST   | `/policies/compile`          | Admin | Natural-language to Turtle policy compilation (LLM) |
| GET    | `/llm/findings`              | Admin | LLM security findings (placeholder)                |
| GET    | `/llm/suggestions`           | Admin | Classification observer suggestions                |

## Security

### Authentication

- **Admin password**: Verified with bcrypt (`$2b$` prefix). Legacy plaintext passwords are supported as a migration path using constant-time comparison. Configure via `SAFECLAW_ADMIN_PASSWORD`.
- **API keys**: Hashed with bcrypt on creation. Legacy SHA-256 hashes are accepted as a fallback for unmigrated keys. Keys use the `sc_` prefix format.
- **Agent tokens**: Per-agent tokens issued on registration, verified on every tool call and heartbeat.

### Admin auth model

Admin endpoints use a two-layer check:
1. If API-key auth is active, the key must have `"admin"` in its scope (exact set membership, not substring).
2. If `admin_password` is configured, the `X-Admin-Password` header must match.

## NemoClaw Integration

SafeClaw integrates with NemoClaw sandbox policies. When enabled, NemoClaw YAML policy files are converted to RDF triples and loaded into the knowledge graph, extending the policy checker with:

- **Network allowlist**: Validates outbound connections against host/port/protocol rules.
- **Filesystem prefix checks**: Validates file access against path and access mode rules (read-only, read-write, denied).

### Enabling NemoClaw

NemoClaw activates automatically when any of these conditions are met:

1. `SAFECLAW_NEMOCLAW_ENABLED=true` is set explicitly.
2. `SAFECLAW_NEMOCLAW_POLICY_DIR` points to a directory with `.yaml` files.
3. `~/.nemoclaw/` exists and contains `.yaml` files.
4. `OPENSHELL_SANDBOX` env var points to a directory with a `policies/` subdirectory.

YAML policies are re-ingested on hot-reload (`POST /reload`).

### NemoClaw ontology

The `nemoclaw-policy.ttl` ontology defines `NemoNetworkRule` and `NemoFilesystemRule` classes with properties for host, port, protocol, path, access mode, and binary restrictions.

## State Persistence

Critical governance state is persisted to a SQLite database at `~/.safeclaw/governance_state.db` via the `StateStore` class:

- **Agent kills** -- survive service restarts so killed agents stay killed.
- **Rate-limit counters** -- prevent reset-by-restart circumvention.
- **Temporary permission grants** -- time-limited grants persist across restarts.

Ephemeral state (session locks, delegation detection history, active session context) is intentionally not persisted.

## Ontologies

Turtle (.ttl) files in `safeclaw/ontologies/`:

| File                        | Description                                           |
|-----------------------------|-------------------------------------------------------|
| `safeclaw-agent.ttl`        | Agent action class hierarchy                          |
| `safeclaw-policy.ttl`       | Policy rules                                          |
| `safeclaw-channels.ttl`     | Channel trust level definitions (DM, public, webhook) |
| `safeclaw-sandbox.ttl`      | Sandbox policy classes and properties                 |
| `nemoclaw-policy.ttl`       | NemoClaw network and filesystem rule classes          |
| `shapes/action-shapes.ttl`  | SHACL shapes for action validation                    |
| `shapes/command-shapes.ttl` | SHACL shapes for command validation                   |
| `shapes/file-shapes.ttl`    | SHACL shapes for file operation validation            |
| `shapes/message-shapes.ttl` | SHACL shapes for message validation                   |
| `shapes/sandbox-shapes.ttl` | SHACL shapes for sandbox policy validation            |
| `roles/admin.ttl`           | Admin role definition                                 |
| `roles/developer.ttl`       | Developer role definition                             |
| `roles/researcher.ttl`      | Researcher role definition                            |
| `users/user-default.ttl`    | Default user preferences                              |

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_engine.py -v

# Single test
python -m pytest tests/test_engine.py::test_function_name -v

# Lint
ruff check safeclaw/ tests/
ruff format --check safeclaw/ tests/
```

## License

MIT
