import React from 'react';
import { Text, Box } from 'ink';

export default function About() {
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>About SafeClaw</Text>
      </Box>
      <Text>  Neurosymbolic governance for AI agents.</Text>
      <Text dimColor>  Validates tool calls, messages, and actions against</Text>
      <Text dimColor>  OWL ontologies and SHACL constraints before execution.</Text>

      <Box marginTop={1} marginBottom={1}>
        <Text bold>  Features</Text>
      </Box>
      <Text dimColor>  - 9-step constraint pipeline (SHACL, policies, preferences, dependencies)</Text>
      <Text dimColor>  - Role-based access control with per-user preferences</Text>
      <Text dimColor>  - Multi-agent governance with delegation detection</Text>
      <Text dimColor>  - Append-only audit trail with compliance reporting</Text>
      <Text dimColor>  - Passive LLM security reviewer and classification observer</Text>
      <Text dimColor>  - Natural language policy compilation</Text>

      <Box marginTop={1} marginBottom={1}>
        <Text bold>  CLI commands</Text>
      </Box>
      <Text dimColor>  safeclaw-plugin  This plugin CLI (connect, status, config, tui)</Text>
      <Text dimColor>  safeclaw         Service CLI (serve, audit, policy, pref, status)</Text>

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
