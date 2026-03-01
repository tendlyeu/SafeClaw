#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import { execSync } from 'child_process';
import App from './tui/App.js';

const args = process.argv.slice(2);
const command = args[0];

if (command === 'tui') {
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
  console.log('  tui                Open the interactive SafeClaw settings TUI');
  console.log('  restart-openclaw   Restart the OpenClaw daemon');
  process.exit(0);
}
