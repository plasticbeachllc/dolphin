import type { AgentEvent } from "../../../shared/types/events";
import type { MCPClient } from "../mcp/mcp-client";
import {
  createErrorResult,
  createToolResult,
  type MCPTool,
  type ToolCall,
  type ToolResult,
} from "./tool-utils";
import { generateFileWriteDiff } from "./diff-generator";

export interface ToolExecutorMessage<TContent = unknown> {
  role: "user" | "assistant";
  content: TContent;
}

export interface UsageStats {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
}

export interface ExecutionResult<TContent = unknown> {
  messages: ToolExecutorMessage<TContent>[];
  stopReason?: string;
  toolRounds: number;
  usage: UsageStats;
}

export interface ToolExecutorAdapter<TContent, TTool, TResponse> {
  mapMCPTools(tools: MCPTool[]): TTool[];
  callModel(options: {
    messages: ToolExecutorMessage<TContent>[];
    tools: TTool[];
    signal: AbortSignal;
  }): Promise<{
    response: TResponse;
    assistantMessage: ToolExecutorMessage<TContent>;
    usage: UsageStats;
    stopReason?: string;
  }>;
  extractToolCalls(response: TResponse): ToolCall[];
  createToolResultMessage(results: ToolResult[]): ToolExecutorMessage<TContent>;
  onEvent(event: AgentEvent): void;
}

export interface ToolExecutorConfig<TContent, TTool, TResponse> {
  adapter: ToolExecutorAdapter<TContent, TTool, TResponse>;
  mcpClient: MCPClient;
  maxToolRounds: number;
}

export class ToolExecutorEngine<TContent, TTool, TResponse> {
  private readonly adapter: ToolExecutorAdapter<TContent, TTool, TResponse>;
  private readonly mcpClient: MCPClient;
  private readonly maxToolRounds: number;
  private availableTools: TTool[] = [];
  private totalUsage: UsageStats = {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
  };
  private abortController: AbortController | null = null;
  private isAborted = false;

  constructor(config: ToolExecutorConfig<TContent, TTool, TResponse>) {
    this.adapter = config.adapter;
    this.mcpClient = config.mcpClient;
    this.maxToolRounds = config.maxToolRounds;
  }

  async initialize(): Promise<void> {
    const mcpTools = await this.mcpClient.listTools();
    this.availableTools = this.adapter.mapMCPTools(mcpTools);
  }

  abort(): void {
    this.isAborted = true;
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  async executeWithTools(
    userMessage: ToolExecutorMessage<TContent>,
    conversationHistory: ToolExecutorMessage<TContent>[] = []
  ): Promise<ExecutionResult<TContent>> {
    this.isAborted = false;
    this.abortController = new AbortController();

    const messages: ToolExecutorMessage<TContent>[] = [...conversationHistory, userMessage];
    let toolRound = 0;
    let stopReason: string | undefined;
    const usageTotals: UsageStats = {
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    };

    while (toolRound < this.maxToolRounds) {
      if (this.isAborted) {
        throw new Error("Generation aborted by user");
      }

      const {
        response,
        assistantMessage,
        usage,
        stopReason: callStopReason,
      } = await this.adapter.callModel({
        messages,
        tools: this.availableTools,
        signal: this.abortController.signal,
      });

      messages.push(assistantMessage);

      usageTotals.inputTokens += usage.inputTokens;
      usageTotals.outputTokens += usage.outputTokens;
      usageTotals.cacheReadTokens += usage.cacheReadTokens;
      usageTotals.cacheWriteTokens += usage.cacheWriteTokens;
      stopReason = callStopReason;

      const toolCalls = this.adapter.extractToolCalls(response);
      if (toolCalls.length === 0) {
        break;
      }

      const toolResults = await this.executeToolCalls(toolCalls);

      if (this.isAborted) {
        throw new Error("Generation aborted by user");
      }

      const toolResultMessage = this.adapter.createToolResultMessage(toolResults);
      messages.push(toolResultMessage);

      toolRound++;
    }

    if (toolRound >= this.maxToolRounds) {
      console.warn("[ToolExecutor] WARNING: Max tool rounds reached");
    }

    this.abortController = null;

    this.totalUsage.inputTokens += usageTotals.inputTokens;
    this.totalUsage.outputTokens += usageTotals.outputTokens;
    this.totalUsage.cacheReadTokens += usageTotals.cacheReadTokens;
    this.totalUsage.cacheWriteTokens += usageTotals.cacheWriteTokens;

    return {
      messages,
      stopReason,
      toolRounds: toolRound,
      usage: usageTotals,
    };
  }

  getUsage(): UsageStats {
    return { ...this.totalUsage };
  }

  private async executeToolCalls(toolCalls: ToolCall[]): Promise<ToolResult[]> {
    const results = await Promise.all(
      toolCalls.map(async (toolCall) => {
        const startTime = Date.now();
        this.adapter.onEvent({
          type: "tool_call_started",
          toolId: toolCall.id,
          tool: toolCall.name,
          input: toolCall.input,
        });

        try {
          const toolName = toolCall.name.replace(/^mcp__[^_]+__/, "");
          const processedInput = this.preprocessToolInput(toolCall.input);
          const mcpResult = await this.mcpClient.callTool(toolName, processedInput);
          const executionTime = Date.now() - startTime;

          let diff: string | undefined;
          if (toolName === "file_write" && mcpResult && !mcpResult.isError) {
            try {
              const content = mcpResult.content as Array<{ text?: string }> | undefined;
              const resultText = content && content[0] ? content[0].text : undefined;
              if (resultText) {
                const parsedResult = JSON.parse(resultText) as Record<string, unknown>;
                const generatedDiff = await generateFileWriteDiff(
                  processedInput,
                  parsedResult,
                  process.cwd()
                );
                diff = generatedDiff ?? undefined;
              }
            } catch (error) {
              console.warn("[ToolExecutor] Failed to generate diff:", error);
            }
          }

          if (mcpResult.isError) {
            const content = mcpResult.content as Array<{ text?: string }> | undefined;
            const errorMessage =
              (content && content[0] ? content[0].text : undefined) || "Tool execution failed";

            this.adapter.onEvent({
              type: "tool_call_completed",
              toolId: toolCall.id,
              result: null,
              error: errorMessage,
              executionTime,
            });

            return createErrorResult(toolCall.id, new Error(errorMessage));
          }

          this.adapter.onEvent({
            type: "tool_call_completed",
            toolId: toolCall.id,
            result: mcpResult,
            executionTime,
            diff,
          });

          return createToolResult(toolCall.id, mcpResult, false);
        } catch (error) {
          const executionTime = Date.now() - startTime;
          const message = error instanceof Error ? error.message : String(error);

          this.adapter.onEvent({
            type: "tool_call_completed",
            toolId: toolCall.id,
            result: null,
            error: message,
            executionTime,
          });

          return createErrorResult(
            toolCall.id,
            error instanceof Error ? error : new Error(String(error))
          );
        }
      })
    );

    return results;
  }

  private preprocessToolInput(input: Record<string, unknown>): Record<string, unknown> {
    const processed: Record<string, unknown> = {};

    for (const [key, value] of Object.entries(input)) {
      if (typeof value === "string" && (value.startsWith("[") || value.startsWith("{"))) {
        try {
          processed[key] = JSON.parse(value);
        } catch {
          processed[key] = value;
        }
      } else {
        processed[key] = value;
      }
    }

    return processed;
  }
}
