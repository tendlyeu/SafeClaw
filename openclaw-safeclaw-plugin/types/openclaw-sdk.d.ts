/**
 * Ambient type declarations for the OpenClaw Plugin SDK.
 * Transcribed from the published `openclaw@2026.6.8` source
 * (`src/plugins/hook-types.ts`, `hook-message.types.ts`,
 * `hook-before-tool-call-result.ts`). When installed inside OpenClaw the real
 * SDK types take precedence.
 *
 * Design note (#317): each registered hook has BOTH a precise event payload and
 * a precise *context* type — the contexts genuinely differ (agent runs expose
 * `agentId`/`sessionId`; message hooks expose neither, only `sessionKey`;
 * subagent hooks expose only `requesterSessionKey`/`childSessionKey`/`runId`).
 * `on()` is typed via per-hook overloads keyed off `PluginHookEventMap` /
 * `PluginHookContextMap`, so reading a field that does not exist on that hook's
 * real payload/context (e.g. `ctx.agentId` on a subagent hook, `ctx.sessionId`
 * on a message hook) fails `tsc` instead of silently reading `undefined`.
 */

declare module 'openclaw/plugin-sdk/core' {
  // ---- Per-hook contexts (v2026.6.8) ----

  /** PluginHookAgentContext — agent-runtime hooks (tool calls, prompts, llm, session). */
  export interface PluginHookAgentContext {
    runId?: string;
    jobId?: string;
    agentId?: string;
    /** Canonical conversation key — present on agent-runtime hooks. */
    sessionKey?: string;
    sessionId?: string;
    workspaceDir?: string;
    modelProviderId?: string;
    modelId?: string;
    messageProvider?: string;
    /** Channel/plugin id for channel-originated runs, e.g. "discord". */
    channel?: string;
    chatId?: string;
    senderId?: string;
    trigger?: string;
    channelId?: string;
  }

  /** PluginHookMessageContext — inbound/outbound message hooks. No agentId / sessionId. */
  export interface PluginHookMessageContext {
    channelId: string;
    accountId?: string;
    conversationId?: string;
    /** Canonical conversation key; the message-hook equivalent of sessionId. */
    sessionKey?: string;
    runId?: string;
    messageId?: string;
    senderId?: string;
    replyToId?: string;
  }

  /** PluginHookSubagentContext — subagent_spawning / subagent_ended. Session keys only. */
  export interface PluginHookSubagentContext {
    runId?: string;
    childSessionKey?: string;
    /** The requesting (parent) session key. There is no parent agentId here. */
    requesterSessionKey?: string;
  }

  /** Loose fallback context for hooks SafeClaw does not strongly type. */
  export interface OpenClawPluginContext {
    [key: string]: unknown;
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

  /** v2026.6.8 PluginHookMessageSendingEvent — no sessionId on the event. */
  export interface MessageSendingEvent {
    to: string;
    content: string;
    replyToId?: string | number;
    threadId?: string | number;
    metadata?: Record<string, unknown>;
  }

  /** v2026.6.8 PluginHookMessageReceivedEvent — sender is `from`; key is `sessionKey`. */
  export interface MessageReceivedEvent {
    from: string;
    content: string;
    timestamp?: number;
    threadId?: string | number;
    messageId?: string;
    senderId?: string;
    replyToId?: string;
    replyToSender?: string;
    sessionKey?: string;
    runId?: string;
    metadata?: Record<string, unknown>;
  }

  export interface LlmInputEvent {
    runId?: string;
    sessionId?: string;
    provider?: string;
    model?: string;
    systemPrompt?: string;
    prompt?: string;
  }

  /** v2026.6.8: reliable text is `assistantTexts: string[]`; `lastAssistant` is untyped. */
  export interface LlmOutputEvent {
    runId?: string;
    sessionId?: string;
    provider?: string;
    model?: string;
    prompt?: string;
    assistantTexts?: string[];
    lastAssistant?: unknown;
    usage?: Record<string, unknown>;
  }

  /**
   * Deprecated compatibility hook (removal scheduled after 2026-08-16).
   * v2026.6.8 PluginHookSubagentSpawnBase — `requester` is an object, not a string.
   */
  export interface SubagentSpawningEvent {
    childSessionKey: string;
    agentId: string;
    label?: string;
    mode: 'run' | 'session';
    requester?: {
      channel?: string;
      accountId?: string;
      to?: string;
      threadId?: string | number;
    };
    threadRequested: boolean;
  }

  export interface SubagentEndedEvent {
    targetSessionKey: string;
    targetKind: 'subagent' | 'acp';
    reason: string;
    sendFarewell?: boolean;
    accountId?: string;
    runId?: string;
    endedAt?: number;
    outcome?: 'ok' | 'error' | 'timeout' | 'killed' | 'reset' | 'deleted';
    error?: string;
  }

  export interface SessionLifecycleEvent {
    sessionId?: string;
    sessionKey?: string;
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

  export interface PluginHookContextMap {
    before_tool_call: PluginHookAgentContext;
    after_tool_call: PluginHookAgentContext;
    before_prompt_build: PluginHookAgentContext;
    message_sending: PluginHookMessageContext;
    message_received: PluginHookMessageContext;
    llm_input: PluginHookAgentContext;
    llm_output: PluginHookAgentContext;
    subagent_spawning: PluginHookSubagentContext;
    subagent_ended: PluginHookSubagentContext;
    session_start: PluginHookAgentContext;
    session_end: PluginHookAgentContext;
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
    content?: string;
    cancel?: boolean;
    cancelReason?: string;
  }

  /** v2026.6.8 discriminated union — the error variant requires `error: string`. */
  export type SubagentSpawningResult =
    | {
        status: 'ok';
        threadBindingReady?: boolean;
        deliveryOrigin?: {
          channel?: string;
          accountId?: string;
          to?: string;
          threadId?: string | number;
        };
      }
    | { status: 'error'; error: string };

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
    /** Typed overload for the hooks SafeClaw registers (precise event + context). */
    on<K extends keyof PluginHookEventMap>(
      hookName: K,
      handler: (
        event: PluginHookEventMap[K],
        ctx: PluginHookContextMap[K],
      ) => PluginHookResultMap[K] | void | Promise<PluginHookResultMap[K] | void>,
      options?: { priority?: number; timeoutMs?: number },
    ): void;
    /** Generic fallback for any other hook. */
    on(
      hookName: string,
      handler: (
        event: OpenClawPluginEvent,
        ctx: OpenClawPluginContext,
      ) => Promise<Record<string, unknown> | void> | void,
      options?: { priority?: number; timeoutMs?: number },
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
