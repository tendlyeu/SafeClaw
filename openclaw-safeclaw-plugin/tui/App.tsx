import React, { useState } from 'react';
import { Text, Box, useInput, useApp } from 'ink';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { loadConfig, type SafeClawConfig } from './config.js';
import Status from './Status.js';
import Settings from './Settings.js';
import About from './About.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_VERSION = JSON.parse(readFileSync(join(__dirname, '..', '..', 'package.json'), 'utf-8')).version as string;

const TABS = ['Status', 'Settings', 'About'] as const;
type Tab = typeof TABS[number];

export default function App() {
  const { exit } = useApp();
  const [tab, setTab] = useState<Tab>('Status');
  const [config, setConfig] = useState<SafeClawConfig>(loadConfig());

  useInput((input, key) => {
    if (input === 'q' && tab !== 'Settings') {
      exit();
      return;
    }
    if (key.tab || (input === '1' || input === '2' || input === '3')) {
      if (input === '1') setTab('Status');
      else if (input === '2') setTab('Settings');
      else if (input === '3') setTab('About');
      else {
        const idx = TABS.indexOf(tab);
        setTab(TABS[(idx + 1) % TABS.length]);
      }
    }
  });

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box borderStyle="single" borderColor="green" paddingX={1}>
        <Text bold color="green">SafeClaw </Text>
        <Text dimColor>v{PKG_VERSION}</Text>
      </Box>

      {/* Tab bar */}
      <Box paddingX={1} gap={2}>
        {TABS.map((t, i) => (
          <Text
            key={t}
            bold={tab === t}
            color={tab === t ? 'cyan' : 'white'}
            dimColor={tab !== t}
          >
            {`${i + 1}:${t}`}
          </Text>
        ))}
        <Text dimColor> tab/1-3 to switch</Text>
      </Box>

      {/* Content */}
      <Box marginTop={1}>
        {tab === 'Status' && <Status config={config} />}
        {tab === 'Settings' && (
          <Settings config={config} onConfigChange={setConfig} />
        )}
        {tab === 'About' && <About />}
      </Box>
    </Box>
  );
}
