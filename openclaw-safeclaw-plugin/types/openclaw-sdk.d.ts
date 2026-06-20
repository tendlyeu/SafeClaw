/**
 * Ambient type declarations for the OpenClaw Plugin SDK.
 * These mirror the types exported by `openclaw/plugin-sdk` as of OpenClaw v2026.6.8.
 * When installed inside OpenClaw, the real SDK types take precedence.
 *
 * Design note (#317): each hook has a *precise* event payload (no catch-all
 * index signature) and `on()` is typed via per-hook overloads, so stale field
 * reads (e.g. the removed `event.parentAgentId` / `event.sender` /
 * `event.lastAssistant`-as-string) fail `tsc` instead of silently reading
 * `undefined`. We only model the hooks SafeClaw actually registers; everything
 * else falls through to the generic string overload.
 */

declare module 'openclaw/plugin-sdk/core' {
  // ---- Shared context (PluginHookAgentContext / PluginHookMessageContext) ----
  export interface OpenClawPluginContext {
    sessionId?: string;
    agentId?: string;
    runId?: string;
    conversationId?: string;
    accountId?: string;
    channelId?: string;
    /** Stable per-account sender identity on message hooks. */
    senderId?: string;
    /** Delivery platform on message hooks (e.g. "discord", "telegram", "line"). */
    messageProvider?: string;
    /** Present on cron/scheduled-triggered runs; absent on interactive runs. */
    jobId?: string;
    workspaceDir?: string;
  }

  // ---- Per-hook event payloads (v2026.6.8) ----

  export interface BeforeToolCallEvent {
    toolName?: string;
    params?: Record<string, unknown>;
    sessionId?: string;
    runId?: string;
    toolCallId?: string;
    /** e.g. "code_mode_exec" — distinguishes code-mode exec cells from shell exec. */
    toolKind?: string;
    /** Code-mode body language, e.g. "javascript" | "typescript". */
    toolInputKind?: string;
    /** Host-derived target paths for file-touching envelopes (e.g. apply_patch). */
    derivedPaths?: readonly string[];
  }

  export interface AfterToolCallEvent {
    toolName?: string;
    params?: Record<string, unknown>;
    result?: unknown;
    error?: string;
    durationMs?: number;
    sessionId?: string;
    runId?: string;
  }

  export interface BeforePromptBuildEvent {
    sessionId?: string;
  }

  export interface MessageSendingEvent {
    to?: string;
    content?: string;
    sessionId?: string;
  }

  /** v2026.6.8: sender is `from` (+ optional `senderId`); there is no `channel`. */
  export interface MessageReceivedEvent {
    from?: string;
    senderId?: string;
    content?: string;
    timestamp?: string;
    threadId?: string;
    messageId?: string;
    replyToId?: string;
    sessionId?: string;
    metadata?: Record<string, unknown>;
  }

  export interface LlmInputEvent {
    runId?: string;
    sessionId?: string;
    provider?: string;
    model?: string;
    systemPrompt?: string;
    prompt?: string;
    historyMessages?: unknown[];
    imagesCount?: number;
    tools?: unknown[];
  }

  /** v2026.6.8: reliable text is `assistantTexts: string[]`; `lastAssistant` is untyped. */
  export interface LlmOutputEvent {
    runId?: string;
    sessionId?: string;
    provider?: string;
    model?: string;
    assistantTexts?: string[];
    lastAssistant?: unknown;
    usage?: Record<string, unknown>;
  }

  /**
   * Deprecated compatibility hook (scheduled for removal after 2026-08-16).
   * v2026.6.8 payload — note there is no `parentAgentId` / `childConfig` / `reason`.
   */
  export interface SubagentSpawningEvent {
    childSessionKey?: string;
    agentId?: string;
    label?: string;
    mode?: string;
    requester?: string;
    threadRequested?: boolean;
    sessionId?: string;
  }

  export interface SubagentEndedEvent {
    targetSessionKey?: string;
    targetKind?: string;
    reason?: string;
    runId?: string;
    outcome?: 'ok' | 'error' | 'timeout' | 'killed' | 'reset' | 'deleted';
    error?: string;
    sessionId?: string;
  }

  export interface SessionLifecycleEvent {
    sessionId?: string;
    metadata?: Record<string, unknown>;
  }

  /** Generic fallback payload for hooks SafeClaw does not strongly type. */
  export interface OpenClawPluginEvent {
    [key: string]: unknown;
  }

