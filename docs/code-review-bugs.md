# SafeClaw Code Review — Bug Report

## Round 1 Findings

Consolidated from 5 parallel review agents covering: engine layer, constraints layer, API/governance/CLI, plugin/landing, and tests/ontologies.

---

### CRITICAL

#### BUG-001: `reload()` destroys in-flight state without synchronization
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:148-152`
- **Category:** Race condition / data corruption
- **Description:** `reload()` calls `_init_components()` which replaces all internal state (KG, classifiers, checkers, registries, session locks, rate limiters). Any in-flight `evaluate_tool_call` coroutine between await points will use stale references while attributes now point to new empty components. Agent tokens, rate limits, session state, and temp permissions are all destroyed.

---

### HIGH

#### BUG-002: `enforcement_mode` on Roles is never checked
- **File:** `safeclaw-service/safeclaw/engine/roles.py:22`, `full_engine.py` (entire)
- **Category:** Logic error / dead feature
- **Description:** Roles have `enforcement_mode` ("enforce"/"warn-only"). Admin role is "warn-only". But `full_engine.py` never checks this field — all roles are treated as "enforce". The "warn-only" mode is dead configuration.

#### BUG-003: Shell classifier strips quoted strings, hiding dangerous commands
- **File:** `safeclaw-service/safeclaw/constraints/action_classifier.py:112-114`
- **Category:** Security — classifier bypass
- **Description:** `bash -c "rm -rf /"` — after quote stripping becomes `bash -c  `, matching no dangerous pattern. Falls through to `ExecuteCommand/HighRisk/reversible=True`, missing CriticalRisk classification and preference-based delete confirmation. The dangerous payload inside quotes becomes invisible.

#### BUG-004: `session_history` is client-supplied and untrusted, used for security decisions
- **File:** `safeclaw-service/safeclaw/engine/core.py:13`, `reasoning_rules.py:85,137-150`, `full_engine.py:390`
- **Category:** Security — trust boundary violation
- **Description:** `ToolCallEvent.session_history` comes from the API client. The derived checker's `_check_cumulative_risk` does substring matching on these strings. A malicious client can bypass cumulative risk by sending empty history, or trigger false escalations by stuffing risk labels. The server has `SessionTracker` but doesn't use it for this check.

#### BUG-005: Multiple API endpoints missing authentication
- **File:** `safeclaw-service/safeclaw/api/routes.py:359,377,225-242`
- **Category:** Security — missing authorization
- **Description:** `/audit/{id}/explain` lacks `require_admin`. `/events` SSE has no auth (exposes real-time governance events). `/ontology/graph` and `/ontology/search` expose full policy structure. All admin-protected endpoints are effectively unprotected since auth is always disabled (BUG-008).

#### BUG-006: Kill switch, invalid token, and delegation bypass leave no audit trail
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:207-226`
- **Category:** Logic error — missing audit for security events
- **Description:** When agent token verification fails, kill switch is active, or delegation bypass is detected, the function returns `Decision(block=True)` without creating an audit record. These are the most security-critical events and should always be audited.

#### BUG-007: `require_auth=True` causes immediate crash on startup
- **File:** `safeclaw-service/safeclaw/main.py:58-62`
- **Category:** Logic error — auth is non-functional
- **Description:** If `SAFECLAW_REQUIRE_AUTH=true`, module-level code raises `RuntimeError` unconditionally. Authentication can never actually be enabled. The `APIKeyAuthMiddleware` is always `require_auth=False`.

#### BUG-008: All admin endpoints unprotected when auth disabled
- **File:** `safeclaw-service/safeclaw/api/routes.py:38-46`
- **Category:** Security — admin bypass
- **Description:** `require_admin` uses `getattr(request.state, "api_key_scope", None)` which returns `None` when auth is disabled (always). The condition `if scope is not None and "admin" not in scope` is `False`, so all admin-only endpoints are accessible to anyone.

#### BUG-009: Path traversal bypass via `..` in resource paths
- **File:** `safeclaw-service/safeclaw/engine/roles.py:130`
- **Category:** Security — path traversal
- **Description:** `os.path.normpath` resolves `..` segments, so `/secrets/../home/user` normalizes to `/home/user`, bypassing the `/secrets/**` deny pattern. Also platform-dependent (Windows vs Unix path separators).

#### BUG-010: `rm -rf /` regex is trivially bypassed with variants
- **File:** `safeclaw-service/safeclaw/ontologies/safeclaw-policy.ttl:117`
- **Category:** Security — insufficient regex
- **Description:** Policy pattern `rm\\s+-rf\\s+/` only matches `rm -rf /`. Does NOT match: `rm -r -f /`, `rm -fr /`, `rm --recursive --force /`, `find / -delete`. The classifier uses a different regex for the same threat, creating inconsistency.

#### BUG-011: Chained commands only return highest-risk action, masking prohibited lower-risk actions
- **File:** `safeclaw-service/safeclaw/constraints/action_classifier.py:115-133`
- **Category:** Logic error — information loss
- **Description:** `echo hello && rm -rf /tmp && git push --force` returns only `ForcePush`. The `rm -rf` deletion is invisible to policy/preference checkers. A temp permission for ForcePush would bypass the delete policy check entirely. Command pattern check partially mitigates but class-level prohibitions are bypassed.

