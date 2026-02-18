# SafeClaw Full Codebase Review — Findings & Resolution

**Date:** 2026-02-18
**Scope:** All files in safeclaw-service/ and openclaw-safeclaw-plugin/
**Tests at start:** 207 passing
**Tests at end:** 216 passing
**Reviewers:** 4 parallel agents (engine, API, multi-agent, tests)
**Validation:** All 59 findings validated against source code by 4 separate agents

### Validation Summary
- **49 CONFIRMED** — real bugs verified against actual code
- **9 PARTIALLY CORRECT** — real issues but claims adjusted (F-15, F-16, F-20, F-24, F-34, F-42, F-43, F-50, F-54)
- **1 FALSE POSITIVE** — F-36 removed (math is correct for two-state decision system)

### Resolution Summary
- **58 FIXED** — all confirmed and partially correct findings resolved
- **1 FALSE POSITIVE** — F-36 removed, no fix needed
- **216 tests passing** (up from 207 at start)

### Fix Commits
1. `a24f2b7` — Apply 58 validated code review fixes across entire codebase (42 files changed)
2. `0f047b0` — Fix F-12 (rate limit all attempts) and F-16 (session cleanup lifecycle)
3. `6aa5059` — Fix remaining LOW priority findings (F-06, F-43, F-47, F-48, F-54, F-55)

---

## CRITICAL (6 findings) — ALL FIXED

### F-01: knowledge_graph.py:7-9 — Namespace mismatch with role ontology files [FIXED]

**Problem:** `knowledge_graph.py` defines namespaces as `http://safeclaw.ai/ontology/...` but the role `.ttl` files use `http://safeclaw.uku.ai/ontology/...`. If namespaces don't match, SPARQL queries will silently return no results for role-based data.

**Fix:** Standardized ALL namespace URIs to `http://safeclaw.uku.ai/ontology/...` across knowledge_graph.py, action_classifier.py, dependency_checker.py, and all 9 .ttl files.

### F-02: config.py — SafeClawConfig has no `raw` attribute [FIXED]

**Problem:** `full_engine.py:94` does `config.raw if hasattr(config, 'raw')` but `SafeClawConfig` has no `raw` field. Multi-agent config (roles, delegation policy, requireTokenAuth) is NEVER loaded from config.

**Fix:** Added `raw` property to `SafeClawConfig` that loads config.json.

### F-03: main.py:39-44 — CORS allows all origins + auth middleware not wired up [FIXED]

**Problem:** `allow_origins=["*"]` permits any website to call SafeClaw endpoints. `APIKeyAuthMiddleware` is never added to the app.

**Fix:** Replaced `allow_origins=["*"]` with `["http://localhost:*"]`. Added `APIKeyAuthMiddleware` to the app with configurable `require_auth`.

### F-04: routes.py — No auth on sensitive agent/admin endpoints [FIXED]

**Problem:** `/agents/register`, `/agents/{id}/kill`, `/agents/{id}/revive`, `/reload`, `/agents/{id}/temp-grant` have zero authentication.

**Fix:** Added `require_admin` dependency to all 6 sensitive endpoints.

### F-05: shacl_validator.py:55-57 — SHACL errors fail-open (silently allow all) [FIXED]

**Problem:** When pySHACL throws an exception, the validator returns `SHACLResult(conforms=True)` — a fail-open security issue.

**Fix:** Changed to fail-closed: exception returns `SHACLResult(conforms=False, violations=[...])`.

### F-06: No API route tests or middleware tests exist [FIXED]

**Problem:** The routes module has 17 endpoints. None are tested via TestClient.

**Fix:** Added `test_api.py` with 10 FastAPI TestClient tests covering health, evaluate/tool-call (allowed + blocked), evaluate/message, context/build, session/end, record/tool-result, audit, agents/register, and reload.

---

## HIGH (11 findings) — ALL FIXED

### F-07: audit/logger.py:25 — Path traversal via session_id [FIXED]

**Problem:** `_get_session_file()` uses `session_id` directly in the filename.

**Fix:** Sanitized session_id: `re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)`.

### F-08: multi_agent.py — Dead code (superseded by agent_registry.py) [FIXED]

**Problem:** `MultiAgentGovernor` is not used by any route or engine.

**Fix:** Deleted `multi_agent.py` and removed corresponding test class `TestMultiAgentGovernor`.

### F-09: hybrid_engine.py — Doesn't send agent_id/agent_token to remote [FIXED]

**Problem:** `HybridEngine` builds JSON bodies without `agentId` or `agentToken`.