  export interface PluginHookEventMap {
    before_tool_call: BeforeToolCallEvent;
    after_tool_call: AfterToolCallEvent;
    before_prompt_build: BeforePromptBuildEvent;
    message_sending: MessageSendingEvent;
    message_received: MessageReceivedEvent;
    llm_input: LlmInputEvent;
    llm_output: LlmOutputEvent;
    subagent_spawning: SubagentSpawningEvent;
    subagent_ended: SubagentEndedEvent;
    session_start: SessionLifecycleEvent;
    session_end: SessionLifecycleEvent;
  }

  // ---- Hook results ----

  export type PluginApprovalDecision = 'allow-once' | 'allow-always' | 'deny';
  /** v2026.6.8: typed resolution union (was a free-form string). */
  export type PluginApprovalResolution = PluginApprovalDecision | 'timeout' | 'cancelled';

  export interface PluginApprovalRequest {
    title: string;
    description: string;
    severity?: 'info' | 'warning' | 'critical';
    timeoutMs?: number;
    timeoutBehavior?: 'allow' | 'deny';
    /** v2026.6.8: restrict the offered decisions (e.g. forbid durable "allow-always"). */
    allowedDecisions?: PluginApprovalDecision[];
    pluginId?: string;
    onResolution?: (decision: PluginApprovalResolution) => Promise<void> | void;
  }

  export interface BeforeToolCallResult {
    block?: boolean;
    blockReason?: string;
    requireApproval?: PluginApprovalRequest;
    /** v2026.6.8: rewrite tool params before execution. */
    params?: Record<string, unknown>;
  }

  export interface BeforePromptBuildResult {
    prependSystemContext?: string;
  }

  export interface MessageSendingResult {
    cancel?: boolean;
  }

  export interface SubagentSpawningResult {
    status?: 'ok' | 'error';
    error?: string;
  }

  export interface PluginHookResultMap {
    before_tool_call: BeforeToolCallResult;
    after_tool_call: void;
    before_prompt_build: BeforePromptBuildResult;
    message_sending: MessageSendingResult;
    message_received: void;
    llm_input: void;
    llm_output: void;
    subagent_spawning: SubagentSpawningResult;
    subagent_ended: void;
    session_start: void;
    session_end: void;
  }

  export interface OpenClawPluginApi {
    /** Typed overload for the hooks SafeClaw registers. */
    on<K extends keyof PluginHookEventMap>(
      hookName: K,
      handler: (
        event: PluginHookEventMap[K],
        ctx: OpenClawPluginContext,
      ) => PluginHookResultMap[K] | void | Promise<PluginHookResultMap[K] | void>,
      options?: { priority?: number },
    ): void;
    /** Generic fallback for any other hook. */
    on(
      hookName: string,
      handler: (
        event: OpenClawPluginEvent,
        ctx: OpenClawPluginContext,
      ) => Promise<Record<string, unknown> | void> | void,
      options?: { priority?: number },
    ): void;

    registerService?(service: OpenClawPluginService): void;
    registerCli?(registrar: (ctx: { program: unknown; config: unknown }) => void, opts?: { commands: string[] }): void;
    registerTool?(tool: OpenClawPluginTool): void;
    registerCommand?(def: { name: string; description: string; execute: (ctx: unknown) => Promise<string | void> }): void;
    pluginConfig?: Record<string, unknown>;
    logger?: OpenClawPluginLogger;
  }

  export interface OpenClawPluginService {
    id: string;
    start: () => void | Promise<void>;
    stop?: () => void | Promise<void>;
  }

  export interface OpenClawPluginTool {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
    execute: (params: Record<string, unknown>, ctx: Record<string, unknown>) => Promise<unknown>;
  }

  export interface OpenClawPluginLogger {
    info: (...args: unknown[]) => void;
    warn: (...args: unknown[]) => void;
    error: (...args: unknown[]) => void;
  }
}

declare module 'openclaw/plugin-sdk/plugin-entry' {
  import type { OpenClawPluginApi } from 'openclaw/plugin-sdk/core';

  export interface PluginDefinition {
    id: string;
    name: string;
    description?: string;
    version?: string;
    configSchema?: Record<string, unknown>;
    register?: (api: OpenClawPluginApi) => void | Promise<void>;
  }

  export function definePluginEntry(def: PluginDefinition): PluginDefinition;
}
