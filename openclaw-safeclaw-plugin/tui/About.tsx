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
