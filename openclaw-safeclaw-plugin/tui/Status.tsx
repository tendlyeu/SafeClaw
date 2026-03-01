import React, { useState, useEffect } from 'react';
import { Text, Box, useInput } from 'ink';
import { exec } from 'child_process';
import { type SafeClawConfig } from './config.js';

interface StatusProps {
  config: SafeClawConfig;
}

interface HealthData {
  status: string;
  version?: string;
  engine_ready?: boolean;
}

type OpenClawStatus = 'checking' | 'running' | 'not running' | 'error';

export default function Status({ config }: StatusProps) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [openclawStatus, setOpenclawStatus] = useState<OpenClawStatus>('checking');
  const [restartMsg, setRestartMsg] = useState<string | null>(null);

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

  const checkOpenClaw = () => {
    exec('openclaw daemon status', { timeout: 10000 }, (err, stdout) => {
      if (err) {
        setOpenclawStatus('not running');
      } else {
        const output = stdout.toLowerCase();
        setOpenclawStatus(output.includes('running') ? 'running' : 'not running');
      }
    });
  };

  const restartOpenClaw = () => {
    setRestartMsg('Restarting...');
    exec('openclaw daemon restart', { timeout: 15000 }, (err) => {
      if (err) {
        setRestartMsg('Restart failed');
      } else {
        setRestartMsg('Restarted');
        checkOpenClaw();
      }
      setTimeout(() => setRestartMsg(null), 3000);
    });
  };

  useEffect(() => {
    checkHealth();
    checkOpenClaw();
    const interval = setInterval(() => {
      checkHealth();
      checkOpenClaw();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  useInput((input) => {
    if (input === 'r') {
      restartOpenClaw();
    }
  });

  const connected = health !== null;
  const dot = '●';
  const serviceDotColor = connected ? 'green' : 'red';
  const serviceText = connected
    ? `Connected (${config.serviceUrl.replace(/^https?:\/\//, '').replace(/\/api\/v1$/, '')})`
    : error ?? 'Disconnected';

  const openclawDotColor = openclawStatus === 'running' ? 'green' : openclawStatus === 'checking' ? 'yellow' : 'red';
  const openclawText = openclawStatus === 'checking' ? 'Checking...'
    : openclawStatus === 'running' ? 'Running'
    : 'Not running';

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>Status</Text>
      </Box>

      <Box>
        <Text dimColor>{'  Service     '}</Text>
        <Text color={serviceDotColor}>{dot} </Text>
        <Text>{serviceText}</Text>
      </Box>

      <Box>
        <Text dimColor>{'  OpenClaw    '}</Text>
        <Text color={openclawDotColor}>{dot} </Text>
        <Text>{openclawText}</Text>
        {restartMsg && <Text dimColor>{`  (${restartMsg})`}</Text>}
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

      <Box marginTop={1}>
        <Text dimColor>{'  Press '}</Text>
        <Text bold>r</Text>
        <Text dimColor>{' to restart OpenClaw daemon'}</Text>
      </Box>
    </Box>
  );
}
