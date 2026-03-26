# Phase 2: OpenClaw Compatibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SafeClaw plugin functional and safe in current OpenClaw (stop killing the gateway, fix hook field mappings, modernize plugin structure, add new governance hooks).

**Architecture:** Batch 2A fixes the two critical bugs (process.exit, hook fields). Batch 2B modernizes the plugin structure. Batch 2C updates the manifest. Batches 2D/2E add new capabilities. Batch 2F publishes to ClawHub.

**Tech Stack:** TypeScript, OpenClaw Plugin SDK, Python FastAPI (service-side for new endpoints)

**Constraint:** The OpenClaw Plugin SDK (`openclaw/plugin-sdk`) is not available as an npm package we can install locally. We define compatible types based on research of OpenClaw's source, add the SDK as a `peerDependency`, and structure code so it works when installed inside OpenClaw's runtime.

---

## Batch 2A — Critical Plugin Fixes (single PR)

### Task 1: #194 — Remove process.exit() + register as OpenClaw service

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`

- [ ] **Step 1: Remove signal handlers**

Remove lines 205-206 that kill the entire OpenClaw gateway:
```typescript
// DELETE THESE:
process.on('SIGINT', async () => { await shutdown(); process.exit(0); });
process.on('SIGTERM', async () => { await shutdown(); process.exit(0); });
```

- [ ] **Step 2: Register heartbeat as an OpenClaw service**

Replace the raw `setInterval` + signal handlers with a service registration. Since we don't have the SDK types yet, use the `api` object's runtime methods:

```typescript
// Replace the checkConnection().then(...) chain and signal handlers with:
if (typeof (api as any).registerService === 'function') {
  (api as any).registerService({
    id: 'safeclaw-heartbeat',
    async start() {
      await checkConnection();
      const ok = await performHandshake();
      if (!ok && getConfig().failMode === 'closed') {
        console.warn('[SafeClaw] Handshake failed with fail-mode=closed — tool calls will be BLOCKED');
      }
      heartbeatInterval = setInterval(sendHeartbeat, 30000);
      await sendHeartbeat();
    },
    async stop() {
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      try {
        await post('/heartbeat', {
          agentId: instanceId,
          configHash: configHash(getConfig()),
          status: 'shutdown',
        });
      } catch { /* best-effort */ }
    },
  });
} else {
  // Fallback for standalone/older OpenClaw: keep the old pattern minus process.exit
  checkConnection()
    .then(() => performHandshake())
    .then((ok) => {
      if (!ok && getConfig().failMode === 'closed') {
        console.warn('[SafeClaw] Handshake failed with fail-mode=closed — tool calls will be BLOCKED');
      }
      heartbeatInterval = setInterval(sendHeartbeat, 30000);
      return sendHeartbeat();
    })
    .catch(() => {});
}
```

- [ ] **Step 3: Build and verify**

```bash
cd openclaw-safeclaw-plugin && npm run typecheck && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add index.ts && git commit -m "fix(#194): remove process.exit() signal handlers, register heartbeat as OpenClaw service"
```

### Task 2: #195 — Fix hook event/context field mappings

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `safeclaw-service/safeclaw/api/models.py` (update request models)
- Modify: `safeclaw-service/safeclaw/api/routes.py` (update endpoints)

- [ ] **Step 1: Fix before_tool_call field mappings**

```typescript
api.on('before_tool_call', async (event: PluginEvent, ctx: PluginContext) => {
  const cfg = getConfig();
  if (!handshakeCompleted && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
    return { block: true, blockReason: 'SafeClaw handshake not completed (fail-closed)' };
  }

  const r = await post('/evaluate/tool-call', {
    sessionId: ctx.sessionId ?? event.sessionId,
    userId: ctx.agentId ?? (ctx as any).agentId,  // OpenClaw uses agentId, not userId
    toolName: event.toolName,                       // canonical field name, no fallback
    params: event.params ?? {},
    runId: (ctx as any).runId,
  });

  // ... rest of blocking logic unchanged
}, { priority: 100 });
```

- [ ] **Step 2: Switch from before_agent_start to before_prompt_build**

```typescript
// REPLACE before_agent_start with before_prompt_build
api.on('before_prompt_build', async (event: PluginEvent, ctx: PluginContext) => {
  const r = await post('/context/build', {
    sessionId: ctx.sessionId ?? event.sessionId,
    userId: (ctx as any).agentId,
  });

  if (r?.prependContext) {
    return { prependSystemContext: r.prependContext as string };
  }
}, { priority: 100 });
```

- [ ] **Step 3: Fix message_sending field mappings**

```typescript
api.on('message_sending', async (event: PluginEvent, ctx: PluginContext) => {
  const cfg = getConfig();
  const r = await post('/evaluate/message', {
    sessionId: (ctx as any).conversationId ?? ctx.sessionId,
    userId: (ctx as any).accountId,
    channelId: (ctx as any).channelId,
    to: event.to,
    content: event.content,
  });

  if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
    return { cancel: true };  // cancelReason not supported by OpenClaw
  }
  // ... rest of logic, but use { cancel: true } instead of { cancel: true, cancelReason: ... }
}, { priority: 100 });
```

- [ ] **Step 4: Fix after_tool_call field mappings**

```typescript
api.on('after_tool_call', (event: PluginEvent, ctx: PluginContext) => {
  post('/record/tool-result', {
    sessionId: ctx.sessionId ?? event.sessionId,
    toolName: event.toolName,           // canonical, no tool_name fallback
    params: event.params ?? {},
    result: event.result ?? '',
    success: !event.error,              // infer from absence of error
    error: event.error,
    durationMs: event.durationMs,
  }).catch((e) => console.warn('[SafeClaw] Failed to record tool result:', e));
});
```

- [ ] **Step 5: Fix llm_input/llm_output field mappings**

```typescript
api.on('llm_input', (event: PluginEvent, ctx: PluginContext) => {
  post('/log/llm-input', {
    sessionId: event.sessionId ?? ctx.sessionId,
    provider: event.provider,
    model: event.model,
    prompt: event.prompt,
  }).catch(() => {});
});

