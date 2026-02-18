# SafeClaw Full Codebase Review — Findings & Fix Plans

**Date:** 2026-02-18
**Scope:** All files in safeclaw-service/ and openclaw-safeclaw-plugin/
**Tests at start:** 207 passing
**Reviewers:** 4 parallel agents (engine, API, multi-agent, tests)
**Validation:** All 59 findings validated against source code by 4 separate agents

### Validation Summary
- **49 CONFIRMED** — real bugs verified against actual code
- **9 PARTIALLY CORRECT** — real issues but claims adjusted (F-15, F-16, F-20, F-24, F-34, F-42, F-43, F-50, F-54)
- **1 FALSE POSITIVE** — F-36 removed (math is correct for two-state decision system)

---

## CRITICAL (6 findings)

### F-01: knowledge_graph.py:7-9 — Namespace mismatch with role ontology files

**Problem:** `knowledge_graph.py` defines namespaces as `http://safeclaw.ai/ontology/...` but the role `.ttl` files use `http://safeclaw.uku.ai/ontology/...`. If namespaces don't match, SPARQL queries will silently return no results for role-based data.

**Fix plan:** Standardize ALL namespace URIs to `http://safeclaw.uku.ai/ontology/...` across:
- `safeclaw/engine/knowledge_graph.py` lines 7-9 (SC, SP, SU)
- `safeclaw/constraints/action_classifier.py` line 8 (SC)
- `safeclaw/engine/context_builder.py` line 5 (import SP, SU)
- Verify all `.ttl` files use `safeclaw.uku.ai`

### F-02: config.py — SafeClawConfig has no `raw` attribute

**Problem:** `full_engine.py:94` does `config.raw if hasattr(config, 'raw')` but `SafeClawConfig` has no `raw` field. Multi-agent config (roles, delegation policy, requireTokenAuth) is NEVER loaded from config.

**Fix plan:** Add a `raw` property to `SafeClawConfig`:
```python
@property
def raw(self) -> dict:
    from safeclaw.config_template import load_config
    return load_config(self.data_dir / "config.json")
```

### F-03: main.py:39-44 — CORS allows all origins + auth middleware not wired up

**Problem:** `allow_origins=["*"]` with `allow_methods=["*"]` permits any website to call SafeClaw endpoints. Combined with the fact that `APIKeyAuthMiddleware` is never added to the app in `main.py`, ALL endpoints are completely unauthenticated and accessible cross-origin.

**Fix plan:** (1) Add `APIKeyAuthMiddleware` to the app in `main.py`, with `require_auth` from config (default `False` for local, `True` for cloud). (2) Replace `allow_origins=["*"]` with configurable origins, defaulting to `["http://localhost:*"]`.

### F-04: routes.py — No auth on sensitive agent/admin endpoints

**Problem:** `/agents/register`, `/agents/{id}/kill`, `/agents/{id}/revive`, `/reload`, `/agents/{id}/temp-grant`, and all audit endpoints have zero authentication. Anyone on the network can register rogue agents, kill agents, reload ontologies, or read audit data. The `/reload` endpoint reinitializes the entire engine with no audit trail.

**Fix plan:** Wire up `APIKeyAuthMiddleware`. Agent management and `/reload` should require admin-level auth. Audit endpoints should require at least read auth. Add audit logging for `/reload`.

### F-05: shacl_validator.py:55-57 — SHACL errors fail-open (silently allow all)

**Problem:** When pySHACL throws an exception, the validator returns `SHACLResult(conforms=True)`, meaning the action passes validation. This is a fail-open security issue.

**Fix plan:** Change to fail-closed:
```python
except Exception as e:
    logger.error(f"SHACL validation error: {e}")
    return SHACLResult(conforms=False, violations=[{"message": f"SHACL validation error: {e}"}])
```

### F-06: No API route tests or middleware tests exist

**Problem:** The routes module has 17 endpoints. None are tested via TestClient. `TimingMiddleware` and `APIKeyAuthMiddleware` dispatch are also untested. If endpoint wiring breaks, no test catches it.