#### BUG-012: Plugin `success` field defaults to `true`, could bypass dependency checks
- **File:** `openclaw-safeclaw-plugin/index.ts:259`
- **Category:** Security — incorrect default
- **Description:** `event.success ?? true` defaults to `true` when not provided. If OpenClaw doesn't reliably set `success`, failed tests are recorded as successful, allowing git pushes that should be blocked by dependency checks.

#### BUG-013: `ForcePush` is not a subclass of `GitPush` in ontology
- **File:** `safeclaw-service/safeclaw/ontologies/safeclaw-agent.ttl:86-88`
- **Category:** Ontology design inconsistency
- **Description:** Both are siblings under `ShellAction`. Policies targeting `GitPush` won't catch `ForcePush` via hierarchy. The `NoForcePush` policy works via explicit targeting, but a "block all git pushes" policy wouldn't block force pushes.

#### BUG-014: Role TTL files are loaded but never consumed by RoleManager
- **File:** `safeclaw-service/safeclaw/ontologies/roles/*.ttl`, `engine/roles.py`
- **Category:** Dead ontology configuration
- **Description:** TTL role files define roles with `sp:allowsAction`, `sp:deniesAction`, etc. But `RoleManager` reads from Python `BUILTIN_ROLES` dict or config JSON, never from the KG. The researcher.ttl denies `ShellAction` (parent) while Python denies only `ExecuteCommand` (child) — they disagree.

---

### MEDIUM

#### BUG-015: `resource_path` extraction uses inconsistent key precedence
- **File:** `full_engine.py:255` vs `policy_checker.py:97`
- **Category:** Logic error — security
- **Description:** Engine role check prefers `"path"` over `"file_path"`. Policy checker prefers `"file_path"` over `"path"`. If both are set to different values, role check and policy check evaluate different paths.

#### BUG-016: `never_modify_paths` and `max_files_per_commit` preferences never enforced
- **File:** `safeclaw-service/safeclaw/constraints/preference_checker.py:15-16,64-102`
- **Category:** Dead code — incomplete implementation
- **Description:** Fields declared in `UserPreferences` but never populated from SPARQL results and never checked in `check()`. Users setting `neverModifyPaths` have false sense of security.

#### BUG-017: Dependency checker not hierarchy-aware
- **File:** `safeclaw-service/safeclaw/constraints/dependency_checker.py:68-84`
- **Category:** Logic error — inconsistency
- **Description:** Uses exact string matching for both action class and prerequisite. PolicyChecker and RoleManager are hierarchy-aware but DependencyChecker is not.

#### BUG-018: Policy checker path check only examines two param keys
- **File:** `safeclaw-service/safeclaw/constraints/policy_checker.py:97`
- **Category:** Edge case — incomplete coverage
- **Description:** Only checks `file_path` and `path` params. Shell commands embed paths in `command` param. Tools could use `target`, `destination`, `source_path`, `dir`, etc.

#### BUG-019: `evaluate_message` not protected by session lock
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:438-485`
- **Category:** Race condition — TOCTOU
- **Description:** `evaluate_tool_call` acquires per-session lock, but `evaluate_message` does not. Two concurrent messages could both pass rate limit check.

#### BUG-020: Temporal constraints silently swallowed on parse errors
- **File:** `safeclaw-service/safeclaw/constraints/temporal_checker.py:63-64,79-80`
- **Category:** Error handling — fail-open
- **Description:** Malformed `notBefore`/`notAfter` datetime raises `ValueError`/`TypeError` which is silently caught. Constraint is skipped (fail-open) instead of blocking (fail-closed).

#### BUG-021: CORS regex missing `$` anchor
- **File:** `safeclaw-service/safeclaw/config.py:20`
- **Category:** Security — CORS bypass
- **Description:** Regex `r"https?://localhost:\d+"` lacks `$` anchor. `https://localhost:1234.evil.com` would match.

#### BUG-022: Plugin config file overrides environment variables (wrong precedence)
- **File:** `openclaw-safeclaw-plugin/index.ts:27-55`
- **Category:** Logic error — configuration precedence
- **Description:** Config file values overwrite env vars. Standard 12-factor convention is env vars take highest precedence.

#### BUG-023: Plugin `message_sending` handler missing `warn-only` logging for blocks
- **File:** `openclaw-safeclaw-plugin/index.ts:233-235`
- **Category:** Logic error — inconsistency
- **Description:** When service returns `block=true` and enforcement is `warn-only`, the handler silently swallows it. `before_tool_call` correctly logs a warning in this case.

#### BUG-024: Plugin `audit-only` + `fail-closed` silently ignores service unavailability
- **File:** `openclaw-safeclaw-plugin/index.ts:191-204,228-235`
- **Category:** Logic error — missing case
- **Description:** When service is unreachable and mode is `audit-only` with `fail-closed`, no block, no warning, no log.

#### BUG-025: `TempGrantRequest` allows both `durationSeconds` and `taskId` as None (500 error)
- **File:** `safeclaw-service/safeclaw/api/models.py:117-120`
- **Category:** Error handling — missing validation
- **Description:** Both Optional, but `TempPermissionManager.grant()` raises `ValueError` if both None, causing unhandled 500 instead of 422.

