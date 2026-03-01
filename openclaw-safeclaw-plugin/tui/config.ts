/**
 * SafeClaw shared configuration module.
 *
 * Used by both the OpenClaw plugin (index.ts) and the TUI.
 * Reads ~/.safeclaw/config.json, applies env-var overrides,
 * and exposes helpers for saving and hashing config state.
 */

import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { homedir } from 'os';
import crypto from 'crypto';

// --- Types ---

export interface SafeClawConfig {
  serviceUrl: string;
  apiKey: string;
  timeoutMs: number;
  enabled: boolean;
  enforcement: 'enforce' | 'warn-only' | 'audit-only' | 'disabled';
  failMode: 'open' | 'closed';
  agentId: string;
  agentToken: string;
}

// --- Constants ---

export const CONFIG_PATH = join(homedir(), '.safeclaw', 'config.json');

// --- Functions ---

export function loadConfig(): SafeClawConfig {
  const defaults: SafeClawConfig = {
    serviceUrl: 'https://api.safeclaw.eu/api/v1',
    apiKey: '',
    timeoutMs: 500,
    enabled: true,
    enforcement: 'enforce',
    failMode: 'closed',
    agentId: '',
    agentToken: '',
  };

  // Load from config file first
  if (existsSync(CONFIG_PATH)) {
    try {
      const raw = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
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

  // Env vars override config file
  if (process.env.SAFECLAW_URL) defaults.serviceUrl = process.env.SAFECLAW_URL;
  if (process.env.SAFECLAW_API_KEY) defaults.apiKey = process.env.SAFECLAW_API_KEY;
  if (process.env.SAFECLAW_TIMEOUT_MS) defaults.timeoutMs = parseInt(process.env.SAFECLAW_TIMEOUT_MS, 10);
  if (process.env.SAFECLAW_ENABLED === 'false') defaults.enabled = false;
  if (process.env.SAFECLAW_ENFORCEMENT) defaults.enforcement = process.env.SAFECLAW_ENFORCEMENT as SafeClawConfig['enforcement'];
  if (process.env.SAFECLAW_FAIL_MODE) defaults.failMode = process.env.SAFECLAW_FAIL_MODE as SafeClawConfig['failMode'];
  if (process.env.SAFECLAW_AGENT_ID) defaults.agentId = process.env.SAFECLAW_AGENT_ID;
  if (process.env.SAFECLAW_AGENT_TOKEN) defaults.agentToken = process.env.SAFECLAW_AGENT_TOKEN;

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

/**
 * Persist managed config fields back to ~/.safeclaw/config.json.
 * Reads the existing file (if any), merges the fields SafeClaw manages,
 * and writes the result. Fields not managed by SafeClaw are preserved.
 */
export function saveConfig(config: SafeClawConfig): void {
  let existing: Record<string, unknown> = {};
  if (existsSync(CONFIG_PATH)) {
    try {
      existing = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
    } catch {
      // Unreadable — start fresh
    }
  }

  // Merge managed fields into existing structure
  existing.enabled = config.enabled;

  if (!existing.remote || typeof existing.remote !== 'object') {
    existing.remote = {};
  }
  (existing.remote as Record<string, unknown>).serviceUrl = config.serviceUrl;

  if (!existing.enforcement || typeof existing.enforcement !== 'object') {
    existing.enforcement = {};
  }
  (existing.enforcement as Record<string, unknown>).mode = config.enforcement;
  (existing.enforcement as Record<string, unknown>).failMode = config.failMode;

  // Ensure parent directory exists
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });

  writeFileSync(CONFIG_PATH, JSON.stringify(existing, null, 2) + '\n', 'utf-8');
}

/**
 * SHA-256 hash of the four TUI-managed config fields.
 * Used to detect whether the on-disk config has drifted from the in-memory state.
 */
export function configHash(config: SafeClawConfig): string {
  const payload = JSON.stringify({
    enabled: config.enabled,
    enforcement: config.enforcement,
    failMode: config.failMode,
    serviceUrl: config.serviceUrl,
  });
  return crypto.createHash('sha256').update(payload).digest('hex');
}