**Fix plan:** Add `test_api.py` using FastAPI's `TestClient` covering: POST /evaluate/tool-call, POST /evaluate/message, POST /context/build, POST /agents/register, GET /health, middleware headers, and auth enforcement.

---

## HIGH (11 findings)

### F-07: audit/logger.py:25 — Path traversal via session_id

**Problem:** `_get_session_file()` uses `session_id` directly in the filename. A malicious session_id like `../../etc/evil` could write files outside the audit directory.

**Fix plan:** Sanitize: `safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)`

### F-08: multi_agent.py — Dead code (superseded by agent_registry.py)

**Problem:** `MultiAgentGovernor` is not used by any route or engine. Superseded by `AgentRegistry`. Creates confusion about which module manages agents.

**Fix plan:** Merge useful features (`get_effective_constraints`, `get_ancestry`) into `AgentRegistry`/`RoleManager`, delete the file, update imports and tests.

### F-09: hybrid_engine.py — Doesn't send agent_id/agent_token to remote

**Problem:** `HybridEngine` builds JSON bodies without `agentId` or `agentToken`. In hybrid mode, the remote service never knows which agent is making the request, so all multi-agent governance is bypassed.

**Fix plan:** Add `"agentId": event.agent_id` and `"agentToken": event.agent_token` to all JSON bodies.

### F-10: roles.py:101 — fnmatch resource patterns vulnerable to path traversal

**Problem:** `is_resource_allowed` uses `fnmatch` without path normalization. An attacker could bypass deny patterns like `/secrets/**` with paths like `/secrets/../secrets/key`.

**Fix plan:** Normalize `resource_path` with `os.path.normpath()` before pattern matching. Normalize patterns at construction time too.

### F-11: roles.py:131 — Flawed intersection logic for allowed actions

**Problem:** When `org_allowed` is non-empty but `allowed` (from role) is empty, the code replaces the role's "allow everything" semantics with `org_allowed`. The `is_action_allowed` method treats empty `allowed_action_classes` as "allow all", but `get_effective_constraints` does not follow that convention.

**Fix plan:** Use a sentinel value (e.g., `None` or `{"*"}`) to represent "all allowed". Document the convention explicitly.

### F-12: full_engine.py:119-325 — Rate limiter only counts allowed actions

**Problem:** Blocked actions are not recorded in the rate limiter. An attacker could spam the same blocked action indefinitely without triggering rate limits.

**Fix plan:** Add a separate "attempt counter" that tracks all attempts and enforce a secondary attempt rate limit to prevent brute-force probing.

### F-13: agent_registry.py:54 — Eviction silently drops agents without audit trail

**Problem:** When `MAX_AGENTS` is exceeded, the oldest agent is silently evicted. No audit event. A child agent of an evicted parent gets a dangling `parent_id`.

**Fix plan:** Log an audit event on eviction. Handle dangling `parent_id` in hierarchy lookups. Consider marking evicted agents as killed first.

### F-14: cli/policy_cmd.py:70-84 — Turtle injection via CLI policy add

**Problem:** The `add_policy` command builds Turtle snippets by string concatenation without escaping user input. A `reason` containing `" ;` could inject arbitrary RDF statements.

**Fix plan:** Escape special Turtle characters or use rdflib to programmatically construct and serialize triples.

### F-15: action_classifier.py:24 — Non-deterministic RDF node IDs using `id(self)`

**Problem:** `SC[f"action_{id(self)}"]` uses Python's `id()` for RDF node URIs. `id()` returns memory addresses which can be reused after GC.

**Fix plan:** Use `uuid.uuid4()`: `SC[f"action_{uuid4().hex}"]`

### F-16: Multiple files — No session cleanup lifecycle

**Problem:** `SessionTracker`, `ContextBuilder`, `DependencyChecker`, `RateLimiter`, and `MessageGate` all maintain per-session state. There is no coordinated cleanup. `FullEngine` has NO `clear_session` method.

