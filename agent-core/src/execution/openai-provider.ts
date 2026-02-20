import type { AgentEvent } from "../../../shared/types/events";
import type { ToolExecutorMessage } from "../llm/tool-executor";
import { OpenAIClient } from "../llm/openai-client";
import { OpenAIToolExecutor, type OpenAIMessageContent } from "../llm/openai-tool-executor";
import { MCPClient } from "../mcp/mcp-client";
import type { ChatProvider, AuthStatus, ExecuteParams, ExecuteResult } from "./chat-provider";

export interface OpenAIProviderConfig {
  workspaceRoot: string;
  mcpClient?: MCPClient;
  openAIClient?: OpenAIClient;
  maxToolRounds?: number;
  toolExecutor?: OpenAIToolExecutor;
  onEvent?: (event: AgentEvent) => void;
  model?: string;
  temperature?: number;
  baseUrl?: string;
  apiKey?: string;
}

export class OpenAIProvider implements ChatProvider {
  private readonly mcpClient: MCPClient;
  private readonly openAIClient: OpenAIClient;
  private readonly maxToolRounds: number;
  private readonly defaultOnEvent: (event: AgentEvent) => void;
  private readonly model: string;
  private readonly apiKey?: string;
  private readonly apiKeySource?: string;
  private readonly baseUrl?: string;
  private readonly baseUrlSource?: string;
  private executor: OpenAIToolExecutor;

  constructor(config: OpenAIProviderConfig) {
    this.mcpClient = config.mcpClient ?? new MCPClient();
    this.model = config.model ?? "gpt-5.1-codex";
    this.defaultOnEvent =
      config.onEvent ?? ((event) => console.error(`[OpenAIProvider] Event: ${event.type}`));
    this.apiKey = this.resolveApiKey(config.apiKey);
    this.apiKeySource = this.resolveApiKeySource(config.apiKey);
    this.baseUrl = this.resolveBaseUrl(config.baseUrl);
    this.baseUrlSource = this.resolveBaseUrlSource(config.baseUrl);

    this.openAIClient =
      config.openAIClient ??
      new OpenAIClient({
        model: this.model,
        temperature: config.temperature,
        apiKey: this.apiKey,
        baseUrl: this.baseUrl,
      });

    this.maxToolRounds = config.maxToolRounds ?? 10;
    this.executor =
      config.toolExecutor ??
      new OpenAIToolExecutor({
        client: this.openAIClient,
        mcpClient: this.mcpClient,
        maxToolRounds: this.maxToolRounds,
        onEvent: this.defaultOnEvent,
      });
  }

  async execute(params: ExecuteParams): Promise<ExecuteResult> {
    let executor = this.executor;

    if (params.onEvent) {
      executor = new OpenAIToolExecutor({
        client: this.openAIClient,
        mcpClient: this.mcpClient,
        maxToolRounds: this.maxToolRounds,
        onEvent: params.onEvent,
      });
      await executor.initialize();
    }

    const history = this.mapHistory(params.conversationHistory);
    const userMessage: ToolExecutorMessage<OpenAIMessageContent> = {
      role: "user",
      content: [{ type: "text", text: params.message }],
    };

    return await executor.executeWithTools(userMessage, history);
  }

  async initialize(): Promise<void> {
    await this.executor.initialize();
  }

  abort(): void {
    this.executor.abort();
  }

  async detectAuthStatus(): Promise<AuthStatus> {
    if (this.apiKey) {
      return {
        authenticated: true,
        mode: "api_key",
        source: this.apiKeySource ?? "OPENAI_API_KEY",
        warning: this.baseUrl
          ? `Routing through custom OpenAI-compatible endpoint (${this.baseUrlSource ?? this.baseUrl}).`
          : undefined,
      };
    }

    return {
      authenticated: false,
      mode: "none",
      error: "OpenAI is not authenticated. Set OPENAI_API_KEY or provide provider.openai.api_key.",
    };
  }

  async ensureAuthenticated(): Promise<void> {
    const status = await this.detectAuthStatus();
    if (!status.authenticated) {
      throw new Error(status.error ?? "OpenAI is not authenticated");
    }
  }

  getUsage() {
    return this.executor.getUsage();
  }

  getProviderMetadata() {
    return { provider: "openai", model: this.model, baseUrl: this.baseUrl };
  }

  private mapHistory(
    history?: Array<{ role: "user" | "assistant"; content: string }>
  ): ToolExecutorMessage<OpenAIMessageContent>[] {
    if (!history) {
      return [];
    }

    return history.map((message) => ({
      role: message.role,
      content: [{ type: "text", text: message.content }],
    }));
  }

  private resolveApiKey(provided?: string): string | undefined {
    if (provided) {
      return provided;
    }
    if (process.env.DOLPHIN_OPENAI_API_KEY) {
      return process.env.DOLPHIN_OPENAI_API_KEY;
    }
    if (process.env.OPENAI_API_KEY) {
      return process.env.OPENAI_API_KEY;
    }
    return undefined;
  }

  private resolveApiKeySource(provided?: string): string | undefined {
    if (provided) {
      return "provider.openai.api_key";
    }
    if (process.env.DOLPHIN_OPENAI_API_KEY) {
      return "DOLPHIN_OPENAI_API_KEY";
    }
    if (process.env.OPENAI_API_KEY) {
      return "OPENAI_API_KEY";
    }
    return undefined;
  }

  private resolveBaseUrl(provided?: string): string | undefined {
    if (provided) {
      return provided;
    }
    if (process.env.DOLPHIN_OPENAI_BASE_URL) {
      return process.env.DOLPHIN_OPENAI_BASE_URL;
    }
    if (process.env.OPENAI_BASE_URL) {
      return process.env.OPENAI_BASE_URL;
    }
    return undefined;
  }

  private resolveBaseUrlSource(provided?: string): string | undefined {
    if (provided) {
      return "provider.openai.base_url";
    }
    if (process.env.DOLPHIN_OPENAI_BASE_URL) {
      return "DOLPHIN_OPENAI_BASE_URL";
    }
    if (process.env.OPENAI_BASE_URL) {
      return "OPENAI_BASE_URL";
    }
    return undefined;
  }
}
