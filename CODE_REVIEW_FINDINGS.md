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

## Previous Review (Round 1) Summary

Round 1 found 59 findings (6 CRITICAL, 11 HIGH, 25 MEDIUM, 17 LOW). All 58 confirmed findings were fixed. 1 was a false positive (F-36). Tests went from 207 to 216. See git history for full details:
- `a24f2b7` — Apply 58 validated code review fixes (42 files changed)
- `0f047b0` — Fix F-12 and F-16
- `6aa5059` — Fix remaining LOW priority findings