**Fix plan:** Add `clear_session(session_id)` to `FullEngine` that calls cleanup on all components. Expose as `POST /api/v1/session/end`.

### F-17: main.py:50-52 — `get_engine()` uses assert instead of proper error handling

**Problem:** `assert engine is not None` can be disabled with `python -O`. If engine is None with assertions disabled, routes crash with unhelpful `AttributeError`.

**Fix plan:** Replace with `if engine is None: raise RuntimeError("Engine not initialized")`.

---

## MEDIUM (25 findings)

### F-18: context_builder.py:80-88 + preference_checker.py:37-44 — SPARQL injection risk

**Problem:** Both files construct SPARQL queries with incomplete user_id sanitization. Characters `}`, `{`, `#`, newlines can break the query.

**Fix plan:** Use rdflib's `initBindings` for parameterized SPARQL: `graph.query(sparql, initBindings={"user_id": Literal(user_id)})`.

### F-19: cached_engine.py — Bypasses all agent governance

**Problem:** `CachedEngine` always returns `Decision(block=False)`. Killed agents or restricted roles bypass all checks in local fallback mode.

**Fix plan:** Add basic agent checks (kill switch, role-based action checks). Accept `AgentRegistry` and `RoleManager` in constructor.

### F-20: delegation_detector.py — No max size for _blocks list + fragile serialization

**Problem:** `_blocks` has no size cap and `json.dumps(params)` crashes on non-JSON-serializable values.

**Fix plan:** Use `deque(maxlen=10000)`. Wrap `json.dumps` in try/except with `default=str` fallback.

### F-21: routes.py:165 — `format` parameter shadows Python built-in

**Problem:** Parameter name `format` shadows Python's built-in. Also no validation — any string accepted, silently falls through to markdown.

**Fix plan:** Rename to `fmt` with `alias="format"`. Add `Literal["markdown", "json", "csv"]` type validation.

### F-22: full_engine.py:137-142 — Duplicate make_signature calls

**Problem:** `DelegationDetector.make_signature(event.params)` is computed up to 3 times for the same params.

**Fix plan:** Compute once at the top of the method and reuse.

### F-23: roles.py:92 — Default role is "researcher" not "developer"

**Problem:** `get_default_role()` returns "researcher" but `config_template.py:54` specifies `"defaultRole": "developer"`. Config value never read.

**Fix plan:** Read `defaultRole` from config in `RoleManager.__init__` and use it in `get_default_role()`.

### F-24: roles.py — camelCase config keys (`defaultRole`, `policyFile`) never read

**Problem:** Core keys (`enforcement_mode`, `autonomy_level`) DO match between `RoleManager` and `config_template.py`. However, camelCase keys like `defaultRole` and `policyFile` in the config template are never read by `RoleManager`. (Original claim of snake_case mismatch was incorrect — validated as PARTIALLY CORRECT.)

**Fix plan:** Read `defaultRole` and `policyFile` from config in `RoleManager.__init__`. See also F-23 which covers the defaultRole issue.

### F-25: full_engine.py:321,429 — Double recording of actions in dependency tracker

**Problem:** Successful actions are recorded in both `evaluate_tool_call` (before execution) and `record_action_result` (after). Duplicate entries affect cumulative risk counting.

**Fix plan:** Remove the `record_action` call from `evaluate_tool_call`. Record only in `record_action_result` after the action executes.

### F-26: reasoner.py:28-30 — Only the last .ttl file retained as `self._ontology`

**Problem:** The loop overwrites `self._ontology` each iteration. Only the last loaded ontology is stored, but `with self._ontology:` reasoning context uses it.

**Fix plan:** Collect all ontologies or use a single merged ontology approach.

### F-27: shacl_validator.py:59-72 — Fragile text parsing of SHACL violations

**Problem:** `_parse_violations` parses pySHACL's `results_text` string by looking for prefixes. Brittle and dependent on output format.

**Fix plan:** Parse the `results_graph` (RDF graph) instead of `results_text` for stable structured data.

