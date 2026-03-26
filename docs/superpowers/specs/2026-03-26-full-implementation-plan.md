# SafeClaw Full Implementation Plan

**Date:** 2026-03-26
**Status:** Approved

## Overview

Comprehensive plan for implementing all 185 open tickets across two major initiatives (OpenClaw compatibility, NemoClaw support) plus existing bug backlog and final documentation pass. Uses a safest-first ordering: critical bugs, then OpenClaw compat, then NemoClaw, then medium bugs, then documentation.

## Ticket Inventory

| Theme | Tickets | Count |
|-------|---------|-------|
| Critical/High bugs | #128-#143 | 16 |
| OpenClaw compatibility | #187-#197 | 11 |
| NemoClaw support | #198-#206 | 9 |
| Medium/Low bugs | #22-#127, #144-#171 | ~149 |
| Documentation (new) | Phase 5 | TBD |

## Conflict Analysis

### Direct file conflicts requiring coordination

| Tickets | File | Resolution |
|---------|------|------------|
| #193 vs #199 | New ontology files | Different namespaces (`sc:` vs `sp:`), different pipeline steps (SHACL validation vs policy check). Add `rdfs:seeAlso` cross-references. No code conflict. |
| #196 vs #203 | `tui/config.ts` | #196 makes `api.pluginConfig` primary, #203 adds sandbox detection to file fallback. Compatible. **Do #196 first.** |
| #197 vs #205 | `cli.tsx` | Both add CLI commands. **Do #197 first**, then #205 adds NemoClaw status to both standalone and OpenClaw-registered commands. |
| #187 + #195 + #196 | `index.ts` | All three rewrite parts of the plugin. **Strict sequence: #195 -> #187 -> #196**, or combine #194 + #195 into one PR. |
| #194 + #196 | `register()` in `index.ts` | #194 removes signal handlers + registers service, #196 uses `api.logger` + `api.pluginConfig`. **Do #194 first or same PR.** |

### Tickets that supersede existing bugs

| New ticket | Supersedes | Why |
|------------|-----------|-----|
| #194 | #55 (process.on exit) | #194 removes signal handlers entirely |
| #195 | #89 (r.reason undefined), #88 (audit-only branch), #164 (cancelReason) | #195 rewrites all hook handlers with correct field mappings |
| #192 | #95 (version inconsistency) | #192 syncs manifest version |
| #196 | #168 (config never refreshed) | #196 replaces file config with `api.pluginConfig` |

When a superseding ticket is completed, close the superseded ticket with a reference.

### Cross-cutting dependencies with existing bugs

| Bug | Affects | Coordination |
|-----|---------|-------------|
| #144 (PATH_PARAM_KEYS duplication) | #201 (NemoClaw filesystem checker) | If #144 done first, #201 imports from shared module. Either order works — just an import path change. |
| #126 (path param coverage) | #201 | NemoClaw filesystem checker should use the same expanded key list. |
| #137 (dead engine modes) | #198, #202 | Both touch `config.py` / `full_engine.py` but different sections. No conflict, any order. |
| #155 (default serviceUrl) | #203 | Sandbox detection checks against localhost default. Compatible regardless of order. |

## Phase 1: Critical & High Bugs

**Goal:** Make the running service secure and correct before adding features.

### Batch 1A — Security-critical (parallelizable, no dependencies)

| # | Title | File(s) |
|---|-------|---------|
| #132 | Admin passwords stored plaintext | `api/routes.py`, `db.py` |
| #133 | Config file world-readable (0644) | `config.py`, CLI |
| #130 | LLM kill_switch auto-executes without confirmation | `llm/security_reviewer.py` |
| #131 | Session lock race condition | `engine/session.py` |
| #128 | "Requires confirmation" indistinguishable from "blocked" | `engine/full_engine.py`, `api/models.py` |
| #129 | CSRF token regenerated on every POST | `landing/app.py` |

### Batch 1B — High bugs (parallelizable after 1A)

| # | Title | File(s) |
|---|-------|---------|
| #139 | SHA-256 hashing -> bcrypt/argon2 | `auth/`, `db.py` |
| #136 | evaluate_tool_call doesn't sanitize input | `engine/full_engine.py` |
| #135 | _sanitize_params doesn't recurse nested | `engine/full_engine.py` |
| #140 | Delegation detection trivially bypassed | `agents/delegation_detector.py` |
| #138 | Governance state in-memory only, lost on restart | `engine/`, `agents/` |
| #134 | Audit hash chain resets on restart | `audit/logger.py` |
| #143 | graph_builder cache uses id() | `engine/graph_builder.py` |
| #142 | _glob_match breaks on Python 3.11 | `constraints/` |
| #141 | HeartbeatMonitor fires continuously | `agents/heartbeat.py` |
| #137 | Dead engine modes (hybrid/cached) | `config.py`, `engine/` |

## Phase 2: OpenClaw Compatibility

**Goal:** Plugin stops being harmful and starts being functional in current OpenClaw.

