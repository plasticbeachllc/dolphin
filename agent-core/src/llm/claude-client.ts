// agent-core/src/llm/claude-client.ts
import Anthropic from "@anthropic-ai/sdk";
import { ClaudeCLIDetector } from "./claude-cli-detector";
import { executeClaudeCode } from "./claude-cli-process";

export type AuthMode = "claude_cli" | "api_key" | "auto";

export interface ClaudeConfig {
  authMode?: AuthMode;
  apiKey?: string;
  model: string;
  maxTokens: number;
  temperature?: number;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface CompletionRequest {
  messages: Message[];
  system?: string;
  maxTokens?: number;
  temperature?: number;
}

export interface CompletionResult {
  content: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens?: number;
    cache_write_tokens?: number;
  };
  stop_reason?: string;
  isPaidUsage?: boolean;
  totalCostUsd?: number;
}

/**
 * Unified Claude client supporting both CLI (subscription) and API modes
 */
export class ClaudeClient {
  private authMode: AuthMode;
  public apiClient: Anthropic | null = null; // Exposed for tool executor
  private cliDetector: ClaudeCLIDetector;
  private config: ClaudeConfig;

  constructor(config: ClaudeConfig) {
    this.config = config;
    this.authMode = config.authMode || "auto";
    this.cliDetector = new ClaudeCLIDetector();

    // Initialize API client if API key provided or in environment
    if (config.apiKey || process.env.ANTHROPIC_API_KEY) {
      this.apiClient = new Anthropic({
        apiKey: config.apiKey || process.env.ANTHROPIC_API_KEY,
      });
    }
  }

  /**
   * Detect and set the best authentication mode
   */
  async detectAuthMode(): Promise<AuthMode> {
    if (this.authMode !== "auto") {
      return this.authMode;
    }

    // Check for Claude CLI first (preferred for subscription users)
    const hasCLI = await this.cliDetector.isInstalled();

    if (hasCLI) {
      const isAuthenticated = await this.cliDetector.isAuthenticated();

      if (isAuthenticated) {
        // Check if it will use API key instead of subscription
        const willUseAPIKey = await this.cliDetector.willUseAPIKey();

        if (willUseAPIKey) {
          console.warn(
            "[ClaudeClient] ANTHROPIC_API_KEY is set. CLI will use API instead of subscription."
          );
          console.warn(
            "[ClaudeClient] To use your subscription, unset ANTHROPIC_API_KEY environment variable."
          );
        }

        this.authMode = "claude_cli";
        console.error("[ClaudeClient] Using Claude Code CLI (subscription mode)");
        return "claude_cli";
      }
    }

    // Fallback to API key
    if (this.config.apiKey || process.env.ANTHROPIC_API_KEY) {
      this.authMode = "api_key";
      console.error("[ClaudeClient] Using Anthropic API (pay-per-token mode)");

      if (!this.apiClient) {
        this.apiClient = new Anthropic({
          apiKey: this.config.apiKey || process.env.ANTHROPIC_API_KEY!,
        });
      }

      return "api_key";
    }

    throw new Error("No authentication configured. Install Claude CLI or set ANTHROPIC_API_KEY.");
  }

  /**
   * Complete a chat request (unified interface)
   */
  async complete(request: CompletionRequest): Promise<CompletionResult> {
    const mode = await this.detectAuthMode();

    if (mode === "claude_cli") {
      return await this.completeCLI(request);
    } else {
      return await this.completeAPI(request);
    }
  }

  /**
   * Complete using Claude CLI
   */
  private async completeCLI(request: CompletionRequest): Promise<CompletionResult> {
    // Convert messages to Anthropic format
    const anthropicMessages: Anthropic.Messages.MessageParam[] = request.messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    // Execute via Claude Code CLI
    const response = await executeClaudeCode({
      systemPrompt: request.system || "",
      messages: anthropicMessages,
      model: this.config.model,
      maxOutputTokens: request.maxTokens || this.config.maxTokens,
    });

    return {
      content: response.content,
      usage: {
        input_tokens: response.usage.input_tokens,
        output_tokens: response.usage.output_tokens,
        cache_read_tokens: response.usage.cache_read_tokens,
        cache_write_tokens: response.usage.cache_write_tokens,
      },
      stop_reason: response.stop_reason,
      isPaidUsage: response.isPaidUsage,
      totalCostUsd: response.totalCostUsd,
    };
  }

  /**
   * Complete using Anthropic API
   */
  private async completeAPI(request: CompletionRequest): Promise<CompletionResult> {
    if (!this.apiClient) {
      throw new Error("API client not initialized");
    }

    const response = await this.apiClient.messages.create({
      model: this.config.model,
      max_tokens: request.maxTokens || this.config.maxTokens,
      temperature: request.temperature || this.config.temperature || 1.0,
      system: request.system,
      messages: request.messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
    });

    return {
      content: response.content
        .filter((c) => c.type === "text")
        .map((c) => (c as any).text)
        .join(""),
      usage: {
        input_tokens: response.usage.input_tokens,
        output_tokens: response.usage.output_tokens,
      },
      stop_reason: response.stop_reason || undefined,
    };
  }

  /**
   * Streaming complete (API only - CLI doesn't support streaming)
   */
  async *completeStreaming(
    request: CompletionRequest,
    onChunk?: (chunk: string) => void
  ): AsyncGenerator<string, void, unknown> {
    const mode = await this.detectAuthMode();

    if (mode === "claude_cli") {
      // CLI doesn't support streaming, return full response at once
      const result = await this.completeCLI(request);
      if (onChunk) onChunk(result.content);
      yield result.content;
      return;
    }

    if (!this.apiClient) {
      throw new Error("API client not initialized");
    }

    const stream = await this.apiClient.messages.stream({
      model: this.config.model,
      max_tokens: request.maxTokens || this.config.maxTokens,
      temperature: request.temperature || this.config.temperature || 1.0,
      system: request.system,
      messages: request.messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
    });

    for await (const event of stream) {
      if (event.type === "content_block_delta") {
        if (event.delta.type === "text_delta") {
          const chunk = event.delta.text;
          if (onChunk) onChunk(chunk);
          yield chunk;
        }
      }
    }
  }

  /**
   * Get current auth status (doesn't throw errors)
   */
  async getAuthStatus(): Promise<{
    mode: AuthMode;
    cliInstalled: boolean;
    cliAuthenticated: boolean;
    apiKeySet: boolean;
    willUseSubscription: boolean;
  }> {
    const cliInstalled = await this.cliDetector.isInstalled();
    const cliAuthenticated = cliInstalled ? await this.cliDetector.isAuthenticated() : false;
    const apiKeySet = !!(this.config.apiKey || process.env.ANTHROPIC_API_KEY);
    const willUseAPIKey = cliInstalled ? await this.cliDetector.willUseAPIKey() : false;

    // Try to detect auth mode, but don't throw if none available
    let mode: AuthMode = "auto";
    try {
      mode = await this.detectAuthMode();
    } catch (error) {
      // No auth configured - return "auto" as mode
      mode = "auto";
    }

    return {
      mode,
      cliInstalled,
      cliAuthenticated,
      apiKeySet,
      willUseSubscription: cliAuthenticated && !willUseAPIKey,
    };
  }
}
