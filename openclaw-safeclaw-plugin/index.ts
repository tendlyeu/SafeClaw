/**
 * SafeClaw — Neurosymbolic Governance Plugin for OpenClaw
 *
 * This TypeScript file is the ENTIRE client-side codebase.
 * All governance logic lives in the SafeClaw Python service.
 * This plugin is a thin HTTP bridge that forwards OpenClaw events
 * to the SafeClaw service and acts on the responses.
 */

import { loadConfig, configHash } from './tui/config.js';
import crypto from 'crypto';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const { version: PLUGIN_VERSION } = require('./package.json') as { version: string };

// --- Configuration ---

const CONFIG_RELOAD_INTERVAL_MS = 60_000; // Reload config every 60 seconds

let config = loadConfig();
let configLoadedAt = Date.now();

function getConfig(): typeof config {
  const now = Date.now();
  if (now - configLoadedAt >= CONFIG_RELOAD_INTERVAL_MS) {
    config = loadConfig();
    configLoadedAt = now;
  }
  return config;
}

// --- HTTP Client ---

async function post(path: string, body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  const cfg = getConfig();
  if (!cfg.enabled) return null;

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (cfg.apiKey) {
    headers['Authorization'] = `Bearer ${cfg.apiKey}`;
  }

  const agentFields = cfg.agentId ? { agentId: cfg.agentId, agentToken: cfg.agentToken } : {};

  try {
    const res = await fetch(`${cfg.serviceUrl}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ ...body, ...agentFields }),
      signal: AbortSignal.timeout(cfg.timeoutMs),
    });
    if (!res.ok) {
      // Try to parse structured error body from service
      try {
        const errBody = await res.json() as Record<string, unknown>;
        const rawDetail = errBody.detail ?? `HTTP ${res.status}`;
        const detail = typeof rawDetail === 'string' ? rawDetail : JSON.stringify(rawDetail);
        const hint = errBody.hint ? ` (${errBody.hint})` : '';
        console.warn(`[SafeClaw] ${path}: ${detail}${hint}`);
      } catch {
        console.warn(`[SafeClaw] HTTP ${res.status} from ${path}`);
      }
      return null;  // Caller checks failMode
    }
    return await res.json() as Record<string, unknown>;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      console.warn(`[SafeClaw] Timeout after ${cfg.timeoutMs}ms on ${path} (${cfg.serviceUrl})`);
    } else if (e instanceof TypeError && (e.message.includes('fetch') || e.message.includes('ECONNREFUSED'))) {
      console.warn(`[SafeClaw] Connection refused: ${cfg.serviceUrl}${path} — is the service running?`);
    } else {
      console.warn(`[SafeClaw] Service unavailable: ${cfg.serviceUrl}${path}`);
    }
    return null;  // Caller checks failMode
  }
}

// --- Plugin Definition ---

interface PluginEvent {
  sessionId?: string;
  userId?: string;
  [key: string]: unknown;
}

interface PluginContext {
  sessionId?: string;
  userId?: string;
  [key: string]: unknown;
}

interface PluginApi {
  on(
    event: string,
    handler: (event: PluginEvent, ctx: PluginContext) => Promise<Record<string, unknown> | void> | void,
    options?: { priority?: number },
  ): void;
}

let handshakeCompleted = false;

async function performHandshake(): Promise<boolean> {
  const cfg = getConfig();
  if (!cfg.apiKey) {
    console.warn('[SafeClaw] No API key configured — skipping handshake');
    return false;
  }

  const r = await post('/handshake', {
    pluginVersion: PLUGIN_VERSION,
    configHash: configHash(cfg),
  });

  if (r === null) {
    console.warn('[SafeClaw] ✗ Handshake failed — API key may be invalid or service unreachable');
    return false;
  }

  console.log(`[SafeClaw] ✓ Handshake OK — org=${r.orgId}, scope=${r.scope}, engine=${r.engineReady ? 'ready' : 'not ready'}`);
  handshakeCompleted = true;
  return true;
}

async function checkConnection(): Promise<void> {
  const cfg = getConfig();
  const label = `[SafeClaw]`;
  console.log(`${label} Connecting to ${cfg.serviceUrl} ...`);
  console.log(`${label} Mode: enforcement=${cfg.enforcement}, failMode=${cfg.failMode}`);

  try {
    const res = await fetch(`${cfg.serviceUrl}/health`, {
      signal: AbortSignal.timeout(cfg.timeoutMs * 2),
    });
    if (res.ok) {
      const data = await res.json() as Record<string, unknown>;
      console.log(`${label} ✓ Connected — service ${data.status ?? 'ok'}`);
    } else {
      console.warn(`${label} ✗ Service responded with HTTP ${res.status}`);
    }
  } catch {
    console.warn(`${label} ✗ Cannot reach service at ${cfg.serviceUrl}`);
    if (cfg.failMode === 'closed') {
      console.warn(`${label}   fail-mode=closed → tool calls will be BLOCKED until service is reachable`);
    } else {
      console.warn(`${label}   fail-mode=open → tool calls will be ALLOWED despite no connection`);
    }
  }
}

export default {
  id: 'safeclaw',
  name: 'SafeClaw Neurosymbolic Governance',
  version: PLUGIN_VERSION,

  register(api: PluginApi) {
    if (!getConfig().enabled) {
      console.log('[SafeClaw] Plugin disabled');
      return;
    }

    // Generate a unique instance ID for this plugin run (fallback when agentId is not configured)
    const instanceId = getConfig().agentId || `instance-${crypto.randomUUID()}`;

    // Heartbeat watchdog — send config hash to service every 30s
    const sendHeartbeat = async () => {
      try {
        await post('/heartbeat', {
          agentId: instanceId,
          configHash: configHash(getConfig()),
          status: 'alive',
        });
      } catch {
        // Heartbeat failure is non-fatal
      }
    };

    // Start heartbeat only after connection check + handshake completes (#84)
    let heartbeatInterval: ReturnType<typeof setInterval> | undefined;
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

    // Clean shutdown: send shutdown heartbeat and clear interval
    // Use async shutdown for SIGINT/SIGTERM where async is supported (#55)
    const shutdown = async () => {
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      try {
        await post('/heartbeat', {
          agentId: instanceId,
          configHash: configHash(getConfig()),
          status: 'shutdown',
        });
      } catch {
        // Best-effort shutdown notification
      }
    };
    process.on('SIGINT', async () => { await shutdown(); process.exit(0); });
    process.on('SIGTERM', async () => { await shutdown(); process.exit(0); });

    // THE GATE — constraint checking on every tool call
    api.on('before_tool_call', async (event: PluginEvent, ctx: PluginContext) => {
      const cfg = getConfig();
      if (!handshakeCompleted && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
        return { block: true, blockReason: 'SafeClaw handshake not completed (fail-closed)' };
      }

      const r = await post('/evaluate/tool-call', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.userId ?? event.userId,
        toolName: event.toolName ?? event.tool_name,
        params: event.params ?? {},
        sessionHistory: event.sessionHistory ?? [],
      });

      if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
        return { block: true, blockReason: `SafeClaw service unavailable at ${cfg.serviceUrl} (fail-closed)` };
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'warn-only') {
        console.warn(`[SafeClaw] Service unavailable at ${cfg.serviceUrl} (fail-closed mode, warn-only)`);
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'audit-only') {
        console.warn(`[SafeClaw] Service unavailable at ${cfg.serviceUrl} (fail-closed mode, audit-only)`);
      }
      if (r?.block) {
        const blockReason = (r.reason as string) || 'Blocked by SafeClaw (no reason provided)';
        if (cfg.enforcement === 'enforce') {
          return { block: true, blockReason };
        }
        if (cfg.enforcement === 'warn-only') {
          console.warn(`[SafeClaw] Warning: ${blockReason}`);
        }
        // audit-only: logged server-side, no action here
      }
    }, { priority: 100 });

    // Context injection — prepend governance context to agent system prompt
    api.on('before_agent_start', async (event: PluginEvent, ctx: PluginContext) => {
      const r = await post('/context/build', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.userId ?? event.userId,
      });

      if (r?.prependContext) {
        return { prependContext: r.prependContext as string };
      }
    }, { priority: 100 });

    // Message governance — check outbound messages
    api.on('message_sending', async (event: PluginEvent, ctx: PluginContext) => {
      const cfg = getConfig();
      const r = await post('/evaluate/message', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.userId ?? event.userId,
        to: event.to,
        content: event.content,
      });

      if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
        return { cancel: true, cancelReason: 'SafeClaw service unavailable (fail-closed mode)' };
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'warn-only') {
        console.warn('[SafeClaw] Service unavailable (fail-closed mode, warn-only)');
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'audit-only') {
        console.info('[SafeClaw] audit-only: service unreachable, allowing message (fail-closed)');
      }
      if (r?.block) {
        const blockReason = (r.reason as string) || 'Blocked by SafeClaw (no reason provided)';
        if (cfg.enforcement === 'enforce') {
          return { cancel: true, cancelReason: blockReason };
        }
        if (cfg.enforcement === 'warn-only') {
          console.warn(`[SafeClaw] Warning: ${blockReason}`);
        }
        // audit-only: logged server-side, no action here
      }
    }, { priority: 100 });

    // Async logging — fire-and-forget, no return value needed
    api.on('llm_input', (event: PluginEvent, ctx: PluginContext) => {
      post('/log/llm-input', {
        sessionId: ctx.sessionId ?? event.sessionId,
        content: event.content,
      }).catch(() => {});
    });

    api.on('llm_output', (event: PluginEvent, ctx: PluginContext) => {
      post('/log/llm-output', {
        sessionId: ctx.sessionId ?? event.sessionId,
        content: event.content,
      }).catch(() => {});
    });

    api.on('after_tool_call', (event: PluginEvent, ctx: PluginContext) => {
      post('/record/tool-result', {
        sessionId: ctx.sessionId ?? event.sessionId,
        toolName: event.toolName ?? event.tool_name,
        params: event.params ?? {},
        result: event.result ?? '',
        success: event.success ?? false,
      }).catch((e) => console.warn('[SafeClaw] Failed to record tool result:', e));
    });
  },
};
