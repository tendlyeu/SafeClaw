# NemoClaw Support for SafeClaw

**Date:** 2026-03-26
**Status:** Approved

## Overview

Add first-class NemoClaw support to SafeClaw so it works inside NemoClaw sandboxes and reasons about NemoClaw's infrastructure policies (network allowlists, filesystem restrictions) as part of its semantic governance decisions.

NemoClaw and SafeClaw are complementary layers: NemoClaw provides OS-level sandboxing (Landlock, seccomp, network namespaces), SafeClaw provides ontology-based semantic governance (OWL/SHACL). Together, an agent gets infrastructure enforcement AND human-readable policy reasoning.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration depth | SafeClaw reads NemoClaw policies and incorporates into governance | Agents get semantic explanations for infra blocks, not raw OS denials |
| Service deployment | Flexible — host-side or embedded | Matches existing embedded/remote mode split |
| Policy ingestion | Import at startup, re-ingest on hot-reload | Simple, matches existing TTL loading pattern |
| Extension mechanism | Policy preset only (no blueprint component) | Decoupled, stable, easy to contribute upstream; NemoClaw blueprints are still alpha |

## Architecture

```
+---------------------------------------------+
|  NemoClaw Sandbox                           |
|  +---------------+   +-------------------+  |
|  |   OpenClaw     |   | SafeClaw Plugin   |  |
|  |   Agent        |-->| (hooks)           |--+--> SafeClaw Service (host or remote)
|  +---------------+   +-------------------+  |
|                                             |
|  /sandbox/.openclaw (read-only)             |
|  /sandbox/.openclaw-data (read-write)       |
+---------------------------------------------+
         |
         | NemoClaw policy YAML
         v
+---------------------------------------------+
|  SafeClaw Service (host-side or embedded)   |
|  +------------------+                       |
|  | NemoPolicy Loader |-->  Knowledge Graph  |
|  | (YAML -> Turtle)  |   (existing triples  |
|  +------------------+    + NemoClaw rules)  |
|                                             |
|  9-step pipeline:                           |
|  Step 5 (policy check) extended with        |
|  new NemoClaw-specific check methods        |
+---------------------------------------------+
```

Two deployment modes (matching existing embedded/remote split):
- **Host-side service** — plugin in sandbox calls out via network allowlist. Service reads NemoClaw policy YAML from `~/.nemoclaw/` on the host.
- **Embedded in sandbox** — service runs inside container, reads policy YAML from mounted paths.

## Components

### 1. NemoClaw Policy Loader

**File:** `safeclaw-service/safeclaw/nemoclaw/policy_loader.py`

**New dependency:** `pyyaml` — add to `pyproject.toml` under `[project.dependencies]`.

New module that reads NemoClaw's YAML policy files and converts them to Turtle triples in SafeClaw's knowledge graph.

**Input:** NemoClaw policy YAML files (`openclaw-sandbox.yaml`, preset files).

**Output:** RDF triples inserted into the existing `KnowledgeGraph` instance.

**Mapping rules:**

| NemoClaw YAML | SafeClaw Turtle |
|---------------|-----------------|
| Network allow rule (host, port, protocol) | `sp:NemoNetworkRule` instance with `sp:allowsHost`, `sp:allowsPort`, `sp:allowsProtocol`, `sp:source "nemoclaw"`, and auto-generated `sp:reason` |
| Network deny rule | No triple generated (deny-by-default; absence = denied) |
| Binary-level restriction (e.g., only git can reach github.com) | `sp:binaryRestriction` property on the rule. SafeClaw maps this to tool names where possible (e.g., git binary -> `exec` tool with `git` command pattern). Exact binary enforcement stays with NemoClaw. |
| Filesystem read-only path | `sp:NemoFilesystemRule` instance with `sp:path`, `sp:accessMode "read-only"`, `sp:source "nemoclaw"`, and auto-generated `sp:reason` |
| Filesystem read-write path | `sp:NemoFilesystemRule` instance with `sp:path`, `sp:accessMode "read-write"`, `sp:source "nemoclaw"`, and auto-generated `sp:reason` |
| Filesystem denied path | `sp:NemoFilesystemRule` instance with `sp:path`, `sp:accessMode "denied"`, `sp:source "nemoclaw"`, and auto-generated `sp:reason` |

**Auto-generated `sp:reason` examples:**
- `"NemoClaw: host github.com allowed on port 443 (https)"`
- `"NemoClaw: /usr is read-only (Landlock filesystem policy)"`
- `"NemoClaw: /sandbox is read-write"`

These reasons appear in context builder output (which queries `sp:reason` on constraints) and in audit log block justifications.