**Fix:** Added `agentId` and `agentToken` to all 4 JSON request bodies, conditional on `event.agent_id` being set.

### F-10: roles.py:101 — fnmatch resource patterns vulnerable to path traversal [FIXED]

**Problem:** `is_resource_allowed` uses `fnmatch` without path normalization.

**Fix:** Added `os.path.normpath()` on resource_path before pattern matching.

### F-11: roles.py:131 — Flawed intersection logic for allowed actions [FIXED]

**Problem:** Empty `allowed_action_classes` means "allow all" in `is_action_allowed` but not in `get_effective_constraints`.

**Fix:** Used `None` sentinel to represent "all allowed", documented convention.

### F-12: full_engine.py:119-325 — Rate limiter only counts allowed actions [FIXED]

**Problem:** Blocked actions are not recorded in the rate limiter.

**Fix:** Moved `rate_limiter.record()` call before constraint checks (after action classification) so ALL attempts count. Removed old record-on-success call.

### F-13: agent_registry.py:54 — Eviction silently drops agents without audit trail [FIXED]

**Problem:** When `MAX_AGENTS` is exceeded, the oldest agent is silently evicted.

**Fix:** Added warning-level logging on eviction. Handled dangling `parent_id` in hierarchy lookups.

### F-14: cli/policy_cmd.py:70-84 — Turtle injection via CLI policy add [FIXED]

**Problem:** The `add_policy` command builds Turtle snippets by string concatenation without escaping.

**Fix:** Added `_escape_turtle()` helper that escapes special Turtle characters.

### F-15: action_classifier.py:24 — Non-deterministic RDF node IDs using `id(self)` [FIXED]

**Problem:** `id()` returns memory addresses which can be reused after GC.

**Fix:** Changed to `uuid4().hex` for unique RDF node URIs.

### F-16: Multiple files — No session cleanup lifecycle [FIXED]

**Problem:** No coordinated cleanup across SessionTracker, ContextBuilder, DependencyChecker, RateLimiter, MessageGate.

**Fix:** Added `clear_session(session_id)` to FullEngine and MessageGate. Exposed as `POST /api/v1/session/end` endpoint. Cleans up all sub-components and per-session locks.

### F-17: main.py:50-52 — `get_engine()` uses assert instead of proper error handling [FIXED]

**Problem:** `assert engine is not None` can be disabled with `python -O`.

**Fix:** Replaced with `raise RuntimeError("Engine not initialized — call startup first")`.

---

## MEDIUM (25 findings) — ALL FIXED

### F-18: context_builder.py + preference_checker.py — SPARQL injection risk [FIXED]

**Problem:** SPARQL queries with incomplete user_id sanitization.

**Fix:** Added `re.sub(r'[^a-zA-Z0-9_@.-]', '', user_id)` sanitization before SPARQL interpolation.

### F-19: cached_engine.py — Bypasses all agent governance [FIXED]

**Problem:** `CachedEngine` always returns `Decision(block=False)` even for killed agents.

**Fix:** Added optional `AgentRegistry` parameter and kill switch check in `evaluate_tool_call`.

### F-20: delegation_detector.py — No max size for _blocks list + fragile serialization [FIXED]

**Problem:** `_blocks` has no size cap and `json.dumps(params)` crashes on non-JSON-serializable values.

**Fix:** Added `MAX_BLOCKS = 10000` size cap. Wrapped `json.dumps` with `default=str` in try/except.

### F-21: routes.py:165 — `format` parameter shadows Python built-in [FIXED]

**Problem:** Parameter name `format` shadows Python's built-in. No validation.

**Fix:** Renamed to `fmt` with `alias="format"`. Added `Literal["markdown", "json", "csv"]` type validation.

### F-22: full_engine.py:137-142 — Duplicate make_signature calls [FIXED]

**Problem:** `DelegationDetector.make_signature(event.params)` computed up to 3 times.

**Fix:** Computed once at method top and reused via `params_sig` variable.

### F-23: roles.py:92 — Default role is "researcher" not "developer" [FIXED]

**Problem:** `get_default_role()` returns "researcher" but config specifies "developer".

**Fix:** `get_default_role()` now reads `defaultRole` from config, defaults to "developer".

### F-24: roles.py — camelCase config keys never read [FIXED]

**Problem:** `defaultRole` and `policyFile` from config template never read by `RoleManager`.

**Fix:** `RoleManager.__init__` now reads `defaultRole` from config. (Validated as PARTIALLY CORRECT — core snake_case keys DO match.)

### F-25: full_engine.py — Double recording of actions in dependency tracker [FIXED]