#### BUG-026: `admin_password` config field is unused
- **File:** `safeclaw-service/safeclaw/config.py:29`
- **Category:** Misleading config / incomplete feature
- **Description:** Defined but never referenced. Operators may think dashboard is password-protected when it's not.

#### BUG-027: Agent re-registration silently replaces existing agent
- **File:** `safeclaw-service/safeclaw/engine/agent_registry.py:57`
- **Category:** Security — silent state replacement
- **Description:** No check for existing agent. Any admin can silently replace another agent's token, role, and parent with no audit trail of the replacement.

#### BUG-028: `end_session` calls `clear_session` without session lock
- **File:** `safeclaw-service/safeclaw/api/routes.py:107-112`
- **Category:** Race condition
- **Description:** `clear_session()` modifies internal state while concurrent `evaluate_tool_call` may hold the session lock. Lock removal while held could lead to inconsistent state.

#### BUG-029: CLI `pref set`/`policy add` write to bundled package directory
- **File:** `safeclaw-service/safeclaw/cli/pref_cmd.py:60-63`, `policy_cmd.py`
- **Category:** Logic error — writes to package dir
- **Description:** `config.get_ontology_dir()` defaults to the installed package's `safeclaw/ontologies/`. Package upgrades overwrite changes, containers are read-only.

#### BUG-030: `RoleManager` config doesn't validate list types for action classes
- **File:** `safeclaw-service/safeclaw/engine/roles.py:95-100`
- **Category:** Type error — missing validation
- **Description:** `set("ForcePush")` produces `{'F','o','r','c','e','P','u','s','h'}` if config value is a string instead of list.

#### BUG-031: `STRENDS` SPARQL filter allows user ID suffix collisions
- **File:** `safeclaw-service/safeclaw/constraints/preference_checker.py:38-47`
- **Category:** Security — data leakage
- **Description:** User `"bob"` could match URI ending in `"/bigbob"`. Empty user_id matches any user ending in `/`.

#### BUG-032: EventBus silently returns empty stream at max subscribers
- **File:** `safeclaw-service/safeclaw/engine/event_bus.py:47-51`
- **Category:** Silent failure / DoS
- **Description:** At 50 subscribers, new ones get empty 200 OK with no events and no indication of rejection. Attacker can exhaust all SSE slots.

#### BUG-033: Session summary includes unsanitized command text in LLM context
- **File:** `safeclaw-service/safeclaw/engine/session_tracker.py:71`
- **Category:** Security — prompt injection
- **Description:** `detail = f"cmd: {cmd[:80]}"` includes command text in session summary injected into LLM system prompts. Malicious commands could contain prompt injection payloads.

#### BUG-034: Delegation detector mode `"configurable"` (default) is effectively "detect-but-never-block"
- **File:** `safeclaw-service/safeclaw/engine/delegation_detector.py:36`
- **Category:** Logic error — undocumented default
- **Description:** Only "strict" blocks. Default "configurable" from config_template detects but never blocks, which is likely not the intended behavior.

#### BUG-035: `_check_cumulative_risk` uses naive substring matching
- **File:** `safeclaw-service/safeclaw/engine/reasoning_rules.py:137-150`
- **Category:** Logic error — fragile matching
- **Description:** `elif` chain with substring matching. Entry containing both "MediumRisk" and "HighRisk" only counts as Medium. Combined with BUG-004 (client-supplied history), this is doubly fragile.

#### BUG-036: `.sesskey` file possibly committed to repository
- **File:** `safeclaw-landing/.sesskey`
- **Category:** Security — credential exposure
- **Description:** Contains session signing key. If committed before `.gitignore` was added, it remains tracked. Anyone can forge session cookies.

#### BUG-037: `config.raw` doesn't catch `UnicodeDecodeError`
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:103-107`
- **Category:** Error handling
- **Description:** `try/except` catches `json.JSONDecodeError`, `AttributeError`, `OSError` but not `UnicodeDecodeError` (subclass of `ValueError`). Invalid UTF-8 in config crashes engine init.

#### BUG-038: Transitive prohibition rule is redundant with policy checker
- **File:** `safeclaw-service/safeclaw/engine/reasoning_rules.py:113-135`
- **Category:** Logic error — redundancy
- **Description:** Checks same `sp:appliesTo` prohibitions already checked by PolicyChecker in step 3. Since step 3 blocks first, step 8 never triggers independently. Creates maintenance confusion.

#### BUG-039: Policy checker command pattern matches quotes that classifier strips
- **File:** `safeclaw-service/safeclaw/constraints/policy_checker.py:109`
- **Category:** Inconsistency — false positive
- **Description:** Policy checker matches forbidden patterns against full command including quoted strings. Classifier strips quotes before matching. `echo "git push --force" && ls` is blocked by policy but correctly classified as safe by classifier.

---

### LOW

#### BUG-040: `_enrich_from_ontology` mutates input action object in place
- **File:** `safeclaw-service/safeclaw/constraints/action_classifier.py:145-154`
- **Category:** Code smell

#### BUG-041: Rate limiter `check()` doesn't prune expired records
- **File:** `safeclaw-service/safeclaw/constraints/rate_limiter.py:49-76`
- **Category:** Performance

#### BUG-042: `BUILTIN_ROLES` objects are mutable and shared across instances
- **File:** `safeclaw-service/safeclaw/engine/roles.py:31-73,104`
- **Category:** Shared mutable state

#### BUG-043: `ToolResultEvent` missing `user_id` field
- **File:** `safeclaw-service/safeclaw/engine/core.py:37-44`
- **Category:** Incomplete data model

#### BUG-044: `clear_session` doesn't clean delegation_detector records
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:548-556`
- **Category:** Incomplete cleanup