api.on('llm_output', (event: PluginEvent, ctx: PluginContext) => {
  post('/log/llm-output', {
    sessionId: event.sessionId ?? ctx.sessionId,
    provider: event.provider,
    model: event.model,
    content: (event as any).lastAssistant,
    usage: event.usage,
  }).catch(() => {});
});
```

- [ ] **Step 6: Update service-side request models**

In `safeclaw-service/safeclaw/api/models.py`, make `userId` optional on all request models (since it maps from agentId which may not always be set), and add new fields:

```python
# ToolCallRequest: add runId
runId: str | None = None

# MessageRequest: add channelId
channelId: str | None = None

# ToolResultRequest: add error, durationMs
error: str | None = None
durationMs: float | None = None
```

- [ ] **Step 7: Build and verify**

```bash
cd openclaw-safeclaw-plugin && npm run typecheck && npm run build
cd ../safeclaw-service && source .venv/bin/activate && python -m pytest tests/ -q
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "fix(#195): fix hook event/context field mappings for OpenClaw compatibility"
```

- [ ] **Step 9: Close superseded tickets**

```bash
gh issue close 55 --comment "Superseded by #194 — signal handlers removed entirely"
gh issue close 89 --comment "Superseded by #195 — hook handlers rewritten with correct field mappings"
gh issue close 88 --comment "Superseded by #195 — message_sending handler rewritten"
gh issue close 164 --comment "Superseded by #195 — cancelReason removed (not supported by OpenClaw)"
```

---

## Batch 2B — Plugin Modernization

### Task 3: #187 — Migrate to OpenClaw Plugin SDK types

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `openclaw-safeclaw-plugin/package.json`

- [ ] **Step 1: Add SDK as peer dependency**

In `package.json`:
```json
"peerDependencies": {
  "openclaw": ">=2026.1.0"
}
```

- [ ] **Step 2: Create SDK type definitions**

Create `openclaw-safeclaw-plugin/types/openclaw-sdk.d.ts` with types based on our research of OpenClaw's source. This provides compile-time safety without requiring the SDK at build time:

```typescript
declare module 'openclaw/plugin-sdk/core' {
  export interface OpenClawPluginApi {
    on<K extends string>(
      hookName: K,
      handler: (event: Record<string, unknown>, ctx: Record<string, unknown>) => Promise<Record<string, unknown> | void> | void,
      options?: { priority?: number },
    ): void;
    registerService?(service: { id: string; start: () => Promise<void>; stop?: () => Promise<void> }): void;
    registerCli?(registrar: (ctx: { program: unknown }) => void, opts?: { commands: string[] }): void;
    registerTool?(tool: Record<string, unknown>): void;
    pluginConfig?: Record<string, unknown>;
    logger?: { info: (...args: unknown[]) => void; warn: (...args: unknown[]) => void; error: (...args: unknown[]) => void };
  }
}
```

- [ ] **Step 3: Replace inline interfaces with SDK types**

Remove the inline `PluginApi`, `PluginEvent`, `PluginContext` interfaces (lines 81-99) and import from the SDK type declarations.

- [ ] **Step 4: Remove toolName/tool_name dual-read hacks**

Remove all `event.toolName ?? event.tool_name` patterns — use `event.toolName` only.

- [ ] **Step 5: Build and verify**

```bash
npm run typecheck && npm run build
```

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(#187): migrate to OpenClaw Plugin SDK types, remove inline interfaces"
```

