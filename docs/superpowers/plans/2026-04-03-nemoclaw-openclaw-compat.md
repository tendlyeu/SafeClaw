# NemoClaw + OpenClaw Compatibility Update

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken NemoClaw integration against real NemoClaw YAML schema, fix OpenClaw plugin contract issues, and add requireApproval support.

**Architecture:** Four independent work groups: (1) NemoClaw loader/checker rewrite, (2) plugin subagent_spawning fix, (3) SDK type update, (4) requireApproval integration. Groups 2-3 are quick fixes. Group 1 is the largest. Group 4 builds on existing `confirmationRequired` infrastructure.

**Tech Stack:** Python 3.11+, RDFLib, PyYAML, TypeScript 5.4+, OpenClaw Plugin SDK v2026.4

**Issues:** #260, #261, #262, #265, #266, #267, #269, #270

---

## File Structure

### Group 1: NemoClaw (Python service)
- Modify: `safeclaw-service/safeclaw/nemoclaw/policy_loader.py` — rewrite for real NemoClaw YAML schema
- Modify: `safeclaw-service/safeclaw/config.py` — fix auto-detection path
- Modify: `safeclaw-service/safeclaw/constraints/policy_checker.py` — protocol mapping + binary restriction checks
- Modify: `safeclaw-service/safeclaw/ontologies/nemoclaw-policy.ttl` — add enforcement/tls properties
- Modify: `safeclaw-service/tests/test_nemoclaw_loader.py` — rewrite tests for real schema
- Modify: `safeclaw-service/tests/test_nemoclaw_policy_checker.py` — rewrite tests for real schema
- Modify: `safeclaw-service/tests/test_nemoclaw_integration.py` — rewrite tests for real schema

### Group 2: Plugin subagent fix (TypeScript)
- Modify: `openclaw-safeclaw-plugin/index.ts:350-375` — change throw to return

### Group 3: SDK type update (TypeScript)
- Modify: `openclaw-safeclaw-plugin/types/openclaw-sdk.d.ts` — add v2026.4 types

### Group 4: requireApproval (TypeScript + Python)
- Modify: `openclaw-safeclaw-plugin/index.ts:236-267` — map confirmationRequired to requireApproval
- Modify: `openclaw-safeclaw-plugin/types/openclaw-sdk.d.ts` — add requireApproval types (done in Group 3)

---

## Task 1: Rewrite NemoClaw Policy Loader (#260)

**Files:**
- Modify: `safeclaw-service/safeclaw/nemoclaw/policy_loader.py`
- Modify: `safeclaw-service/tests/test_nemoclaw_loader.py`

The loader must handle the real NemoClaw YAML schema:

**Network policies** — `data["network_policies"]` is a dict of named groups, each with `endpoints` (list) and `binaries` (list):
```yaml
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
        rules:
          - allow: { method: GET, path: "/**" }
          - allow: { method: POST, path: "/**" }
    binaries:
      - { path: /usr/local/bin/claude }
```

**Filesystem policy** — `data["filesystem_policy"]` has `read_only` and `read_write` path lists:
```yaml
filesystem_policy:
  include_workdir: true
  read_only:
    - /usr
    - /lib
  read_write:
    - /sandbox
    - /tmp
```

**Backward compatibility:** Keep the old `data["rules"]` / `data["filesystem"]` parsing as a legacy fallback so existing test YAMLs and custom configs still work during migration.

- [ ] **Step 1: Write failing tests for real NemoClaw network format**

Add to `test_nemoclaw_loader.py`:

