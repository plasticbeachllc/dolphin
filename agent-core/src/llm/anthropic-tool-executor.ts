import type Anthropic from "@anthropic-ai/sdk";
import type { AgentEvent } from "../../../shared/types/events";
import type { MCPClient } from "../mcp/mcp-client";
import {
  ToolExecutorEngine,
  type ToolExecutorMessage,
  type ToolExecutorAdapter,
  type UsageStats,
} from "./tool-executor";
import type { ClaudeClient } from "./claude-client";
import {
  mapMCPToAnthropic,
  extractToolCalls,
  type AnthropicTool,
  type MCPTool,
  type ToolResult,
} from "./tool-utils";

export type AnthropicMessageContent = string | Anthropic.ContentBlock[];

interface AnthropicAdapterOptions {
  claudeClient: ClaudeClient;
  onEvent: (event: AgentEvent) => void;
}

class AnthropicAdapter
  implements ToolExecutorAdapter<AnthropicMessageContent, AnthropicTool, Anthropic.Message>
{
  private readonly claudeClient: ClaudeClient;
  private readonly onAdapterEvent: (event: AgentEvent) => void;

  constructor(options: AnthropicAdapterOptions) {
    this.claudeClient = options.claudeClient;
    this.onAdapterEvent = options.onEvent;
  }

  mapMCPTools(tools: MCPTool[]): AnthropicTool[] {
    return mapMCPToAnthropic(tools);
  }

  async callModel({
    messages,
    tools,
    signal,
  }: {
    messages: ToolExecutorMessage<AnthropicMessageContent>[];
    tools: AnthropicTool[];
    signal: AbortSignal;
  }): Promise<{
    response: Anthropic.Message;
    assistantMessage: ToolExecutorMessage<AnthropicMessageContent>;
    usage: UsageStats;
    stopReason?: string;
  }> {
    const authStatus = await this.claudeClient.getAuthStatus();
    if (authStatus.mode === "api_key") {
      if (!this.claudeClient.apiClient) {
        throw new Error("API client not initialized");
      }
      const response = await this.callAnthropicAPI(messages, tools, signal);
      return {
        response,
        assistantMessage: { role: "assistant", content: response.content },
        usage: this.toUsage(response.usage),
        stopReason: response.stop_reason || undefined,
      };
    }

    const response = await this.callClaudeCLI(messages, tools);
    return {
      response,
      assistantMessage: { role: "assistant", content: response.content },
      usage: this.toUsage(response.usage),
      stopReason: response.stop_reason || undefined,
    };
  }

  extractToolCalls(response: Anthropic.Message) {
    return extractToolCalls(response.content);
  }

  createToolResultMessage(results: ToolResult[]): ToolExecutorMessage<AnthropicMessageContent> {
    return {
      role: "user",
      content: results as unknown as Anthropic.ContentBlock[],
    };
  }

  onEvent(event: AgentEvent): void {
    this.onAdapterEvent(event);
  }

  private toUsage(usage: Anthropic.Message["usage"]): UsageStats {
    const extendedUsage = usage as Anthropic.Message["usage"] & {
      cache_read_input_tokens?: number;
      cache_creation_input_tokens?: number;
    };
    return {
      inputTokens: usage.input_tokens,
      outputTokens: usage.output_tokens,
      cacheReadTokens: extendedUsage.cache_read_input_tokens || 0,
      cacheWriteTokens: extendedUsage.cache_creation_input_tokens || 0,
    };
  }

  private async callAnthropicAPI(
    messages: ToolExecutorMessage<AnthropicMessageContent>[],
    tools: AnthropicTool[],
    signal: AbortSignal
  ): Promise<Anthropic.Message> {
    const apiClient = this.claudeClient.apiClient;
    if (!apiClient) {
      throw new Error("API client not initialized");
    }

    const stream = apiClient.messages.stream(
      {
        model: "claude-sonnet-4-20250514",
        max_tokens: 4096,
        tools,
        messages: messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
      },
      { signal }
    );

    const fullContent: Anthropic.ContentBlock[] = [];
    let currentTextBlock = "";
    let currentToolUse:
      | {
          type: "tool_use";
          id: string;
          name: string;
          inputJson: string;
          input?: Record<string, unknown>;
        }
      | null = null;

    for await (const event of stream) {
      switch (event.type) {
        case "content_block_start":
          if (event.content_block.type === "text") {
            currentTextBlock = "";
          } else if (event.content_block.type === "tool_use") {
            currentToolUse = {
              type: "tool_use",
              id: event.content_block.id,
              name: event.content_block.name,
              inputJson: "",
            };
          }
          break;
        case "content_block_delta":
          if (event.delta.type === "text_delta") {
            currentTextBlock += event.delta.text;
            this.onAdapterEvent({ type: "content_delta", delta: event.delta.text });
          } else if (event.delta.type === "input_json_delta") {
            if (currentToolUse) {
              currentToolUse.inputJson += event.delta.partial_json;
            }
          }
          break;
        case "content_block_stop":
          if (currentTextBlock !== "") {
            fullContent.push({ type: "text", text: currentTextBlock } as Anthropic.TextBlock);
            currentTextBlock = "";
          } else if (currentToolUse) {
            try {
              currentToolUse.input = JSON.parse(currentToolUse.inputJson) as Record<string, unknown>;
            } catch {
              currentToolUse.input = {};
            }
            delete currentToolUse.inputJson;
            fullContent.push(currentToolUse as Anthropic.ToolUseBlock);
            this.onAdapterEvent({
              type: "tool_call_started",
              toolId: currentToolUse.id,
              tool: currentToolUse.name,
              input: currentToolUse.input,
            });
            currentToolUse = null;
          }
          break;
      }
    }

    const finalMessage = await stream.finalMessage();
    return {
      ...finalMessage,
      content: fullContent,
    };
  }

  private async callClaudeCLI(
    messages: ToolExecutorMessage<AnthropicMessageContent>[],
    tools: AnthropicTool[]
  ): Promise<Anthropic.Message> {
    const { runClaudeCode } = await import("./claude-cli-process");
    const systemPrompt = `You have access to the following tools via MCP:\n\n${tools
      .map((tool) => `- ${tool.name}: ${tool.description}\n  Input: ${JSON.stringify(tool.input_schema)}`)
      .join("\n\n")}`;

    const anthropicMessages = messages.map(
      (message) =>
        ({
          role: message.role,
          content: message.content,
        }) as Anthropic.Messages.MessageParam
    );

    const fullContent: Anthropic.ContentBlock[] = [];
    let usage = {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    };
    let stopReason: string | undefined;

    for await (const chunk of runClaudeCode({
      systemPrompt,
      messages: anthropicMessages,
      model: "claude-sonnet-4-20250514",
      maxOutputTokens: 4096,
    })) {
      if (typeof chunk === "string") {
        continue;
      }

      if (chunk.type === "assistant" && "message" in chunk) {
        const message = chunk.message;
        for (const block of message.content) {
          if (block.type === "text") {
            this.onAdapterEvent({ type: "content_delta", delta: block.text });
            fullContent.push(block);
          } else if (block.type === "tool_use") {
            fullContent.push(block as Anthropic.ToolUseBlock);
            this.onAdapterEvent({
              type: "tool_call_started",
              toolId: block.id,
              tool: block.name,
              input: block.input,
            });
          }
        }

        usage.input_tokens += message.usage.input_tokens;
        usage.output_tokens += message.usage.output_tokens;
        usage.cache_read_input_tokens += message.usage.cache_read_input_tokens || 0;
        usage.cache_creation_input_tokens += message.usage.cache_creation_input_tokens || 0;
        stopReason = message.stop_reason || undefined;
      }
    }

    return {
      id: "cli-" + Date.now(),
      type: "message",
      role: "assistant",
      content: fullContent,
      model: "claude-sonnet-4-20250514",
      stop_reason: stopReason,
      stop_sequence: null,
      usage,
    } as Anthropic.Message;
  }
}

export interface AnthropicToolExecutorConfig {
  claudeClient: ClaudeClient;
  mcpClient: MCPClient;
  maxToolRounds: number;
  onEvent: (event: AgentEvent) => void;
}

export class AnthropicToolExecutor extends ToolExecutorEngine<
  AnthropicMessageContent,
  AnthropicTool,
  Anthropic.Message
> {
  constructor(config: AnthropicToolExecutorConfig) {
    super({
      adapter: new AnthropicAdapter({ claudeClient: config.claudeClient, onEvent: config.onEvent }),
      mcpClient: config.mcpClient,
      maxToolRounds: config.maxToolRounds,
    });
  }
}
