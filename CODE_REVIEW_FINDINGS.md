# SafeClaw Code Review Round 2 — Findings & Fix Plans

**Date:** 2026-02-18
**Scope:** All files in safeclaw-service/ and openclaw-safeclaw-plugin/
**Tests at start:** 216 passing
**Reviewers:** 3 parallel agents (engine, API, tests/ontology)
**Tests at end:** 227 passing
**Status:** ALL FIXES APPLIED

### Validation Summary (verified by 3 parallel agents reading actual source)
- **36 CONFIRMED** — real issues verified against source code
- **3 PARTIALLY CORRECT** — R2-05 (fnmatch example wrong but concern valid), R2-75 (also never produced by classifier), R2-78 (limited by design)
- **1 FALSE POSITIVE** — R2-35 (Pydantic v2 handles mutable defaults correctly, not a bug)
- **1 DESIGN DECISION** — R2-01 (Henrik chose "Count all attempts" for rate limiting)
- **1 AWARENESS ONLY** — R2-42 (Dockerfile pip as root, no fix needed)

### Totals: 42 findings (40 actionable after removing false positive + design decision)
| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 4 |
| MEDIUM | 23 (was 24, R2-35 removed as false positive) |
| LOW | 12 |
| DESIGN DECISION | 1 |
| FALSE POSITIVE | 1 |

---

## Fix Phase Order (non-conflicting)

Fixes are organized into 5 sequential phases. Within each phase, all changes touch different files/sections and can be done in parallel by separate agents.