#### BUG-045: Hardcoded copyright year 2025 on landing page
- **File:** `safeclaw-landing/main.py:309`
- **Category:** Maintenance

#### BUG-046: `rm` without flags (simple file deletion) not classified
- **File:** `safeclaw-service/safeclaw/constraints/action_classifier.py:45`
- **Category:** Security — classification gap

#### BUG-047: `sys.getsizeof` used instead of `len(encode())` for payload size
- **File:** `safeclaw-service/safeclaw/api/models.py:32`
- **Category:** Logic error — incorrect measurement

#### BUG-048: Policy checker returns only first violation
- **File:** `safeclaw-service/safeclaw/constraints/policy_checker.py:94-136`
- **Category:** Logic limitation — incomplete audit

#### BUG-049: SHACL error message leaks internal details
- **File:** `safeclaw-service/safeclaw/engine/shacl_validator.py:55-57`
- **Category:** Information disclosure

#### BUG-050: `_log_message_decision` hardcodes risk_level for messages
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:487-507`
- **Category:** Correctness

#### BUG-051: Missing `rel="noopener"` on `target="_blank"` links
- **File:** `safeclaw-landing/main.py:34,52,304`
- **Category:** Security best practice

#### BUG-052: `NetworkRequest` lacks ontology defaults and SHACL shapes
- **File:** `safeclaw-service/safeclaw/ontologies/safeclaw-agent.ttl:119-121`
- **Category:** Ontology incompleteness

#### BUG-053: No test that `rm -rf /` is caught by SHACL when shapes ARE loaded
- **File:** `safeclaw-service/tests/test_shacl_validation.py:46-51`
- **Category:** Missing test coverage

#### BUG-054: Multiple tests don't test what their names claim
- **Files:** `test_config.py:106-111`, `test_phase5.py:109-116,101-107`, `test_api.py:182-193`
- **Category:** Test quality

#### BUG-055: `_extract_csrf` returns empty string on regex miss instead of failing
- **Files:** `test_dashboard_agents.py:72-77`, `test_dashboard_settings.py:57-62`
- **Category:** Test setup — silent failure

---

## Round 2 Findings (NEW bugs from deeper review)

### HIGH

#### BUG-056: `record_action_result` has no agent auth/kill check — killed agent can poison dependency state
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:532-546`
- **Category:** Security — privilege escalation
- **Description:** Unlike `evaluate_tool_call` and `evaluate_message`, `record_action_result` performs NO agent governance checks. A killed agent can call this to inject fake successful "RunTests" into the dependency checker, then pass the dependency check on a subsequent `evaluate_tool_call` for "GitPush".

### MEDIUM

#### BUG-057: `TempPermissionManager.check()` uses exact match, not hierarchy-aware
- **File:** `safeclaw-service/safeclaw/engine/temp_permissions.py:74`
- **Category:** Logic gap — inconsistency
- **Description:** A temp grant for `"GitPush"` won't match `"ForcePush"` (a subclass). RoleManager uses hierarchy-aware matching but TempPermissionManager does not.

#### BUG-058: Unknown action classes bypass developer role restrictions
- **File:** `safeclaw-service/safeclaw/engine/class_hierarchy.py:76-78`, `roles.py:112-127`
- **Category:** Logic error — security
- **Description:** `get_superclasses("UnknownClass")` returns `{"UnknownClass"}`. If developer role has no `allowed_action_classes` (empty set), `is_action_allowed` returns `True` for unknown classes, bypassing all denied_action_classes.

#### BUG-059: RiskBadge never matches actual risk level strings
- **File:** `safeclaw-service/safeclaw/dashboard/components.py:363-373`
- **Category:** Logic error — UI
- **Description:** Risk badge maps `"low"`, `"medium"`, `"high"`, `"critical"` but actual values are `"LowRisk"`, `"MediumRisk"` etc. After `.lower()` → `"lowrisk"` etc. — no match. No color styling ever applied.

#### BUG-060: Dashboard login uses `==` not constant-time comparison
- **File:** `safeclaw-service/safeclaw/dashboard/app.py:141`
- **Category:** Security — timing attack
- **Description:** `if password == cfg.admin_password` enables timing side-channel. Should use `secrets.compare_digest()`.

#### BUG-061: Dashboard session secret derived from weak hash of admin password
- **File:** `safeclaw-service/safeclaw/dashboard/app.py:24-28`
- **Category:** Security — weak key derivation
- **Description:** `hashlib.sha256(f"safeclaw-session-{admin_password}")` with known prefix. Attacker knowing password can forge session cookies.

