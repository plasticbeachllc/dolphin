// agent-core/src/execution/claude-provider.ts
import { existsSync, readFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";

import type { AgentEvent } from "../../../shared/types/events";
import { ClaudeClient, type AuthMode } from "../llm/claude-client";
import {
  ClaudeToolExecutor,
  type Message as ToolExecutorMessage,
} from "../llm/claude-tool-executor";
import { MCPClient } from "../mcp/mcp-client";

export interface AuthStatus {
  authenticated: boolean;
  mode: "subscription" | "api_key" | "none";
  source?: string;
  warning?: string;
  error?: string;
}

export interface AuthManagerOptions {
  settingsPath?: string;
  apiKeyEnvVar?: string;
}

/**
 * Lightweight helper for detecting Claude authentication state.
 *
 * The integration tests exercise OAuth detection via the Claude CLI as well as
 * fallback Anthropic API key usage. We intentionally keep the implementation
 * resilient: the presence of a settings file is treated as an OAuth login even
 * if the JSON cannot be parsed so corrupted files don't break the workflow.
 */
export class AuthManager {
  private readonly settingsPath: string;
  private readonly apiKeyEnvVar: string;

  constructor(options: AuthManagerOptions = {}) {
    this.apiKeyEnvVar = options.apiKeyEnvVar ?? "ANTHROPIC_API_KEY";
    this.settingsPath = options.settingsPath ?? join(homedir(), ".claude", "settings.json");
  }

  private hasOAuthToken(): boolean {
    if (!existsSync(this.settingsPath)) {
      return false;
    }

    try {
      const raw = readFileSync(this.settingsPath, "utf-8");
      if (!raw.trim()) {
        // Empty file means no token
        return false;
      }

      const data = JSON.parse(raw) as { token?: string } | undefined;
      return !!data?.token;
    } catch {
      // Corrupted or unreadable files indicate a problem, not valid auth
      return false;
    }
  }

  async detectAuthStatus(): Promise<AuthStatus> {
    const hasOAuth = this.hasOAuthToken();
    const apiKey = process.env[this.apiKeyEnvVar];

    if (hasOAuth) {
      return {
        authenticated: true,
        mode: "subscription",
        source: "Claude CLI OAuth",
        warning: apiKey
          ? `${this.apiKeyEnvVar} ignored because Claude CLI OAuth is active.`
          : undefined,
      };
    }

    if (apiKey) {
      return {
        authenticated: true,
        mode: "api_key",
        source: this.apiKeyEnvVar,
        warning: `Using ${this.apiKeyEnvVar} (pay-as-you-go). Consider running 'claude auth login' for subscription benefits.`,
      };
    }

    return {
      authenticated: false,
      mode: "none",
      error: `Claude is not authenticated. Run 'claude auth login' or set ${this.apiKeyEnvVar}.`,
    };
  }

  async ensureAuthenticated(): Promise<void> {
    const status = await this.detectAuthStatus();

    if (!status.authenticated) {
      throw new Error(status.error ?? "Claude is not authenticated.");
    }

    if (status.mode === "api_key") {
      console.warn(
        `[Claude Auth] Using ${this.apiKeyEnvVar} (pay-as-you-go). Consider running 'claude auth login' for subscription benefits.`
      );
    }
  }
}

export interface ClaudeProviderConfig {
  workspaceRoot: string;
  claudeClient?: ClaudeClient;
  mcpClient?: MCPClient;
  maxToolRounds?: number;
  authManager?: AuthManager;
  toolExecutor?: ClaudeToolExecutor;
  onEvent?: (event: AgentEvent) => void;
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
  private mcpClient: MCPClient;
  private workspaceRoot: string;
  private authManager: AuthManager;
  private maxToolRounds: number;
  private defaultOnEvent: (event: AgentEvent) => void;

  constructor(config: ClaudeProviderConfig) {
    this.workspaceRoot = config.workspaceRoot;
    this.authManager = config.authManager ?? new AuthManager();

    this.claudeClient =
      config.claudeClient ??
      new ClaudeClient({
        model: "claude-sonnet-4-20250514",
        maxTokens: 4096,
        temperature: 1.0,
      });

    this.mcpClient = config.mcpClient ?? new MCPClient();
    this.maxToolRounds = config.maxToolRounds ?? 10;
    this.defaultOnEvent =
      config.onEvent ?? ((event) => console.error(`[ClaudeProvider] Event: ${event.type}`));

    // Create tool executor with default event handler if none provided
    this.executor =
      config.toolExecutor ??
      new ClaudeToolExecutor({
        claudeClient: this.claudeClient,
        mcpClient: this.mcpClient,
        maxToolRounds: this.maxToolRounds,
        onEvent: this.defaultOnEvent,
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
        mcpClient: this.mcpClient,
        maxToolRounds: this.maxToolRounds,
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

  async detectAuthStatus(): Promise<AuthStatus> {
    return await this.authManager.detectAuthStatus();
  }

  async ensureAuthenticated(): Promise<void> {
    await this.authManager.ensureAuthenticated();
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
