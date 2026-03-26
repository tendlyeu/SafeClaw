#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { execSync } from 'child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync, copyFileSync, lstatSync, unlinkSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { homedir } from 'os';
import { fileURLToPath } from 'url';
import App from './tui/App.js';
import { loadConfig, saveConfig, isNemoClawSandbox, getSandboxName, type SafeClawConfig } from './tui/config.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_VERSION = JSON.parse(readFileSync(join(__dirname, '..', 'package.json'), 'utf-8')).version as string;

function readJson(path: string): Record<string, unknown> {
  try {
    return JSON.parse(readFileSync(path, 'utf-8'));
  } catch {
    return {};
  }
}

function registerWithOpenClaw(): boolean {
  const pluginRoot = join(__dirname, '..');  // one level up from dist/
  const extensionDir = join(homedir(), '.openclaw', 'extensions', 'safeclaw');
  const entryPoint = join(pluginRoot, 'dist', 'index.js');
  const manifestSrc = join(pluginRoot, 'openclaw.plugin.json');

  // Clean up stale symlink if it exists
  try {
    if (existsSync(extensionDir)) {
      const stat = lstatSync(extensionDir);
      if (stat.isSymbolicLink()) {
        unlinkSync(extensionDir);
      }
    }
  } catch { /* ignore */ }

  // Create extension directory with manifest + loader that imports from npm install
  try {
    mkdirSync(extensionDir, { recursive: true });

    // Copy the manifest
    if (existsSync(manifestSrc)) {
      copyFileSync(manifestSrc, join(extensionDir, 'openclaw.plugin.json'));
    } else {
      // Write manifest inline if source file missing
      writeFileSync(join(extensionDir, 'openclaw.plugin.json'), JSON.stringify({
        id: 'safeclaw',
        name: 'SafeClaw Neurosymbolic Governance',
        configSchema: { type: 'object', additionalProperties: false, properties: {} },
      }, null, 2) + '\n');
    }

    // Create index.js that loads from the actual npm install location
    writeFileSync(join(extensionDir, 'index.js'),
      `export { default } from '${entryPoint}';\n`);
  } catch (e) {
    console.warn(`Warning: Could not create extension: ${e instanceof Error ? e.message : e}`);
    return false;
  }

  // Enable plugin in ~/.openclaw/openclaw.json
  const openclawConfigPath = join(homedir(), '.openclaw', 'openclaw.json');
  const ocConfig = readJson(openclawConfigPath);

  if (!ocConfig.plugins || typeof ocConfig.plugins !== 'object') {
    ocConfig.plugins = {};
  }
  const plugins = ocConfig.plugins as Record<string, unknown>;
  if (!plugins.entries || typeof plugins.entries !== 'object') {
    plugins.entries = {};
  }
  const entries = plugins.entries as Record<string, unknown>;

  if (!entries.safeclaw || typeof entries.safeclaw !== 'object') {
    entries.safeclaw = { enabled: true };
  } else {
    (entries.safeclaw as Record<string, unknown>).enabled = true;
  }

  try {
    writeFileSync(openclawConfigPath, JSON.stringify(ocConfig, null, 2) + '\n');
  } catch (e) {
    console.warn(`Warning: Could not update OpenClaw config: ${e instanceof Error ? e.message : e}`);
    return false;
  }

  return true;
}

const args = process.argv.slice(2);
const command = args[0];

