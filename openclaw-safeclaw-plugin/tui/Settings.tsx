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
  { key: 'apiKey', label: 'API Key', type: 'text' },
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
        const editingKey = SETTINGS[selected].key;
        if (editingKey === 'apiKey' && editBuffer && !editBuffer.startsWith('sc_')) {
          // Reject invalid API keys — must start with sc_
          return;
        }
        try {
          updateConfig({ [editingKey]: editBuffer } as Partial<SafeClawConfig>);
        } catch {
          // saveConfig may throw on invalid URL — stay in edit mode
          return;
        }
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
        setEditBuffer(String(config[setting.key as keyof SafeClawConfig] ?? ''));
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
        } else if (setting.type === 'text' && editing && isSelected) {
          value = (setting.key === 'apiKey' ? '*'.repeat(editBuffer.length) : editBuffer) + '█';
        } else if (setting.key === 'apiKey') {
          value = config.apiKey
            ? `${config.apiKey.slice(0, 6)}..${config.apiKey.slice(-4)}`
            : '(not set)';
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
            ? SETTINGS[selected].key === 'apiKey' && editBuffer && !editBuffer.startsWith('sc_')
              ? '  API key must start with sc_ · esc to cancel'
              : '  type to edit · enter to save · esc to cancel'
            : '  ↑↓ navigate · ←→/enter cycle/toggle · enter to edit text fields · q quit'}
        </Text>
      </Box>

      <Box marginTop={1}>
        <Text dimColor>{'  Enforcement: enforce=block violations, warn-only=log only, audit-only=record only, disabled=off'}</Text>
      </Box>
      <Box>
        <Text dimColor>{'  Fail Mode:   open=allow if service unreachable, closed=block if service unreachable'}</Text>
      </Box>

      <Box marginTop={1}>
        <Text dimColor>{'  All changes save to ~/.safeclaw/config.json immediately.'}</Text>
      </Box>
    </Box>
  );
}