### Batch 2A — Critical plugin fixes (single PR recommended)

| # | Title | File(s) |
|---|-------|---------|
| #194 | Remove process.exit() + register as service | `index.ts` |
| #195 | Fix hook field mappings + switch to before_prompt_build | `index.ts`, service `api/models.py` |

**Closes:** #55, #89, #88, #164 (all superseded by the rewrite)

### Batch 2B — Plugin modernization (after 2A)

| # | Title | File(s) |
|---|-------|---------|
| #187 | Import SDK types, remove inline interfaces | `index.ts`, `package.json` |
| #196 | definePluginEntry() + api.pluginConfig + api.logger | `index.ts`, `tui/config.ts` |

**Closes:** #168 (superseded by api.pluginConfig)

### Batch 2C — Manifest + metadata (after 2B)

| # | Title | File(s) |
|---|-------|---------|
| #192 | Update openclaw.plugin.json (version, configSchema, metadata) | `openclaw.plugin.json` |

**Closes:** #95 (superseded by version sync)

### Batch 2D — New hooks (parallelizable, after 2B)

| # | Title | File(s) |
|---|-------|---------|
| #188 | Subagent governance hooks | `index.ts`, service `api/routes.py`, `engine/full_engine.py` |
| #189 | Session lifecycle hooks | `index.ts`, service `api/routes.py`, `engine/full_engine.py` |
| #190 | Inbound message governance | `index.ts`, service `api/routes.py`, new `safeclaw-channels.ttl` |

### Batch 2E — New capabilities (parallelizable with 2D)

| # | Title | File(s) |
|---|-------|---------|
| #193 | Sandbox SHACL shapes | Service: new `safeclaw-sandbox.ttl`, `shapes/sandbox-shapes.ttl`, `api/routes.py` |
| #197 | CLI commands + agent tools + dry-run | `index.ts`, `cli.tsx`, service `api/routes.py` |

### Batch 2F — Ship (after 2A-2E)

| # | Title |
|---|-------|
| #191 | Publish to ClawHub marketplace |

## Phase 3: NemoClaw Support

**Goal:** SafeClaw works inside NemoClaw sandboxes and reasons about NemoClaw policies.

### Batch 3A — Foundation (sequential)

| # | Title | File(s) |
|---|-------|---------|
| #198 | Config fields + PyYAML dependency | `pyproject.toml`, `config.py` |
| #199 | NemoClaw ontology | New `ontologies/nemoclaw-policy.ttl` |

### Batch 3B — Core (sequential, depends on 3A)

| # | Title | File(s) |
|---|-------|---------|
| #200 | YAML policy loader | New `nemoclaw/policy_loader.py` |
| #201 | PolicyChecker extensions | `constraints/policy_checker.py` |
| #202 | Wire loader into FullEngine | `engine/full_engine.py` |

### Batch 3C — Plugin side (parallelizable with 3B, after Phase 2 batch 2B)

| # | Title | File(s) |
|---|-------|---------|
| #203 | Sandbox-aware plugin config | `tui/config.ts` (after #196) |
| #204 | NemoClaw policy preset YAML | New `policies/safeclaw.yaml`, `package.json` |

### Batch 3D — UI + tests (depends on 3B + 3C)

| # | Title | File(s) |
|---|-------|---------|
| #205 | NemoClaw status in CLI/TUI | `cli.tsx`, `tui/Status.tsx` (after #197) |
| #206 | End-to-end integration tests | New `tests/test_nemoclaw_integration.py` |

## Phase 4: Medium & Low Bugs

**Goal:** Clean up remaining code review issues from passes 1-3.

### Batch 4A — Security bugs

| # | Tickets |
|---|---------|
| Auth/access | #22, #26, #32, #33, #34, #35, #37, #42 |
| CSRF/SSRF | #38, #39, #73, #103 |
| Injection | #23, #36, #64, #93 |
| Crypto/secrets | #31, #41, #71, #111 |

### Batch 4B — Engine correctness

| # | Tickets |
|---|---------|
| Policy/classification | #27, #30, #44, #46, #47, #48, #116, #122, #125, #150, #159, #165, #166 |
| Preferences | #29, #59, #80, #83, #107, #121, #126 |
| Audit | #43, #115, #161 |
| Agent management | #49, #50, #51, #52, #57, #58, #60, #62, #63, #78, #81, #82 |
| Session/rate | #53, #61, #112, #119, #148, #149 |
| Hot-reload | #24, #92 |

### Batch 4C — Plugin bugs

| # | Tickets |
|---|---------|
| Config | #54, #84, #91, #94, #156 |
| Misc | #85, #104, #155 |

### Batch 4D — Infrastructure

| # | Tickets |
|---|---------|
| Docker | #65, #66, #67, #68, #70, #153, #158 |
| CI/CD | #96, #154 |
| Install | #69, #100 |

### Batch 4E — Landing site (FastHTML dashboard)