// Handle --help / -h for any command position
if (!command || command === '--help' || command === '-h' || command === 'help') {
  // Fall through to the else block at the bottom which prints full help
} else if (command === 'connect') {
  const apiKey = args[1];
  const serviceUrlIdx = args.indexOf('--service-url');
  const serviceUrl = serviceUrlIdx !== -1 && args[serviceUrlIdx + 1]
    ? args[serviceUrlIdx + 1]
    : 'https://api.safeclaw.eu/api/v1';

  if (!apiKey || apiKey.startsWith('--')) {
    console.error('Usage: safeclaw-plugin connect <api-key> [--service-url <url>]');
    process.exit(1);
  }

  if (!apiKey.startsWith('sc_')) {
    console.error('Error: Invalid API key. Keys start with "sc_".');
    console.error('Get your key at https://safeclaw.eu/dashboard');
    process.exit(1);
  }

  const configDir = join(homedir(), '.safeclaw');
  const configPath = join(configDir, 'config.json');

  // Load existing config or start fresh
  let config: Record<string, unknown> = {};
  if (existsSync(configPath)) {
    try {
      config = JSON.parse(readFileSync(configPath, 'utf-8'));
    } catch {
      // Start fresh
    }
  }

  // Set remote config
  if (!config.remote || typeof config.remote !== 'object') {
    config.remote = {};
  }
  (config.remote as Record<string, string>).apiKey = apiKey;
  (config.remote as Record<string, string>).serviceUrl = serviceUrl;

  // Write config with owner-only permissions (atomic mode via writeFileSync option)
  mkdirSync(configDir, { recursive: true, mode: 0o700 });
  writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n', { mode: 0o600 });

  console.log(`API key saved to ${configPath}`);

  // Validate key via handshake
  try {
    const res = await fetch(`${serviceUrl}/handshake`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ pluginVersion: PKG_VERSION, configHash: '' }),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const data = await res.json() as Record<string, unknown>;
      console.log(`Connected! org=${data.orgId}, scope=${data.scope}`);
    } else {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json() as Record<string, unknown>;
        detail = (body.error ?? body.detail ?? detail) as string;
      } catch { /* ignore */ }
      console.warn(`Warning: API key saved but handshake failed — ${detail}`);
      if (res.status === 401) {
        console.warn('The key may be invalid or revoked. Check https://safeclaw.eu/dashboard');
      }
    }
  } catch {
    console.warn(`Warning: API key saved but could not reach ${serviceUrl}`);
    console.warn('Run "safeclaw-plugin status" later to verify the connection.');
  }

  // Register with OpenClaw
  console.log('Registering SafeClaw plugin with OpenClaw...');
  const registered = registerWithOpenClaw();
  if (registered) {
    console.log('SafeClaw plugin registered with OpenClaw.');
    console.log('');
    console.log('Restart OpenClaw to activate:');
    console.log('  safeclaw-plugin restart-openclaw');
  } else {
    console.log('');
    console.log('Could not auto-register with OpenClaw.');
    console.log('Register manually:');
    console.log('  openclaw plugins install openclaw-safeclaw-plugin');
  }
} else if (command === 'config') {
  const subcommand = args[1];

  if (subcommand === 'show') {
    const cfg = loadConfig();
    console.log(`enabled:     ${cfg.enabled}`);
    console.log(`enforcement: ${cfg.enforcement}`);
    console.log(`failMode:    ${cfg.failMode}`);
    console.log(`serviceUrl:  ${cfg.serviceUrl}`);
    console.log(`apiKey:      ${cfg.apiKey ? `${cfg.apiKey.slice(0, 6)}...` : '(not set)'}`);
    console.log(`timeoutMs:   ${cfg.timeoutMs}`);
  } else if (subcommand === 'set') {
    const key = args[2];
    const value = args[3];

    if (!key || !value) {
      console.error('Usage: safeclaw-plugin config set <key> <value>');
      console.error('');
      console.error('Keys:');
      console.error('  enforcement   enforce | warn-only | audit-only | disabled');
      console.error('  failMode      open | closed');
      console.error('  enabled       true | false');
      console.error('  serviceUrl    https://...');
      process.exit(1);
    }

    const cfg = loadConfig();
    const validEnforcement = ['enforce', 'warn-only', 'audit-only', 'disabled'] as const;
    const validFailModes = ['open', 'closed'] as const;

    if (key === 'enforcement') {
      if (!validEnforcement.includes(value as any)) {
        console.error(`Invalid enforcement mode: "${value}". Valid: ${validEnforcement.join(', ')}`);
        process.exit(1);
      }
      cfg.enforcement = value as SafeClawConfig['enforcement'];
    } else if (key === 'failMode') {
      if (!validFailModes.includes(value as any)) {
        console.error(`Invalid fail mode: "${value}". Valid: ${validFailModes.join(', ')}`);
        process.exit(1);
      }
      cfg.failMode = value as SafeClawConfig['failMode'];
    } else if (key === 'enabled') {
      if (value !== 'true' && value !== 'false') {
        console.error('Invalid value for enabled: must be "true" or "false"');
        process.exit(1);
      }
      cfg.enabled = value === 'true';
    } else if (key === 'serviceUrl') {
      cfg.serviceUrl = value;
    } else {
      console.error(`Unknown config key: "${key}"`);
      console.error('Valid keys: enforcement, failMode, enabled, serviceUrl');
      process.exit(1);
    }

    try {
      saveConfig(cfg);
    } catch (e) {
      console.error(`Error: ${e instanceof Error ? e.message : e}`);
      process.exit(1);
    }
    console.log(`Set ${key} = ${value}`);
  } else {
    console.error('Usage: safeclaw-plugin config <show|set>');
    console.error('');
    console.error('  show          Display all current config values');
    console.error('  set <k> <v>   Set a config value (enforcement, failMode, enabled, serviceUrl)');
    process.exit(1);
  }
} else if (command === 'tui') {
  render(React.createElement(App));
} else if (command === 'restart-openclaw') {
  try {
    const output = execSync('openclaw daemon restart', { encoding: 'utf-8', timeout: 15000 });
    console.log(output.trim());
    console.log('OpenClaw daemon restarted successfully.');
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('Failed to restart OpenClaw daemon:', message);
    process.exit(1);
  }
} else if (command === 'setup') {
  console.log('Registering SafeClaw plugin with OpenClaw...');
  const registered = registerWithOpenClaw();
  if (registered) {
    console.log('SafeClaw plugin registered with OpenClaw.');
    console.log('');
    console.log('Next steps:');
    console.log('  1. Get an API key at https://safeclaw.eu/dashboard');
    console.log('  2. Run: safeclaw-plugin connect <your-api-key>');
    console.log('  3. Run: safeclaw-plugin restart-openclaw');
  } else {
    console.log('Could not auto-register.');
    console.log('Try: openclaw plugins install openclaw-safeclaw-plugin');
  }
} else if (command === 'status') {
  const cfg = loadConfig();
  const configPath = join(homedir(), '.safeclaw', 'config.json');
  let allOk = true;

  // 0. Active config summary
  console.log(`Config: enforcement=${cfg.enforcement}, failMode=${cfg.failMode}, timeout=${cfg.timeoutMs}ms`);
  console.log(`Service: ${cfg.serviceUrl}`);
  console.log('');

  // 1. Config file
  if (existsSync(configPath)) {
    console.log('[ok] Config file: ' + configPath);
  } else {
    console.log('[!!] Config file not found. Run: safeclaw-plugin connect <api-key>');
    allOk = false;
  }

  // 2. API key
  if (cfg.apiKey && cfg.apiKey.startsWith('sc_')) {
    console.log('[ok] API key: configured (sc_...)');
  } else if (cfg.apiKey) {
    console.log('[!!] API key: invalid (must start with sc_)');
    allOk = false;
  } else {
    console.log('[!!] API key: not set. Run: safeclaw-plugin connect <api-key>');
    allOk = false;
  }

  // 3. SafeClaw service — health check (uses same timeout as plugin)
  let serviceHealthy = false;
  try {
    const res = await fetch(`${cfg.serviceUrl}/health`, {
      signal: AbortSignal.timeout(cfg.timeoutMs),
      headers: cfg.apiKey ? { 'Authorization': `Bearer ${cfg.apiKey}` } : {},
    });
    if (res.ok) {
      const data = await res.json() as Record<string, unknown>;
      console.log(`[ok] Service health: ${data.status ?? 'ok'}`);
      serviceHealthy = true;
    } else {
      console.log(`[!!] Service health: HTTP ${res.status}`);
      allOk = false;
    }
  } catch (e) {
    const isTimeout = e instanceof DOMException && e.name === 'TimeoutError';
    console.log(`[!!] Service health: ${isTimeout ? `timeout after ${cfg.timeoutMs}ms` : 'unreachable'}`);
    allOk = false;
  }

  // 4. SafeClaw service — evaluate endpoint (the actual gate)
  if (serviceHealthy) {
    try {
      const res = await fetch(`${cfg.serviceUrl}/evaluate/tool-call`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(cfg.apiKey ? { 'Authorization': `Bearer ${cfg.apiKey}` } : {}),
        },
        body: JSON.stringify({
          sessionId: 'status-check',
          userId: 'status-check',
          toolName: 'echo',
          params: { message: 'status-check' },
        }),
        signal: AbortSignal.timeout(cfg.timeoutMs),
      });
      if (res.ok || res.status === 422) {
        // 422 = validation error is fine — means the service is processing requests
        console.log('[ok] Service evaluate: responding');
      } else if (res.status === 401 || res.status === 403) {
        console.log('[ok] Service evaluate: responding (auth required)');
      } else {
        let detail = '';
        try {
          const body = await res.json() as Record<string, unknown>;
          detail = ` — ${body.detail ?? body.error ?? JSON.stringify(body)}`;
        } catch { /* ignore */ }
        console.log(`[!!] Service evaluate: HTTP ${res.status}${detail}`);
        allOk = false;
      }
    } catch (e) {
      const isTimeout = e instanceof DOMException && e.name === 'TimeoutError';
      console.log(`[!!] Service evaluate: ${isTimeout ? `timeout after ${cfg.timeoutMs}ms` : 'unreachable'}`);
      if (cfg.failMode === 'closed') {
        console.log('     ↳ failMode=closed means ALL tool calls will be blocked!');
      }
      allOk = false;
    }
  }

  // 5. Handshake — validates API key actually works
  if (serviceHealthy && cfg.apiKey) {
    try {
      const res = await fetch(`${cfg.serviceUrl}/handshake`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${cfg.apiKey}`,
        },
        body: JSON.stringify({ pluginVersion: PKG_VERSION, configHash: '' }),
        signal: AbortSignal.timeout(cfg.timeoutMs),
      });
      if (res.ok) {
        const data = await res.json() as Record<string, unknown>;
        console.log(`[ok] Handshake: org=${data.orgId}, scope=${data.scope}, engine=${data.engineReady ? 'ready' : 'not ready'}`);
      } else {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json() as Record<string, unknown>;
          detail = (body.error ?? body.detail ?? detail) as string;
        } catch { /* ignore parse errors */ }
        console.log(`[!!] Handshake failed: ${detail}`);
        if (res.status === 401) {
          console.log('     ↳ API key is invalid or revoked. Get a new key at https://safeclaw.eu/dashboard');
        } else if (res.status === 403) {
          console.log('     ↳ API key lacks required scope. Check key permissions in your dashboard.');
        } else if (res.status === 500) {
          console.log('     ↳ Server error — check service logs for details.');
        }
        allOk = false;
      }
    } catch (e) {
      const isTimeout = e instanceof DOMException && e.name === 'TimeoutError';
      if (isTimeout) {
        console.log(`[!!] Handshake failed: timeout after ${cfg.timeoutMs}ms`);
        console.log('     ↳ Service may be overloaded. Try increasing SAFECLAW_TIMEOUT_MS.');
      } else {
        console.log('[!!] Handshake failed: could not connect');
        console.log(`     ↳ Is the service running at ${cfg.serviceUrl}?`);
      }
      allOk = false;
    }
  } else if (serviceHealthy && !cfg.apiKey) {
    console.log('[!!] Handshake: skipped — no API key configured');
    console.log('     ↳ Run: safeclaw-plugin connect <your-api-key>');
    allOk = false;
  }

  // 6. OpenClaw installed
  try {
    execSync('which openclaw', { encoding: 'utf-8', stdio: 'pipe' });
    console.log('[ok] OpenClaw: installed');
  } catch {
    console.log('[!!] OpenClaw: not found in PATH');
    allOk = false;
  }

  // 7. Plugin extension files exist
  const extensionDir = join(homedir(), '.openclaw', 'extensions', 'safeclaw');
  const hasManifest = existsSync(join(extensionDir, 'openclaw.plugin.json'));
  const hasEntry = existsSync(join(extensionDir, 'index.js'));
  if (hasManifest && hasEntry) {
    console.log('[ok] Plugin files: ' + extensionDir);
  } else if (existsSync(extensionDir)) {
    const stat = lstatSync(extensionDir);
    if (stat.isSymbolicLink()) {
      console.log('[!!] Plugin: stale symlink (run safeclaw-plugin setup to fix)');
    } else {
      console.log('[!!] Plugin: missing files in ' + extensionDir);
    }
    allOk = false;
  } else {
    console.log('[!!] Plugin: not installed. Run: safeclaw-plugin setup');
    allOk = false;
  }

  // 8. Plugin enabled in OpenClaw config
  const ocConfigPath = join(homedir(), '.openclaw', 'openclaw.json');
  if (existsSync(ocConfigPath)) {
    const ocConfig = readJson(ocConfigPath);
    const plugins = ocConfig.plugins as Record<string, unknown> | undefined;
    const entries = plugins?.entries as Record<string, unknown> | undefined;
    const safeclaw = entries?.safeclaw as Record<string, unknown> | undefined;
    if (safeclaw?.enabled) {
      console.log('[ok] OpenClaw config: safeclaw enabled');
    } else {
      console.log('[!!] OpenClaw config: safeclaw not enabled');
      allOk = false;
    }
  } else {
    console.log('[!!] OpenClaw config: not found');
    allOk = false;
  }

  // 9. NemoClaw sandbox
  if (isNemoClawSandbox()) {
    console.log(`[ok] NemoClaw sandbox: ${getSandboxName()}`);
  } else {
    console.log('[--] NemoClaw: not in sandbox (standalone mode)');
  }

  // Summary
  console.log('');
  if (allOk) {
    console.log('All checks passed. SafeClaw is ready.');
  } else {
    console.log('Some checks failed. Fix the issues above.');
  }
} else {
  console.log('safeclaw-plugin — OpenClaw plugin CLI for SafeClaw governance');
  console.log('');
  console.log('Usage: safeclaw-plugin <command> [options]');
  console.log('');
  console.log('Setup:');
  console.log('  connect <api-key>    Save API key, validate via handshake, register with OpenClaw');
  console.log('                       Keys start with "sc_". Get yours at https://safeclaw.eu/dashboard');
  console.log('  setup                Register plugin with OpenClaw without an API key (manual setup)');
  console.log('  restart-openclaw     Restart the OpenClaw daemon to pick up plugin changes');
  console.log('');
  console.log('Diagnostics:');
  console.log('  status               Run 9 checks: config, API key, service health, evaluate endpoint,');
  console.log('                       handshake, OpenClaw binary, plugin files, OpenClaw config, NemoClaw');
  console.log('');
  console.log('Configuration:');
  console.log('  config show          Show current enforcement, failMode, enabled, serviceUrl, apiKey');
  console.log('  config set <k> <v>   Set a config value. Keys: enforcement, failMode, enabled, serviceUrl');
  console.log('                       enforcement: enforce | warn-only | audit-only | disabled');
  console.log('                       failMode:    open (allow on error) | closed (block on error)');
  console.log('                       enabled:     true | false');
  console.log('');
  console.log('Interactive:');
  console.log('  tui                  Open the interactive settings TUI (Status, Settings, About tabs)');
  console.log('');
  console.log('For the service CLI (serve, audit, policy, pref), use the "safeclaw" command.');
  process.exit(0);
}
