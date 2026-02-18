# SafeClaw Full Codebase Review — Findings & Fix Plans

**Date:** 2026-02-18
**Scope:** All files in safeclaw-service/ and openclaw-safeclaw-plugin/
**Tests at start:** 207 passing

---

## CRITICAL

### F-01: knowledge_graph.py:7-9 — Namespace mismatch with role ontology files

**Problem:** `knowledge_graph.py` defines namespaces as `http://safeclaw.ai/ontology/...` but the role `.ttl` files use `http://safeclaw.uku.ai/ontology/...`. The two agent/policy ontology files (`safeclaw-agent.ttl`, `safeclaw-policy.ttl`) need to be checked as well. If namespaces don't match, SPARQL queries will silently return no results for role-based data.

**Fix plan:** Standardize ALL namespace URIs to `http://safeclaw.uku.ai/ontology/...` across:
- `safeclaw/engine/knowledge_graph.py` lines 7-9 (SC, SP, SU)
- `safeclaw/constraints/action_classifier.py` line 8 (SC)
- `safeclaw/engine/context_builder.py` line 5 (import SP, SU)
- Verify `safeclaw-agent.ttl` and `safeclaw-policy.ttl` use `safeclaw.uku.ai`
- Verify `user-default.ttl` uses `safeclaw.uku.ai`
- Verify shapes/ `.ttl` files use `safeclaw.uku.ai`

### F-02: config.py — SafeClawConfig has no `raw` attribute

**Problem:** `full_engine.py:94` does `config.raw if hasattr(config, 'raw')` but `SafeClawConfig` (pydantic-settings BaseSettings) has no `raw` field. This means the multi-agent config (roles, delegation policy, requireTokenAuth) is NEVER loaded from config. Everything silently uses defaults.

**Fix plan:** Add a `raw` property or classmethod to `SafeClawConfig` that loads `~/.safeclaw/config.json` and returns the raw dict. Or better: load config_template defaults and merge in the pydantic settings, then pass as dict. In `config.py`, add:
```python
@property
def raw(self) -> dict:
    from safeclaw.config_template import load_config
    return load_config(self.data_dir / "config.json")
```

---

## HIGH

### F-03: main.py:40-44 — CORS allows all origins

**Problem:** `allow_origins=["*"]` allows any website to make cross-origin requests to the SafeClaw API. An attacker could craft a malicious webpage that calls SafeClaw endpoints if a user has the service running locally.

**Fix plan:** Default to `["http://localhost:*"]` or load allowed origins from config. In `main.py`, change to:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins if hasattr(config, 'cors_origins') else ["http://localhost:8420"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Requires moving `config` to module scope or reading it in lifespan and patching CORS.

### F-04: routes.py — No auth on sensitive agent endpoints

**Problem:** `/agents/register`, `/agents/{id}/kill`, `/agents/{id}/revive`, `/reload`, `/agents/{id}/temp-grant` have no authentication. Anyone on the network can register rogue agents, kill legitimate agents, or reload ontologies. The `APIKeyAuthMiddleware` exists but isn't applied to these routes.

**Fix plan:** The `APIKeyAuthMiddleware` in `auth/middleware.py` already exists and is wired up when `require_auth=True`. Ensure it covers these endpoints. Additionally, the kill/revive/temp-grant endpoints should require admin-level auth. Add path prefix checks or use FastAPI dependency injection for auth on the agent management routes.

### F-05: multi_agent.py — Dead code (superseded by agent_registry.py)

**Problem:** `MultiAgentGovernor` in `multi_agent.py` is not used by any route or engine. It was superseded by `AgentRegistry` in `agent_registry.py`. Tests in `test_phase6.py` still test it, but it's unreachable from production code. This creates confusion about which module manages agents.

**Fix plan:** Either:
- (a) Delete `multi_agent.py` and move the `test_phase6.py::TestMultiAgentGovernor` tests to a legacy/deprecated test file, OR
- (b) Merge useful features (like `get_effective_constraints` which merges parent-child overrides) into `agent_registry.py` and delete the original.
Option (b) is preferred. Then remove the file and update imports.

### F-06: hybrid_engine.py — Doesn't send agent_id/agent_token to remote

**Problem:** `HybridEngine.evaluate_tool_call()` builds the JSON body without `agentId` or `agentToken` fields (lines 80-86). Same for `evaluate_message` and `build_context`. In hybrid mode, the remote service never knows which agent is making the request, so all multi-agent governance is bypassed.

**Fix plan:** Add `"agentId": event.agent_id` and `"agentToken": event.agent_token` to all JSON bodies in `hybrid_engine.py` for `evaluate_tool_call`, `evaluate_message`, `build_context`, and `record_action_result`.

### F-07: audit/logger.py:25 — Path traversal via session_id

**Problem:** `_get_session_file()` uses `session_id` directly in the filename: `f"session-{session_id}.jsonl"`. A malicious session_id like `../../etc/evil` could write files outside the audit directory.

**Fix plan:** Sanitize session_id before using in filename. Replace unsafe characters:
```python
safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)
return day_dir / f"session-{safe_id}.jsonl"
```
Add `import re` at top of file.

---

## MEDIUM

### F-08: context_builder.py:80-88 — SPARQL injection risk

**Problem:** `_get_user_preferences()` strips `\`, `"`, `'` from user_id but doesn't strip `}`, `#`, `{`, `;` which could break or manipulate the SPARQL query. A user_id like `foo") . ?x ?y ?z } #` could inject arbitrary SPARQL.

