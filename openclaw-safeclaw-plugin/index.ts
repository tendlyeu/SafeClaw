/**
 * SafeClaw — Neurosymbolic Governance Plugin for OpenClaw
 *
 * This TypeScript file is the ENTIRE client-side codebase.
 * All governance logic lives in the SafeClaw Python service.
 * This plugin is a thin HTTP bridge that forwards OpenClaw events
 * to the SafeClaw service and acts on the responses.
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';

// --- Configuration ---

interface SafeClawPluginConfig {
  serviceUrl: string;
  apiKey: string;
  timeoutMs: number;
  enabled: boolean;
  enforcement: 'enforce' | 'warn-only' | 'audit-only' | 'disabled';
  failMode: 'open' | 'closed';
  agentId: string;
  agentToken: string;
}

function loadConfig(): SafeClawPluginConfig {
  const defaults: SafeClawPluginConfig = {
    serviceUrl: process.env.SAFECLAW_URL ?? 'https://api.safeclaw.eu/api/v1',
    apiKey: process.env.SAFECLAW_API_KEY ?? '',
    timeoutMs: parseInt(process.env.SAFECLAW_TIMEOUT_MS ?? '500', 10),
    enabled: process.env.SAFECLAW_ENABLED !== 'false',
    enforcement: (process.env.SAFECLAW_ENFORCEMENT as SafeClawPluginConfig['enforcement']) ?? 'enforce',
    failMode: (process.env.SAFECLAW_FAIL_MODE as SafeClawPluginConfig['failMode']) ?? 'closed',
    agentId: process.env.SAFECLAW_AGENT_ID ?? '',
    agentToken: process.env.SAFECLAW_AGENT_TOKEN ?? '',
  };

  // Try loading from config file
  const configPath = join(homedir(), '.safeclaw', 'config.json');
  if (existsSync(configPath)) {
    try {
      const raw = JSON.parse(readFileSync(configPath, 'utf-8'));
      if (raw.enabled === false) defaults.enabled = false;
      if (raw.remote?.serviceUrl) defaults.serviceUrl = raw.remote.serviceUrl;
      if (raw.remote?.apiKey) defaults.apiKey = raw.remote.apiKey;
      if (raw.remote?.timeoutMs) defaults.timeoutMs = raw.remote.timeoutMs;
      if (raw.enforcement?.mode) defaults.enforcement = raw.enforcement.mode;
      if (raw.enforcement?.failMode) defaults.failMode = raw.enforcement.failMode;
      if (raw.agentId) defaults.agentId = raw.agentId;
      if (raw.agentToken) defaults.agentToken = raw.agentToken;
    } catch {
      // Config file unreadable — use defaults
    }
  }

  defaults.serviceUrl = defaults.serviceUrl.replace(/\/+$/, '');

  const validModes = ['enforce', 'warn-only', 'audit-only', 'disabled'] as const;
  if (!validModes.includes(defaults.enforcement as any)) {
    console.warn(`[SafeClaw] Invalid enforcement mode "${defaults.enforcement}", defaulting to "enforce"`);
    defaults.enforcement = 'enforce';
  }

  const validFailModes = ['open', 'closed'] as const;
  if (!validFailModes.includes(defaults.failMode as any)) {
    console.warn(`[SafeClaw] Invalid fail mode "${defaults.failMode}", defaulting to "closed"`);
    defaults.failMode = 'closed';
  }

  return defaults;
}

const config = loadConfig();

// --- HTTP Client ---

async function post(path: string, body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  if (!config.enabled) return null;

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (config.apiKey) {
    headers['Authorization'] = `Bearer ${config.apiKey}`;
  }

  const agentFields = config.agentId ? { agentId: config.agentId, agentToken: config.agentToken } : {};

  try {
    const res = await fetch(`${config.serviceUrl}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ ...body, ...agentFields }),
      signal: AbortSignal.timeout(config.timeoutMs),
    });
    if (!res.ok) {
      // Try to parse structured error body from service
      try {
        const errBody = await res.json() as Record<string, unknown>;
        const detail = errBody.detail ?? `HTTP ${res.status}`;
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
      console.warn(`[SafeClaw] Timeout after ${config.timeoutMs}ms on ${path} (${config.serviceUrl})`);
    } else if (e instanceof TypeError && (e.message.includes('fetch') || e.message.includes('ECONNREFUSED'))) {
      console.warn(`[SafeClaw] Connection refused: ${config.serviceUrl}${path} — is the service running?`);
    } else {
      console.warn(`[SafeClaw] Service unavailable: ${config.serviceUrl}${path}`);
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

async function checkConnection(): Promise<void> {
  const label = `[SafeClaw]`;
  console.log(`${label} Connecting to ${config.serviceUrl} ...`);
  console.log(`${label} Mode: enforcement=${config.enforcement}, failMode=${config.failMode}`);

  try {
    const res = await fetch(`${config.serviceUrl}/health`, {
      signal: AbortSignal.timeout(config.timeoutMs * 2),
    });
    if (res.ok) {
      const data = await res.json() as Record<string, unknown>;
      console.log(`${label} ✓ Connected — service ${data.status ?? 'ok'}`);
    } else {
      console.warn(`${label} ✗ Service responded with HTTP ${res.status}`);
    }
  } catch {
    console.warn(`${label} ✗ Cannot reach service at ${config.serviceUrl}`);
    if (config.failMode === 'closed') {
      console.warn(`${label}   fail-mode=closed → tool calls will be BLOCKED until service is reachable`);
    } else {
      console.warn(`${label}   fail-mode=open → tool calls will be ALLOWED despite no connection`);
    }
  }
}

export default {
  id: 'openclaw-safeclaw-plugin',
  name: 'SafeClaw Neurosymbolic Governance',
  version: '0.1.2',

  register(api: PluginApi) {
    if (!config.enabled) {
      console.log('[SafeClaw] Plugin disabled');
      return;
    }

    // Fire-and-forget startup health check
    checkConnection().catch(() => {});

    // THE GATE — constraint checking on every tool call
    api.on('before_tool_call', async (event: PluginEvent, ctx: PluginContext) => {
      const r = await post('/evaluate/tool-call', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.userId ?? event.userId,
        toolName: event.toolName ?? event.tool_name,
        params: event.params ?? {},
        sessionHistory: event.sessionHistory ?? [],
      });

      if (r === null && config.failMode === 'closed' && config.enforcement === 'enforce') {
        return { block: true, blockReason: `SafeClaw service unavailable at ${config.serviceUrl} (fail-closed)` };
      } else if (r === null && config.failMode === 'closed' && config.enforcement === 'warn-only') {
        console.warn(`[SafeClaw] Service unavailable at ${config.serviceUrl} (fail-closed mode, warn-only)`);
      }
      if (r?.block) {
        if (config.enforcement === 'enforce') {
          return { block: true, blockReason: r.reason as string };
        }
        if (config.enforcement === 'warn-only') {
          console.warn(`[SafeClaw] Warning: ${r.reason}`);
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
      const r = await post('/evaluate/message', {
        sessionId: ctx.sessionId ?? event.sessionId,
        userId: ctx.userId ?? event.userId,
        to: event.to,
        content: event.content,
      });

      if (r === null && config.failMode === 'closed' && config.enforcement === 'enforce') {
        return { cancel: true };
      } else if (r === null && config.failMode === 'closed' && config.enforcement === 'warn-only') {
        console.warn('[SafeClaw] Service unavailable (fail-closed mode, warn-only)');
      }
      if (r?.block && config.enforcement === 'enforce') {
        return { cancel: true };
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
        success: event.success ?? true,
      }).catch(() => {});
    });
  },
};