```python
class TestRealNemoClawNetworkFormat:
    def test_network_policies_format(self, kg, policy_dir):
        """Real NemoClaw uses network_policies with named groups and endpoints."""
        _write_yaml(policy_dir, "sandbox.yaml", """
network_policies:
  claude_code:
    name: claude_code
    endpoints:
      - host: api.anthropic.com
        port: 443
        protocol: rest
        enforcement: enforce
        tls: terminate
    binaries:
      - path: /usr/local/bin/claude
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host ?port ?protocol WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:allowsHost ?host ;
                      sp:allowsPort ?port ;
                      sp:allowsProtocol ?protocol .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "api.anthropic.com"
        assert int(results[0]["port"]) == 443
        assert str(results[0]["protocol"]) == "rest"

    def test_multiple_endpoints_in_group(self, kg, policy_dir):
        _write_yaml(policy_dir, "sandbox.yaml", """
network_policies:
  apis:
    name: apis
    endpoints:
      - host: api.anthropic.com
        port: 443
      - host: api.openai.com
        port: 443
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{ ?rule a sp:NemoNetworkRule ; sp:allowsHost ?host . }}
        """)
        hosts = {str(r["host"]) for r in results}
        assert hosts == {"api.anthropic.com", "api.openai.com"}

    def test_multiple_named_groups(self, kg, policy_dir):
        _write_yaml(policy_dir, "sandbox.yaml", """
network_policies:
  claude:
    endpoints:
      - host: api.anthropic.com
        port: 443
  github:
    endpoints:
      - host: github.com
        port: 443
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{ ?rule a sp:NemoNetworkRule ; sp:allowsHost ?host . }}
        """)
        hosts = {str(r["host"]) for r in results}
        assert hosts == {"api.anthropic.com", "github.com"}

    def test_binaries_list_format(self, kg, policy_dir):
        _write_yaml(policy_dir, "sandbox.yaml", """
network_policies:
  git:
    endpoints:
      - host: github.com
        port: 443
    binaries:
      - path: /usr/bin/git
      - path: /usr/local/bin/git
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?binary WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:binaryRestriction ?binary .
            }}
        """)
        binaries = {str(r["binary"]) for r in results}
        assert binaries == {"/usr/bin/git", "/usr/local/bin/git"}

    def test_enforcement_and_tls_stored(self, kg, policy_dir):
        _write_yaml(policy_dir, "sandbox.yaml", """
network_policies:
  api:
    endpoints:
      - host: api.example.com
        port: 443
        enforcement: enforce
        tls: terminate
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?enforcement ?tls WHERE {{
                ?rule a sp:NemoNetworkRule ;
                      sp:enforcement ?enforcement ;
                      sp:tlsMode ?tls .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["enforcement"]) == "enforce"
        assert str(results[0]["tls"]) == "terminate"
```

- [ ] **Step 2: Write failing tests for real NemoClaw filesystem format**

```python
class TestRealNemoClawFilesystemFormat:
    def test_filesystem_policy_path_lists(self, kg, policy_dir):
        """Real NemoClaw uses filesystem_policy with read_only/read_write lists."""
        _write_yaml(policy_dir, "sandbox.yaml", """
filesystem_policy:
  read_only:
    - /usr
    - /lib
  read_write:
    - /sandbox
    - /tmp
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        rules = {str(r["path"]): str(r["mode"]) for r in results}
        assert rules["/usr"] == "read-only"
        assert rules["/lib"] == "read-only"
        assert rules["/sandbox"] == "read-write"
        assert rules["/tmp"] == "read-write"

    def test_include_workdir_ignored_gracefully(self, kg, policy_dir):
        """include_workdir is a NemoClaw runtime feature, loader should not crash."""
        _write_yaml(policy_dir, "sandbox.yaml", """
filesystem_policy:
  include_workdir: true
  read_write:
    - /sandbox
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path WHERE {{ ?rule a sp:NemoFilesystemRule ; sp:path ?path . }}
        """)
        assert len(results) == 1
        assert str(results[0]["path"]) == "/sandbox"
```

- [ ] **Step 3: Write failing test for legacy format backward compat**

```python
class TestLegacyFormatBackwardCompat:
    def test_old_rules_format_still_works(self, kg, policy_dir):
        """Old flat rules format should still work as fallback."""
        _write_yaml(policy_dir, "net.yaml", """
rules:
  - name: github
    host: "github.com"
    port: 443
    protocol: https
    allow: true
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?host WHERE {{ ?rule a sp:NemoNetworkRule ; sp:allowsHost ?host . }}
        """)
        assert len(results) == 1
        assert str(results[0]["host"]) == "github.com"

    def test_old_filesystem_format_still_works(self, kg, policy_dir):
        _write_yaml(policy_dir, "fs.yaml", """
filesystem:
  - path: "/sandbox"
    mode: "read-write"
""")
        loader = NemoClawPolicyLoader(policy_dir)
        loader.load(kg)

        results = kg.query(f"""
            PREFIX sp: <{SP}>
            SELECT ?path ?mode WHERE {{
                ?rule a sp:NemoFilesystemRule ;
                      sp:path ?path ;
                      sp:accessMode ?mode .
            }}
        """)
        assert len(results) == 1
        assert str(results[0]["path"]) == "/sandbox"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd safeclaw-service && python -m pytest tests/test_nemoclaw_loader.py -v`
Expected: New tests FAIL (old tests pass)

- [ ] **Step 5: Rewrite policy_loader.py**

Rewrite `_process_policy` to handle both new and legacy formats. Add `_process_network_policies` for the new `network_policies` format, `_process_filesystem_policy` for the new `filesystem_policy` format. Keep `_process_legacy_rules` and `_process_legacy_filesystem` for backward compatibility. Update `_process_network_rule` to accept `enforcement`, `tls` fields and `binaries` as a list of `{path: ...}` dicts.