#### BUG-062: `build_context` does not verify agent token or kill switch
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:509-530`
- **Category:** Security — information leak
- **Description:** A killed agent can still call `build_context` and receive governance context including policies, constraints, violations, and role definitions.

#### BUG-063: Early-exit governance blocks not recorded for delegation detection
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:206-226`
- **Category:** Security — incomplete detection
- **Description:** When blocked by token auth or kill switch, no `_maybe_record_delegation_block` call. Agent A killed → tries action (blocked, not recorded) → delegates to agent B → delegation not detected.

#### BUG-064: `search_nodes()` rebuilds entire graph per request on unauthenticated endpoint
- **File:** `safeclaw-service/safeclaw/engine/graph_builder.py:109-116`
- **Category:** DoS — performance
- **Description:** `/ontology/search` (no auth) calls `build_graph()` running 2 SPARQL queries per request. No caching or rate limiting.

#### BUG-065: `audit/explain` searches only 200 recent records, should use `get_record_by_id()`
- **File:** `safeclaw-service/safeclaw/api/routes.py:368-369`
- **Category:** Logic error — incorrect lookup
- **Description:** Records older than 200 most recent always return 404. `AuditLogger.get_record_by_id()` exists but isn't used.

#### BUG-066: Half-open probe in HybridEngine allows race condition
- **File:** `safeclaw-service/safeclaw/engine/hybrid_engine.py:50-61`
- **Category:** Race condition
- **Description:** `_probe_lock.locked()` check vs `async with _probe_lock` has TOCTOU gap. `_probing` flag mitigates but lock release before `record_failure/success` creates a window for multiple probes.

#### BUG-067: `MessageGate.check()` creates session state as side-effect
- **File:** `safeclaw-service/safeclaw/constraints/message_gate.py:92-96`
- **Category:** Logic error — side effect
- **Description:** Merely checking a message for a new session creates a session entry (empty list) and may evict an old session. Check should be read-only.

### LOW

#### BUG-068: File operations throughout codebase missing `encoding="utf-8"`
- **Files:** `audit/logger.py:37`, `engine/knowledge_store.py:36`, `api/routes.py:409`
- **Category:** Unicode — platform portability
- **Description:** Multiple `open()` calls don't specify encoding. On Windows, default encoding may not be UTF-8, causing `UnicodeDecodeError`.

#### BUG-069: `ContextBuilder.record_violation` doesn't `move_to_end` for LRU eviction
- **File:** `safeclaw-service/safeclaw/engine/context_builder.py:17-25`
- **Category:** Logic error — LRU
- **Description:** Active sessions not moved to end of OrderedDict, so they may be evicted despite active use.

#### BUG-070: Per-session history lists grow unboundedly in DependencyChecker and SessionTracker
- **Files:** `dependency_checker.py:62`, `session_tracker.py:73`
- **Category:** Memory leak
- **Description:** No per-session cap on lists. Long-running sessions accumulate unlimited entries.

#### BUG-071: `RateLimiter.clear_session` doesn't clear `_agent_records`
- **File:** `safeclaw-service/safeclaw/constraints/rate_limiter.py:137-139`
- **Category:** State leak
- **Description:** Agent records from cleared sessions persist and count against hierarchy rate limits.

#### BUG-072: `HybridEngine.record_action_result` failures don't open circuit breaker
- **File:** `safeclaw-service/safeclaw/engine/hybrid_engine.py:185-202`
- **Category:** Circuit breaker gap

#### BUG-073: `as_rdf_graph()` only adds `file_path` param, not `path`
- **File:** `safeclaw-service/safeclaw/constraints/action_classifier.py:36-39`
- **Category:** SHACL validation gap
- **Description:** Tools using `path` instead of `file_path` won't have path data in RDF graph for SHACL validation.

---

## Round 3 Findings (NEW bugs from third review)

### HIGH

#### BUG-074: `require_auth=True` causes unconditional RuntimeError at import time
- **File:** `safeclaw-service/safeclaw/main.py:58-62`
- **Category:** Import-time side effect
- **Description:** Lines 58-62 execute at module import time (not inside lifespan). If `SAFECLAW_REQUIRE_AUTH=true`, `RuntimeError` is raised unconditionally, preventing any module that imports `safeclaw.main` from functioning. Duplicate of BUG-007 root cause but distinct symptom (import vs startup).

#### BUG-075: `reload()` replaces `agent_registry`, losing all registered agents
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:148-152`
- **Category:** State loss on reload
- **Description:** `_init_components()` creates new `AgentRegistry`, `TempPermissionManager`, `DelegationDetector`, and `RoleManager`, discarding all registered agents, tokens, kill states, temp grants, and delegation records. Related to BUG-001 but distinct: BUG-001 is about race conditions, BUG-075 is about state loss.

#### BUG-087: `AuditLogger` uses `threading.Lock` and sync file I/O in async context
- **File:** `safeclaw-service/safeclaw/audit/logger.py:19,36-38`
- **Category:** Blocking I/O in async context
- **Description:** Synchronous `open()`/`write()` inside `threading.Lock` blocks the asyncio event loop, stalling all concurrent requests until file write completes.

### MEDIUM

#### BUG-076: `reload()` replaces `_session_locks` while locks may be held
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:120`
- **Category:** Race condition
- **Description:** New `_session_locks` OrderedDict means in-flight requests holding old locks lose mutual exclusion with new requests getting fresh locks.