**Fix plan:** Use parameterized SPARQL or a stricter allowlist. Replace the FILTER with a safer approach:
```python
safe_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id)
```
Add `import re` to imports.

### F-09: cached_engine.py — Bypasses all agent governance

**Problem:** `CachedEngine` always returns `Decision(block=False)` for all actions. When the hybrid engine falls back to local mode, a killed agent or a researcher-role agent could execute any action without restriction.

**Fix plan:** Add basic agent checks to `CachedEngine.evaluate_tool_call()`: at minimum, check the kill switch and role-based action allow/deny. This requires `CachedEngine` to accept an `AgentRegistry` and `RoleManager` in its constructor.

### F-10: delegation_detector.py — No max size for _blocks list

**Problem:** `_blocks` list is only pruned when `record_block()` or `check_delegation()` is called. In a scenario with many blocks and infrequent checks, the list could grow unbounded. `_prune_expired()` does time-based pruning but no size cap.

**Fix plan:** Add `MAX_BLOCKS = 10000` constant and cap the list size in `record_block()`:
```python
if len(self._blocks) > MAX_BLOCKS:
    self._blocks = self._blocks[-MAX_BLOCKS:]
```

### F-11: routes.py:165 — `format` parameter shadows Python built-in

**Problem:** The parameter name `format` in `audit_report()` shadows Python's built-in `format()` function. While not a bug (it's scoped to the function), it's a code smell and linter warning.

**Fix plan:** Rename to `report_format` or `fmt`:
```python
async def audit_report(session_id: str, fmt: str = Query("markdown", alias="format")):
```
Then update usages of `format` to `fmt` within the function body.

### F-12: full_engine.py:137-142 — Duplicate make_signature call

**Problem:** In `evaluate_tool_call()`, `DelegationDetector.make_signature(event.params)` is called at line 137, then again at lines 160 and 172 via `DelegationDetector.make_signature(event.params)`. The signature is re-computed for the same params up to 3 times.

**Fix plan:** Compute `params_sig` once at the top of the method (after the `if event.agent_id` check on line 126) and reuse it. Move line 137 up and use the cached `params_sig` variable in lines 158-161 and 170-173 instead of recomputing.

### F-13: roles.py:92 — Default role is "researcher" not "developer"

**Problem:** `get_default_role()` returns the "researcher" role as fallback, but `config_template.py:54` specifies `"defaultRole": "developer"`. The config value is never read by `RoleManager`.

