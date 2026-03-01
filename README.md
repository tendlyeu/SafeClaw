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
│   └── tests/                     # 330 tests
├── openclaw-safeclaw-plugin/      # TypeScript bridge for OpenClaw
│   ├── index.ts                   # Plugin hooks (~80 lines)
│   └── SKILL.md                   # ClawHub distribution docs
└── safeclaw-landing/              # FastHTML landing site + user dashboard
    ├── main.py                    # Routes, docs page, landing page
    ├── db.py                      # SQLite user/key models
    └── dashboard/                 # Dashboard pages (onboard, keys, prefs, agents)
```

## Quick Start

### Hosted (recommended)

Sign up at [safeclaw.eu](https://safeclaw.eu), get your API key from the onboarding wizard, then:

```bash
npm install -g openclaw-safeclaw-plugin
safeclaw connect sc_your_key_here
```

`safeclaw connect` writes your key to `~/.safeclaw/config.json` — no environment variables needed.

### Self-hosted

```bash
cd safeclaw-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

safeclaw init --user-id yourname
safeclaw serve
# → http://localhost:8420
```

Then install and connect the plugin:

```bash
npm install -g openclaw-safeclaw-plugin
safeclaw connect sc_your_key --service-url http://localhost:8420/api/v1
```

## What it does

- **Blocks dangerous actions** - force push, deleting root, exposing secrets
- **Enforces dependencies** - tests must pass before git push
- **Checks user preferences** - confirmation for irreversible actions
- **Governs messages** - blocks sensitive data leaks, enforces contact rules
- **Full audit trail** - every decision logged with ontological justification

## Constraint Pipeline

Every action passes through a 9-step validation:

1. Agent Governance (token auth, kill switch, delegation detection)
2. Action Classification (OWL reasoning + LLM)
3. Role-Based Access (allowed/denied actions and resources)
4. SHACL Shape Validation
5. Policy Check
6. Preference Check
7. Dependency Check
8. Temporal + Rate Limit
9. Derived Rules

## Running Tests

```bash
cd safeclaw-service
source .venv/bin/activate
python -m pytest tests/ -v
```

## License

MIT