#### BUG-077: `clear_session()` does not clear delegation detector blocks
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:548-556`
- **Category:** Incomplete cleanup
- **Description:** Duplicate of BUG-044 with additional detail: stale blocks cause false delegation detection if session ID is reused within 5-minute window.

#### BUG-078: `RateLimiter.clear_session()` does not clear per-agent records
- **File:** `safeclaw-service/safeclaw/constraints/rate_limiter.py:137-139`
- **Category:** State leak
- **Description:** Duplicate of BUG-071.

#### BUG-079: `CircuitBreakerState.should_try_remote()` TOCTOU race on probe lock
- **File:** `safeclaw-service/safeclaw/engine/hybrid_engine.py:50-62`
- **Category:** Race condition
- **Description:** Duplicate of BUG-066.

#### BUG-080: `HybridEngine.record_action_result()` consumes circuit breaker probe without reporting outcome
- **File:** `safeclaw-service/safeclaw/engine/hybrid_engine.py:185-205`
- **Category:** Circuit breaker state corruption
- **Description:** Duplicate of BUG-072. Neither `record_success()` nor `record_failure()` is called, so probe is wasted and circuit breaker cannot recover.

#### BUG-081: EventBus silently returns empty stream at max subscribers
- **File:** `safeclaw-service/safeclaw/engine/event_bus.py:47-51`
- **Category:** Silent failure
- **Description:** Duplicate of BUG-032.

#### BUG-082: SSE `/events` endpoint has no keepalive or timeout
- **File:** `safeclaw-service/safeclaw/api/routes.py:377-388`
- **Category:** Resource leak
- **Description:** Dead client connections hang forever on `await q.get()`, subscriber queue never cleaned up until 100-event backlog triggers dead-subscriber removal.

#### BUG-083: `/llm/suggestions` creates separate `SafeClawConfig()` instance
- **File:** `safeclaw-service/safeclaw/api/routes.py:399-416`
- **Category:** Configuration inconsistency
- **Description:** Creates `SafeClawConfig()` instead of using `engine.config`, may read wrong data dir in test environments.

#### BUG-084: `sys.getsizeof` for payload size (duplicate of BUG-047)
- **File:** `safeclaw-service/safeclaw/api/models.py:32`

#### BUG-085: `ToolResultEvent` missing `user_id` (duplicate of BUG-043)
- **File:** `safeclaw-service/safeclaw/engine/core.py:37-44`

#### BUG-086: Dashboard password comparison timing attack (duplicate of BUG-060)
- **File:** `safeclaw-service/safeclaw/dashboard/app.py:141`

#### BUG-088: `config.raw` re-reads config file on every access
- **File:** `safeclaw-service/safeclaw/config.py:49-56`
- **Category:** Performance
- **Description:** Property re-opens and re-parses config.json on every access. No caching, no error handling for PermissionError.

#### BUG-089: `reload()` doesn't re-create EventBus but replaces all components
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:56,148-152`
- **Category:** State inconsistency
- **Description:** In-progress evaluations that started before reload mix old and new component references. Subsumes by BUG-001/BUG-075/BUG-076.

#### BUG-090: `TempGrantRequest` allows both scope params None (duplicate of BUG-025)
- **File:** `safeclaw-service/safeclaw/api/models.py:117-120`

#### BUG-091: `DelegationDetector.make_signature()` produces different sigs for equivalent params
- **File:** `safeclaw-service/safeclaw/engine/delegation_detector.py:103-110`
- **Category:** False negatives
- **Description:** `default=str` serializes Path objects platform-dependently. Minor.

#### BUG-092: `search_nodes()` rebuilds graph per request (duplicate of BUG-064)
- **File:** `safeclaw-service/safeclaw/engine/graph_builder.py:109-116`

#### BUG-093: Shell classifier misses `$(...)` command substitution inside quotes
- **File:** `safeclaw-service/safeclaw/constraints/action_classifier.py:108-143`
- **Category:** Security — evasion
- **Description:** `cmd "$(rm -rf /)"` — quote stripping removes the entire quoted string including the `$()` substitution, preventing detection. Addressed by BUG-003 fix (remove quote stripping).

#### BUG-094: `_fire_llm_tasks()` creates untracked `asyncio.Task` objects
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:585,592-594`
- **Category:** Resource management
- **Description:** Fire-and-forget tasks not tracked; during shutdown may cause AttributeError if engine is None.

#### BUG-095: `MessageGate.check()` eviction affects other sessions (duplicate concern of BUG-067)
- **File:** `safeclaw-service/safeclaw/constraints/message_gate.py:90-96`

#### BUG-096: `AuditLogger.get_record_by_id()` string containment check fragile
- **File:** `safeclaw-service/safeclaw/audit/logger.py:98`
- **Category:** Minor correctness
- **Description:** Fast-path filter uses JSON string containment; fragile if serializer changes whitespace. Minor since IDs are UUIDs.

#### BUG-097: `KnowledgeStore._save()` performs sync file I/O on every `record_fact()`
- **File:** `safeclaw-service/safeclaw/engine/knowledge_store.py:46-53,75`
- **Category:** Performance
- **Description:** Rewrites entire file on every fact update, blocking event loop.

#### BUG-098: `reload()` replaces session_tracker/rate_limiter, losing session state
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:96,92`
- **Category:** State loss
- **Description:** Agent can bypass rate limits and dependency checks by triggering admin reload. Subsumed by BUG-001/BUG-075.

