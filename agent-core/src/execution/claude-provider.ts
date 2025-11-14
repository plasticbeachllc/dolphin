// agent-core/src/execution/claude-provider.ts
import type { AgentEvent } from "../../../shared/types/events";
import { ClaudeClient, type AuthMode } from "../llm/claude-client";
import {
  ClaudeToolExecutor,
  type Message as ToolExecutorMessage,
} from "../llm/claude-tool-executor";
import { MCPClient } from "../mcp/mcp-client";

export interface ClaudeProviderConfig {
  claudeClient: ClaudeClient;
  mcpClient: MCPClient;
  maxToolRounds?: number;
  workspaceRoot: string;
}

export interface ExecuteParams {
  message: string;
  conversationHistory?: ToolExecutorMessage[];
  onEvent?: (event: AgentEvent) => void;
}

export interface ExecuteResult {
  messages: ToolExecutorMessage[];
  stopReason: string | undefined;
  toolRounds: number;
  usage: {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheWriteTokens: number;
  };
}

/**
 * ClaudeProvider - Simplified wrapper around ClaudeToolExecutor
 *
 * Provides a clean interface for workflows to execute Claude with tool support.
 * Delegates actual execution to ClaudeToolExecutor.
 */
export class ClaudeProvider {
  private executor: ClaudeToolExecutor;
  private claudeClient: ClaudeClient;
  private workspaceRoot: string;

  constructor(config: ClaudeProviderConfig) {
    this.claudeClient = config.claudeClient;
    this.workspaceRoot = config.workspaceRoot;

    // Create tool executor with default event handler if none provided
    this.executor = new ClaudeToolExecutor({
      claudeClient: config.claudeClient,
      mcpClient: config.mcpClient,
      maxToolRounds: config.maxToolRounds || 10,
      onEvent: (event) => {
        // Default: log events
        console.error(`[ClaudeProvider] Event: ${event.type}`);
      },
    });
  }

  /**
   * Execute a message with Claude and tool support
   */
  async execute(params: ExecuteParams): Promise<ExecuteResult> {
    // If custom event handler provided, create new executor instance
    let executor = this.executor;

    if (params.onEvent) {
      executor = new ClaudeToolExecutor({
        claudeClient: this.claudeClient,
        mcpClient: this.executor["config"].mcpClient,
        maxToolRounds: this.executor["config"].maxToolRounds,
        onEvent: params.onEvent,
      });

      // Initialize tools
      await executor.initialize();
    }

    // Execute with tool support
    const result = await executor.executeWithTools(
      params.message,
      params.conversationHistory || []
    );

    return result;
  }

  /**
   * Initialize tool executor (must be called before first execute)
   */
  async initialize(): Promise<void> {
    await this.executor.initialize();
  }

  /**
   * Abort current execution
   */
  abort(): void {
    this.executor.abort();
  }

  /**
   * Get authentication status
   */
  async getAuthStatus(): Promise<{
    mode: AuthMode;
    cliInstalled: boolean;
    cliAuthenticated: boolean;
    apiKeySet: boolean;
    willUseSubscription: boolean;
  }> {
    return await this.claudeClient.getAuthStatus();
  }

  /**
   * Get usage statistics
   */
  getUsage(): {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheWriteTokens: number;
  } {
    return this.executor.getUsage();
  }
}