### F-28: hybrid_engine.py:77 — New HTTP client created per request

**Problem:** `httpx.AsyncClient` created per request. Loses connection pooling and HTTP/2 multiplexing.

**Fix plan:** Create a single `httpx.AsyncClient` in `__init__` and reuse it. Add `close()` for cleanup.

### F-29: hybrid_engine.py:45-51 — Circuit breaker race condition

**Problem:** Multiple concurrent requests can all see `should_try_remote() == True` simultaneously, causing a thundering herd against a potentially down remote.

**Fix plan:** Add a "half-open" state where only one request probes the remote; others fall back locally.

### F-30: message_gate.py:14 — Base64 pattern has high false positive rate

**Problem:** Pattern `r"(?i)\b[A-Za-z0-9+/]{40,}={0,2}\b"` matches any 40+ char alphanumeric string, catching SHA hashes, UUIDs, encoded URLs, etc.

**Fix plan:** Tighten the pattern or add a whitelist for known safe patterns (SHA-256 = 64 hex chars, UUIDs, etc.).

### F-31: action_classifier.py:93-115 — Shell classifier doesn't handle command chaining

**Problem:** `echo hi && rm -rf /` only returns one classification. Multi-command strings aren't split.

**Fix plan:** For strings containing `&&`, `||`, `;`, `|`, split and classify each sub-command, return highest-risk.

### F-32: cloud/tenant.py:87 — Tenant org_id only 8 chars, collision risk

**Problem:** `str(uuid4())[:8]` has only 32 bits of entropy. ~1% collision at 10k tenants.

**Fix plan:** Use full UUID or at least 16 characters. Check for existence before provisioning.

### F-33: config.py:11 — Default host `0.0.0.0` exposes to network

**Problem:** Default host binds to all interfaces, exposing the unauthenticated API to local network.

**Fix plan:** Default to `127.0.0.1`. Users who need network access override via `SAFECLAW_HOST`.

### F-34: Dockerfile:11-13 — pip install before source COPY + runs as root

**Problem:** `pip install .` runs before the source directory is copied (will fail). Container also runs as root.

**Fix plan:** Copy source before install. Add `RUN useradd -m safeclaw` and `USER safeclaw`.

### F-35: audit/logger.py:55-68 — No error handling for malformed JSONL

**Problem:** If a JSONL line is corrupted, `model_validate_json` raises `ValidationError` and the entire method fails.

**Fix plan:** Wrap parsing in try/except, log the error, continue processing remaining lines.

### ~~F-36: audit/reporter.py:108~~ — REMOVED (FALSE POSITIVE)

**Validation:** The math `blocked = total - allowed` is correct — the system only has two decision states ("allowed" and "blocked"). No `allowed_with_warning` state exists.

### F-37: Full engine concurrent access — TOCTOU in rate limiting

**Problem:** Multiple concurrent `evaluate_tool_call` calls can race between rate limit check and record, allowing limits to be exceeded.

**Fix plan:** Add per-session async locks or atomic check-and-record operations.

### F-38: temp_permissions.py:64 — check() doesn't prune expired grants

**Problem:** `check()` iterates all grants including expired ones without cleanup. `list_grants()` calls `cleanup_expired()` but `check()` does not.

**Fix plan:** Call `cleanup_expired()` at the start of `check()`.

### F-39: agent_registry.py:33 — Token hashing uses SHA-256 without salt

**Problem:** Unsalted SHA-256 for token storage. If store is ever persisted or leaked, hashes could be rainbow-tabled.

**Fix plan:** Use `hmac.new(server_secret, token.encode(), 'sha256')` with a server-side secret for defense-in-depth.

### F-40: roles.py:16 — resource_patterns typed as bare dict, no validation

**Problem:** No validation that config follows `{"allow": [...], "deny": [...]}` shape. A string instead of list would fail silently.

**Fix plan:** Use a TypedDict or Pydantic model. Validate shape in `RoleManager.__init__`.

### F-41: plugin index.ts:76 — HTTP errors silently swallowed, no error distinction