#### BUG-099: Plugin `after_tool_call` silently ignores recording failures
- **File:** `openclaw-safeclaw-plugin/index.ts:253-261`
- **Category:** Logic gap
- **Description:** `.catch(() => {})` swallows all errors. Missing recordings break dependency checks.

#### BUG-100: `ContextBuilder._get_user_preferences()` leaks RDF internal properties
- **File:** `safeclaw-service/safeclaw/engine/context_builder.py:81-92`
- **Category:** Data leakage
- **Description:** SPARQL `?pref ?property ?value` returns `rdf:type` and other internal triples alongside preferences, all injected into LLM context.

#### BUG-101: `_evict_unlocked_session_locks()` O(n) scan on every new session
- **File:** `safeclaw-service/safeclaw/engine/full_engine.py:176-187`
- **Category:** Performance
- **Description:** Creates full list copy of all session IDs on every eviction check.

#### BUG-102: `HybridEngine.record_action_result` never reports circuit breaker outcome (duplicate of BUG-072/BUG-080)
- **File:** `safeclaw-service/safeclaw/engine/hybrid_engine.py:185-205`

---

## Deduplication Summary

The following Round 3 bugs are duplicates and will use the earlier bug's fix plan:
- BUG-074 → same root cause as BUG-007
- BUG-077 → duplicate of BUG-044
- BUG-078 → duplicate of BUG-071
- BUG-079 → duplicate of BUG-066
- BUG-080/BUG-102 → duplicate of BUG-072
- BUG-081 → duplicate of BUG-032
- BUG-084 → duplicate of BUG-047
- BUG-085 → duplicate of BUG-043
- BUG-086 → duplicate of BUG-060
- BUG-089 → subsumed by BUG-001/BUG-075/BUG-076
- BUG-090 → duplicate of BUG-025
- BUG-092 → duplicate of BUG-064
- BUG-093 → addressed by BUG-003 fix
- BUG-095 → duplicate concern of BUG-067
- BUG-098 → subsumed by BUG-001/BUG-075

**Unique new bugs from Round 3:** BUG-075, BUG-076, BUG-082, BUG-083, BUG-087, BUG-088, BUG-091, BUG-094, BUG-096, BUG-097, BUG-099, BUG-100, BUG-101

---

## Fix Plan Summary

### Execution Order (grouped by file to minimize merge conflicts)

**Batch 1 — CRITICAL + HIGH security (must-fix)**

| Bug | File(s) | Fix | Effort |
|-----|---------|-----|--------|
| BUG-001/075/076 | full_engine.py | Async reload with lock drain; preserve agent state | M |
| BUG-003/093 | action_classifier.py | Remove quote stripping; handle `bash -c "..."` recursion | M |
| BUG-006/063 | full_engine.py | Audit + delegation recording for early-exit governance blocks | S |
| BUG-007/074 | main.py | Remove import-time RuntimeError; defer to middleware 503 | S |
| BUG-008/026 | routes.py | Fix `require_admin` to use admin_password when auth disabled | S |
| BUG-009 | roles.py | Reject paths with `..` components after normpath | S |
| BUG-010 | safeclaw-policy.ttl, action_classifier.py | Broaden rm regex to catch flag variants | S |
| BUG-011 | action_classifier.py | Track all chained command classes; check deps for each | S |
| BUG-013 | safeclaw-agent.ttl | ForcePush subClassOf GitPush | S |
| BUG-056 | full_engine.py | Add token/kill check to record_action_result | S |
| BUG-062 | full_engine.py | Add token/kill check to build_context | S |

**Batch 2 — MEDIUM functional bugs**