| # | Tickets |
|---|---------|
| Security | #73, #86, #97, #106, #108, #109 |
| UI/UX | #76, #83, #87, #99, #102, #105, #110, #162 |
| Docs mismatch | #107, #152 |

### Batch 4F — Engine quality & observability

| # | Tickets |
|---|---------|
| Performance | #77, #113, #114, #118, #148 |
| Correctness | #40, #74, #79, #101, #117, #120, #123, #124, #127, #144, #160, #163 |
| Architecture | #145, #146, #147, #167, #169, #170, #171 |

## Phase 5: Documentation

**Goal:** All documentation reflects the current state after Phases 1-4.

### Batch 5A — SafeClaw service documentation

| Item | File(s) | What to update |
|------|---------|---------------|
| Main README | `README.md` | Project overview reflecting OpenClaw + NemoClaw support, updated architecture diagram, quick-start for both standalone and OpenClaw-integrated modes |
| API reference | `safeclaw-service/README.md` or `docs/api.md` | New endpoints added in Phases 2-3 (`/evaluate/subagent-spawn`, `/evaluate/inbound-message`, `/evaluate/sandbox-policy`, `/session/start`, `/session/end`, dry-run flag) |
| NemoClaw guide | `docs/nemoclaw.md` (new) | Setup guide for NemoClaw integration: host-side vs embedded deployment, config auto-detection, policy ingestion, Docker volume mounts |
| Ontology reference | `docs/ontologies.md` (new or update existing) | Document new ontology files: `nemoclaw-policy.ttl`, `safeclaw-channels.ttl`, `safeclaw-sandbox.ttl`, SHACL shapes |
| Configuration reference | `docs/configuration.md` (new or update) | All config fields including NemoClaw fields, env vars, auto-detection behavior |
| Pipeline documentation | Update CLAUDE.md or `docs/` | Update 9-step pipeline description to reflect NemoClaw extensions to step 5, new inbound message evaluation, sandbox policy validation |
| CLI help text | `safeclaw-service/safeclaw/cli/` | Ensure all CLI commands have accurate `--help` text matching current behavior |

### Batch 5B — Plugin documentation

| Item | File(s) | What to update |
|------|---------|---------------|
| Plugin README | `openclaw-safeclaw-plugin/README.md` | Rewrite for current state: OpenClaw SDK integration, all registered hooks (original 6 + new subagent/session/inbound), agent-facing tools, ClawHub install instructions, NemoClaw sandbox setup |
| SKILL.md | `openclaw-safeclaw-plugin/SKILL.md` | Update skill description for ClawHub listing |
| NemoClaw section | `openclaw-safeclaw-plugin/README.md` | NemoClaw sandbox setup: policy preset, auto-detection, `nemoclaw policy-add safeclaw` |
| Config reference | Plugin README or separate doc | All config fields: those from `openclaw.plugin.json` configSchema + env var overrides + sandbox auto-detection behavior |
| Migration guide | `docs/migration.md` (new) | For users upgrading from pre-SDK plugin: what changed, how to reconfigure if using file-based config |

### Batch 5C — Project-level documentation

| Item | File(s) | What to update |
|------|---------|---------------|
| CLAUDE.md | `CLAUDE.md` | Update architecture section: new endpoints, NemoClaw module, plugin SDK integration, new ontology files. Update build commands if any changed. |
| CHANGELOG | `CHANGELOG.md` (new) | Summary of all changes from Phases 1-4 organized by component |
| Contributing guide | `CONTRIBUTING.md` (new, optional) | How to add new ontology classes, SHACL shapes, policy checker methods, plugin hooks |

### Batch 5D — Inline documentation

| Item | Scope | What to update |
|------|-------|---------------|
| CLI --help | All CLI commands in both Python and TypeScript | Verify every command's help text matches actual behavior after all fixes |
| OpenAPI spec | FastAPI auto-generated | Verify all endpoint descriptions, request/response models are accurate |
| Ontology comments | All `.ttl` files | Ensure `rdfs:comment` on new classes accurately describes their purpose and relationships |

## Execution Summary

| Phase | Tickets | Focus | Estimated batches |
|-------|---------|-------|-------------------|
| 1 | 16 | Critical/High bugs | 2 batches |
| 2 | 11 (+4 closed) | OpenClaw compatibility | 6 batches |
| 3 | 9 | NemoClaw support | 4 batches |
| 4 | ~149 | Medium/Low bugs | 6 batches |
| 5 | — | Documentation | 4 batches |
| **Total** | **185 tickets + docs** | | **22 batches** |

## Dependency Graph (batch-level)

```
Phase 1:  1A ──> 1B
                  │
Phase 2:  2A ──> 2B ──> 2C
                  │       │
                  ├──> 2D ├──> 2F
                  │       │
                  └──> 2E ┘
                  │
Phase 3:  3A ──> 3B ──────> 3D
                  │
           3C ───────────> 3D
           (after 2B)  (after 3B+3C)

Phase 4:  4A through 4F (largely parallelizable, after Phase 1)

Phase 5:  5A through 5D (after Phases 1-4)
```
