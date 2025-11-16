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
}

export class OpenAIProvider implements ChatProvider {
  private readonly mcpClient: MCPClient;
  private readonly openAIClient: OpenAIClient;
  private readonly maxToolRounds: number;
  private readonly defaultOnEvent: (event: AgentEvent) => void;
  private readonly model: string;
  private executor: OpenAIToolExecutor;

  constructor(config: OpenAIProviderConfig) {
    this.mcpClient = config.mcpClient ?? new MCPClient();
    this.model = config.model ?? "gpt-4.1-mini";
    this.defaultOnEvent = config.onEvent ?? ((event) => console.error(`[OpenAIProvider] Event: ${event.type}`));

    this.openAIClient =
      config.openAIClient ??
      new OpenAIClient({
        model: this.model,
        temperature: config.temperature,
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
    if (process.env.OPENAI_API_KEY) {
      return { authenticated: true, mode: "api_key", source: "OPENAI_API_KEY" };
    }

    return {
      authenticated: false,
      mode: "none",
      error: "OpenAI is not authenticated. Set OPENAI_API_KEY.",
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
    return { provider: "openai", model: this.model };
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
}
