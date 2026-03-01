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
  const dot = '●';
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