**Lifecycle:**
- Called during `FullEngine._init_components()` after `kg.load_directory()` and before checker instantiation
- Called during `FullEngine._reload_kg_components()` after `new_kg.load_directory()` and before new checker creation
- Skipped silently when no NemoClaw policy directory is found

**Binary-level restriction caveat:** NemoClaw can restrict network access per-binary (e.g., only `/usr/bin/git` can reach `github.com`). SafeClaw sees tool calls at the semantic level (`tool_name: "exec"`, `params: { command: "git push" }`), not which OS binary runs. SafeClaw maps these where possible (git command -> git binary rule) but does not replicate the OS-level binary enforcement. NemoClaw still handles that.

### 2. NemoClaw Ontology

**File:** `safeclaw-service/safeclaw/ontologies/nemoclaw-policy.ttl`

New Turtle file defining NemoClaw-specific classes and properties:

```turtle
@prefix sp: <http://safeclaw.uku.ai/ontology/policy#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# --- NemoClaw Network Rule ---
sp:NemoNetworkRule a owl:Class ;
    rdfs:subClassOf sp:Constraint ;
    rdfs:label "NemoClaw Network Rule" ;
    rdfs:comment "An allowed network endpoint from NemoClaw sandbox policy" .

sp:allowsHost a owl:DatatypeProperty ;
    rdfs:domain sp:NemoNetworkRule ;
    rdfs:range xsd:string ;
    rdfs:label "allowed host" .

sp:allowsPort a owl:DatatypeProperty ;
    rdfs:domain sp:NemoNetworkRule ;
    rdfs:range xsd:integer ;
    rdfs:label "allowed port" .

sp:allowsProtocol a owl:DatatypeProperty ;
    rdfs:domain sp:NemoNetworkRule ;
    rdfs:range xsd:string ;
    rdfs:label "allowed protocol" .

sp:binaryRestriction a owl:DatatypeProperty ;
    rdfs:domain sp:NemoNetworkRule ;
    rdfs:range xsd:string ;
    rdfs:label "binary restriction" .

# --- NemoClaw Filesystem Rule ---
sp:NemoFilesystemRule a owl:Class ;
    rdfs:subClassOf sp:Constraint ;
    rdfs:label "NemoClaw Filesystem Rule" ;
    rdfs:comment "A filesystem access rule from NemoClaw sandbox policy" .

sp:path a owl:DatatypeProperty ;
    rdfs:domain sp:NemoFilesystemRule ;
    rdfs:range xsd:string ;
    rdfs:label "filesystem path" .

sp:accessMode a owl:DatatypeProperty ;
    rdfs:domain sp:NemoFilesystemRule ;
    rdfs:range xsd:string ;
    rdfs:label "access mode" ;
    rdfs:comment "Values: read-only, read-write, denied" .

# --- Provenance ---
sp:source a owl:DatatypeProperty ;
    rdfs:domain sp:Constraint ;
    rdfs:range xsd:string ;
    rdfs:label "policy source" ;
    rdfs:comment "Origin of this constraint (e.g., 'nemoclaw', 'manual', 'nl-compiler')" .
```

### 3. PolicyChecker NemoClaw Extensions

**File:** `safeclaw-service/safeclaw/constraints/policy_checker.py`

The existing PolicyChecker uses hardcoded SPARQL queries that match specific properties (`sp:forbiddenPathPattern`, `sp:forbiddenCommandPattern`, `sp:appliesTo`) on `sp:Prohibition` instances. It does NOT generically evaluate all `sp:Constraint` subclasses. NemoClaw rules use different properties and inverted semantics (allowlist, not denylist).

**New methods to add:**

**`_check_nemo_network_rules(action)`** — Allowlist check for network-affecting tool calls.

Trigger condition: tool call is classified as `WebFetch`, `WebSearch`, or `ExecuteCommand` where the command contains `curl`, `wget`, `fetch`, or `http`.

URL/host extraction from tool call parameters:
- For `WebFetch`/`WebSearch`: extract from `params["url"]` or `params["endpoint"]`
- For `ExecuteCommand`: regex-extract URLs from `params["command"]` string
- Parse URL with `urllib.parse.urlparse()` to get host, port, scheme
- Default ports: 443 for https, 80 for http (when URL has no explicit port)

SPARQL query:
```sparql
PREFIX sp: <{SP}>
SELECT ?rule ?host ?port ?protocol WHERE {
    ?rule a sp:NemoNetworkRule ;
          sp:allowsHost ?host .
    OPTIONAL { ?rule sp:allowsPort ?port }
    OPTIONAL { ?rule sp:allowsProtocol ?protocol }
}
```