### Task 4: #196 — Adopt definePluginEntry() and OpenClaw config system

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `openclaw-safeclaw-plugin/tui/config.ts`

- [ ] **Step 1: Update config loading to prefer api.pluginConfig**

In `index.ts`, inside `register(api)`:
```typescript
// Read config from OpenClaw first, file config as fallback
const ocConfig = (api as any).pluginConfig ?? {};
const fileConfig = loadConfig();
const mergedConfig = {
  serviceUrl: ocConfig.serviceUrl ?? fileConfig.serviceUrl,
  apiKey: ocConfig.apiKey ?? fileConfig.apiKey,
  enforcement: ocConfig.enforcement ?? fileConfig.enforcement,
  failMode: ocConfig.failMode ?? fileConfig.failMode,
  agentId: ocConfig.agentId ?? fileConfig.agentId,
  agentToken: ocConfig.agentToken ?? fileConfig.agentToken,
  timeoutMs: ocConfig.timeoutMs ?? fileConfig.timeoutMs,
  enabled: ocConfig.enabled ?? fileConfig.enabled,
};
```

- [ ] **Step 2: Use api.logger when available**

Replace `console.log`/`console.warn` with:
```typescript
const log = (api as any).logger ?? console;
```

- [ ] **Step 3: Build and verify**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(#196): adopt OpenClaw config system and logger, file config as fallback"
```

- [ ] **Step 5: Close superseded ticket**

```bash
gh issue close 168 --comment "Superseded by #196 — plugin now uses api.pluginConfig with file fallback"
```

---

## Batch 2C — Manifest Update

### Task 5: #192 — Update openclaw.plugin.json

**Files:**
- Modify: `openclaw-safeclaw-plugin/openclaw.plugin.json`

- [ ] **Step 1: Sync version and add metadata**

Update to match package.json version and add missing fields.

- [ ] **Step 2: Complete configSchema**

Add missing config fields: `agentId`, `agentToken`, `timeoutMs`, `enabled`.

- [ ] **Step 3: Commit**

- [ ] **Step 4: Close superseded ticket**

```bash
gh issue close 95 --comment "Superseded by #192 — version synced across manifest and package.json"
```

---

## Batch 2D — New Hooks (parallelizable)

### Task 6: #188 — Subagent governance hooks

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Modify: `safeclaw-service/safeclaw/api/models.py`
- Create: `safeclaw-service/tests/test_subagent_governance.py`

Add `subagent_spawning` (blocking) and `subagent_ended` (observing) hooks. Service endpoints `/evaluate/subagent-spawn` and `/record/subagent-ended`.

### Task 7: #189 — Session lifecycle hooks

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Modify: `safeclaw-service/safeclaw/api/models.py`
- Create: `safeclaw-service/tests/test_session_lifecycle.py`

Add `session_start` and `session_end` hooks. Service endpoints for session init/teardown.

### Task 8: #190 — Inbound message governance

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Modify: `safeclaw-service/safeclaw/api/models.py`
- Create: `safeclaw-service/safeclaw/ontologies/safeclaw-channels.ttl`
- Create: `safeclaw-service/tests/test_inbound_governance.py`

Add `message_received` hook (observing). Service endpoint `/evaluate/inbound-message`. New channel trust ontology.

---

## Batch 2E — New Capabilities (parallelizable with 2D)

### Task 9: #193 — SHACL shapes for sandbox policies

**Files (service-side only):**
- Create: `safeclaw-service/safeclaw/ontologies/safeclaw-sandbox.ttl`
- Create: `safeclaw-service/safeclaw/ontologies/shapes/sandbox-shapes.ttl`
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Create: `safeclaw-service/tests/test_sandbox_shapes.py`

### Task 10: #197 — CLI commands and agent tools

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`
- Modify: `safeclaw-service/safeclaw/api/routes.py`

Register CLI commands via `api.registerCli()` and agent tools (`safeclaw_status`, `safeclaw_check_action`). Add dry-run flag to evaluate endpoint.

---

## Batch 2F — Ship

### Task 11: #191 — Publish to ClawHub

Research ClawHub submission requirements and publish. Depends on all prior batches.

---

## Execution Order

Tasks 1-2 first (critical fixes), then 3-4 (modernization), then 5 (manifest), then 6-10 in parallel, then 11.
