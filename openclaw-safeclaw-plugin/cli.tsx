#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { execSync } from 'child_process';
import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import App from './tui/App.js';

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

  console.log(`Connected! Your API key has been saved to ${configPath}`);
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
} else {
  console.log('Usage: safeclaw <command>');
  console.log('');
  console.log('Commands:');
  console.log('  connect <api-key>  Save your API key to ~/.safeclaw/config.json');
  console.log('  tui                Open the interactive SafeClaw settings TUI');
  console.log('  restart-openclaw   Restart the OpenClaw daemon');
  process.exit(0);
}
