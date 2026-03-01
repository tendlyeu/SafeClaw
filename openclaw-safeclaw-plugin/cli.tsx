#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { execSync } from 'child_process';
import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync, copyFileSync, lstatSync, unlinkSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { homedir } from 'os';
import { fileURLToPath } from 'url';
import App from './tui/App.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

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

if (command === 'connect') {
  const apiKey = args[1];
  const serviceUrlIdx = args.indexOf('--service-url');
  const serviceUrl = serviceUrlIdx !== -1 && args[serviceUrlIdx + 1]
    ? args[serviceUrlIdx + 1]
    : 'https://api.safeclaw.eu/api/v1';

  if (!apiKey || apiKey.startsWith('--')) {
    console.error('Usage: safeclaw connect <api-key> [--service-url <url>]');
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

  // Write config with owner-only permissions
  mkdirSync(configDir, { recursive: true });
  writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n');
  chmodSync(configPath, 0o600);

  console.log(`Connected! API key saved to ${configPath}`);

  // Register with OpenClaw
  console.log('Registering SafeClaw plugin with OpenClaw...');
  const registered = registerWithOpenClaw();
  if (registered) {
    console.log('SafeClaw plugin registered with OpenClaw.');
    console.log('');
    console.log('Restart OpenClaw to activate:');
    console.log('  safeclaw restart-openclaw');
  } else {
    console.log('');
    console.log('Could not auto-register with OpenClaw.');
    console.log('Register manually:');
    console.log('  openclaw plugins install openclaw-safeclaw-plugin');
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
    console.log('  2. Run: safeclaw connect <your-api-key>');
    console.log('  3. Run: safeclaw restart-openclaw');
  } else {
    console.log('Could not auto-register.');
    console.log('Try: openclaw plugins install openclaw-safeclaw-plugin');
  }
} else if (command === 'status') {
  const configPath = join(homedir(), '.safeclaw', 'config.json');
  let allOk = true;

  // 1. Config file
  if (existsSync(configPath)) {
    console.log('[ok] Config file: ' + configPath);
  } else {
    console.log('[!!] Config file not found. Run: safeclaw connect <api-key>');
    allOk = false;
  }

  // 2. API key
  let apiKey = '';
  let serviceUrl = 'https://api.safeclaw.eu/api/v1';
  if (existsSync(configPath)) {
    try {
      const cfg = JSON.parse(readFileSync(configPath, 'utf-8'));
      const remote = cfg.remote as Record<string, string> | undefined;
      apiKey = remote?.apiKey ?? '';
      serviceUrl = remote?.serviceUrl ?? serviceUrl;
    } catch { /* ignore */ }
  }

  if (apiKey && apiKey.startsWith('sc_')) {
    console.log('[ok] API key: configured (sc_...)');
  } else if (apiKey) {
    console.log('[!!] API key: invalid (must start with sc_)');
    allOk = false;
  } else {
    console.log('[!!] API key: not set. Run: safeclaw connect <api-key>');
    allOk = false;
  }

  // 3. SafeClaw service reachable
  try {
    const res = await fetch(`${serviceUrl}/health`, {
      signal: AbortSignal.timeout(5000),
      headers: apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {},
    });
    if (res.ok) {
      const data = await res.json() as Record<string, unknown>;
      console.log(`[ok] SafeClaw service: ${data.status ?? 'ok'} (${serviceUrl})`);
    } else {
      console.log(`[!!] SafeClaw service: HTTP ${res.status} (${serviceUrl})`);
      allOk = false;
    }
  } catch {
    console.log(`[!!] SafeClaw service: unreachable (${serviceUrl})`);
    allOk = false;
  }

  // 4. OpenClaw installed
  try {
    execSync('which openclaw', { encoding: 'utf-8', stdio: 'pipe' });
    console.log('[ok] OpenClaw: installed');
  } catch {
    console.log('[!!] OpenClaw: not found in PATH');
    allOk = false;
  }

  // 5. Plugin extension files exist
  const extensionDir = join(homedir(), '.openclaw', 'extensions', 'safeclaw');
  const hasManifest = existsSync(join(extensionDir, 'openclaw.plugin.json'));
  const hasEntry = existsSync(join(extensionDir, 'index.js'));
  if (hasManifest && hasEntry) {
    console.log('[ok] Plugin files: ' + extensionDir);
  } else if (existsSync(extensionDir)) {
    const stat = lstatSync(extensionDir);
    if (stat.isSymbolicLink()) {
      console.log('[!!] Plugin: stale symlink (run safeclaw setup to fix)');
    } else {
      console.log('[!!] Plugin: missing files in ' + extensionDir);
    }
    allOk = false;
  } else {
    console.log('[!!] Plugin: not installed. Run: safeclaw setup');
    allOk = false;
  }

  // 6. Plugin enabled in OpenClaw config
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

  // Summary
  console.log('');
  if (allOk) {
    console.log('All checks passed. SafeClaw is ready.');
  } else {
    console.log('Some checks failed. Fix the issues above.');
  }
} else {
  console.log('Usage: safeclaw <command>');
  console.log('');
  console.log('Commands:');
  console.log('  connect <api-key>  Connect to SafeClaw and register with OpenClaw');
  console.log('  setup              Register SafeClaw plugin with OpenClaw (no key needed)');
  console.log('  status             Check SafeClaw + OpenClaw connection status');
  console.log('  tui                Open the interactive SafeClaw settings TUI');
  console.log('  restart-openclaw   Restart the OpenClaw daemon');
  process.exit(0);
}
