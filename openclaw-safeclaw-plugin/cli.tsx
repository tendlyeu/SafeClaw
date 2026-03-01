#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { execSync } from 'child_process';
import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync, symlinkSync, lstatSync, unlinkSync, realpathSync } from 'fs';
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
  // Plugin root is one level up from dist/
  const pluginRoot = join(__dirname, '..');
  const extensionsDir = join(homedir(), '.openclaw', 'extensions');
  const linkPath = join(extensionsDir, 'safeclaw');

  // 1. Create symlink in ~/.openclaw/extensions/safeclaw -> plugin root
  try {
    mkdirSync(extensionsDir, { recursive: true });

    // Remove existing symlink/dir if it points elsewhere
    if (existsSync(linkPath)) {
      const stat = lstatSync(linkPath);
      if (stat.isSymbolicLink()) {
        const target = realpathSync(linkPath);
        if (target === realpathSync(pluginRoot)) {
          // Already linked correctly
        } else {
          unlinkSync(linkPath);
          symlinkSync(pluginRoot, linkPath);
        }
      }
      // If it's a real directory (from openclaw plugins install), leave it
    } else {
      symlinkSync(pluginRoot, linkPath);
    }
  } catch (e) {
    console.warn(`Warning: Could not create extension symlink: ${e instanceof Error ? e.message : e}`);
    return false;
  }

  // 2. Enable plugin in ~/.openclaw/openclaw.json
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

  // Only add/update if not already configured
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
  const registered = registerWithOpenClaw();
  if (registered) {
    console.log('SafeClaw plugin registered with OpenClaw.');
    console.log('');
    console.log('Restart OpenClaw to activate:');
    console.log('  safeclaw restart-openclaw');
    console.log('  — or —');
    console.log('  openclaw daemon restart');
  } else {
    console.log('');
    console.log('Could not auto-register with OpenClaw.');
    console.log('Register manually: openclaw plugins install openclaw-safeclaw-plugin');
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
  // Just register with OpenClaw (no API key needed)
  const registered = registerWithOpenClaw();
  if (registered) {
    console.log('SafeClaw plugin registered with OpenClaw.');
    console.log('');
    console.log('Next steps:');
    console.log('  1. Get an API key at https://safeclaw.eu/dashboard');
    console.log('  2. Run: safeclaw connect <your-api-key>');
    console.log('  3. Run: safeclaw restart-openclaw');
  } else {
    console.log('Could not auto-register. Try: openclaw plugins install openclaw-safeclaw-plugin');
  }
} else {
  console.log('Usage: safeclaw <command>');
  console.log('');
  console.log('Commands:');
  console.log('  connect <api-key>  Connect to SafeClaw and register with OpenClaw');
  console.log('  setup              Register SafeClaw plugin with OpenClaw (no key needed)');
  console.log('  tui                Open the interactive SafeClaw settings TUI');
  console.log('  restart-openclaw   Restart the OpenClaw daemon');
  process.exit(0);
}
