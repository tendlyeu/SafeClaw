/**
 * SafeClaw — Neurosymbolic Governance Plugin for OpenClaw
 *
 * This TypeScript file is the ENTIRE client-side codebase.
 * All governance logic lives in the SafeClaw Python service.
 * This plugin is a thin HTTP bridge that forwards OpenClaw events
 * to the SafeClaw service and acts on the responses.
 */

import type { OpenClawPluginApi, OpenClawPluginEvent, OpenClawPluginContext } from 'openclaw/plugin-sdk/core';
import { loadConfig, configHash } from './tui/config.js';
import crypto from 'crypto';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const { version: PLUGIN_VERSION } = require('./package.json') as { version: string };

// --- Configuration ---

const CONFIG_RELOAD_INTERVAL_MS = 60_000; // Reload config every 60 seconds

let config = loadConfig();
let configLoadedAt = Date.now();

// OpenClaw plugin config — merged on top of file config when available
let _ocPluginConfig: Record<string, unknown> = {};

// Logger — defaults to console, replaced by api.logger when available
let log: { info: (...args: unknown[]) => void; warn: (...args: unknown[]) => void; error: (...args: unknown[]) => void } = console;

function getConfig(): typeof config {
  const now = Date.now();
  if (now - configLoadedAt >= CONFIG_RELOAD_INTERVAL_MS) {
    config = loadConfig();
    configLoadedAt = now;
  }
  // OpenClaw config takes priority over file config
  return {
    ...config,
    ...Object.fromEntries(Object.entries(_ocPluginConfig).filter(([_, v]) => v != null)),
  } as typeof config;
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
        log.warn(`[SafeClaw] ${path}: ${detail}${hint}`);
      } catch {
        log.warn(`[SafeClaw] HTTP ${res.status} from ${path}`);
      }
      return null;  // Caller checks failMode
    }
    return await res.json() as Record<string, unknown>;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      log.warn(`[SafeClaw] Timeout after ${cfg.timeoutMs}ms on ${path} (${cfg.serviceUrl})`);
    } else if (e instanceof TypeError && (e.message.includes('fetch') || e.message.includes('ECONNREFUSED'))) {
      log.warn(`[SafeClaw] Connection refused: ${cfg.serviceUrl}${path} — is the service running?`);
    } else {
      log.warn(`[SafeClaw] Service unavailable: ${cfg.serviceUrl}${path}`);
    }
    return null;  // Caller checks failMode
  }
}

// --- Plugin Definition ---

let handshakeCompleted = false;

async function performHandshake(): Promise<boolean> {
  const cfg = getConfig();
  if (!cfg.apiKey) {
    log.warn('[SafeClaw] No API key configured — skipping handshake');
    return false;
  }

  const r = await post('/handshake', {
    pluginVersion: PLUGIN_VERSION,
    configHash: configHash(cfg),
  });

  if (r === null) {
    log.warn('[SafeClaw] Handshake failed — API key may be invalid or service unreachable');
    return false;
  }

  log.info(`[SafeClaw] Handshake OK — org=${r.orgId}, scope=${r.scope}, engine=${r.engineReady ? 'ready' : 'not ready'}`);
  handshakeCompleted = true;
  return true;
}

async function checkConnection(): Promise<void> {
  const cfg = getConfig();
  const label = `[SafeClaw]`;
  log.info(`${label} Connecting to ${cfg.serviceUrl} ...`);
  log.info(`${label} Mode: enforcement=${cfg.enforcement}, failMode=${cfg.failMode}`);

  try {
    const res = await fetch(`${cfg.serviceUrl}/health`, {
      signal: AbortSignal.timeout(cfg.timeoutMs * 2),
    });
    if (res.ok) {
      const data = await res.json() as Record<string, unknown>;
      log.info(`${label} Connected — service ${data.status ?? 'ok'}`);
    } else {
      log.warn(`${label} Service responded with HTTP ${res.status}`);
    }
  } catch {
    log.warn(`${label} Cannot reach service at ${cfg.serviceUrl}`);
    if (cfg.failMode === 'closed') {
      log.warn(`${label}   fail-mode=closed — tool calls will be BLOCKED until service is reachable`);
    } else {
      log.warn(`${label}   fail-mode=open — tool calls will be ALLOWED despite no connection`);
    }
  }
}