**Fix plan:** Read `defaultRole` from config in `RoleManager.__init__`:
```python
self._default_role_name = "developer"
if config and "roles" in config:
    self._default_role_name = config["roles"].get("defaultRole", "developer")
```
Then in `get_default_role()`:
```python
return self._roles.get(self._default_role_name, BUILTIN_ROLES["developer"])
```

### F-14: roles.py:69-84 — Config keys don't match config_template format

**Problem:** `RoleManager.__init__` reads `rdef.get("enforcement_mode")` and `rdef.get("autonomy_level")` (snake_case), but `config_template.py` uses `"enforcement"` and `"autonomyLevel"` (camelCase) in the role definitions. So config-based role loading silently fails and falls through to builtins.

**Fix plan:** Update `RoleManager.__init__` to read both formats:
```python
enforcement_mode=rdef.get("enforcement_mode", rdef.get("enforcement", "enforce")),
autonomy_level=rdef.get("autonomy_level", rdef.get("autonomyLevel", "supervised")),
```

---

## LOW

### F-15: Test files organized by phase rather than feature

**Problem:** Tests are in `test_phase2.py`, `test_phase3.py`, etc. This makes it hard to find tests for a specific module. Someone looking for rate limiter tests has to know it was added in Phase 2.

**Fix plan:** No immediate fix needed. For future tests, prefer feature-based names (e.g., `test_rate_limiter.py`, `test_message_gate.py`). Consider reorganizing in a future cleanup.

### F-16: TypeScript plugin doesn't validate agentId/agentToken consistency

**Problem:** If `agentToken` is set but `agentId` is empty, the token is sent to the server for no agent. No harm, but wasteful.

**Fix plan:** In `index.ts`, only include agent fields when both are set:
```typescript
const agentFields = config.agentId ? { agentId: config.agentId, agentToken: config.agentToken } : {};
body: JSON.stringify({ ...body, ...agentFields }),
```

### F-17: knowledge_store.py and audit/logger.py both use JSONL

**Problem:** Both modules write JSONL files but use completely different patterns (knowledge_store uses a single file with line-by-line records; audit uses daily-rotated per-session files). No actual conflict, but inconsistent patterns.

**Fix plan:** Document the different patterns. No code change needed.

### F-18: Ontology roles/ .ttl files have no OWL import declarations

**Problem:** The role `.ttl` files reference classes like `sc:ReadFile` and `sp:Role` but don't declare `owl:imports` to the base ontologies. This means the role files are only valid when loaded alongside the main ontologies (which SafeClaw does), but they're not self-describing.

**Fix plan:** Add `owl:imports` triples to each role `.ttl` file:
```turtle
<http://safeclaw.uku.ai/ontology/roles/researcher> owl:imports
    <http://safeclaw.uku.ai/ontology/agent> ,
    <http://safeclaw.uku.ai/ontology/policy> .
```

---

## Fix Dependency Order (non-conflicting)

Apply fixes in this order to avoid conflicts:

1. **F-01** (namespace mismatch) — touches knowledge_graph.py, action_classifier.py, .ttl files
2. **F-02** (config.raw) — touches config.py only
3. **F-14** (roles config keys) — touches roles.py only
4. **F-13** (default role) — touches roles.py only (same file as F-14, do together)
5. **F-08** (SPARQL injection) — touches context_builder.py only
6. **F-07** (path traversal) — touches audit/logger.py only
7. **F-11** (format shadow) — touches routes.py only
8. **F-04** (auth on endpoints) — touches routes.py only (same file as F-11, do together)
9. **F-03** (CORS) — touches main.py only
10. **F-06** (hybrid agent_id) — touches hybrid_engine.py only
11. **F-12** (duplicate make_signature) — touches full_engine.py only
12. **F-10** (delegation max blocks) — touches delegation_detector.py only
13. **F-05** (dead multi_agent.py) — delete file + update tests
14. **F-09** (cached engine) — touches cached_engine.py only
15. **F-16** (TS plugin) — touches index.ts only
16. **F-18** (TTL imports) — touches role .ttl files only

No two consecutive fixes touch the same file (except where noted to do together).
