# Changelog

All notable changes to the SafeClaw project, organized by implementation phase.

## Phase 4 -- Medium/Low Bug Fixes and Validation

Resolved 128 medium and low severity bugs with 102 regression tests.

### Security

- Add CSRF token verification to all landing site dashboard POST routes (#39)
- Allow TTL role definitions to override Python builtins without injection risk (#46)
- Add agent token verification to heartbeat endpoint to prevent heartbeat spoofing (#56)

### Bug Fixes

- Remove duplicate `id` from NewKeyModal to fix HTMX target mismatch (#102)
- Correct stale documentation references in landing site (#152, #162)
- Update CLAUDE.md pipeline description to match actual 11-step implementation (#171)

### Tests

- Add 63 regression tests for policy, classification, and preference issues
- Add 39 regression tests for 27 previously-fixed issues (#43, #115, #161, #49-#52, #57, #58, #60, #62, #63, #78, #81, #82, #25, #53, #61, #112, #119, #148, #149, #24, #92)

## Phase 3 -- NemoClaw Sandbox Integration

Added NemoClaw YAML policy support for sandbox governance.

### New Features

- **NemoClaw YAML policy loader** (`safeclaw/nemoclaw/policy_loader.py`): converts NemoClaw YAML policies to RDF triples in the knowledge graph (#200)
- **NemoClaw ontology** (`nemoclaw-policy.ttl`): defines `NemoNetworkRule` and `NemoFilesystemRule` classes (#199)
- **Network allowlist enforcement**: PolicyChecker validates outbound connections against NemoClaw host/port/protocol rules (#201)
- **Filesystem prefix enforcement**: PolicyChecker validates file access against path and access mode rules (#201)
- **NemoClaw config fields**: `nemoclaw_enabled` and `nemoclaw_policy_dir` with auto-detection fallback chain (#198)
- **NemoClaw policy preset YAML**: example policy file for common sandbox configurations (#204)
- **NemoClaw status in CLI and TUI**: displays NemoClaw status and loaded policy count (#205)
- **Sandbox-aware plugin config detection**: plugin detects NemoClaw environment automatically (#203)
- **NemoClaw wired into engine**: policies loaded on init and re-ingested on hot-reload (#202)

### Tests

- End-to-end NemoClaw integration tests (#206)

### Bug Fixes

- Address path traversal, fail-closed network default, and unused import from Phase 3 review

## Phase 2 -- OpenClaw Compatibility and New Hooks

Migrated to OpenClaw Plugin SDK types and added new governance endpoints.

### New Features

- **Subagent spawn evaluation** (`POST /evaluate/subagent-spawn`): governance gate for subagent creation with delegation bypass detection (#188)
- **Subagent ended recording** (`POST /record/subagent-ended`): audit trail for subagent completion (#188)
- **Session lifecycle endpoints** (`POST /session/start`, `POST /session/end`): initialize and clean up session-scoped governance state (#189)
- **Inbound message evaluation** (`POST /evaluate/inbound-message`): prompt injection risk assessment with channel trust levels and pattern detection (#190)
- **Channel trust ontology** (`safeclaw-channels.ttl`): defines trust levels for DM, public, webhook, and API channels (#190)
- **Sandbox policy validation** (`POST /evaluate/sandbox-policy`): validates sandbox configuration against required sections and mount point rules (#193)
- **Sandbox ontology and SHACL shapes** (`safeclaw-sandbox.ttl`, `shapes/sandbox-shapes.ttl`): sandbox policy classes and validation shapes (#193)
- **OpenClaw Plugin SDK migration**: plugin now uses OpenClaw event hooks and type definitions (#187)
- **OpenClaw config system adoption**: plugin reads from OpenClaw config with file config as fallback (#196)
- **Plugin subagent and session hooks**: TypeScript plugin registers hooks for `before_subagent_spawn`, `subagent_ended`, `session_start`, `inbound_message` (#188, #189, #190, #197)
- **dryRun support**: tool-call evaluation supports dry-run mode that skips audit logging (#208)
- **Plugin handshake endpoint** (`POST /handshake`): validates API key and logs connection events

### Bug Fixes

- Fix hook event/context field mappings for OpenClaw compatibility (#195)
- Remove `process.exit()` signal handlers, register heartbeat as OpenClaw service (#194)
- Upgrade python-fasthtml to fix Starlette `on_startup` incompatibility (#208)
- Update `openclaw.plugin.json` with correct version, complete configSchema, and metadata (#192)

## Phase 1 -- Critical and High Severity Bug Fixes

Fixed 16 critical/high bugs and resolved a production crash-loop.

### Security

- **bcrypt for API keys** (#139): replace SHA-256 with bcrypt for API key hashing (SHA-256 legacy fallback retained for migration)
- **bcrypt for admin passwords** (#132): hash admin passwords with bcrypt instead of storing plaintext
- **Input sanitization at engine level** (#136): sanitize tool call inputs (tool name and params) at the engine level, not just API routes
- **Recursion depth limit for params** (#135): add depth and size limits to `_sanitize_params` to prevent stack overflow via deeply nested payloads

### New Features

- **SQLite-backed StateStore** (#138): persist agent kills, rate-limit counters, and temporary permission grants to `governance_state.db` so governance state survives service restarts
- **Computed `decision` field** (#128): `DecisionResponse` includes a disambiguated `decision` string (`"allowed"`, `"needs_confirmation"`, or `"blocked"`)

### Bug Fixes

- Resolve production crash-loop caused by landing site home directory and fasthtml installation issues (#207)
- Remove dead `CachedEngine` and `HybridEngine` -- always use `FullEngine` (#137)
- Harden delegation detection with tool aliases, cross-session checks, and command normalization (#140)
- Harden `_glob_match` for Python 3.11+ edge cases and mitigate ReDoS with segment limits (#142)
- Prevent HeartbeatMonitor config drift from firing continuously (#141)
- Use `weakref.finalize` to clean stale `graph_builder` cache entries (#143)
- Add ref counting to session locks to prevent eviction of in-use locks (#131)
- Write config files with `0o600` permissions in dashboard settings (#133)

### Tests

- Regression test for audit hash chain persistence (#134)
- Regression test for CSRF token stability within sessions (#129)
- Regression test confirming kill switch never auto-executes (#130)

## Pre-Phase (Code Review Rounds 1-4)

Initial code review and bug fix rounds before the phased implementation began.

### Summary

- Filed 127 issues across 3 review passes (#22-#127)
- Fixed 164 validated code review findings across 4 rounds
- Established the 11-step constraint pipeline (expanded from original 9-step)
- Added multi-agent governance: agent registry, role manager, delegation detection, temporary permissions
- Added LLM layer: security reviewer, classification observer, decision explainer, policy compiler
- Added landing site with FastHTML + MonsterUI
- Established test suite (now 500+ tests across 59 test files)