export default {
  id: 'safeclaw',
  name: 'SafeClaw Neurosymbolic Governance',
  version: PLUGIN_VERSION,

  register(api: OpenClawPluginApi) {
    if (!getConfig().enabled) {
      console.log('[SafeClaw] Plugin disabled');
      return;
    }

    log = api.logger ?? console;
    _ocPluginConfig = api.pluginConfig ?? {};

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

    // Clean shutdown: send shutdown heartbeat and clear interval (#194)
    let heartbeatInterval: ReturnType<typeof setInterval> | undefined;

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

    // Start heartbeat after connection check + handshake completes (#84)
    const startupPromise = checkConnection()
      .then(() => performHandshake())
      .then((ok) => {
        if (!ok && getConfig().failMode === 'closed') {
          log.warn('[SafeClaw] Handshake failed with fail-mode=closed — tool calls will be BLOCKED');
        }
        heartbeatInterval = setInterval(sendHeartbeat, 30000);
        return sendHeartbeat();
      })
      .catch(() => {});

    // Register as an OpenClaw service so the gateway manages our lifecycle.
    // The service's stop() method sends the shutdown heartbeat — no process.exit()
    // needed, which avoids killing the entire gateway process (#194).
    if (api.registerService) {
      api.registerService({
        id: 'safeclaw-governance',
        start() { /* startup handled above via startupPromise */ },
        async stop() {
          await startupPromise;  // Ensure startup finished before tearing down
          await shutdown();
        },
      });
    } else {
      // Fallback for older OpenClaw versions without registerService:
      // No process.exit() — just clean up on beforeExit
      process.on('beforeExit', () => { shutdown().catch(() => {}); });
    }

    // THE GATE — constraint checking on every tool call (#195: use correct OpenClaw field names)
    api.on('before_tool_call', async (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      const cfg = getConfig();
      if (!handshakeCompleted && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
        return { block: true, blockReason: 'SafeClaw handshake not completed (fail-closed)' };
      }

      const r = await post('/evaluate/tool-call', {
        sessionId: ctx.sessionId ?? event.sessionId ?? '',
        userId: ctx.agentId ?? '',
        toolName: event.toolName ?? '',
        params: event.params ?? {},
        runId: ctx.runId ?? '',
      });

      if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
        return { block: true, blockReason: `SafeClaw service unavailable at ${cfg.serviceUrl} (fail-closed)` };
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'warn-only') {
        log.warn(`[SafeClaw] Service unavailable at ${cfg.serviceUrl} (fail-closed mode, warn-only)`);
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'audit-only') {
        log.warn(`[SafeClaw] Service unavailable at ${cfg.serviceUrl} (fail-closed mode, audit-only)`);
      }
      if (r?.block) {
        const blockReason = (r.reason as string) || 'Blocked by SafeClaw (no reason provided)';
        if (cfg.enforcement === 'enforce') {
          return { block: true, blockReason };
        }
        if (cfg.enforcement === 'warn-only') {
          log.warn(`[SafeClaw] Warning: ${blockReason}`);
        }
        // audit-only: logged server-side, no action here
      }
    }, { priority: 100 });

    // Context injection — prepend governance context to agent system prompt
    // (#195: before_agent_start is deprecated; use before_prompt_build + prependSystemContext)
    api.on('before_prompt_build', async (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      const r = await post('/context/build', {
        sessionId: ctx.sessionId ?? event.sessionId ?? '',
        userId: ctx.agentId ?? '',
      });

      if (r?.prependContext) {
        return { prependSystemContext: r.prependContext as string };
      }
    }, { priority: 100 });

    // Message governance — check outbound messages
    // (#195: use ctx.conversationId/sessionId, ctx.accountId; return only { cancel: true })
    api.on('message_sending', async (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      const cfg = getConfig();
      const r = await post('/evaluate/message', {
        sessionId: ctx.conversationId ?? ctx.sessionId ?? event.sessionId ?? '',
        userId: ctx.accountId ?? '',
        to: event.to,
        content: event.content,
        channelId: ctx.channelId ?? '',
      });

      if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'enforce') {
        log.warn('[SafeClaw] Blocking message: service unavailable (fail-closed mode)');
        return { cancel: true };
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'warn-only') {
        log.warn('[SafeClaw] Service unavailable (fail-closed mode, warn-only)');
      } else if (r === null && cfg.failMode === 'closed' && cfg.enforcement === 'audit-only') {
        log.info('[SafeClaw] audit-only: service unreachable, allowing message (fail-closed)');
      }
      if (r?.block) {
        const blockReason = (r.reason as string) || 'Blocked by SafeClaw (no reason provided)';
        if (cfg.enforcement === 'enforce') {
          log.warn(`[SafeClaw] Blocking message: ${blockReason}`);
          return { cancel: true };
        }
        if (cfg.enforcement === 'warn-only') {
          log.warn(`[SafeClaw] Warning: ${blockReason}`);
        }
        // audit-only: logged server-side, no action here
      }
    }, { priority: 100 });

    // Async logging — fire-and-forget, no return value needed
    // (#195: use event.prompt for input, event.lastAssistant for output; add provider/model)
    api.on('llm_input', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/log/llm-input', {
        sessionId: event.sessionId ?? ctx.sessionId ?? '',
        content: event.prompt ?? '',
        provider: event.provider ?? '',
        model: event.model ?? '',
      }).catch(() => {});
    });

    api.on('llm_output', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/log/llm-output', {
        sessionId: event.sessionId ?? ctx.sessionId ?? '',
        content: event.lastAssistant ?? '',
        provider: event.provider ?? '',
        model: event.model ?? '',
        usage: event.usage ?? {},
      }).catch(() => {});
    });

    // (#195: use event.toolName, !event.error for success, add durationMs and error)
    api.on('after_tool_call', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/record/tool-result', {
        sessionId: ctx.sessionId ?? event.sessionId ?? '',
        toolName: event.toolName ?? '',
        params: event.params ?? {},
        result: event.result ?? '',
        success: !event.error,
        error: event.error ? String(event.error) : '',
        durationMs: event.durationMs ?? 0,
      }).catch((e) => log.warn('[SafeClaw] Failed to record tool result:', e));
    });

    // Subagent governance — block delegation bypass attempts (#188)
    api.on('subagent_spawning', async (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      const cfg = getConfig();
      const r = await post('/evaluate/subagent-spawn', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.agentId,
        parentAgentId: event.parentAgentId,
        childConfig: event.childConfig ?? {},
        reason: event.reason ?? '',
      });

      if (r?.block && cfg.enforcement === 'enforce') {
        throw new Error((r.reason as string) || 'Blocked by SafeClaw: delegation bypass detected');
      }
      if (r?.block && cfg.enforcement === 'warn-only') {
        log.warn(`[SafeClaw] Subagent spawn warning: ${r.reason}`);
      }
    }, { priority: 100 });

    // Subagent ended — record child agent lifecycle (#188)
    api.on('subagent_ended', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/record/subagent-ended', {
        sessionId: ctx.sessionId ?? event.sessionId,
        parentAgentId: event.parentAgentId,
        childAgentId: event.childAgentId,
      }).catch(() => {});
    });

    // Session lifecycle — notify service of session start (#189)
    api.on('session_start', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/session/start', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.agentId,
        agentId: instanceId,
        metadata: event.metadata ?? {},
      }).catch(() => {});
    });

    // Session lifecycle — notify service of session end (#189)
    api.on('session_end', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/session/end', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.agentId,
        agentId: instanceId,
      }).catch(() => {});
    });

    // Inbound message governance — evaluate received messages (#190)
    api.on('message_received', (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => {
      post('/evaluate/inbound-message', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.agentId,
        channel: event.channel ?? (ctx as any).channelId ?? '',
        sender: event.sender ?? '',
        content: event.content ?? '',
        metadata: event.metadata ?? {},
      }).catch(() => {});
    });

    // Agent tools — let agents introspect governance state (#197)
    if (api.registerTool) {
      api.registerTool({
        name: 'safeclaw_status',
        description: 'Check SafeClaw governance service status, enforcement mode, and active constraints',
        parameters: {},
        async execute(_params: Record<string, unknown>, _ctx: Record<string, unknown>) {
          const health = await post('/health', {});
          const cfg = getConfig();
          return {
            status: health?.status ?? 'unreachable',
            enforcement: cfg.enforcement,
            failMode: cfg.failMode,
            serviceUrl: cfg.serviceUrl,
            handshakeCompleted,
          };
        },
      });

      api.registerTool({
        name: 'safeclaw_check_action',
        description: 'Check if a specific tool call would be allowed by SafeClaw governance (dry run, no side effects)',
        parameters: {
          type: 'object',
          properties: {
            toolName: { type: 'string', description: 'Tool name to check' },
            params: { type: 'object', description: 'Tool parameters to validate' },
          },
          required: ['toolName'],
        },
        async execute(params: Record<string, unknown>, ctx: Record<string, unknown>) {
          const r = await post('/evaluate/tool-call', {
            sessionId: (ctx as any).sessionId ?? '',
            userId: (ctx as any).agentId ?? '',
            toolName: params.toolName,
            params: (params.params as Record<string, unknown>) ?? {},
            dryRun: true,
          });
          return r ?? { error: 'Service unreachable' };
        },
      });
    }

    // CLI extension — `safeclaw status` command (#197)
    if (api.registerCli) {
      api.registerCli(({ program }: { program: any }) => {
        const cmd = program.command('safeclaw').description('SafeClaw governance controls');
        cmd.command('status')
          .description('Show SafeClaw service status and enforcement mode')
          .action(async () => {
            const cfg = getConfig();
            const health = await post('/health', {});
            console.log(`SafeClaw: ${health?.status ?? 'unreachable'}`);
            console.log(`  Enforcement: ${cfg.enforcement}`);
            console.log(`  Fail mode: ${cfg.failMode}`);
            console.log(`  Service: ${cfg.serviceUrl}`);
          });
      }, { commands: ['safeclaw'] });
    }
  },
};
