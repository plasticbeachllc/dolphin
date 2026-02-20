import type { AgentEvent } from "../../../shared/types/events";
import type { MCPClient } from "../mcp/mcp-client";
import {
  ToolExecutorEngine,
  type ToolExecutorAdapter,
  type ToolExecutorMessage,
  type UsageStats,
} from "./tool-executor";
import type { MCPTool, ToolResult, ToolCall } from "./tool-utils";
import type { OpenAIClient } from "./openai-client";
import {
  type OpenAIResponse,
  type OpenAIInputMessage,
  type OpenAIResponseTool,
} from "./openai-client";

export type OpenAIMessageContent = Array<{ type: string; [key: string]: unknown }>;

interface OpenAIAdapterOptions {
  client: OpenAIClient;
  onEvent: (event: AgentEvent) => void;
}

class OpenAIAdapter
  implements ToolExecutorAdapter<OpenAIMessageContent, OpenAIResponseTool, OpenAIResponse>
{
  private readonly client: OpenAIClient;
  private readonly onAdapterEvent: (event: AgentEvent) => void;

  constructor(options: OpenAIAdapterOptions) {
    this.client = options.client;
    this.onAdapterEvent = options.onEvent;
  }

  mapMCPTools(tools: MCPTool[]): OpenAIResponseTool[] {
    return tools
      .filter((tool) => {
        const hasName = typeof tool.name === "string" && tool.name.trim().length > 0;
        if (!hasName) {
          console.warn("[OpenAIAdapter] Skipping MCP tool without name", tool);
        }
        return hasName;
      })
      .map((tool) => ({
        type: "function",
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.inputSchema,
        },
      }));
  }

  async callModel({
    messages,
    tools,
    signal,
  }: {
    messages: ToolExecutorMessage<OpenAIMessageContent>[];
    tools: OpenAIResponseTool[];
    signal: AbortSignal;
  }): Promise<{
    response: OpenAIResponse;
    assistantMessage: ToolExecutorMessage<OpenAIMessageContent>;
    usage: UsageStats;
    stopReason?: string;
  }> {
    const openaiMessages: OpenAIInputMessage[] = messages.map((message) => ({
      role: message.role,
      content: this.normalizeContent(message.role, message.content),
    }));

    const response = await this.client.streamResponse({
      messages: openaiMessages,
      tools: tools.length > 0 ? tools : undefined,
      signal,
      onTextChunk: (delta) => {
        if (typeof delta === "string") {
          this.onAdapterEvent({ type: "content_delta", delta });
        }
      },
    });

    const assistantMessage: ToolExecutorMessage<OpenAIMessageContent> = {
      role: "assistant",
      content: this.extractAssistantContent(response),
    };

    return {
      response,
      assistantMessage,
      usage: this.toUsage(response),
      stopReason: response.stop_reason,
    };
  }

  extractToolCalls(response: OpenAIResponse): ToolCall[] {
    return response.output
      .filter(
        (item): item is { type: "tool_call"; call_id: string; name: string; arguments: string } =>
          item.type === "tool_call"
      )
      .map((call) => ({
        id: call.call_id,
        name: call.name,
        input: this.parseArguments(call.arguments),
      }));
  }

  createToolResultMessage(results: ToolResult[]): ToolExecutorMessage<OpenAIMessageContent> {
    return {
      role: "user",
      content: results.map((result) => ({
        type: "tool_result",
        tool_call_id: result.tool_use_id,
        output: [
          {
            type: "output_text",
            text:
              typeof result.content === "string" ? result.content : JSON.stringify(result.content),
          },
        ],
        is_error: result.is_error,
      })),
    };
  }

  onEvent(event: AgentEvent): void {
    this.onAdapterEvent(event);
  }

  private extractAssistantContent(response: OpenAIResponse): OpenAIMessageContent {
    const messageBlock = response.output.find((item) => item.type === "message");
    if (messageBlock && "content" in messageBlock) {
      return (messageBlock as { content: OpenAIMessageContent }).content;
    }
    return [{ type: "output_text", text: "" }];
  }

  private toUsage(response: OpenAIResponse): UsageStats {
    return {
      inputTokens: response.usage?.input_tokens ?? 0,
      outputTokens: response.usage?.output_tokens ?? 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    };
  }

  private parseArguments(input: string): Record<string, unknown> {
    try {
      return JSON.parse(input) as Record<string, unknown>;
    } catch {
      return {};
    }
  }

  private normalizeContent(
    role: "user" | "assistant",
    content: OpenAIMessageContent
  ): OpenAIMessageContent {
    return content;
  }
}

export interface OpenAIToolExecutorConfig {
  client: OpenAIClient;
  mcpClient: MCPClient;
  maxToolRounds: number;
  onEvent: (event: AgentEvent) => void;
}

export class OpenAIToolExecutor extends ToolExecutorEngine<
  OpenAIMessageContent,
  OpenAIResponseTool,
  OpenAIResponse
> {
  constructor(config: OpenAIToolExecutorConfig) {
    super({
      adapter: new OpenAIAdapter({ client: config.client, onEvent: config.onEvent }),
      mcpClient: config.mcpClient,
      maxToolRounds: config.maxToolRounds,
    });
  }
}