- [ ] **Step 6: Update nemoclaw-policy.ttl ontology**

Add `sp:enforcement`, `sp:tlsMode`, `sp:policyGroup` properties.

- [ ] **Step 7: Run all tests**

Run: `cd safeclaw-service && python -m pytest tests/test_nemoclaw_loader.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add safeclaw-service/safeclaw/nemoclaw/policy_loader.py safeclaw-service/safeclaw/ontologies/nemoclaw-policy.ttl safeclaw-service/tests/test_nemoclaw_loader.py
git commit -m "fix: rewrite NemoClaw policy loader for real NemoClaw YAML schema (#260)"
```

---

## Task 2: Fix NemoClaw Auto-Detection Path (#261)

**Files:**
- Modify: `safeclaw-service/safeclaw/config.py:58-70`

- [ ] **Step 1: Fix get_nemoclaw_policy_dir()**

The `~/.nemoclaw/` directory contains JSON configs, not YAML policies. Remove the `~/.nemoclaw/*.yaml` check. Instead, check `~/.nemoclaw/sandboxes.json` to discover sandbox configs. Also support `NEMOCLAW_POLICY_PATH` env var pointing directly to a policy YAML file.

- [ ] **Step 2: Run existing tests**

Run: `cd safeclaw-service && python -m pytest tests/ -k nemoclaw -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

---

## Task 3: Fix Protocol Value Mismatch (#269)

**Files:**
- Modify: `safeclaw-service/safeclaw/constraints/policy_checker.py:290-310`
- Modify: `safeclaw-service/tests/test_nemoclaw_policy_checker.py`

- [ ] **Step 1: Write failing test**

```python
def test_rest_protocol_matches_https(self, kg, tmp_path):
    """NemoClaw protocol 'rest' should match URL scheme 'https'."""
    _load_network_policy(kg, tmp_path / "policies", """
network_policies:
  api:
    endpoints:
      - host: "api.example.com"
        port: 443
        protocol: rest
""")
    checker = PolicyChecker(kg, nemoclaw_enabled=True)
    action = _make_action("WebFetch", url="https://api.example.com/data")
    result = checker.check(action)
    assert result.violated is False
```

- [ ] **Step 2: Add protocol normalization map to PolicyChecker**

```python
_PROTOCOL_SCHEME_MAP: dict[str, set[str] | None] = {
    "rest": {"https", "http"},
    "grpc": {"https", "http", "grpc"},
    "websocket": {"wss", "ws"},
    "full": None,  # matches any scheme
    "https": {"https"},
    "http": {"http"},
    "wss": {"wss"},
    "ws": {"ws"},
}
```

Update `_check_nemo_network_rules` to use this map.

- [ ] **Step 3: Run tests, commit**

---

## Task 4: Add Binary Restriction Checking (#270)

**Files:**
- Modify: `safeclaw-service/safeclaw/constraints/policy_checker.py`
- Modify: `safeclaw-service/tests/test_nemoclaw_policy_checker.py`

- [ ] **Step 1: Write failing test**

- [ ] **Step 2: Update SPARQL query to include sp:binaryRestriction**

- [ ] **Step 3: Run tests, commit**

---

## Task 5: Fix subagent_spawning Hook Contract (#267)

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts:350-375`

- [ ] **Step 1: Replace throw with return**

Change `throw new Error(...)` to `return { status: "error", error: "..." }` in both places.

- [ ] **Step 2: TypeScript typecheck**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`

- [ ] **Step 3: Commit**

---

## Task 6: Update OpenClaw SDK Type Declarations (#266)

**Files:**
- Modify: `openclaw-safeclaw-plugin/types/openclaw-sdk.d.ts`

- [ ] **Step 1: Add new types**

Add `requireApproval` return type, `PluginApprovalResolution`, new hook names, deprecation on `before_agent_start`, `runId`/`toolCallId` on event type.

- [ ] **Step 2: TypeScript typecheck**

- [ ] **Step 3: Commit**

---

## Task 7: Add requireApproval Support (#265)

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts:236-267`

- [ ] **Step 1: Update before_tool_call handler**

When the service returns `confirmationRequired: true`, return `requireApproval` instead of `{ block: true }`:

```typescript
if (r?.confirmationRequired) {
  return {
    requireApproval: {
      title: 'SafeClaw Governance Check',
      description: (r.reason as string) || 'This action requires confirmation',
      severity: mapRiskToSeverity(r.riskLevel as string),
      timeoutMs: 30_000,
      timeoutBehavior: (r.riskLevel === 'HighRisk') ? 'deny' : 'allow',
    },
  };
}
```

- [ ] **Step 2: TypeScript typecheck**

- [ ] **Step 3: Commit**
