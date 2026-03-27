# Configuration Reference

SafeClaw uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for configuration. All fields can be set via environment variables with the `SAFECLAW_` prefix.

## SafeClawConfig Fields

### Server

| Field               | Env Variable              | Type   | Default        | Description                                      |
|---------------------|---------------------------|--------|----------------|--------------------------------------------------|
| `host`              | `SAFECLAW_HOST`           | `str`  | `"127.0.0.1"`  | Bind address for the FastAPI server              |
| `port`              | `SAFECLAW_PORT`           | `int`  | `8420`         | Bind port for the FastAPI server                 |
| `cors_origin_regex` | `SAFECLAW_CORS_ORIGIN_REGEX` | `str` | `r"https?://localhost:\d+$"` | Regex for allowed CORS origins |
| `log_level`         | `SAFECLAW_LOG_LEVEL`      | `str`  | `"INFO"`       | Python logging level                             |

### Paths

| Field           | Env Variable                | Type          | Default              | Description                                                  |
|-----------------|-----------------------------|---------------|----------------------|--------------------------------------------------------------|
| `data_dir`      | `SAFECLAW_DATA_DIR`         | `Path`        | `~/.safeclaw`        | Root data directory for config, audit logs, and state DB     |
| `ontology_dir`  | `SAFECLAW_ONTOLOGY_DIR`     | `Path | None` | `None` (bundled)     | Custom ontology directory. When `None`, uses bundled ontologies from `safeclaw/ontologies/` |
| `audit_dir`     | `SAFECLAW_AUDIT_DIR`        | `Path | None` | `None` (data_dir/audit) | Custom audit log directory. When `None`, uses `data_dir/audit` |
| `db_path`       | `SAFECLAW_DB_PATH`          | `str`         | `""`                 | Path to shared SQLite DB (SaaS mode)                         |

### Authentication

| Field            | Env Variable               | Type   | Default | Description                                                    |
|------------------|----------------------------|--------|---------|----------------------------------------------------------------|
| `require_auth`   | `SAFECLAW_REQUIRE_AUTH`    | `bool` | `False` | When `True`, all requests must include a valid API key         |
| `admin_password` | `SAFECLAW_ADMIN_PASSWORD`  | `str`  | `""`    | Admin password for dashboard and admin endpoints. Should be a bcrypt hash (`$2b$...`). When empty, admin endpoints are open (local dev mode). |

### Dashboard Admin

| Field | Env Variable | Type | Default | Description |
|-------|-------------|------|---------|-------------|
| — | `SAFECLAW_ADMINS` | `str` | `""` | Comma-separated GitHub logins who are always admin in the landing dashboard (e.g., `henrikaavik,marekkask`). These users cannot be demoted via the UI. When empty, the first registered user becomes admin automatically. |

### NemoClaw Integration

| Field                | Env Variable                   | Type          | Default | Description                                           |
|----------------------|--------------------------------|---------------|---------|-------------------------------------------------------|
| `nemoclaw_enabled`   | `SAFECLAW_NEMOCLAW_ENABLED`    | `bool`        | `False` | Explicitly enable NemoClaw policy loading              |
| `nemoclaw_policy_dir`| `SAFECLAW_NEMOCLAW_POLICY_DIR` | `Path | None` | `None`  | Directory containing NemoClaw YAML policy files        |

### LLM Layer

All LLM features are gated on `mistral_api_key`. When the key is empty, the LLM layer is completely disabled (no external API calls are made).

| Field                          | Env Variable                              | Type   | Default                  | Description                                    |
|--------------------------------|-------------------------------------------|--------|--------------------------|------------------------------------------------|
| `mistral_api_key`              | `SAFECLAW_MISTRAL_API_KEY`                | `str`  | `""`                     | Mistral API key. Empty disables all LLM features. |
| `mistral_model`                | `SAFECLAW_MISTRAL_MODEL`                  | `str`  | `"mistral-small-latest"` | Model for lightweight LLM tasks                |
| `mistral_model_large`          | `SAFECLAW_MISTRAL_MODEL_LARGE`            | `str`  | `"mistral-large-latest"` | Model for complex LLM tasks (policy compilation) |
| `mistral_timeout_ms`           | `SAFECLAW_MISTRAL_TIMEOUT_MS`             | `int`  | `3000`                   | Timeout in milliseconds for LLM API calls      |
| `llm_security_review_enabled`  | `SAFECLAW_LLM_SECURITY_REVIEW_ENABLED`   | `bool` | `True`                   | Enable LLM-powered security review of tool calls |
| `llm_classification_observe`   | `SAFECLAW_LLM_CLASSIFICATION_OBSERVE`     | `bool` | `True`                   | Enable LLM classification observer (suggestions) |

## NemoClaw Auto-Detection

When `nemoclaw_enabled` is `False` (the default), SafeClaw still activates NemoClaw if it detects a policy directory. The `is_nemoclaw_enabled` property returns `True` when:

1. `nemoclaw_enabled` is explicitly `True`, **or**
2. `get_nemoclaw_policy_dir()` finds a valid directory.

The directory resolution follows this fallback chain:

1. `nemoclaw_policy_dir` config field (if set and the directory exists)
2. `~/.nemoclaw/` (if it exists and contains `*.yaml` files)
3. `$OPENSHELL_SANDBOX/policies/` (if the `OPENSHELL_SANDBOX` env var is set and the `policies/` subdirectory exists)

If none of these resolve, NemoClaw remains disabled.

## Data Directory Structure

```
~/.safeclaw/
├── config.json              # Runtime configuration (generated by `safeclaw init`)
├── governance_state.db      # SQLite database for persistent governance state
├── audit/                   # Append-only JSONL audit logs
│   ├── 2026-03-26.jsonl     # One file per day
│   └── ...
├── ontologies/              # User-supplied ontology overrides (optional)
│   └── users/               # Per-user preference Turtle files
│       └── user-yourname.ttl
└── llm/                     # LLM layer data (when Mistral key is configured)
    └── classification_suggestions.jsonl
```

### Key files

- **config.json**: Generated by `safeclaw init --user-id <name>`. Contains user ID, agent configuration, delegation policy, and role definitions. Read by both the Python service and the TypeScript plugin.
- **governance_state.db**: SQLite database managed by `StateStore`. Contains tables for agent kills, rate-limit counters, and temporary permission grants. Created automatically on first service start.
- **audit/*.jsonl**: Append-only audit log files. Each line is a JSON `DecisionRecord` with full justification. One file per UTC day.

## Admin Password Format

The `admin_password` field supports two formats:

- **Bcrypt hash** (recommended): A string starting with `$2b$`. Verified via `bcrypt.checkpw()`.
- **Plaintext** (legacy, migration path): Any other non-empty string. Verified via `secrets.compare_digest()` for constant-time comparison.

To generate a bcrypt hash:

```python
import bcrypt
hashed = bcrypt.hashpw(b"your-password", bcrypt.gensalt()).decode()
print(hashed)  # Use this value for SAFECLAW_ADMIN_PASSWORD
```

## API Key Format

API keys use the `sc_` prefix followed by 32 URL-safe random bytes:

```
sc_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8
```

Keys are hashed with bcrypt before storage. Legacy SHA-256 hashes are accepted as a fallback for keys created before the bcrypt migration.
