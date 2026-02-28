# SafeClaw

> Built during the Mistral hackathon

Neurosymbolic governance layer for autonomous AI agents. SafeClaw validates every tool call, message, and action against OWL ontologies and SHACL constraints before execution.

## Architecture

```
SafeClaw/
├── safeclaw-service/              # Python FastAPI service (the brain)
│   ├── safeclaw/                  # Core library
│   │   ├── ontologies/            # OWL + SHACL definitions
│   │   ├── constraints/           # 9-step validation pipeline
│   │   ├── engine/                # Hybrid reasoning engine
│   │   ├── cloud/                 # Multi-tenant + API key auth
│   │   ├── api/                   # FastAPI routes
│   │   ├── audit/                 # Append-only JSONL logging
│   │   └── cli/                   # CLI commands
│   └── tests/                     # 157 tests
└── openclaw-safeclaw-plugin/      # TypeScript bridge for OpenClaw
    ├── index.ts                   # Plugin hooks (~80 lines)
    └── SKILL.md                   # ClawHub distribution docs
```

## Quick Start

### 1. Start the SafeClaw service

```bash
cd safeclaw-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Initialize config
safeclaw init --user-id yourname

# Run the service
safeclaw serve
# → http://localhost:8420
```

### 2. Install the OpenClaw plugin

The TypeScript plugin connects your OpenClaw agent to the SafeClaw service:

```bash
cd openclaw-safeclaw-plugin
npm install
npm run build
```

Or install via ClawHub (when available).

## What it does

- **Blocks dangerous actions** - force push, deleting root, exposing secrets
- **Enforces dependencies** - tests must pass before git push
- **Checks user preferences** - confirmation for irreversible actions
- **Governs messages** - blocks sensitive data leaks, enforces contact rules
- **Full audit trail** - every decision logged with ontological justification

## Constraint Pipeline

Every action passes through a 9-step validation:

1. Action Classification (OWL reasoning)
2. SHACL Shape Validation
3. Policy Check
4. Preference Check
5. Dependency Check
6. Temporal Check
7. Rate Limit
8. Derived Rules
9. Decision + Audit

## Running Tests

```bash
cd safeclaw-service
source .venv/bin/activate
python -m pytest tests/ -v
```

## License

MIT