**Problem:** Successful actions recorded in both `evaluate_tool_call` and `record_action_result`.

**Fix:** Removed `record_action` call from `evaluate_tool_call`. Actions now only recorded in `record_action_result`.

### F-26: reasoner.py — Only the last .ttl file retained as `self._ontology` [FIXED]

**Problem:** Loop overwrites `self._ontology` each iteration.

**Fix:** Collects all ontologies in `self._ontologies` list.

### F-27: shacl_validator.py — Fragile text parsing of SHACL violations [FIXED]

**Problem:** `_parse_violations` parses `results_text` string by looking for prefixes.

**Fix:** Changed to parse `results_graph` (RDF graph) using `SH.resultMessage` and `SH.sourceShape` predicates.

### F-28: hybrid_engine.py — New HTTP client created per request [FIXED]

**Problem:** `httpx.AsyncClient` created per request.

**Fix:** Single `httpx.AsyncClient` created in `__init__` and reused.

### F-29: hybrid_engine.py — Circuit breaker race condition [FIXED]

**Problem:** Multiple concurrent requests can all see `should_try_remote() == True`.

**Fix:** Added half-open state with async probe lock — only one request probes the remote; others fall back locally.

### F-30: message_gate.py — Base64 pattern has high false positive rate [FIXED]

**Problem:** Pattern matches any 40+ char alphanumeric string.

**Fix:** Tightened Base64 pattern to require mandatory padding `={1,2}`.

### F-31: action_classifier.py — Shell classifier doesn't handle command chaining [FIXED]

**Problem:** `echo hi && rm -rf /` only returns one classification.

**Fix:** `_classify_shell` now splits on `&&`, `||`, `;` and returns highest-risk classification via `RISK_ORDER` dict.

### F-32: cloud/tenant.py — Tenant org_id only 8 chars, collision risk [FIXED]

**Problem:** `str(uuid4())[:8]` has only 32 bits of entropy.

**Fix:** Changed to `str(uuid4())` — full UUID (36 chars).

### F-33: config.py — Default host `0.0.0.0` exposes to network [FIXED]

**Problem:** Default host binds to all interfaces.

**Fix:** Default changed to `127.0.0.1`.

### F-34: Dockerfile — pip install before source COPY + runs as root [FIXED]

**Problem:** Source COPY after pip install, container runs as root.

**Fix:** Moved source COPY before pip install. Added non-root `safeclaw` user.

### F-35: audit/logger.py — No error handling for malformed JSONL [FIXED]

**Problem:** `model_validate_json` raises `ValidationError` on corrupted lines.

**Fix:** Wrapped parsing in try/except in `get_session_records` and `get_recent_records`, logs error, continues.

### ~~F-36: audit/reporter.py:108~~ — REMOVED (FALSE POSITIVE)

**Validation:** The math `blocked = total - allowed` is correct — the system only has two decision states ("allowed" and "blocked"). No fix needed.

### F-37: Full engine concurrent access — TOCTOU in rate limiting [FIXED]

**Problem:** Multiple concurrent `evaluate_tool_call` calls can race.

**Fix:** Added per-session async locks via `_get_session_lock(session_id)`. All constraint checks run under the lock.

### F-38: temp_permissions.py — check() doesn't prune expired grants [FIXED]

**Problem:** `check()` iterates all grants including expired ones.

**Fix:** Added `cleanup_expired()` call at the start of `check()`.

### F-39: agent_registry.py — Token hashing uses SHA-256 without salt [FIXED]

**Problem:** Unsalted SHA-256 for token storage.

**Fix:** Changed to HMAC with `self._server_secret = os.urandom(32)`. `_hash_token` is now an instance method.

### F-40: roles.py — resource_patterns typed as bare dict, no validation [FIXED]

**Problem:** No validation that config follows `{"allow": [...], "deny": [...]}` shape.

**Fix:** Added validation in `RoleManager.__init__` that checks `allow` and `deny` are lists.

### F-41: plugin index.ts — HTTP errors silently swallowed [FIXED]

**Problem:** `post()` returns `null` for ALL failures. Cannot debug.

**Fix:** Differentiated error logging: `warn` for HTTP errors, `debug` for timeouts.

### F-42: plugin index.ts — No URL validation on serviceUrl [FIXED]

**Problem:** Trailing slash causes doubled paths.

**Fix:** Strip trailing slashes from `serviceUrl`. Validate enforcement mode at runtime.

---

## LOW (17 findings) — ALL FIXED

### F-43: Test files organized by phase rather than feature [FIXED]

