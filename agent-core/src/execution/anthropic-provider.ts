import { existsSync, readFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";

import type { AgentEvent } from "../../../shared/types/events";
import type { ToolExecutorMessage } from "../llm/tool-executor";
import { AnthropicToolExecutor, type AnthropicMessageContent } from "../llm/anthropic-tool-executor";
import { ClaudeClient, type AuthMode } from "../llm/claude-client";
import { MCPClient } from "../mcp/mcp-client";
import type { ChatProvider, AuthStatus, ExecuteParams, ExecuteResult } from "./chat-provider";

export interface AuthManagerOptions {
  settingsPath?: string;
  apiKeyEnvVar?: string;
}

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
        return false;
      }
      const data = JSON.parse(raw) as { token?: string } | undefined;
      return !!data?.token;
    } catch {
      return false;
    }
  }

  async detectAuthStatus(): Promise<AuthStatus> {
    const hasOAuth = this.hasOAuthToken();
    const apiKey = process.env[this.apiKeyEnvVar];

    if (hasOAuth && apiKey) {
      return {
        authenticated: true,
        mode: "api_key",
        source: this.apiKeyEnvVar,
        warning: `${this.apiKeyEnvVar} is set. Claude CLI will use API key billing (pay-per-token) instead of your subscription. To use subscription: unset ${this.apiKeyEnvVar}.`,
      };
    }

    if (hasOAuth) {
      return {
        authenticated: true,
        mode: "subscription",
        source: "Claude CLI OAuth",
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

export interface AnthropicProviderConfig {
  workspaceRoot: string;
  claudeClient?: ClaudeClient;
  mcpClient?: MCPClient;
  maxToolRounds?: number;
  authManager?: AuthManager;
  toolExecutor?: AnthropicToolExecutor;
  onEvent?: (event: AgentEvent) => void;
  model?: string;
  temperature?: number;
}

export class AnthropicProvider implements ChatProvider {
  private executor: AnthropicToolExecutor;
  private claudeClient: ClaudeClient;
  private mcpClient: MCPClient;
  private workspaceRoot: string;
  private authManager: AuthManager;
  private maxToolRounds: number;
  private defaultOnEvent: (event: AgentEvent) => void;
  private readonly model: string;

  constructor(config: AnthropicProviderConfig) {
    this.workspaceRoot = config.workspaceRoot;
    this.authManager = config.authManager ?? new AuthManager();
    this.model = config.model ?? "claude-sonnet-4-20250514";

    this.claudeClient =
      config.claudeClient ??
      new ClaudeClient({
        model: this.model,
        maxTokens: 4096,
        temperature: config.temperature ?? 1.0,
      });

    this.mcpClient = config.mcpClient ?? new MCPClient();
    this.maxToolRounds = config.maxToolRounds ?? 10;
    this.defaultOnEvent =
      config.onEvent ?? ((event) => console.error(`[AnthropicProvider] Event: ${event.type}`));

    this.executor =
      config.toolExecutor ??
      new AnthropicToolExecutor({
        claudeClient: this.claudeClient,
        mcpClient: this.mcpClient,
        maxToolRounds: this.maxToolRounds,
        onEvent: this.defaultOnEvent,
      });
  }

  async execute(params: ExecuteParams): Promise<ExecuteResult> {
    let executor = this.executor;

    if (params.onEvent) {
      executor = new AnthropicToolExecutor({
        claudeClient: this.claudeClient,
        mcpClient: this.mcpClient,
        maxToolRounds: this.maxToolRounds,
        onEvent: params.onEvent,
      });
      await executor.initialize();
    }

    const history = this.mapHistory(params.conversationHistory);
    const userMessage: ToolExecutorMessage<AnthropicMessageContent> = {
      role: "user",
      content: params.message,
    };

    const result = await executor.executeWithTools(userMessage, history);
    return result;
  }

  async initialize(): Promise<void> {
    await this.executor.initialize();
  }

  abort(): void {
    this.executor.abort();
  }

  async detectAuthStatus(): Promise<AuthStatus> {
    return await this.authManager.detectAuthStatus();
  }

  async ensureAuthenticated(): Promise<void> {
    await this.authManager.ensureAuthenticated();
  }

  async getAuthStatus(): Promise<{
    mode: AuthMode;
    cliInstalled: boolean;
    cliAuthenticated: boolean;
    apiKeySet: boolean;
    willUseSubscription: boolean;
  }> {
    return await this.claudeClient.getAuthStatus();
  }

  getUsage() {
    return this.executor.getUsage();
  }

  getProviderMetadata() {
    return { provider: "anthropic", model: this.model };
  }

  private mapHistory(
    history?: Array<{ role: "user" | "assistant"; content: string }>
  ): ToolExecutorMessage<AnthropicMessageContent>[] {
    if (!history) {
      return [];
    }

    return history.map((message) => ({
      role: message.role,
      content: message.content,
    }));
  }
}