| Phase | Focus | Files Touched | Finding IDs |
|-------|-------|---------------|-------------|
| **1** | Security (CRITICAL + HIGH) | audit/logger.py, main.py, routes.py, safeclaw-policy.ttl, roles/*.ttl, test_shacl_validation.py, test_engine.py | R2-30, R2-31, R2-32, R2-62, R2-65, R2-73 |
| **2** | Engine + Constraints (MEDIUM) | full_engine.py, action_classifier.py, knowledge_store.py, roles.py, hybrid_engine.py | R2-02, R2-03, R2-04, R2-05, R2-06 |
| **3** | API + CLI (MEDIUM) | audit/models.py, reporter.py, routes.py (different lines from P1), models.py, auth/middleware.py, audit/logger.py (different method from P1), cli/policy_cmd.py | R2-33, R2-34, R2-36, R2-37, R2-38, R2-39, R2-40 |
| **4** | Tests (MEDIUM) | test_action_classifier.py, test_api.py, test_coverage.py, test_multi_agent_governance.py, new test files | R2-60, R2-61, R2-63, R2-64, R2-67, R2-68, R2-69, R2-71, R2-79 |
| **5** | Ontology + LOW | full_engine.py (different line from P2), index.ts, cli/serve.py, audit/logger.py (different method), test_phase2.py, safeclaw-agent.ttl, roles/*.ttl (different triples from P1), shapes/*.ttl, safeclaw-policy.ttl (different section) | R2-07, R2-41, R2-43, R2-44, R2-66, R2-70, R2-72, R2-74, R2-75, R2-76, R2-77, R2-78 |

**Conflict notes:**
- `audit/logger.py` touched in P1 (get_session_records), P3 (get_recent_records), P5 (get_blocked_records) — all different methods, no conflict
- `routes.py` touched in P1 (require_admin comment) and P3 (limit bounds) — different lines, no conflict
- `full_engine.py` touched in P2 (_session_locks) and P5 (log_llm_io) — different methods, no conflict
- `roles/*.ttl` touched in P1 (add sp:Role definitions) and P5 (fix class names) — different triples, no conflict
- `models.py` touched only in P3 (mutable defaults + remove redundant field) — no conflict

---

## CRITICAL (1 finding)

### R2-30 | CRITICAL | `audit/logger.py:43-48` — Path traversal in `get_session_records`
**Phase:** 1
**Problem:** `get_session_records()` does NOT sanitize `session_id` before constructing a filename (line 48: `day_dir / f"session-{session_id}.jsonl"`), unlike `_get_session_file()` (line 26) which uses `re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)`. A crafted session_id like `../../etc/passwd` could traverse outside the audit directory.
**Fix plan:** Extract `re.sub` into a shared `_safe_id(session_id)` method. Use it in both `_get_session_file()` and `get_session_records()`.

---

## HIGH (4 findings)

### R2-31 | HIGH | `main.py:42` — CORS wildcard pattern does not work in Starlette
**Phase:** 1
**Problem:** `allow_origins=["http://localhost:*"]` — Starlette's CORSMiddleware does NOT support glob patterns in individual origin strings. The `*` is treated literally, matching nothing. This effectively blocks all CORS requests from the TypeScript plugin.
**Fix plan:** Replace with `allow_origin_regex=r"http://localhost:\d+"` for proper localhost matching with any port.

### R2-32 | HIGH | `routes.py:30-34` — `require_admin` bypassed when auth is disabled
**Phase:** 1
**Problem:** When auth middleware is disabled (default: `require_auth=False`), `api_key_scope` is never set. The `require_admin` dependency returns `None` (no scope) and passes through, meaning admin endpoints (`/reload`, `/agents/register`, `/agents/{id}/kill`) are unprotected.
**Fix plan:** This is intentional for local development. Add explicit documentation comment and a config flag `allow_admin_without_auth` (default `True`) that must be explicitly set. When deploying with auth enabled, this should be `False`.

### R2-62 | HIGH | `test_shacl_validation.py` — No SHACL test for ShellAction or MessageAction shapes
**Phase:** 1
**Problem:** Tests only validate `action-shapes.ttl`. No tests for `command-shapes.ttl` (ShellCommandShape) or `message-shapes.ttl` (MessageActionShape). The `MessageActionShape` requires `sc:affectsScope` to be `sc:ExternalWorld` — never tested.
**Fix plan:** Add tests: (1) ShellAction with two `sc:commandText` values → should fail maxCount; (2) MessageAction with `affectsScope` set to `sc:LocalOnly` → should fail the MessageActionShape constraint.

### R2-65 | HIGH | `test_engine.py:62-72` — Test assertion too loose
**Phase:** 1
**Problem:** `test_delete_blocked_by_policy_or_preference` asserts `"SafeClaw" in decision.reason`, which is a prefix on ALL blocked decisions. Cannot distinguish which constraint blocked the action.
**Fix plan:** Assert a specific constraint keyword like `"Recursive deletion"` or `"confirmation"` in the reason.

### R2-73 | HIGH | `roles/*.ttl` — Role ontology uses undefined classes and properties
**Phase:** 1
**Problem:** Role files reference `sp:Role`, `sp:allowsAction`, `sp:deniesAction`, `sp:deniesWritePath`, `sp:autonomyLevel`, `sp:enforcementMode` — none of which are defined in `safeclaw-policy.ttl`. The ontology is internally inconsistent.
**Fix plan:** Add `sp:Role` class and its properties to `safeclaw-policy.ttl`. Define `sp:allowsAction`, `sp:deniesAction`, `sp:deniesWritePath`, `sp:autonomyLevel`, `sp:enforcementMode` with proper `rdfs:domain`/`rdfs:range`.

---

## DESIGN DECISION (1 finding — no fix needed)

### R2-01 | ~~HIGH~~ DESIGN DECISION | `full_engine.py:194-195` — Rate limiter records ALL attempts before checks
**Problem:** `rate_limiter.record()` is called on line 195 before other constraint checks. Actions blocked by SHACL, policy, or roles still count toward the rate limit. This inflates the rate counter with "phantom" blocked actions.
**Resolution:** This is an explicit design choice from F-12 fix. Henrik chose "Count all attempts" to prevent DoS via rapid rejected requests. The current behavior is correct: even blocked attempts consume rate budget. **No fix needed.**

---

## MEDIUM (24 findings)

### R2-02 | MEDIUM | `full_engine.py:104` — `_session_locks` dict grows unboundedly
**Phase:** 2
**Problem:** `_get_session_lock()` creates locks but they're only cleaned up in `clear_session()`. If clients disconnect without cleanup, this dict grows without bound. Other per-session dicts use `OrderedDict` with `MAX_SESSIONS` eviction.
**Fix plan:** Use `OrderedDict` with max size (e.g., 10000). On eviction, pop oldest lock.

### R2-03 | MEDIUM | `action_classifier.py:99-100` — Shell command splitting ignores quoting
**Phase:** 2
**Problem:** `re.split(r'\s*(?:&&|\|\||;)\s*', command)` splits naively, including inside quoted strings. `echo "foo && rm -rf /"` would be mis-split, causing a false positive `DeleteFile` classification.
**Fix plan:** Use `shlex.split()` or add a pre-check: skip splitting when the separator is inside balanced quotes. For a simple approach, use a regex that respects quoted strings: skip content within `"..."` or `'...'`.

### R2-04 | MEDIUM | `knowledge_store.py:30-43` — Single corrupted JSONL line discards entire store
**Phase:** 2
**Problem:** The `except` wraps the entire for-loop. One bad line at position N causes lines 1..N-1 (already loaded) to be cleared via `self._facts.clear()`.
**Fix plan:** Move try/except inside the for-loop to skip individual bad lines:
```python
for line in f:
    line = line.strip()
    if line:
        try:
            fact = json.loads(line)
            self._facts[fact["id"]] = fact
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping corrupted line: {e}")
```

### R2-05 | MEDIUM | `roles.py:112-120` — `fnmatch` does not respect path separators (over-blocks) [PARTIALLY CORRECT]
**Phase:** 2
**Validation:** The specific claim that `/etc/**` matches `/etc-backup/foo` is FALSE (the pattern requires `/etc/` prefix). However, `fnmatch` DOES match `/` inside `*`, so `/secrets/*` would match `/secrets/a/b/c` (deeply nested paths). The over-matching concern is valid, just with different examples.
**Fix plan:** Replace `fnmatch` with `pathlib.PurePosixPath.match()` or implement explicit path-segment matching.

### R2-06 | MEDIUM | `hybrid_engine.py:121-123` — Fail-open when both remote and local unavailable
**Phase:** 2
**Problem:** When remote is down AND no local engine is configured, returns `Decision(block=False)` — allowing ALL actions. Same pattern on lines 151-153 and 175-177.
**Fix plan:** Add a `fail_closed` config parameter (default `True`). When both engines are unavailable: if `fail_closed`, return `Decision(block=True, reason="SafeClaw service unavailable")`.

### R2-33 | ~~HIGH~~ MEDIUM | `audit/models.py:44` + `reporter.py:107` — Misleading `allowed_with_warning` comment
**Phase:** 3
**Problem:** `audit/models.py:44` has a comment `# "allowed" | "blocked" | "allowed_with_warning"` but the engine NEVER produces `allowed_with_warning`. The reporter uses `blocked = total - allowed` which is correct for the two-state system, but the comment suggests a third state exists. Previous review F-36 confirmed only two states exist.
**Fix plan:** Remove the misleading `allowed_with_warning` from the comment. Explicitly count `blocked` in reporter for future-proofing: `blocked = sum(1 for r in records if r.decision == "blocked")`.

### R2-34 | MEDIUM | `routes.py:150,171,196` — No upper bound on `limit` query parameters
**Phase:** 3
**Problem:** The `limit` parameter on `/audit`, `/audit/statistics`, `/audit/compliance` has no max bound. A client can send `limit=999999999`, causing the server to parse arbitrarily many JSONL files into memory. DoS vector.
**Fix plan:** Add `Query(20, ge=1, le=1000)` to cap the limit at 1000.

### ~~R2-35~~ | ~~MEDIUM~~ | `models.py:10,35` — REMOVED (FALSE POSITIVE)
**Validation:** Pydantic v2 correctly creates new instances for mutable default values (`dict = {}`, `list[str] = []`). The default objects are NOT shared across model instances. This is safe and idiomatic Pydantic. Not a bug — no fix needed.

### R2-36 | MEDIUM | `auth/middleware.py:19,28` — Path matching does not handle sub-paths
**Phase:** 3
**Problem:** `SKIP_PATHS` uses exact matching. `/docs` is skipped but `/docs/oauth2-redirect` is NOT, causing potential auth failures for the Swagger OAuth redirect.
**Fix plan:** Use prefix matching for `/docs`: `any(request.url.path.startswith(p) for p in SKIP_PREFIXES)`. Keep exact match for `/api/v1/health` and `/openapi.json`.

### R2-37 | MEDIUM | `audit/logger.py:60-76` — `get_recent_records` returns records in wrong order
**Phase:** 3
**Problem:** Iterates day dirs in reverse (newest first), but reads lines within each file in forward order (oldest first). The result mixes chronological ordering.
**Fix plan:** Sort final result by timestamp descending, or read file lines in reverse order.

### R2-38 | MEDIUM | `models.py:77` — `TempGrantRequest` has redundant `agentId` field
**Phase:** 3
**Problem:** `TempGrantRequest.agentId` is silently ignored because the route uses `agent_id` from the URL path parameter. Confusing if body and URL disagree.
**Fix plan:** Remove `agentId` from `TempGrantRequest`.

### R2-39 | MEDIUM | `cli/policy_cmd.py:119-122` — Policy `remove` regex is greedy with DOTALL
**Phase:** 3
**Problem:** With `re.DOTALL | re.MULTILINE`, the `.*?` can match across line boundaries. Adjacent policy blocks without blank lines could cause the regex to match into the wrong block.
**Fix plan:** Use a more precise pattern that matches Turtle block structure (lines ending with `;` until `.`), or match line-by-line.

### R2-40 | MEDIUM | `cli/policy_cmd.py:10-11` — `_escape_turtle` incomplete
**Phase:** 3
**Problem:** Only escapes `\`, `"`, and `\n`. Missing `\r` and `\t`. Tabs or carriage returns in user input produce malformed Turtle.
**Fix plan:** Add `.replace('\r', '\\r').replace('\t', '\\t')`.

### R2-60 | MEDIUM | `test_action_classifier.py` — Missing test for chained shell commands
**Phase:** 4
**Problem:** `_classify_shell()` splits on `&&`, `||`, `;` and picks highest-risk subcommand. No test for this "highest risk wins" logic.
**Fix plan:** Add test: `"ls -la && git push --force origin main"` should classify as `ForcePush` with `CriticalRisk`.

### R2-61 | MEDIUM | `test_action_classifier.py:77-81` — RDF graph test has no meaningful assertion
**Phase:** 4
**Problem:** `test_action_rdf_graph` only asserts `len(graph) > 0`. Doesn't verify the correct `rdf:type`, `sc:hasRiskLevel`, or `sc:commandText` triples.
**Fix plan:** Add assertions for specific triples: correct `rdf:type sc:GitPush`, `sc:hasRiskLevel sc:HighRisk`, etc.

### R2-63 | MEDIUM | `test_api.py:56-64` — Message evaluation test weak assertion
**Phase:** 4
**Problem:** `test_evaluate_message_normal` only asserts `"block" in data`. Doesn't verify the actual decision or reason.
**Fix plan:** Assert `data["block"] is True` (confirm_before_send default) and check reason mentions preference.

### R2-64 | MEDIUM | `test_api.py` — No API tests for newer endpoints
**Phase:** 4
**Problem:** 18 endpoints defined, only 9 tested. Missing: `/log/llm-input`, `/log/llm-output`, `/audit/statistics`, `/audit/report/{session_id}`, `/audit/compliance`, `/ontology/graph`, `/ontology/search`, `/agents/{id}/kill`, `/agents/{id}/revive`, `/agents`, `/agents/{id}/temp-grant`, `/tasks/{id}/complete`.
**Fix plan:** Add API tests for the most important untested endpoints: agent kill/revive, temp-grant, audit statistics/compliance.

### R2-67 | MEDIUM | `test_coverage.py:103` — Accessing private `_session_history`
**Phase:** 4
**Problem:** Test accesses `engine.dependency_checker._session_history` directly. Tight coupling to implementation internals.
**Fix plan:** Use public interface: verify `dependency_checker.check()` returns `unmet=False` for the recorded action class.

### R2-68 | MEDIUM | `test_coverage.py:147` — Another private attribute access
**Phase:** 4
**Problem:** Asserts `session_id not in engine.dependency_checker._session_history` after `clear_session()`.
**Fix plan:** Verify via public `check()`: after clearing, dependency check should behave as if no history.

### R2-69 | MEDIUM | `test_multi_agent_governance.py:489-490` — Conditional assertion in temp grant test
**Phase:** 4
**Problem:** `if decision.block:` makes assertion conditional. Test passes without verifying the grant actually worked if `block` is `False`.
**Fix plan:** Assert `decision.block is False` directly. If other constraints may block, explain in comment and verify the block reason is NOT role-related.

### R2-71 | MEDIUM | Tests — No test for `PolicyChecker._safe_match()` error handling
**Phase:** 4
**Problem:** `_safe_match` handles `re.error` for malformed regex. No test for this defensive code path.
**Fix plan:** Add test that loads a policy with an invalid regex pattern (`[unclosed`) and verifies the checker doesn't crash.

### R2-72 | MEDIUM | `safeclaw-agent.ttl:172-234` — Risk assignments on classes, not instances
**Phase:** 5
**Problem:** Default risk triples are added directly to OWL classes (e.g., `sc:ReadFile sc:hasRiskLevel sc:LowRisk`). Conflates class/instance distinction. The Python code doesn't read these — they're redundant with hardcoded `TOOL_MAPPINGS`.
**Fix plan:** Either add `owl:NamedIndividual` punning to make dual use explicit, or remove the default risk assignments from the ontology since they're not consumed by code.

### R2-74 | MEDIUM | `roles/developer.ttl:10` — Inconsistent action class names
**Phase:** 5
**Problem:** Developer role denies `sc:GitForcePush`, `sc:DeleteRootFiles`, `sc:SystemConfigChange` — none exist in `safeclaw-agent.ttl`. The canonical names are `sc:ForcePush`, etc.
**Validation note:** The mismatch is partially masked because Python `BUILTIN_ROLES` and tests ALSO use the wrong names (e.g., `GitForcePush`). The `ActionClassifier` produces `ForcePush`, so in a full pipeline test, the role denial wouldn't match. Both .ttl files AND Python code need alignment.
**Fix plan:** Update role .ttl files to use canonical names from `safeclaw-agent.ttl`. Also update `BUILTIN_ROLES` in `roles.py` to match.

### R2-76 | MEDIUM | `shapes/action-shapes.ttl` — SHACL shape name misleading
**Phase:** 5
**Problem:** `CriticalIrreversibleShape` name suggests it enforces the "critical + irreversible requires confirmation" rule, but it only validates cardinality and datatypes. The actual constraint is in Python.
**Fix plan:** Rename to `sc:ActionStructureShape` and update `rdfs:comment`.

### R2-79 | MEDIUM | Tests — No test for `DependencyChecker` loading from KG
**Phase:** 4
**Problem:** `DependencyChecker._load_dependencies()` queries the KG, but the engine test `test_git_push_blocked_without_tests` passes even if the SPARQL query broke (fallback to `DEFAULT_DEPENDENCIES`).
**Fix plan:** Add test that creates a `DependencyChecker` with a KG and verifies `_dependencies` contains KG-loaded entries beyond defaults.

---

## LOW (12 findings)

### R2-07 | LOW | `full_engine.py:456` — Log truncation always shows `...`
**Phase:** 5
**Problem:** `event.content[:100] + "..."` always appends `...` even for content under 100 chars.
**Fix plan:** `content[:100] + ("..." if len(event.content) > 100 else "")`.

### R2-41 | LOW | `index.ts` — Plugin silently swallows non-OK HTTP (fail-open)
**Phase:** 5
**Problem:** Non-200 responses return `null`, treated as "no block decision" — allowing the action. Server errors cause fail-open.
**Fix plan:** Add config option `failMode: 'open' | 'closed'`. Default to `'closed'` for `enforce` mode.

### R2-42 | LOW | Dockerfile — pip runs as root before creating user (AWARENESS ONLY)
**Phase:** N/A
**Problem:** `pip install` runs as root, then `useradd` creates safeclaw user. Standard practice. Safeclaw user cannot update packages at runtime.
**Resolution:** No fix needed. Noting for awareness.

### R2-43 | LOW | `cli/serve.py:7` — Binds to `0.0.0.0` by default
**Phase:** 5
**Problem:** CLI `serve` command defaults to `0.0.0.0`, overriding `config.py`'s `127.0.0.1` default. Combined with `require_auth=False`, this exposes an unauthenticated API to the network.
**Fix plan:** Change CLI default to `127.0.0.1` to match config.py.

### R2-44 | LOW | `audit/logger.py:78-79` — `get_blocked_records` inefficient over-fetch
**Phase:** 5
**Problem:** Fetches `limit * 3` records then filters for blocked. The `3x` multiplier is arbitrary and may not return enough blocked records if block rate is low.
**Fix plan:** Implement scanning approach or document as "best effort". For a simple fix, increase multiplier to 5x or add a loop that keeps fetching until `limit` blocked records found.

### R2-66 | LOW | `test_phase2.py:119-132` — Temporal constraint test is a no-op
**Phase:** 5
**Problem:** Tests that a non-existent constraint doesn't block — identical to the test above it. Misleading docstring says it tests blocking.
**Fix plan:** Rename to `test_temporal_constraint_no_constraint_passes` and fix docstring. Or add actual temporal constraint blocking test.

### R2-70 | LOW | `test_phase2.py:248-250` — Session eviction test uses magic number
**Phase:** 5
**Problem:** Creates 1001 sessions with hardcoded number. Also accesses private `_sessions`.
**Fix plan:** Import `MAX_SESSIONS` from `rate_limiter` and use `MAX_SESSIONS + 1`. Use public `check()` for assertion.

### R2-72 is listed above in MEDIUM section.

### R2-75 | LOW | `roles/researcher.ttl:9` — References undefined `sc:ListFiles` and `sc:SearchFiles` [PARTIALLY CORRECT]
**Phase:** 5
**Problem:** `sc:ListFiles` and `sc:SearchFiles` don't exist in `safeclaw-agent.ttl`.
**Validation note:** Additionally, `ActionClassifier` never produces `ListFiles` or `SearchFiles` — it maps `glob`/`grep` to `ReadFile`. So these allowed actions in the researcher role never match any classified action, making the researcher MORE restrictive than intended.
**Fix plan:** Add `sc:ListFiles` and `sc:SearchFiles` as subclasses of `sc:FileAction` in `safeclaw-agent.ttl`. Also add classifier mappings for these action types.

### R2-77 | LOW | `shapes/command-shapes.ttl` — No `sh:minCount` on `commandText`
**Phase:** 5
**Problem:** A ShellAction without any `commandText` would pass validation. The `ActionClassifier.as_rdf_graph()` always emits it, but the shape doesn't enforce it.
**Fix plan:** Add `sh:minCount 1` to the `sc:commandText` property constraint.

### R2-78 | LOW | `safeclaw-policy.ttl:113` — `NoRootDelete` regex limited scope [PARTIALLY CORRECT]
**Phase:** 5
**Problem:** Pattern `rm\s+-rf\s+/` only matches `rm -rf /...`. Doesn't match `rm -f -r /`, `rm --recursive --force /`, etc. Gap between classifier pattern and policy pattern.
**Validation note:** The classifier pattern `\brm\s+(-[rRf]+\s+|.*--force)` is broader and catches more variants. The policy regex is intentionally narrower (root paths only). The gap is by design but could surprise users.
**Fix plan:** Document the intentional scope difference. Optionally broaden the policy regex to catch `rm -r -f /` variants.

---

## Previous Reviews Summary

**Round 1:** 59 findings (6 CRITICAL, 11 HIGH, 25 MEDIUM, 17 LOW). 58 confirmed, 1 false positive. Tests: 207 → 216.
**Round 2:** 42 findings (1 CRITICAL, 4 HIGH, 24 MEDIUM, 12 LOW). 40 confirmed, 1 false positive, 1 design decision. Tests: 216 → 227.

---
---

# SafeClaw Code Review Round 3 — Findings & Fix Plans

**Date:** 2026-02-18
**Scope:** All files in safeclaw-service/ and openclaw-safeclaw-plugin/
**Reviewers:** 3 parallel agents (engine/constraints, API/auth/audit/CLI, tests/ontology)
**Tests at start:** 227 passing
**Status:** ALL FIXES APPLIED
**Tests at end:** 233 passing (up from 227)

### Validation Summary (verified by 3 parallel agents reading actual source)
- **37 CONFIRMED** — real issues verified against source code
- **9 PARTIALLY CORRECT** — R3-03 (only Python <3.12), R3-07 (backtick non-stripping is correct behavior), R3-10 (crash is unhandled exception, not silent), R3-37 (transport limits exist), R3-43 (replaces all is correct behavior), R3-47 (enforcement validated but failMode not), R3-48 (transport limits reduce severity), R3-62 (behavior tested elsewhere), R3-72 (float value is practically stable)
- **1 FALSE POSITIVE** — R3-42 (regex is well-constructed with re.escape, handles dots correctly)
- **1 DESIGN DECISION** — R3-02 (same as R2-01, Henrik chose "Count all attempts")

### Totals: 49 findings (47 actionable after removing false positive + design decision)
| Severity | Count |
|----------|-------|
| HIGH | 10 (was 11, R3-48 downgraded to MEDIUM) |
| MEDIUM | 25 (was 25, +1 from R3-48, -1 R3-42 removed) |
| LOW | 12 |
| DESIGN DECISION | 1 |
| FALSE POSITIVE | 1 |

---

## Fix Phase Order (non-conflicting)

Fixes are organized into 6 parallel phases. Each phase touches completely different files — all 6 can run simultaneously with zero merge conflicts.

| Phase | Focus | Files Touched | Finding IDs |
|-------|-------|---------------|-------------|
| **1** | Engine Core | full_engine.py, knowledge_store.py, session_tracker.py, temp_permissions.py, graph_builder.py | R3-01, R3-05, R3-09, R3-10, R3-11, R3-12, R3-44, R3-45, R3-49 |
| **2** | Constraints | roles.py, action_classifier.py, message_gate.py, context_builder.py, preference_checker.py | R3-03, R3-04, R3-06, R3-07, R3-08 |
| **3** | API/Auth/Audit/CLI | main.py, routes.py, models.py, auth/middleware.py, audit/logger.py, cli/policy_cmd.py, cli/pref_cmd.py, Dockerfile | R3-30, R3-31, R3-32, R3-33, R3-34, R3-35, R3-36, R3-37, R3-38, R3-39, R3-40, R3-41, R3-43, R3-48, R3-50, R3-51 |
| **4** | TypeScript Plugin | openclaw-safeclaw-plugin/index.ts | R3-46, R3-47 |
| **5** | Tests | test_*.py files | R3-60, R3-61, R3-62, R3-63, R3-64, R3-65, R3-66, R3-67, R3-71, R3-72, R3-73 |
| **6** | Ontologies | roles/*.ttl, admin.ttl, shapes/ (new file-shapes.ttl) | R3-68, R3-69, R3-70, R3-74 |

**Conflict notes:**
- Within Phase 1: full_engine.py touched by R3-01, R3-09, R3-10, R3-49 — all different methods, no conflict
- Within Phase 3: main.py touched by R3-30, R3-31, R3-32, R3-50 — adjacent lines, single fixer handles all
- Within Phase 3: routes.py touched by R3-33, R3-34, R3-35, R3-36, R3-48 — different endpoints
- Within Phase 3: audit/logger.py touched by R3-38, R3-39, R3-40 — different methods
- No cross-phase file conflicts

---

## DESIGN DECISION (1 finding — no fix needed)

### R3-02 | ~~HIGH~~ DESIGN DECISION | `full_engine.py:200-201` — Rate limiter records before pipeline decides
**Problem:** Same issue as R2-01. Rate limiter records ALL attempts (including blocked ones) before the constraint pipeline decides. An attacker could burn through rate limits with deliberately malformed requests.
**Resolution:** Same as R2-01 — Henrik chose "Count all attempts" to prevent DoS via rapid rejected requests. **No fix needed.**

---

## HIGH (10 findings)

### R3-01 | HIGH | `full_engine.py:125-132` — Session lock eviction can delete actively-held locks
**Phase:** 1
**Code:** `_get_session_lock()` uses `OrderedDict.popitem(last=False)` for LRU eviction when max locks reached.
**Problem:** Eviction removes the oldest lock from the dict, but that lock may currently be held by another coroutine inside `evaluate_tool_call`. The evicted lock still exists in memory (the coroutine holds a reference), but if a new request arrives for that same session, a NEW lock is created — allowing two coroutines to run the constraint pipeline concurrently for the same session, defeating TOCTOU protection.
**Fix plan:** Before evicting, check `lock.locked()`. If locked, skip to the next oldest entry. Add a `_try_evict()` method that walks the OrderedDict from oldest to newest, skipping locked entries.

### R3-31 | HIGH | `main.py:40-45` — CORS regex only allows localhost, blocks production
**Phase:** 3
**Code:** `allow_origin_regex=r"http://localhost:\d+"`
**Problem:** Only matches `http://localhost:<port>`. Any non-localhost client (e.g., `safeclaw.uku.ai`) is blocked. Also only matches `http:`, not `https:`. If the TS plugin ever runs in a browser context, this breaks.
**Fix plan:** Make `allow_origin_regex` configurable via `SafeClawConfig`. Default to `r"https?://localhost:\d+"` for dev. Add a `cors_origin_regex` config field.

### R3-33 | HIGH | `routes.py:150-163` — Audit endpoints lack authorization
**Phase:** 3
**Code:** `/audit`, `/audit/statistics`, `/audit/compliance`, `/audit/report/{session_id}` have no `dependencies=[Depends(require_admin)]`.
**Problem:** Any unauthenticated user can query all audit records containing sensitive information (tool params, user IDs, session IDs, action details). Compare with `/reload` which correctly uses `require_admin`.
**Fix plan:** Add `dependencies=[Depends(require_admin)]` to all audit read endpoints.

### R3-48 | ~~HIGH~~ MEDIUM | `routes.py:221-226` — Ontology search has no input length limit
**Phase:** 3
**Code:** `q: str = Query(...)` with no `max_length`.
**Problem:** Unbounded query string. Combined with `search_nodes()` which builds the full graph on every call (new `GraphBuilder` each time), this enables DoS. Graph building is expensive for large ontologies.
**Validation note:** Transport-level limits (uvicorn ~8KB URL limit) provide some protection. Severity downgraded to MEDIUM.
**Fix plan:** Add `Query(..., max_length=200)`. Consider caching the `GraphBuilder` on the engine instance.

### R3-50 | HIGH | `main.py:54-57` — Global mutable engine variable with TOCTOU on shutdown
**Phase:** 3
**Code:** `engine: FullEngine | None = None` read by `get_engine()` on every request, written in `lifespan()`.
**Problem:** During shutdown (`engine = None`), in-flight requests could see `None` after the check passes but before they use the engine, causing `AttributeError` instead of clean `RuntimeError`. TOCTOU race.
**Fix plan:** Accept as benign (process is exiting) and add a comment documenting the known race. Alternatively, use an `asyncio.Event` for shutdown signaling.

### R3-61 | HIGH | `tests/test_phase5.py:96-106` — Circuit breaker concurrent probe completely untested
**Phase:** 5
**Problem:** `CircuitBreakerState` has `_probe_lock` + `_probing` coordination for half-open state, but no test sends concurrent requests. The most error-prone code path is completely untested.
**Fix plan:** Add test using `asyncio.gather` to send multiple concurrent requests when circuit breaker is in half-open state. Verify only one probe gets through while others fall back to local.

### R3-63 | HIGH | `tests/test_action_classifier.py:81-86` — Quote-stripping behavior untested
**Phase:** 5
**Problem:** The classifier strips quoted strings before splitting chained commands (`re.sub` on line 102). No test verifies this. If the regex had a bug, safe quoted commands like `echo "rm -rf /"` would be false-positived as `DeleteFile`.
**Fix plan:** Add two tests: (1) `echo "rm -rf /" && ls` should classify as `ExecuteCommand` (not `DeleteFile`), (2) unquoted `rm -rf /tmp/old && ls` should classify as `DeleteFile`.

### R3-65 | HIGH | `tests/test_coverage.py:73-81` — Always-true assertion, misleading test name
**Phase:** 5
**Code:** `assert isinstance(decision.block, bool)` — always true for any `Decision`.
**Problem:** Test named `test_message_normal_allowed` but the assertion never checks if the message was actually allowed. User `"default"` has `confirm_before_send=True`, so this is always blocked. Test name says "allowed" but outcome is "blocked".
**Fix plan:** Rename to `test_message_default_user_blocked_by_preference` and assert `decision.block is True`. Or create a proper "allowed" test with a user that has `confirm_before_send=False`.

### R3-68 | HIGH | Ontology: `roles/researcher.ttl:9` — References non-existent `sc:GitForcePush`
**Phase:** 6
**Code:** `sp:deniesAction sc:WriteFile, sc:EditFile, sc:DeleteFile, sc:GitPush, sc:GitForcePush, sc:ShellAction, sc:SendMessage ;`
**Problem:** `sc:GitForcePush` doesn't exist in `safeclaw-agent.ttl` — the class is `sc:ForcePush`. If roles are ever loaded from ontology files, researcher would NOT deny force pushes.
**Fix plan:** Change `sc:GitForcePush` to `sc:ForcePush` in `researcher.ttl`.

### R3-74 | HIGH | Ontology: Missing SHACL shape for `sc:FileAction`
**Phase:** 6
**Problem:** `safeclaw-agent.ttl` defines `sc:filePath` with `rdfs:domain sc:FileAction`, but no SHACL shape validates it. A `FileAction` with zero or multiple `filePath` values passes SHACL. File operations with malformed paths (missing path, multiple paths) are not caught.
**Fix plan:** Create `safeclaw/ontologies/shapes/file-shapes.ttl` targeting `sc:FileAction` with `sh:property [sh:path sc:filePath; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:string]`.

---

## MEDIUM (25 findings)

### R3-03 | MEDIUM | `roles.py:112-122` — PurePosixPath.match() doesn't match deny patterns correctly
**Phase:** 2
**Problem:** `PurePosixPath.match()` only matches from the right (tail), not anchored from root. Deny patterns with leading `/` don't work as expected.
**Validation note:** PARTIALLY CORRECT — `**` glob in `PurePosixPath.match()` works correctly in Python 3.12+, but project targets Python 3.11+ where it doesn't. Real bug on Python 3.11.
**Fix plan:** Use `fnmatch.fnmatch()` for glob patterns, combined with `PurePath.is_relative_to()` for prefix checks. Or strip leading `/` from patterns before matching.

### R3-04 | MEDIUM | `roles.py:162-172` — Resource allow intersection uses string equality
**Phase:** 2
**Code:** `p for p in resource_allow if p in org_res_allow`
**Problem:** Uses `in` (exact string match), not glob matching. If role has `allow: ["src/**"]` and org has `allow: ["src/frontend/**"]`, intersection is empty, so the fallback `or org_res_allow` replaces role patterns entirely. "Most restrictive wins" guarantee is broken.
**Fix plan:** Implement glob subset checking, or union both deny lists and document that allow patterns must use identical strings for intersection. Or simplify to: always use the narrower set.

### R3-05 | MEDIUM | `knowledge_store.py:45-49` — Non-atomic file write can corrupt data
**Phase:** 1
**Code:** `open(self._store_file(), "w")` truncates on open. If process crashes mid-write, data is lost.
**Problem:** The old data is truncated immediately, but new data may only be partially written. Crash = data loss.
**Fix plan:** Write to `knowledge.jsonl.tmp`, then `os.replace("knowledge.jsonl.tmp", "knowledge.jsonl")` for atomic swap.

### R3-06 | MEDIUM | `message_gate.py:92-94` — `check()` inserts sessions without MAX_SESSIONS eviction
**Phase:** 2
**Code:** `self._session_message_counts[session_id] = counts` in `check()` method.
**Problem:** Eviction logic only runs in `record_message()`. If `check()` is called for many unique session IDs that never send messages, the OrderedDict grows unbounded.
**Fix plan:** Add eviction check after inserting in `check()`, or only insert into the dict inside `record_message()`.

### R3-07 | MEDIUM | `action_classifier.py:102` — Quote stripping misses backticks and subshells
**Phase:** 2
**Code:** `re.sub(r'''(["'])(?:(?!\1).)*\1''', '', command)`
**Problem:** Doesn't handle backtick commands (`` `rm -rf /` ``), `$()` subshells (`$(rm -rf /)`), or escaped quotes.
**Validation note:** PARTIALLY CORRECT — backtick/`$()` non-stripping is actually *correct* security behavior. Subshell commands SHOULD be detected as dangerous. The real fix is only for escaped quotes.
**Fix plan:** Improve regex to handle escaped quotes: `(["'])(?:\\.|(?!\1).)*\1`. Do NOT strip backticks or `$()`.

### R3-08 | MEDIUM | `context_builder.py:82-88` — SPARQL CONTAINS() allows cross-user preference leakage
**Phase:** 2
**Code:** `FILTER(CONTAINS(STR(?user), "{safe_user_id}"))`
**Problem:** `CONTAINS()` does substring matching. User ID `"admin"` would match `"admin-assistant"`, returning preferences for both users. Authorization boundary violation. Same issue exists in `preference_checker.py:45`.
**Fix plan:** Replace `CONTAINS()` with exact match: `FILTER(STR(?user) = "su:{safe_user_id}")` in both files.

### R3-09 | MEDIUM | `full_engine.py:347-390` — Blocked message attempts not counted for abuse detection
**Phase:** 1
**Problem:** Only allowed messages are recorded via `record_message()`. Blocked attempts (never-contact list, sensitive data, rate limit) don't increment any counter. No way to detect flood of blocked attempts indicating a compromised agent.
**Fix plan:** Add a separate `record_blocked_attempt()` counter, or log blocked attempts to audit with a flag for abuse detection.

### R3-30 | MEDIUM | `main.py:48` — Double SafeClawConfig instantiation
**Phase:** 3
**Code:** `APIKeyAuthMiddleware, require_auth=getattr(SafeClawConfig(), 'require_auth', False)`
**Problem:** Second `SafeClawConfig()` created at module level (outside `lifespan()`). If config is ever updated in-process, middleware uses stale value. Works by coincidence since both read the same env/file.
**Fix plan:** Make `SafeClawConfig` a singleton/cached instance, or pass `require_auth` from the lifespan-created config.

### R3-32 | MEDIUM | `main.py:48` — Auth middleware can never actually enforce
**Phase:** 3
**Code:** Middleware gets `require_auth` but no `api_key_manager`. Dispatch logic: `if not self.require_auth or self.api_key_manager is None: return await call_next(request)`.
**Problem:** Even with `require_auth=True`, `api_key_manager is None` makes it pass through. Auth is always a no-op.
**Fix plan:** When `require_auth=True`, create and pass an `ApiKeyManager` instance. Or raise an error at startup if `require_auth=True` but no key manager configured.

### R3-34 | MEDIUM | `routes.py:265-283` — Monotonic-to-wall-clock conversion is racy
**Phase:** 3
**Code:** `wall_time = time.time() + (g.expires_at - time.monotonic())`
**Problem:** `time.time()` can jump (NTP sync, suspend/resume). Race between reading `time.time()` and `time.monotonic()`. Result can be off by seconds.
**Fix plan:** Store wall-clock expiry at grant creation time in `TempPermissionManager.grant()`. Keep monotonic for actual expiry checking.

### R3-37 | MEDIUM | `models.py:10` — `params: dict` has no depth/size limit
**Phase:** 3
**Problem:** Caller could send `params: {"key": <deeply nested object>}` with arbitrary depth, causing excessive memory/CPU during serialization.
**Fix plan:** Add a Pydantic validator with max-depth or max-size check on `params`. Or constrain to `dict[str, str | int | float | bool | None]`.

### R3-38 | MEDIUM | `audit/logger.py:50-62` — `get_session_records` iterates ALL date directories
**Phase:** 3
**Problem:** After months, could scan hundreds of directories with no date range filter or pagination. Slow API responses.
**Fix plan:** Add optional `since`/`until` date parameters to bound the search.

### R3-39 | MEDIUM | `audit/logger.py:65-83` — `get_recent_records` early return gives wrong results
**Phase:** 3
**Problem:** Early return happens inside inner loop (per-file). Returns once `limit` records found from a single file, but these may not be the most recent globally — another session file in the same day could have newer records.
**Fix plan:** Collect all records from the most recent day directory first, sort globally, then apply limit.

### R3-41 | MEDIUM | `cli/policy_cmd.py:77` — Policy name used in Turtle IRI without escaping
**Phase:** 3
**Code:** `lines = [f"\nsp:{name} a {owl_type}"]` uses original `name`, not `safe_name`.
**Problem:** If `name` contains characters invalid in Turtle local names (spaces, `#`, `/`), the generated Turtle is syntactically invalid. `_escape_turtle` only handles string literal escaping.
**Fix plan:** Validate `name` matches `^[a-zA-Z_][a-zA-Z0-9_-]*$` and reject invalid names.

### R3-44 | MEDIUM | `graph_builder.py:11-21` — Cache invalidation never called
**Phase:** 1
**Code:** `invalidate_cache()` exists but is never called anywhere.
**Problem:** Currently safe because `GraphBuilder` is instantiated per-request in routes.py. But fragile — if ever cached globally, it would serve stale data.
**Fix plan:** Remove the caching mechanism (it's per-request anyway), or integrate invalidation into the reload path.

### R3-45 | MEDIUM | `graph_builder.py:19` — `max_depth` parameter is unused
**Phase:** 1
**Code:** `def build_graph(self, max_depth: int = 10) -> dict:` — `max_depth` never used in body.
**Problem:** Misleads callers. No depth limiting for large ontologies.
**Fix plan:** Either implement depth-limited traversal or remove the parameter.

### R3-46 | MEDIUM | TypeScript `index.ts:144` — Missing fail-closed check for `message_sending`
**Phase:** 4
**Problem:** Unlike `before_tool_call`, the `message_sending` handler does NOT check `r === null && config.failMode === 'closed'`. Messages go through even when service is unavailable in fail-closed mode.
**Fix plan:** Add: `if (r === null && config.failMode === 'closed' && config.enforcement === 'enforce') { return { cancel: true }; }`

### R3-49 | MEDIUM | `full_engine.py:96` — `hasattr(config, 'raw')` is unnecessary dead code
**Phase:** 1
**Code:** `raw = config.raw if hasattr(config, 'raw') else None`
**Problem:** `raw` is always defined as a property on `SafeClawConfig`. `hasattr` always returns True. Misleading defensive check.
**Fix plan:** Simplify to `raw = config.raw`. Add try/except for `json.JSONDecodeError` and log a warning if config file is malformed.

### R3-60 | MEDIUM | `tests/test_shacl_validation.py:46-51` — Missing companion test for full engine bypass
**Phase:** 5
**Problem:** Tests that empty SHACL shapes pass validation, but no test verifies the full engine still blocks `rm -rf /` without shapes (via policy checker). Creates false sense of safety.
**Fix plan:** Add companion test in `test_engine.py` that constructs engine with no SHACL shapes and verifies `rm -rf /` is still blocked by policy checker.

### R3-62 | MEDIUM | `tests/test_phase5.py:284-303` — Circuit breaker test doesn't verify fail-closed behavior
**Phase:** 5
**Problem:** Asserts circuit opens after 3 failures but doesn't verify that subsequent calls actually fail-closed (with `local_engine=None`). Missing the behavioral consequence test.
**Fix plan:** Add assertion after the loop: `decision = await engine.evaluate_tool_call(event)` then `assert decision.block is True`.

### R3-64 | MEDIUM | `tests/test_action_classifier.py:89-111` — Missing `commandText` assertion in RDF graph test
**Phase:** 5
**Problem:** Verifies `as_rdf_graph()` produces correct `rdf:type` triple but never asserts `commandText` is present. If `commandText` was ever dropped, this test would pass but SHACL validation in production would fail.
**Fix plan:** Add: `cmd_triples = list(graph.triples((action_node, SC.commandText, None)))` and `assert len(cmd_triples) == 1`.

### R3-66 | MEDIUM | `tests/test_multi_agent_governance.py:472-490` — Conditional assertion hides test logic
**Phase:** 5
**Code:** `if decision.block: assert "role" not in decision.reason.lower()`
**Problem:** If `block=False`, assertion never runs. Test doesn't control user preferences so behavior depends on engine state. Should explicitly set user with known preferences.
**Fix plan:** Use a specific user with known preferences, or mock preference checker to isolate role bypass behavior.

### R3-67 | MEDIUM | `tests/test_phase3.py:120-129` — Brittle internal coupling in rate limit test
**Phase:** 5
**Code:** `gate._message_rate_limit = 3` — sets private attribute.
**Problem:** If implementation renames the attribute, test silently stops working. No boundary case test (what happens at exactly the limit?).
**Fix plan:** Expose rate limit as constructor parameter. Add boundary test: 2 messages → not blocked, 3rd message → blocked.

### R3-69 | MEDIUM | Ontology: `roles/developer.ttl:10` — Mismatch with Python BUILTIN_ROLES
**Phase:** 6
**Code:** TTL denies `{ForcePush, DeleteFile, SystemConfigChange}`. Python denies `{ForcePush, DeleteFile, GitResetHard}`.
**Problem:** Ontology has `SystemConfigChange` (not in Python), Python has `GitResetHard` (not in ontology). If roles loaded from ontology, behavior would differ.
**Fix plan:** Synchronize TTL to match Python: deny `sc:ForcePush, sc:DeleteFile, sc:GitResetHard`.

### R3-71 | MEDIUM | `tests/test_phase2.py:103-132` — Temporal checker violation path completely untested
**Phase:** 5
**Problem:** Both temporal tests only test "no constraints, passes". Zero tests for constraints that actually violate. If the violation detection code has a bug, tests still pass.
**Fix plan:** Add test that injects a temporal constraint into KG (e.g., "no pushes before 6am") and verifies actions during restricted times are flagged.

### R3-72 | MEDIUM | `tests/test_phase4.py:149-159` — Fragile floating-point assertion
**Phase:** 5
**Code:** `assert stats["block_rate"] == 66.7`
**Problem:** Floating-point equality check. `2/3 * 100 = 66.666...` — depends on exact rounding implementation.
**Fix plan:** Use `pytest.approx(66.7, abs=0.1)`.

---

## LOW (12 findings)

### R3-10 | LOW | `full_engine.py:96-102` — Malformed config.json crashes init with unhandled exception
**Phase:** 1
**Problem:** `config.raw` reads JSON from disk. If malformed, `json.load()` raises unhandled `JSONDecodeError` that crashes init. `hasattr` is dead code (always True since `raw` is a property).
**Validation note:** PARTIALLY CORRECT — crash is not silent (raises exception), but the exception is unhandled.
**Fix plan:** Wrap in try/except, log warning on `JSONDecodeError`, fall back to `{}`.

### R3-11 | LOW | `session_tracker.py:40-44` — Missing `move_to_end` for active sessions
**Phase:** 1
**Problem:** When an existing session is accessed, it's NOT moved to end of OrderedDict. Active sessions created early can be evicted by LRU even though still in use.
**Fix plan:** Add `else: self._sessions.move_to_end(session_id)`.

### R3-12 | LOW | `temp_permissions.py` — No bound on `_grants` dict size
**Phase:** 1
**Problem:** Unlike other components with `MAX_*` bounds, `_grants` is unbounded. Expired grants only cleaned up on access. Task-only grants (no time expiry) persist forever.
**Fix plan:** Add `MAX_GRANTS` bound and eviction. Add maximum grant duration.

### R3-35 | LOW | `routes.py:293-297` — `/tasks/{task_id}/complete` lacks admin auth
**Phase:** 3
**Problem:** Any caller can revoke any agent's temporary permissions by completing tasks. Privilege escalation vector.
**Fix plan:** Add `dependencies=[Depends(require_admin)]`.

### R3-36 | LOW | `routes.py:255-262` — `/agents` endpoint lacks admin auth
**Phase:** 3
**Problem:** Exposes all registered agents (IDs, roles, parents, kill status) without authorization. Leaks internal topology.
**Fix plan:** Add `dependencies=[Depends(require_admin)]`.

### R3-40 | LOW | `audit/logger.py:86-100` — `get_blocked_records` has O(n^2) behavior
**Phase:** 3
**Problem:** Each iteration re-reads from scratch (no cursor). If blocked records are sparse, each call re-reads all previously scanned records.
**Fix plan:** Add cursor/continuation-token pattern, or filter at file-reading level.

### R3-42 | ~~LOW~~ FALSE POSITIVE | `cli/policy_cmd.py:119-126` — Policy removal regex
**Validation:** Regex uses `re.escape(name)` and correctly handles continuation lines via `(?:\n[ \t]+[^\n]*)*\.` pattern. Dots within property values appear on indented continuation lines and are matched correctly. **Not a bug.**

### R3-43 | LOW | `cli/pref_cmd.py:78-82` — Preference regex overwrites all matches
**Phase:** 3
**Problem:** `pattern.sub()` replaces ALL occurrences. If multiple user blocks exist in same file, all get overwritten.
**Fix plan:** Use `re.subn()` and warn if count > 1.

### R3-47 | LOW | TypeScript `index.ts:33` — Unsafe cast of enforcement mode
**Phase:** 4
**Code:** `as SafeClawPluginConfig['enforcement']` — doesn't validate input.
**Problem:** Invalid env value passes type check silently. Later validation (line 60-63) catches it, but there's a window with invalid config.
**Fix plan:** Minor. Move validation earlier or use a parsing function.

### R3-51 | LOW | `Dockerfile:12-13` — pip install before creating non-root user
**Phase:** 3
**Problem:** `pip install` runs as root. Post-install scripts in dependencies could modify system files. Common practice but not ideal for security product.
**Fix plan:** Create user first with `--user` install, or use multi-stage build.

### R3-70 | LOW | Ontology: `roles/admin.ttl:8` — `sc:AllActions` is a dangling reference
**Phase:** 6
**Code:** `sp:allowsAction sc:AllActions ;`
**Problem:** `sc:AllActions` not defined anywhere. Python uses empty `allowed_action_classes` set instead. If ontology is reasoned over, `sc:AllActions` has no semantic meaning.
**Fix plan:** Define `sc:AllActions` in `safeclaw-agent.ttl`, or remove from TTL and use a comment.

### R3-73 | LOW | `tests/test_phase4.py:151` — Tests use hardcoded `/tmp/nonexistent` path
**Phase:** 5
**Problem:** Multiple tests create `AuditLogger(Path("/tmp/nonexistent"))`. If path exists on CI, log writes could leak. Should use `tmp_path` fixture for isolation.
**Fix plan:** Replace `Path("/tmp/nonexistent")` with `tmp_path` fixture in 4 affected tests.