**Problem:** `post()` returns `null` for ALL failures: disabled, timeout, HTTP 403, HTTP 500. Cannot debug production issues.

**Fix plan:** Return discriminated result type or at minimum log different error types at appropriate levels.

### F-42: plugin index.ts:70 — No URL validation on serviceUrl

**Problem:** `serviceUrl` not validated. Trailing slash causes doubled paths. No check for well-formed URL.

**Fix plan:** Strip trailing slashes in `loadConfig()`. Validate with `new URL(serviceUrl)`.

---

## LOW (17 findings)

### F-43: Test files organized by phase rather than feature

**Problem:** Tests in `test_phase2.py`, `test_phase3.py`, etc. Hard to find tests for a specific module.

**Fix plan:** For future tests, prefer feature-based names. Reorganize in a future cleanup.

### F-44: TypeScript plugin doesn't validate agentId/agentToken consistency

**Problem:** If `agentToken` set but `agentId` empty, token is sent for no agent.

**Fix plan:** Only include agent fields when both are set.

### F-45: TTL role files have unused `owl:` prefix + no `owl:imports`

**Problem:** All role `.ttl` files declare `@prefix owl:` but never use it. Also no `owl:imports` declarations.

**Fix plan:** Remove unused prefix. Add `owl:imports` to reference base ontologies.

### F-46: TTL roles don't match Python BUILTIN_ROLES

**Problem:** `researcher.ttl` denies `sc:SendMessage` but Python `BUILTIN_ROLES["researcher"]` does not include it. `developer.ttl` allows `RunTests`/`SendMessage` not in Python.

**Fix plan:** Synchronize Python roles with TTL files, or load roles from TTL at startup.

### F-47: test_shacl_validation.py — Tests silently pass when shapes directory missing

**Problem:** `if shapes_dir.exists()` guards mean tests pass without actually running when shapes are unavailable.

**Fix plan:** Use `pytest.mark.skipif` to make skip visible in test output.

### F-48: test_shacl_validation.py:45 — No test verifies SHACL actually catches violations

**Problem:** Test validates `rm -rf /` with no shapes conforms. No test loads real shapes and checks violations.

**Fix plan:** Add test that loads real shapes and validates `conforms is False` for a known-bad action.

### F-49: graph_builder.py:109-116 — search_nodes rebuilds entire graph on every search

**Problem:** `search_nodes` calls `build_graph()` which runs 2 SPARQL queries and builds full structure. O(N) per search.

**Fix plan:** Cache graph result with TTL or implement direct SPARQL search.

### F-50: session_tracker.py:65 — Unbounded files_modified list per session

**Problem:** `files_modified` grows without bound for long sessions.

**Fix plan:** Cap to 100 entries, evict oldest.

### F-51: hybrid_engine.py:176-177 — Silent exception swallowing in record_action_result

**Problem:** `except Exception: pass` hides all errors silently.

**Fix plan:** Log at debug/warning level.

### F-52: knowledge_graph.py:24-26 — load_directory silently fails on parse errors

**Problem:** If any `.ttl` file is malformed, parsing aborts without loading remaining files.

**Fix plan:** Wrap each `load_ontology` in try/except, log error, continue.

### F-53: agent_registry.py:77 — is_killed returns False for unknown agents

**Problem:** Unknown/evicted agents treated as "alive" rather than "unknown".

**Fix plan:** Return `True` for unknown agents (fail-closed).

### F-54: Various test flakiness — time.sleep, network-dependent, fragile assertions

**Problem:** `test_recovery_timeout` uses `time.sleep(0.15)`. `test_remote_failure` depends on port 99999. Various fragile string assertions.

**Fix plan:** Mock `time.monotonic` instead of sleeping. Mock HTTP calls instead of real network. Relax string assertions.

### F-55: Various missing test coverage

**Problem:** Zero test coverage for: `cached_engine.py`, `reasoner.py`, `main.py` lifespan, CLI commands, `evaluate_message` full pipeline, `record_action_result`, `reload()`.

