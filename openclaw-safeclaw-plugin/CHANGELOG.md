# Changelog

## 2.0.0

Aligns the plugin with **OpenClaw v2026.6.8** hook contracts. This is a breaking
release: the `openclaw` peer range is now `>=2026.6.8` (the plugin reads
v2026.6.8 hook payloads and will lose governance data on older hosts).

### Breaking

- **Peer requirement** raised from `openclaw >=2026.1.0` to `>=2026.6.8`.
- **Conversation hooks now require opt-in.** `llm_input`/`llm_output` (and the
  `before_agent_*` family) only fire for non-bundled plugins when
  `plugins.entries.safeclaw.hooks.allowConversationAccess: true` is set. Without
  it the LLM I/O audit trail is silently empty. See README.

### Fixed

- **Hook payloads updated to v2026.6.8.** `subagent_spawning`/`subagent_ended`
  read the real session-key fields (`requesterSessionKey`/`childSessionKey`/
  `agentId`/`outcome`) instead of the removed `parentAgentId`/`childConfig`;
  `message_received` reads the sender from `from`/`senderId` and the channel from
  `ctx`; `llm_output` logs `assistantTexts` rather than the untyped
  `lastAssistant`. Prior reads were silently `undefined`.
- **Typed SDK declarations.** Per-hook event/context types replace the catch-all
  ambient type, so stale field reads now fail `tsc`.

### Added

- **Forwards `before_tool_call` discriminators** (`toolKind`, `toolInputKind`,
  `derivedPaths`) so the service can classify code-mode exec and file-touching
  envelopes.
- **Trigger origin.** Forwards `triggeredBy`/`jobId` so the service can fail safe
  on autonomous (cron) runs with no interactive approver.
- **Restricted approval decisions.** High-risk `requireApproval` results forbid
  durable "allow-always" via `allowedDecisions`.
- **Param rewrite.** When the service returns sanitized params for an allowed or
  confirmation-required call, the plugin applies them (including through the
  approval flow) so the tool executes the governed params.

## 1.5.0

- Previous release.
