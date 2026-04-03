/**
 * Ambient type declarations for OpenClaw Plugin SDK.
 * These match the types exported by openclaw/plugin-sdk as of v2026.4.
 * When installed inside OpenClaw, the real SDK types take precedence.
 */

declare module 'openclaw/plugin-sdk/core' {
  export interface OpenClawPluginApi {
    /**
     * Register a hook handler for OpenClaw lifecycle events.
     *
     * @deprecated The `before_agent_start` hook is deprecated in v2026.4.
     * Use `before_model_resolve` + `before_prompt_build` instead.
     */
    on(
      hookName: string,
      handler: (event: OpenClawPluginEvent, ctx: OpenClawPluginContext) => Promise<Record<string, unknown> | void> | void,
      options?: { priority?: number },
    ): void;
    registerService?(service: OpenClawPluginService): void;
    registerCli?(registrar: (ctx: { program: unknown; config: unknown }) => void, opts?: { commands: string[] }): void;
    registerTool?(tool: OpenClawPluginTool): void;
    registerCommand?(def: { name: string; description: string; execute: (ctx: unknown) => Promise<string | void> }): void;
    pluginConfig?: Record<string, unknown>;
    logger?: OpenClawPluginLogger;
  }

  export interface OpenClawPluginEvent {
    sessionId?: string;
    toolName?: string;
    params?: Record<string, unknown>;
    to?: string;
    content?: string;
    result?: unknown;
    error?: string;
    durationMs?: number;
    prompt?: string;
    provider?: string;
    model?: string;
    lastAssistant?: string;
    usage?: Record<string, unknown>;
    runId?: string;
    toolCallId?: string;
    childAgentId?: string;
    parentAgentId?: string;
    childConfig?: Record<string, unknown>;
    reason?: string;
    metadata?: Record<string, unknown>;
    channel?: string;
    sender?: string;
    [key: string]: unknown;
  }

  export interface OpenClawPluginContext {
    sessionId?: string;
    agentId?: string;
    runId?: string;
    conversationId?: string;
    accountId?: string;
    channelId?: string;
    workspaceDir?: string;
    [key: string]: unknown;
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

  export interface PluginApprovalRequest {
    title: string;
    description: string;
    severity?: 'info' | 'warning' | 'critical';
    timeoutMs?: number;
    timeoutBehavior?: 'allow' | 'deny';
    pluginId?: string;
    onResolution?: (decision: PluginApprovalResolution) => Promise<void> | void;
  }

  export interface PluginApprovalResolution {
    approved: boolean;
    resolvedBy?: string;
    resolvedAt?: string;
  }

  /**
   * Hook result types for before_tool_call.
   * Return one of: nothing (allow), { block, blockReason }, or { requireApproval }.
   */
  export interface BeforeToolCallResult {
    block?: boolean;
    blockReason?: string;
    requireApproval?: PluginApprovalRequest;
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