Matching logic (allowlist — inverted from existing denylist):
1. Query returns all allowed (host, port, protocol) tuples
2. If no NemoClaw network rules exist in graph, skip (not running with NemoClaw)
3. Match extracted host against `sp:allowsHost` (exact match or wildcard suffix like `*.github.com`)
4. If port specified on rule, match against extracted port; if omitted, any port allowed
5. If protocol specified on rule, match against extracted scheme; if omitted, any protocol allowed
6. If NO matching rule found: block with reason `"Not in NemoClaw network allowlist: {host}:{port}"`
7. If matching rule found: pass

**`_check_nemo_filesystem_rules(action)`** — Check file operations against NemoClaw filesystem policy.

Trigger condition: tool call is classified as `FileWrite`, `FileDelete`, `FileCreate`, or `FileRead`.

Path extraction: from `params["path"]` or `params["file_path"]` (using existing `PATH_PARAM_KEYS`).

SPARQL query:
```sparql
PREFIX sp: <{SP}>
SELECT ?rule ?path ?mode WHERE {
    ?rule a sp:NemoFilesystemRule ;
          sp:path ?path ;
          sp:accessMode ?mode .
}
```

Matching logic (prefix-based, matching NemoClaw's Landlock behavior):
1. Query returns all (path, accessMode) tuples
2. If no NemoClaw filesystem rules exist in graph, skip
3. Find the most specific (longest) rule path that is a prefix of the target file path
4. Check access mode:
   - `"read-write"`: allow reads and writes
   - `"read-only"`: allow reads, block writes/deletes/creates with reason `"NemoClaw filesystem policy: {path} is read-only"`
   - `"denied"`: block all access with reason `"NemoClaw filesystem policy: {path} is denied"`
5. If no matching rule path is a prefix: block with reason `"Path {target} is outside NemoClaw sandbox filesystem policy"`

**Integration point:** These methods are called from the existing `check_policies()` method, after the current denylist checks. They are only called when `nemoclaw_enabled` is true (checked via config passed to PolicyChecker constructor).

### 4. Sandbox-Aware Plugin Config

**File:** `openclaw-safeclaw-plugin/tui/config.ts`

Update `loadConfig()` to detect NemoClaw sandbox:

- Check `OPENSHELL_SANDBOX` env var to detect sandbox environment
- Default service URL to `host.containers.internal:8420` when inside sandbox
- Graceful handling when `~/.safeclaw/config.json` is on read-only filesystem (catch write errors, fall back to env vars)
- No crash, no error — just log and use defaults

### 5. NemoClaw Policy Preset

**File:** `openclaw-safeclaw-plugin/policies/safeclaw.yaml`

YAML file for NemoClaw's `policy-add` system:

```yaml
# SafeClaw governance service egress policy
# Compatible with NemoClaw 0.1.x policy format
# Apply with: nemoclaw policy-add safeclaw
rules:
  - name: safeclaw-remote
    host: "api.safeclaw.eu"
    port: 443
    protocol: https
    allow: true
  - name: safeclaw-host-local
    host: "host.containers.internal"
    port: 8420
    protocol: http
    allow: true
```

### 6. NemoClaw Detection in CLI/TUI

**Files:** `openclaw-safeclaw-plugin/cli.tsx`, `openclaw-safeclaw-plugin/tui/Status.tsx`

`safeclaw-plugin status`:
- Detect NemoClaw sandbox (check `OPENSHELL_SANDBOX` env var)
- Show sandbox name, policy preset status
- Adjust connection checks for sandbox networking

TUI Status tab:
- Add NemoClaw section when running inside sandbox
- Show sandbox status, policy preset applied

`safeclaw-plugin connect`:
- Inside sandbox, skip OpenClaw registration (already migrated by NemoClaw)
- Adjust handshake URL for sandbox networking

### 7. Engine Integration Points

**File:** `safeclaw-service/safeclaw/engine/full_engine.py`

Two methods must be modified to call the NemoClaw policy loader:

**`_init_components()` (line ~110):** After `self.kg.load_directory(ontology_dir)`, add:
```python
if self.config.nemoclaw_enabled:
    from safeclaw.nemoclaw.policy_loader import NemoClawPolicyLoader
    loader = NemoClawPolicyLoader(self.config.nemoclaw_policy_dir)
    loader.load(self.kg)
```

**`_reload_kg_components()` (line ~245):** After `new_kg.load_directory(ontology_dir)` and before checker instantiation, add the same loader call on `new_kg`.

The NemoClaw triples must be in the graph BEFORE the PolicyChecker is constructed, since the checker may cache rule sets at init time.

## Data Flow

### Startup

1. `SafeClawConfig` resolves NemoClaw policy directory (see auto-detection below)
2. `FullEngine._init_components()`:
   a. `KnowledgeGraph.load_directory()` loads existing TTL files (including `nemoclaw-policy.ttl` schema)
   b. If `nemoclaw_enabled`: `NemoClawPolicyLoader.load(kg)` reads YAML, generates and inserts triples
   c. Checkers are instantiated with the now-complete knowledge graph
3. Pipeline is ready — NemoClaw rules are queryable alongside existing ontology triples

### Tool Call Evaluation

1. Plugin sends tool call to service (same as today)
2. Steps 1-4 run as usual (agent governance, classification, RBAC, SHACL)
3. Step 5 (policy check):
   a. Existing denylist checks run (forbiddenPathPattern, forbiddenCommandPattern)
   b. If `nemoclaw_enabled`: `_check_nemo_network_rules()` runs for network-affecting actions
   c. If `nemoclaw_enabled`: `_check_nemo_filesystem_rules()` runs for file-affecting actions
4. Block with semantic explanation if any check violates

### Hot-Reload

- `POST /api/v1/reload` triggers `_reload_kg_components()`
- TTL files reloaded, then NemoClaw YAML re-ingested into the fresh graph
- New checkers instantiated with updated rules
- NemoClaw's `policy-add`/`policy-remove` changes picked up

## Configuration

New `SafeClawConfig` fields:

```python
nemoclaw_enabled: bool = False          # auto-detected or explicit
nemoclaw_policy_dir: Path | None = None # resolved via fallback chain below
```

New env vars:

```
SAFECLAW_NEMOCLAW_ENABLED=true
SAFECLAW_NEMOCLAW_POLICY_DIR=/path/to/nemoclaw/policies
```

**Policy directory resolution** (separate from the enabled flag):

When `nemoclaw_enabled` is true but `nemoclaw_policy_dir` is not set, resolve via fallback chain:
1. `SAFECLAW_NEMOCLAW_POLICY_DIR` env var (if set)
2. `~/.nemoclaw/` (if it exists and contains `.yaml` files)
3. Sandbox policy mount paths (if `OPENSHELL_SANDBOX` is set)
4. If none found: log warning "NemoClaw enabled but no policy directory found", proceed with no NemoClaw rules

**Auto-detection of `nemoclaw_enabled`** (when not explicitly set):
1. If `SAFECLAW_NEMOCLAW_ENABLED=true`, enable
2. Else if policy directory resolution (above) finds a valid directory, enable
3. Else disabled — skip silently

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No NemoClaw policy dir found | Silently skip, no NemoClaw triples loaded |
| NemoClaw enabled but no dir resolved | Log warning, proceed without NemoClaw rules |
| Malformed YAML file | Log warning with filename, skip that file, continue loading others |
| Unknown YAML rule format | Log warning with rule details, skip rule, continue |
| Network unreachable from sandbox | Plugin's existing fail-open/fail-closed logic |
| Read-only config file in sandbox | Plugin falls back to env vars, logs info |
| `pyyaml` not installed | Import error caught, log warning, NemoClaw loading disabled |

## Docker Considerations

The existing `docker-compose.yml` can optionally mount `~/.nemoclaw/` for NemoClaw policy ingestion:

```yaml
volumes:
  - ~/.nemoclaw:/nemoclaw-policies:ro  # optional
environment:
  - SAFECLAW_NEMOCLAW_POLICY_DIR=/nemoclaw-policies
```

This is opt-in. Without the mount, NemoClaw support is simply disabled.

## Testing

- **Unit tests for `NemoClawPolicyLoader`**: YAML-to-Turtle conversion, edge cases (empty rules, missing files, malformed YAML), provenance (`sp:source "nemoclaw"`) and `sp:reason` generation
- **Unit tests for `_check_nemo_network_rules`**: allowlist matching (exact host, port defaulting, protocol matching, wildcard hosts, no rules = skip, no match = block)
- **Unit tests for `_check_nemo_filesystem_rules`**: prefix matching (most-specific wins, read-only blocks writes, read-write allows writes, denied blocks all, no rules = skip)
- **SPARQL round-trip test**: load YAML, generate triples, run the actual SPARQL queries the checker uses, verify results
- **Unit tests for sandbox detection**: env var detection, service URL adjustment, read-only config fallback
- **Integration test**: tool call blocked by NemoClaw network rule via policy checker
- **Integration test**: tool call blocked by NemoClaw filesystem rule
- **Integration test**: hot-reload picks up new NemoClaw policy
- **Integration test**: NemoClaw rules appear in context builder output (via `sp:reason`)
- **Existing tests unaffected**: NemoClaw loading skipped when no policy dir found
