# SafeClaw TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an interactive terminal UI (`safeclaw tui`) to the OpenClaw plugin for managing settings, plus a heartbeat watchdog to detect plugin tampering.

**Architecture:** Ink (React for CLI) renders a 3-tab TUI (Status, Settings, About). Config read/write is extracted to a shared module. The plugin sends periodic heartbeats to the service; a new HeartbeatMonitor on the service side detects staleness and config drift.

**Tech Stack:** TypeScript, Ink, React, Node.js 18+. Python (FastAPI, Pydantic) for service-side heartbeat.

---

### Task 1: Extract shared config module

**Files:**
- Create: `openclaw-safeclaw-plugin/tui/config.ts`
- Modify: `openclaw-safeclaw-plugin/index.ts`

**Step 1: Create `tui/config.ts`**

Create directory and file. This extracts the config read/write logic so both the plugin and the TUI can use it.

```typescript
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';

export interface SafeClawConfig {
  enabled: boolean;
  enforcement: 'enforce' | 'warn-only' | 'audit-only' | 'disabled';
  failMode: 'open' | 'closed';
  serviceUrl: string;
  apiKey: string;
  timeoutMs: number;
  agentId: string;
  agentToken: string;
}

export const CONFIG_PATH = join(homedir(), '.safeclaw', 'config.json');

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
    defaults.enforcement = 'enforce';
  }

  const validFailModes = ['open', 'closed'] as const;
  if (!validFailModes.includes(defaults.failMode as any)) {
    defaults.failMode = 'closed';
  }

  return defaults;
}

export function saveConfig(config: SafeClawConfig): void {
  const dir = join(homedir(), '.safeclaw');
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  // Read existing file to preserve fields we don't manage
  let existing: Record<string, any> = {};
  if (existsSync(CONFIG_PATH)) {
    try {
      existing = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
    } catch {
      // Start fresh
    }
  }

  // Merge our managed fields
  existing.enabled = config.enabled;
  if (!existing.remote) existing.remote = {};
  existing.remote.serviceUrl = config.serviceUrl;
  if (!existing.enforcement) existing.enforcement = {};
  existing.enforcement.mode = config.enforcement;
  existing.enforcement.failMode = config.failMode;

  writeFileSync(CONFIG_PATH, JSON.stringify(existing, null, 2) + '\n', 'utf-8');
}

export function configHash(config: SafeClawConfig): string {
  const crypto = require('crypto') as typeof import('crypto');
  const payload = JSON.stringify({
    enabled: config.enabled,
    enforcement: config.enforcement,
    failMode: config.failMode,
    serviceUrl: config.serviceUrl,
  });
  return crypto.createHash('sha256').update(payload).digest('hex');
}
```

**Step 2: Modify `index.ts` to import from shared config**

Replace the `SafeClawPluginConfig` interface, `loadConfig()` function, and `const config = loadConfig();` at lines 16-84 of `index.ts` with:

```typescript
import { loadConfig, type SafeClawConfig as SafeClawPluginConfig } from './tui/config.js';

const config = loadConfig();
```