| Bug | File(s) | Fix | Effort |
|-----|---------|-----|--------|
| BUG-002 | full_engine.py | Check role.enforcement_mode before blocking | S |
| BUG-004/035 | reasoning_rules.py, session_tracker.py | Use server-side history; structured risk counting | S |
| BUG-005 | routes.py | Add `require_admin` to sensitive endpoints | S |
| BUG-012 | index.ts | Change `event.success ?? true` to `?? false` | S |
| BUG-014 | roles.py | Load roles from KG TTL files | M |
| BUG-015 | full_engine.py | Unify resource_path key precedence (file_path > path) | S |
| BUG-017 | dependency_checker.py | Hierarchy-aware dependency lookup | S |
| BUG-019 | full_engine.py | Add session lock to evaluate_message | S |
| BUG-020 | temporal_checker.py | Log warning + fail-closed on parse errors | S |
| BUG-021 | config.py | Add `$` anchor to CORS regex | S |
| BUG-022 | index.ts | Reverse config precedence: file < env vars | S |
| BUG-025 | models.py | Add Pydantic model_validator for TempGrantRequest | S |
| BUG-027 | agent_registry.py | Reject re-registration with 409 | S |
| BUG-028 | full_engine.py, routes.py | Make clear_session async with session lock | S |
| BUG-030 | roles.py | Validate list types for action classes | S |
| BUG-031 | preference_checker.py, context_builder.py | Exact URI match instead of STRENDS | S |
| BUG-032 | routes.py | Return 429 at max subscribers | S |
| BUG-033 | session_tracker.py | Sanitize command text for LLM context | S |
| BUG-034 | delegation_detector.py | Default mode to "strict"; validate modes | S |
| BUG-057 | temp_permissions.py | Hierarchy-aware temp grant matching | S |
| BUG-058 | roles.py, class_hierarchy.py | Unknown classes denied for restricted roles | S |
| BUG-059 | dashboard/components.py | Fix RiskBadge key mapping | S |
| BUG-060 | dashboard/app.py | Use secrets.compare_digest for password | S |
| BUG-061 | dashboard/app.py | Use os.urandom for session secret | S |
| BUG-064 | graph_builder.py, full_engine.py | Cache graph; add to engine | S |
| BUG-065 | routes.py, cli/audit_cmd.py | Use get_record_by_id instead of 200-limit | S |
| BUG-066 | hybrid_engine.py | Remove lock; use sync _probing flag for asyncio | S |
| BUG-067 | message_gate.py | Move state mutation from check() to record_message() | S |
| BUG-082 | routes.py | Add SSE keepalive; handle disconnects | S |
| BUG-083 | routes.py | Use engine.config instead of new SafeClawConfig() | S |
| BUG-087 | audit/logger.py | Use asyncio.to_thread for file writes | M |
| BUG-088 | config.py | Cache config.raw with lazy loading | S |
| BUG-100 | context_builder.py | Filter RDF internal properties from preferences | S |

**Batch 3 — LOW priority cleanup**

| Bug | File(s) | Fix | Effort |
|-----|---------|-----|--------|
| BUG-016 | preference_checker.py | Implement never_modify_paths check | S |
| BUG-018 | policy_checker.py | Expand path param key search | S |
| BUG-023 | index.ts | Add warn-only logging to message_sending | S |
| BUG-024 | index.ts | Log in audit-only + fail-closed | S |
| BUG-029 | cli/pref_cmd.py | Write to ~/.safeclaw/ontologies/ not package dir | S |
| BUG-036 | .gitignore | Add .sesskey; git rm --cached | S |
| BUG-037 | config.py, full_engine.py | Add encoding="utf-8"; catch UnicodeDecodeError | S |
| BUG-038 | reasoning_rules.py | Remove redundant transitive prohibition rule | S |
| BUG-040 | action_classifier.py | Use dataclasses.replace() in _enrich_from_ontology | S |
| BUG-041 | rate_limiter.py | Prune expired records in check() | S |
| BUG-042 | roles.py | Deep-copy BUILTIN_ROLES | S |
| BUG-043 | core.py, models.py, routes.py | Add user_id to ToolResultEvent | S |
| BUG-044 | delegation_detector.py, full_engine.py | Add clear_session to DelegationDetector | S |
| BUG-045 | safeclaw-landing/main.py | Dynamic copyright year | S |
| BUG-046 | action_classifier.py | Add bare `rm` pattern | S |
| BUG-047 | models.py | Use len(encode()) not sys.getsizeof | S |
| BUG-048 | policy_checker.py | Collect all violations, not just first | S |
| BUG-049 | shacl_validator.py | Generic error message, keep detail in logs | S |
| BUG-050 | full_engine.py | Use classifier for message risk level | S |
| BUG-051 | safeclaw-landing/main.py | Add rel="noopener noreferrer" | S |
| BUG-052 | safeclaw-agent.ttl | Add NetworkRequest defaults | S |
| BUG-068 | multiple files | Add encoding="utf-8" to all open() | S |
| BUG-069 | context_builder.py | Add move_to_end for LRU | S |
| BUG-070 | dependency_checker.py, session_tracker.py | Cap per-session lists | S |
| BUG-071 | rate_limiter.py | Add clear_agent method | S |
| BUG-072 | hybrid_engine.py | Add record_success/failure to record_action_result | S |
| BUG-073 | action_classifier.py | Check `path` param in as_rdf_graph | S |
| BUG-094 | full_engine.py | Track background tasks; cancel on shutdown | S |
| BUG-097 | knowledge_store.py | Batch/debounce file writes | S |
| BUG-099 | index.ts | Log recording failures instead of swallowing | S |
| BUG-101 | full_engine.py | Optimize eviction to avoid list copy | S |

### Conflict Matrix

Files touched by multiple bugs (apply in listed order):
- **full_engine.py**: BUG-001→006→063→056→062→002→015→019→028→050→094→101→044
- **action_classifier.py**: BUG-003→010→011→046→040→073
- **roles.py**: BUG-009→030→042→058→014
- **routes.py**: BUG-005→008→032→065→082→083
- **index.ts**: BUG-012→022→023→024→099
- **hybrid_engine.py**: BUG-066→072
