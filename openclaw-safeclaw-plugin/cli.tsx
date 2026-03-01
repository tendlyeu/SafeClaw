#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import App from './tui/App.js';

const args = process.argv.slice(2);

if (args[0] !== 'tui') {
  console.log('Usage: safeclaw tui');
  console.log('');
  console.log('Opens the interactive SafeClaw settings TUI.');
  process.exit(0);
}

render(React.createElement(App));
