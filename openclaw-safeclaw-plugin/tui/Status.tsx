import React, { useState, useEffect } from 'react';
import { Text, Box, useInput } from 'ink';
import { exec } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { homedir } from 'os';
import { fileURLToPath } from 'url';
import { type SafeClawConfig } from './config.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_VERSION = JSON.parse(readFileSync(join(__dirname, '..', '..', 'package.json'), 'utf-8')).version as string;

interface StatusProps {
  config: SafeClawConfig;
}

interface HealthData {
  status: string;
  version?: string;
  engine_ready?: boolean;
}

type CheckStatus = 'checking' | 'ok' | 'fail';
type OpenClawStatus = 'checking' | 'running' | 'not running' | 'error';

export default function Status({ config }: StatusProps) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [openclawStatus, setOpenclawStatus] = useState<OpenClawStatus>('checking');
  const [restartMsg, setRestartMsg] = useState<string | null>(null);
  const [evaluateStatus, setEvaluateStatus] = useState<CheckStatus>('checking');
  const [handshakeStatus, setHandshakeStatus] = useState<CheckStatus>('checking');
  const [handshakeDetail, setHandshakeDetail] = useState('');

  const checkHealth = async () => {
    try {
      const res = await fetch(`${config.serviceUrl}/health`, {
        signal: AbortSignal.timeout(config.timeoutMs * 2),
      });
      if (res.ok) {
        const data = await res.json() as HealthData;
        setHealth(data);
        setError(null);
        // If healthy, run deeper checks
        checkEvaluate();
        if (config.apiKey) checkHandshake();
        else {
          setHandshakeStatus('fail');
          setHandshakeDetail('No API key');
        }
      } else {
        setHealth(null);
        setError(`HTTP ${res.status}`);
        setEvaluateStatus('fail');
        setHandshakeStatus('fail');
      }
    } catch {
      setHealth(null);
      setError('Cannot connect');
      setEvaluateStatus('fail');
      setHandshakeStatus('fail');
    }
    setLastCheck(new Date());
  };

  const checkEvaluate = async () => {
    try {
      const res = await fetch(`${config.serviceUrl}/evaluate/tool-call`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(config.apiKey ? { 'Authorization': `Bearer ${config.apiKey}` } : {}),
        },
        body: JSON.stringify({
          sessionId: 'tui-check', userId: 'tui-check',
          toolName: 'echo', params: { message: 'tui-check' },
        }),
        signal: AbortSignal.timeout(config.timeoutMs),
      });
      setEvaluateStatus(res.ok || res.status === 422 || res.status === 401 || res.status === 403 ? 'ok' : 'fail');
    } catch {
      setEvaluateStatus('fail');
    }
  };

  const checkHandshake = async () => {
    try {
      const res = await fetch(`${config.serviceUrl}/handshake`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${config.apiKey}`,
        },
        body: JSON.stringify({ pluginVersion: PKG_VERSION, configHash: '' }),
        signal: AbortSignal.timeout(config.timeoutMs),
      });
      if (res.ok) {
        const data = await res.json() as Record<string, unknown>;
        setHandshakeStatus('ok');
        setHandshakeDetail(`org=${data.orgId ?? '?'}`);
      } else {
        setHandshakeStatus('fail');
        setHandshakeDetail(`HTTP ${res.status}`);
      }
    } catch {
      setHandshakeStatus('fail');
      setHandshakeDetail('timeout');
    }
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

  // Derived display values
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

  // Plugin file checks
  const extensionDir = join(homedir(), '.openclaw', 'extensions', 'safeclaw');
  const pluginInstalled = existsSync(join(extensionDir, 'openclaw.plugin.json'))
    && existsSync(join(extensionDir, 'index.js'));

  // Plugin enabled in OpenClaw config
  let pluginEnabled = false;
  const ocConfigPath = join(homedir(), '.openclaw', 'openclaw.json');
  if (existsSync(ocConfigPath)) {
    try {
      const ocConfig = JSON.parse(readFileSync(ocConfigPath, 'utf-8'));
      pluginEnabled = !!ocConfig?.plugins?.entries?.safeclaw?.enabled;
    } catch { /* ignore */ }
  }

  const apiKeyMasked = config.apiKey
    ? `${config.apiKey.slice(0, 6)}..${config.apiKey.slice(-4)}`
    : '(not set)';

  const statusDot = (status: CheckStatus | boolean) => {
    if (status === 'checking') return <Text color="yellow">{dot} </Text>;
    if (status === 'ok' || status === true) return <Text color="green">{dot} </Text>;
    return <Text color="red">{dot} </Text>;
  };

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>Status</Text>
      </Box>

      <Box>
        <Text dimColor>{'  Service      '}</Text>
        <Text color={serviceDotColor}>{dot} </Text>
        <Text>{serviceText}</Text>
      </Box>

      {connected && (
        <>
          <Box>
            <Text dimColor>{'    Evaluate   '}</Text>
            {statusDot(evaluateStatus)}
            <Text>{evaluateStatus === 'ok' ? 'Responding' : evaluateStatus === 'checking' ? 'Checking...' : 'Not responding'}</Text>
          </Box>
          <Box>
            <Text dimColor>{'    Handshake  '}</Text>
            {statusDot(handshakeStatus)}
            <Text>{handshakeStatus === 'ok' ? handshakeDetail : handshakeStatus === 'checking' ? 'Checking...' : handshakeDetail}</Text>
          </Box>
        </>
      )}

      <Box>
        <Text dimColor>{'  OpenClaw      '}</Text>
        <Text color={openclawDotColor}>{dot} </Text>
        <Text>{openclawText}</Text>
        {restartMsg && <Text dimColor>{`  (${restartMsg})`}</Text>}
      </Box>

      <Box>
        <Text dimColor>{'    Plugin     '}</Text>
        {statusDot(pluginInstalled)}
        <Text>{pluginInstalled ? 'Installed' : 'Not installed'}</Text>
      </Box>

      <Box>
        <Text dimColor>{'    Config     '}</Text>
        {statusDot(pluginEnabled)}
        <Text>{pluginEnabled ? 'Enabled' : 'Not enabled'}</Text>
      </Box>

      <Box>
        <Text dimColor>{'  API Key      '}</Text>
        {statusDot(!!config.apiKey)}
        <Text>{apiKeyMasked}</Text>
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