**Problem:** Tests in `test_phase2.py`, `test_phase3.py`, etc. Hard to find tests for a specific module.

**Fix:** Updated module docstrings to accurately list which modules/features are tested. New tests use feature-based naming (test_api.py, test_coverage.py). (Validated as PARTIALLY CORRECT — 6 of 11 test files were already feature-named.)

### F-44: TypeScript plugin doesn't validate agentId/agentToken consistency [FIXED]

**Problem:** If `agentToken` set but `agentId` empty, token is sent for no agent.

**Fix:** Agent fields only included in requests when `config.agentId` is set.

### F-45: TTL role files have unused `owl:` prefix [FIXED]

**Problem:** All role `.ttl` files declare `@prefix owl:` but never use it.

**Fix:** Removed unused `owl:` prefix from role TTL files.

### F-46: TTL roles don't match Python BUILTIN_ROLES [FIXED]

**Problem:** `researcher.ttl` denies `sc:SendMessage` but Python `BUILTIN_ROLES["researcher"]` does not.

**Fix:** Added `"SendMessage"` to researcher's `denied_action_classes` in Python.

### F-47: test_shacl_validation.py — Tests silently pass when shapes missing [FIXED]

**Problem:** `if shapes_dir.exists()` guards mean tests pass without running.

**Fix:** Replaced with `@requires_shapes` skipif marker — skips are now visible in pytest output.

### F-48: test_shacl_validation.py — No test verifies SHACL actually catches violations [FIXED]

**Problem:** No test loads real shapes and checks violations.

**Fix:** Added `test_shacl_catches_invalid_action` (builds RDF with duplicate risk levels violating sh:maxCount) and `test_shacl_validation_error_returns_non_conforming` (mocks pyshacl to raise, verifies fail-closed).

### F-49: graph_builder.py — search_nodes rebuilds entire graph on every search [FIXED]

**Problem:** `search_nodes` calls `build_graph()` per search.

**Fix:** Added `_cached_graph` and `_cache_valid` fields with `invalidate_cache()` method.

### F-50: session_tracker.py — Unbounded files_modified list per session [FIXED]

**Problem:** `files_modified` grows without bound.

**Fix:** Added `MAX_FILES_PER_SESSION = 200` cap. (Validated as PARTIALLY CORRECT — list is deduplicated per unique file, but still needed a hard cap.)

### F-51: hybrid_engine.py — Silent exception swallowing in record_action_result [FIXED]

**Problem:** `except Exception: pass` hides all errors.

**Fix:** Exception now logged with `logger.exception()`.

### F-52: knowledge_graph.py — load_directory silently fails on parse errors [FIXED]

**Problem:** If any `.ttl` file is malformed, parsing aborts.

**Fix:** Wrapped each file load in try/except, logs error, continues with remaining files.

### F-53: agent_registry.py — is_killed returns False for unknown agents [FIXED]

**Problem:** Unknown/evicted agents treated as "alive".

**Fix:** `is_killed` now returns `True` for unknown agents (fail-closed).

### F-54: Various test flakiness [FIXED]

**Problem:** `test_recovery_timeout` uses `time.sleep(0.15)`. `test_remote_failure` makes real HTTP calls.

**Fix:** Replaced `time.sleep` with monkeypatched `time.monotonic`. Replaced real HTTP calls with mocked `httpx.ConnectError`.

### F-55: Various missing test coverage [FIXED]

**Problem:** Zero test coverage for cached_engine, evaluate_message pipeline, record_action_result, reload, clear_session.

**Fix:** Added `test_coverage.py` with 7 tests: CachedEngine (normal + kill switch), evaluate_message (never-contact + normal), record_action_result, reload, and clear_session.

### F-56: api/models.py — Unused model classes [FIXED]

**Problem:** `AgentKillRequest` and `AuditQueryParams` are defined but never used.

**Fix:** Removed both unused classes.

### F-57: cli/pref_cmd.py — Preference set silently falls back to default user [FIXED]

**Problem:** Setting a preference for a specific user_id silently modifies `user-default.ttl`.

**Fix:** Creates user-specific file from default template instead of silent fallback.

### F-58: plugin index.ts — Fire-and-forget promises could reject [FIXED]

**Problem:** `llm_input`/`llm_output` handlers don't catch `post()` rejection.

**Fix:** Added `.catch(() => {})` to fire-and-forget calls.

### F-59: plugin index.ts — Enforcement mode not validated at runtime [FIXED]

**Problem:** Invalid env var value silently becomes audit-only.

**Fix:** Added validation in `loadConfig()` — unrecognized values default to `'enforce'`.
