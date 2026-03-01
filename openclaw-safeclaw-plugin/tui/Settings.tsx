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