**Fix plan:** Add targeted tests for each. Priority: cached_engine, evaluate_message, reload.

### F-56: api/models.py — Unused model classes

**Problem:** `AgentKillRequest` and `AuditQueryParams` are defined but never imported or used.

**Fix plan:** Remove unused classes.

### F-57: cli/pref_cmd.py:64-66 — Preference set silently falls back to default user

**Problem:** Setting a preference for a specific user_id silently modifies `user-default.ttl` if user file doesn't exist.

**Fix plan:** Create user-specific file from default, or warn the user.

### F-58: plugin index.ts:161-166 — Fire-and-forget promises could reject

**Problem:** `llm_input`/`llm_output` handlers don't await or catch `post()` return.

**Fix plan:** Add `.catch(() => {})` to fire-and-forget calls.

### F-59: plugin index.ts:32 — Enforcement mode not validated at runtime

**Problem:** Invalid env var value like `SAFECLAW_ENFORCEMENT=block` passes type cast but matches no condition, silently becoming audit-only.

**Fix plan:** Validate in `loadConfig()` and default to `'enforce'` for unrecognized values.

---

## Fix Dependency Order (non-conflicting)

Apply fixes in this order. Same-file fixes are grouped together.

### Phase A: Critical Security + Data Integrity
1. **F-01** (namespace mismatch) — knowledge_graph.py, action_classifier.py, .ttl files
2. **F-02** (config.raw) — config.py
3. **F-03** (CORS + auth middleware) — main.py
4. **F-04** (auth on endpoints) — routes.py, auth/middleware.py
5. **F-05** (SHACL fail-open) — shacl_validator.py

### Phase B: High Security Fixes
6. **F-07** (path traversal) — audit/logger.py
7. **F-10** (resource path traversal) — roles.py
8. **F-11** (allowed-actions intersection) — roles.py (same file, do with F-10)
9. **F-09** (hybrid agent_id) — hybrid_engine.py
10. **F-14** (Turtle injection) — cli/policy_cmd.py
11. **F-15** (non-deterministic RDF IDs) — action_classifier.py
12. **F-17** (assert in get_engine) — main.py

### Phase C: Medium Fixes
13. **F-18** (SPARQL injection) — context_builder.py, preference_checker.py
14. **F-19** (cached engine governance) — cached_engine.py
15. **F-20** (delegation max blocks + serialization) — delegation_detector.py
16. **F-21** (format shadow + validation) — routes.py
17. **F-22** (duplicate make_signature) — full_engine.py
18. **F-23 + F-24** (default role + config keys) — roles.py
19. **F-25** (double action recording) — full_engine.py
20. **F-26** (reasoner ontology retention) — reasoner.py
21. **F-27** (SHACL violation parsing) — shacl_validator.py
22. **F-28 + F-29** (HTTP client reuse + circuit breaker) — hybrid_engine.py
23. **F-30 + F-31** (message gate patterns + shell chaining) — message_gate.py, action_classifier.py
24. **F-32** (tenant org_id) — cloud/tenant.py
25. **F-33** (default host) — config.py
26. **F-34** (Dockerfile) — Dockerfile
27. **F-35 + F-36** (JSONL error handling + stats) — audit/logger.py, audit/reporter.py
28. **F-37** (concurrent access locks) — full_engine.py
29. **F-38** (temp permissions cleanup) — temp_permissions.py
30. **F-39** (token hashing salt) — agent_registry.py
31. **F-40** (resource_patterns validation) — roles.py
32. **F-41 + F-42** (TS error handling + URL validation) — index.ts

### Phase D: Dead Code + Tests
33. **F-08** (delete multi_agent.py) — multi_agent.py, tests
34. **F-16** (session cleanup lifecycle) — full_engine.py, routes.py
35. **F-06** (API route tests) — new test_api.py
36. **F-55** (missing test coverage) — various test files
37. **F-56** (unused models) — api/models.py

### Phase E: Low Priority
38. Remaining LOW findings (F-43 through F-59) — various files, no urgency