Remove the now-unused imports `readFileSync`, `existsSync`, `join`, `homedir` from lines 10-12 (they're now only needed in `tui/config.ts`).

**Step 3: Verify the plugin still compiles**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
cd openclaw-safeclaw-plugin
git add tui/config.ts index.ts
git commit -m "refactor: extract shared config module for TUI"
```

---

### Task 2: Add Ink dependencies and update build config

**Files:**
- Modify: `openclaw-safeclaw-plugin/package.json`
- Modify: `openclaw-safeclaw-plugin/tsconfig.json`

**Step 1: Install Ink and React**

```bash
cd openclaw-safeclaw-plugin
npm install ink react ink-select-input ink-text-input
npm install --save-dev @types/react
```

**Step 2: Update `package.json`**

Add `bin` field and update `files` array. After `npm install` the package.json will already have the deps. Add these fields manually:

```json
{
  "bin": {
    "safeclaw": "dist/cli.js"
  },
  "files": [
    "dist/",
    "index.ts",
    "cli.tsx",
    "tui/",
    "SKILL.md",
    "README.md"
  ]
}
```

**Step 3: Update `tsconfig.json`**

Replace the entire file:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "declaration": true,
    "outDir": "dist",
    "rootDir": ".",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "lib": ["ES2022"],
    "jsx": "react-jsx"
  },
  "include": ["index.ts", "cli.tsx", "tui/**/*.ts", "tui/**/*.tsx"],
  "exclude": ["node_modules", "dist"]
}
```

**Step 4: Verify it compiles**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`
Expected: No errors (nothing uses JSX yet, but config is ready)

**Step 5: Commit**

```bash
cd openclaw-safeclaw-plugin
git add package.json package-lock.json tsconfig.json
git commit -m "chore: add Ink/React deps and JSX support for TUI"
```

---

### Task 3: Build the Status screen

**Files:**
- Create: `openclaw-safeclaw-plugin/tui/Status.tsx`

**Step 1: Create the Status component**

```tsx
import React, { useState, useEffect } from 'react';
import { Text, Box } from 'ink';
import { type SafeClawConfig } from './config.js';

interface StatusProps {
  config: SafeClawConfig;
}

interface HealthData {
  status: string;
  version?: string;
  engine_ready?: boolean;
}

export default function Status({ config }: StatusProps) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);

  const checkHealth = async () => {
    try {
      const res = await fetch(`${config.serviceUrl}/health`, {
        signal: AbortSignal.timeout(config.timeoutMs * 2),
      });
      if (res.ok) {
        const data = await res.json() as HealthData;
        setHealth(data);
        setError(null);
      } else {
        setHealth(null);
        setError(`HTTP ${res.status}`);
      }
    } catch {
      setHealth(null);
      setError('Cannot connect');
    }
    setLastCheck(new Date());
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const connected = health !== null;
  const dot = connected ? '●' : '●';
  const dotColor = connected ? 'green' : 'red';
  const statusText = connected
    ? `Connected (${config.serviceUrl.replace(/^https?:\/\//, '').replace(/\/api\/v1$/, '')})`
    : error ?? 'Disconnected';

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>Status</Text>
      </Box>

      <Box>
        <Text dimColor>{'  Service     '}</Text>
        <Text color={dotColor}>{dot} </Text>
        <Text>{statusText}</Text>
      </Box>

      <Box>
        <Text dimColor>{'  Enforcement  '}</Text>
        <Text>{config.enforcement}</Text>
      </Box>

      <Box>
        <Text dimColor>{'  Fail Mode    '}</Text>
        <Text>{config.failMode}</Text>
      </Box>

      <Box>
        <Text dimColor>{'  Enabled      '}</Text>
        <Text color={config.enabled ? 'green' : 'red'}>
          {config.enabled ? 'ON' : 'OFF'}
        </Text>
      </Box>

      {health?.version && (
        <Box marginTop={1}>
          <Text dimColor>{'  Service v'}</Text>
          <Text>{health.version}</Text>
        </Box>
      )}

      {lastCheck && (
        <Box marginTop={1}>
          <Text dimColor>
            {'  Last check: '}
            {lastCheck.toLocaleTimeString()}
          </Text>
        </Box>
      )}
    </Box>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
cd openclaw-safeclaw-plugin
git add tui/Status.tsx
git commit -m "feat(tui): add Status screen component"
```

---

### Task 4: Build the Settings screen

**Files:**
- Create: `openclaw-safeclaw-plugin/tui/Settings.tsx`

**Step 1: Create the Settings component**

```tsx
import React, { useState } from 'react';
import { Text, Box, useInput } from 'ink';
import { type SafeClawConfig, saveConfig } from './config.js';

interface SettingsProps {
  config: SafeClawConfig;
  onConfigChange: (config: SafeClawConfig) => void;
}

const ENFORCEMENT_MODES = ['enforce', 'warn-only', 'audit-only', 'disabled'] as const;
const FAIL_MODES = ['closed', 'open'] as const;

interface SettingItem {
  key: string;
  label: string;
  type: 'toggle' | 'cycle' | 'text';
  values?: readonly string[];
}

const SETTINGS: SettingItem[] = [
  { key: 'enabled', label: 'Enabled', type: 'toggle' },
  { key: 'enforcement', label: 'Enforcement', type: 'cycle', values: ENFORCEMENT_MODES },
  { key: 'failMode', label: 'Fail Mode', type: 'cycle', values: FAIL_MODES },
  { key: 'serviceUrl', label: 'Service URL', type: 'text' },
];

export default function Settings({ config, onConfigChange }: SettingsProps) {
  const [selected, setSelected] = useState(0);
  const [editing, setEditing] = useState(false);
  const [editBuffer, setEditBuffer] = useState('');

  const updateConfig = (patch: Partial<SafeClawConfig>) => {
    const updated = { ...config, ...patch };
    saveConfig(updated);
    onConfigChange(updated);
  };

  useInput((input, key) => {
    if (editing) {
      if (key.return) {
        updateConfig({ serviceUrl: editBuffer });
        setEditing(false);
      } else if (key.escape) {
        setEditing(false);
      } else if (key.backspace || key.delete) {
        setEditBuffer(prev => prev.slice(0, -1));
      } else if (input && !key.ctrl && !key.meta) {
        setEditBuffer(prev => prev + input);
      }
      return;
    }

    if (key.upArrow) {
      setSelected(prev => Math.max(0, prev - 1));
    } else if (key.downArrow) {
      setSelected(prev => Math.min(SETTINGS.length - 1, prev + 1));
    } else if (key.return || key.rightArrow || key.leftArrow) {
      const setting = SETTINGS[selected];
      if (setting.type === 'toggle') {
        updateConfig({ enabled: !config.enabled });
      } else if (setting.type === 'cycle' && setting.values) {
        const currentKey = setting.key as 'enforcement' | 'failMode';
        const current = config[currentKey];
        const idx = setting.values.indexOf(current);
        const dir = key.leftArrow ? -1 : 1;
        const next = setting.values[(idx + dir + setting.values.length) % setting.values.length];
        updateConfig({ [currentKey]: next });
      } else if (setting.type === 'text' && key.return) {
        setEditing(true);
        setEditBuffer(config.serviceUrl);
      }
    }
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>Settings</Text>
      </Box>

      {SETTINGS.map((setting, i) => {
        const isSelected = i === selected;
        const prefix = isSelected ? '▸ ' : '  ';
        let value: string;

        if (setting.key === 'enabled') {
          value = config.enabled ? 'ON' : 'OFF';
        } else if (setting.key === 'serviceUrl' && editing && isSelected) {
          value = editBuffer + '█';
        } else {
          value = String(config[setting.key as keyof SafeClawConfig]);
        }

        const showArrows = isSelected && setting.type === 'cycle';

        return (
          <Box key={setting.key}>
            <Text color={isSelected ? 'cyan' : undefined} bold={isSelected}>
              {prefix}
              {setting.label.padEnd(16)}
            </Text>
            {showArrows && <Text dimColor>{'◀ '}</Text>}
            <Text
              color={
                setting.key === 'enabled'
                  ? config.enabled ? 'green' : 'red'
                  : undefined
              }
            >
              {value}
            </Text>
            {showArrows && <Text dimColor>{' ▶'}</Text>}
          </Box>
        );
      })}

      <Box marginTop={1}>
        <Text dimColor>
          {editing
            ? '  type to edit · enter to save · esc to cancel'
            : '  ↑↓ navigate · ←→ change · enter to edit URL · q quit'}
        </Text>
      </Box>

      <Box>
        <Text dimColor>{'  Saves to ~/.safeclaw/config.json'}</Text>
      </Box>
    </Box>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
cd openclaw-safeclaw-plugin
git add tui/Settings.tsx
git commit -m "feat(tui): add Settings screen component"
```

---

### Task 5: Build the About screen and App shell

**Files:**
- Create: `openclaw-safeclaw-plugin/tui/About.tsx`
- Create: `openclaw-safeclaw-plugin/tui/App.tsx`

**Step 1: Create the About component**

```tsx
import React from 'react';
import { Text, Box } from 'ink';

export default function About() {
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>About</Text>
      </Box>
      <Text>  SafeClaw Neurosymbolic Governance</Text>
      <Text dimColor>  Validates AI agent actions against OWL</Text>
      <Text dimColor>  ontologies and SHACL constraints.</Text>
      <Box marginTop={1}>
        <Text>  Web:  </Text>
        <Text color="cyan">https://safeclaw.eu</Text>
      </Box>
      <Box>
        <Text>  Docs: </Text>
        <Text color="cyan">https://safeclaw.eu/docs</Text>
      </Box>
      <Box>
        <Text>  Repo: </Text>
        <Text color="cyan">https://github.com/tendlyeu/SafeClaw</Text>
      </Box>
      <Box marginTop={1}>
        <Text dimColor>  q to quit</Text>
      </Box>
    </Box>
  );
}
```

**Step 2: Create the App shell**

```tsx
import React, { useState } from 'react';
import { Text, Box, useInput, useApp } from 'ink';
import { loadConfig, type SafeClawConfig } from './config.js';
import Status from './Status.js';
import Settings from './Settings.js';
import About from './About.js';

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
        <Text dimColor>v0.2.0</Text>
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
```

**Step 3: Verify it compiles**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
cd openclaw-safeclaw-plugin
git add tui/About.tsx tui/App.tsx
git commit -m "feat(tui): add App shell with tab navigation and About screen"
```

---

### Task 6: Create the CLI entry point

**Files:**
- Create: `openclaw-safeclaw-plugin/cli.tsx`

**Step 1: Create `cli.tsx`**

```tsx
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
```

**Step 2: Build and verify the bin works**

Run:
```bash
cd openclaw-safeclaw-plugin
npx tsc
node dist/cli.js tui
```
Expected: The TUI renders in the terminal. Press `q` to quit.

**Step 3: Test the bin link**

Run:
```bash
cd openclaw-safeclaw-plugin
npm link
safeclaw tui
```
Expected: Same TUI appears. Press `q` to quit.

**Step 4: Commit**

```bash
cd openclaw-safeclaw-plugin
git add cli.tsx
git commit -m "feat(tui): add CLI entry point for 'safeclaw tui'"
```

---

### Task 7: Service-side HeartbeatMonitor

**Files:**
- Create: `safeclaw-service/safeclaw/engine/heartbeat_monitor.py`
- Test: `safeclaw-service/tests/test_heartbeat_monitor.py`

**Step 1: Write the failing test**

```python
import time
from unittest.mock import MagicMock

import pytest

from safeclaw.engine.heartbeat_monitor import HeartbeatMonitor


def test_record_and_check_fresh():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    stale = monitor.check_stale(threshold=90)
    assert len(stale) == 0


def test_check_stale_after_threshold():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    # Manually backdate the timestamp
    monitor._agents["agent-1"]["last_seen"] = time.monotonic() - 100
    stale = monitor.check_stale(threshold=90)
    assert "agent-1" in stale
    # Verify event was published
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.severity == "critical"
    assert "agent-1" in event.title


def test_config_drift_detection():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    assert monitor.check_config_drift("agent-1", "hash-abc") is False
    assert monitor.check_config_drift("agent-1", "hash-CHANGED") is True
    # Verify event was published for drift
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert "config" in event.title.lower()


def test_record_updates_timestamp():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    t1 = monitor._agents["agent-1"]["last_seen"]
    time.sleep(0.01)
    monitor.record("agent-1", "hash-abc")
    t2 = monitor._agents["agent-1"]["last_seen"]
    assert t2 > t1


def test_shutdown_removes_agent():
    bus = MagicMock()
    monitor = HeartbeatMonitor(bus)
    monitor.record("agent-1", "hash-abc")
    monitor.remove("agent-1")
    stale = monitor.check_stale(threshold=0)
    assert len(stale) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd safeclaw-service && python -m pytest tests/test_heartbeat_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'safeclaw.engine.heartbeat_monitor'`

**Step 3: Write the implementation**

```python
"""Heartbeat monitor for detecting plugin tampering."""

import logging
import time

from safeclaw.engine.event_bus import EventBus, SafeClawEvent

logger = logging.getLogger("safeclaw.heartbeat")


class HeartbeatMonitor:
    """Tracks agent heartbeats and detects staleness or config drift."""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        # {agent_id: {"last_seen": monotonic, "config_hash": str, "first_hash": str}}
        self._agents: dict[str, dict] = {}

    def record(self, agent_id: str, config_hash: str) -> None:
        """Record a heartbeat from an agent."""
        now = time.monotonic()
        if agent_id not in self._agents:
            self._agents[agent_id] = {
                "last_seen": now,
                "config_hash": config_hash,
                "first_hash": config_hash,
            }
        else:
            self._agents[agent_id]["last_seen"] = now
            self._agents[agent_id]["config_hash"] = config_hash

    def check_stale(self, threshold: float = 90.0) -> list[str]:
        """Return agent IDs that haven't sent a heartbeat within threshold seconds."""
        now = time.monotonic()
        stale = []
        for agent_id, info in self._agents.items():
            if now - info["last_seen"] > threshold:
                stale.append(agent_id)
                self._event_bus.publish(SafeClawEvent(
                    event_type="heartbeat_lost",
                    severity="critical",
                    title=f"Agent {agent_id} heartbeat lost",
                    detail=f"No heartbeat for {int(now - info['last_seen'])}s (threshold: {int(threshold)}s). "
                           "Plugin may have been disabled or uninstalled.",
                ))
        return stale

    def check_config_drift(self, agent_id: str, current_hash: str) -> bool:
        """Check if an agent's config hash has changed from its first-seen value."""
        info = self._agents.get(agent_id)
        if info is None:
            return False
        if info["first_hash"] != current_hash:
            self._event_bus.publish(SafeClawEvent(
                event_type="config_drift",
                severity="critical",
                title=f"Agent {agent_id} config hash changed",
                detail="Plugin configuration was modified since registration. "
                       "Possible tampering detected.",
            ))
            return True
        return False

    def remove(self, agent_id: str) -> None:
        """Remove an agent (intentional shutdown)."""
        self._agents.pop(agent_id, None)
```

**Step 4: Run tests to verify they pass**

Run: `cd safeclaw-service && python -m pytest tests/test_heartbeat_monitor.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
cd safeclaw-service
git add safeclaw/engine/heartbeat_monitor.py tests/test_heartbeat_monitor.py
git commit -m "feat: add HeartbeatMonitor for plugin tampering detection"
```

---

### Task 8: Add heartbeat API route and wire to engine

**Files:**
- Modify: `safeclaw-service/safeclaw/api/models.py`
- Modify: `safeclaw-service/safeclaw/api/routes.py`
- Modify: `safeclaw-service/safeclaw/engine/full_engine.py`

**Step 1: Add the HeartbeatRequest model**

Add to the end of `safeclaw-service/safeclaw/api/models.py`:

```python
class HeartbeatRequest(BaseModel):
    agentId: str = ""
    configHash: str = ""
    status: str = "alive"  # "alive" or "shutdown"
```

**Step 2: Add the heartbeat import to routes.py**

Add `HeartbeatRequest` to the import from `safeclaw.api.models` at line 10-25 of `routes.py`.

**Step 3: Add the heartbeat route**

Add before the `# ── LLM Layer Routes ──` comment (line 369) in `routes.py`:

```python
@router.post("/heartbeat")
async def heartbeat(request: HeartbeatRequest):
    """Receive plugin heartbeat. No admin auth required — plugins call this."""
    engine = _get_engine()
    if request.status == "shutdown":
        engine.heartbeat_monitor.remove(request.agentId)
        return {"ok": True, "action": "removed"}

    engine.heartbeat_monitor.record(request.agentId, request.configHash)

    # Piggyback: check for stale agents and config drift
    stale = engine.heartbeat_monitor.check_stale()
    drifted = engine.heartbeat_monitor.check_config_drift(
        request.agentId, request.configHash
    )

    return {"ok": True, "stale": stale, "configDrift": drifted}
```

**Step 4: Wire HeartbeatMonitor into FullEngine**

Add to `safeclaw-service/safeclaw/engine/full_engine.py`:
- Add import at the top: `from safeclaw.engine.heartbeat_monitor import HeartbeatMonitor`
- Add after `self.temp_permissions = TempPermissionManager(...)` (around line 116 in `_init_components`):

```python
self.heartbeat_monitor = HeartbeatMonitor(self.event_bus)
```

**Step 5: Run full test suite**

Run: `cd safeclaw-service && python -m pytest tests/ -v`
Expected: All tests pass (existing + new heartbeat tests)

**Step 6: Commit**

```bash
cd safeclaw-service
git add safeclaw/api/models.py safeclaw/api/routes.py safeclaw/engine/full_engine.py
git commit -m "feat: add heartbeat API route and wire to engine"
```

---

### Task 9: Add heartbeat to the plugin

**Files:**
- Modify: `openclaw-safeclaw-plugin/index.ts`

**Step 1: Add heartbeat interval to the plugin**

Add import of `configHash` at the top of `index.ts`:

```typescript
import { loadConfig, configHash, type SafeClawConfig as SafeClawPluginConfig } from './tui/config.js';
```

Add after the `checkConnection().catch(() => {});` line (line 189) inside the `register()` method:

```typescript
    // Heartbeat watchdog — send config hash to service every 30s
    const sendHeartbeat = async () => {
      try {
        await fetch(`${config.serviceUrl}/heartbeat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agentId: config.agentId || 'default',
            configHash: configHash(config),
            status: 'alive',
          }),
          signal: AbortSignal.timeout(config.timeoutMs),
        });
      } catch {
        // Heartbeat failure is non-fatal
      }
    };

    // Start heartbeat after connection check
    checkConnection().then(() => sendHeartbeat()).catch(() => {});
    const heartbeatInterval = setInterval(sendHeartbeat, 30000);

    // Clean shutdown: send shutdown heartbeat and clear interval
    const shutdown = () => {
      clearInterval(heartbeatInterval);
      fetch(`${config.serviceUrl}/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agentId: config.agentId || 'default',
          configHash: configHash(config),
          status: 'shutdown',
        }),
      }).catch(() => {});
    };
    process.on('exit', shutdown);
    process.on('SIGINT', () => { shutdown(); process.exit(0); });
    process.on('SIGTERM', () => { shutdown(); process.exit(0); });
```

Note: Remove the existing `checkConnection().catch(() => {});` at line 189 since the heartbeat code now calls it.

**Step 2: Verify it compiles**

Run: `cd openclaw-safeclaw-plugin && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
cd openclaw-safeclaw-plugin
git add index.ts
git commit -m "feat: add heartbeat watchdog to plugin"
```

---

### Task 10: Build, link, and end-to-end test

**Step 1: Build the plugin**

```bash
cd openclaw-safeclaw-plugin
npx tsc
```
Expected: Compiles with no errors. `dist/` contains `cli.js`, `tui/*.js`, `index.js`.

**Step 2: Verify the shebang line**

Check that `dist/cli.js` starts with `#!/usr/bin/env node`. If tsc strips it, add it manually:

```bash
head -1 dist/cli.js
```

If missing, prepend it:
```bash
echo '#!/usr/bin/env node' | cat - dist/cli.js > tmp && mv tmp dist/cli.js
chmod +x dist/cli.js
```

**Step 3: Test the TUI**

```bash
npm link
safeclaw tui
```

Expected:
- TUI renders with green SafeClaw header
- Tab bar shows `1:Status  2:Settings  3:About`
- Status screen shows connection status
- Press `2` → Settings screen with arrow key navigation
- Change enforcement mode with ←→ arrows
- Press `3` → About screen with links
- Press `q` to quit

**Step 4: Test the plugin still works**

```bash
npx tsc --noEmit
```
Expected: No errors. The plugin export is unchanged.

**Step 5: Run service tests**

```bash
cd ../safeclaw-service
python -m pytest tests/ -v
```
Expected: All tests pass including new heartbeat tests.

**Step 6: Final commit**

```bash
cd ../openclaw-safeclaw-plugin
git add dist/
git commit -m "feat: SafeClaw TUI v0.2.0 with heartbeat watchdog"
```
