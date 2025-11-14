// agent-core/src/llm/claude-tool-executor.ts
import type Anthropic from "@anthropic-ai/sdk";
import type { ClaudeClient } from "./claude-client";
import type { MCPClient } from "../mcp/mcp-client";
import type { AgentEvent } from "../../../shared/types/events";
import {
  mapMCPToAnthropic,
  extractToolCalls,
  createToolResult,
  createErrorResult,
  type AnthropicTool,
  type ToolCall,
  type ToolResult,
} from "./tool-utils";
import { generateFileWriteDiff } from "./diff-generator";

export interface ToolExecutorConfig {
  claudeClient: ClaudeClient;
  mcpClient: MCPClient;
  maxToolRounds: number; // Default: 10
  onEvent: (event: AgentEvent) => void;
}

export interface Message {
  role: "user" | "assistant";
  content: string | Anthropic.ContentBlock[];
}

export interface ExecutionResult {
  messages: Message[];
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
 * Orchestrates Claude API calls with MCP tool execution
 * Implements agentic tool calling loop
 */
export class ClaudeToolExecutor {
  private config: ToolExecutorConfig;
  private availableTools: AnthropicTool[] = [];
  private totalUsage = {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
  };
  private abortController: AbortController | null = null;
  private isAborted = false;

  constructor(config: ToolExecutorConfig) {
    this.config = config;
  }

  /**
   * Abort current generation
   */
  abort() {
    console.error("[ToolExecutor] Abort requested");
    this.isAborted = true;

    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  /**
   * Initialize: Load MCP tools and convert to Anthropic format
   */
  async initialize(): Promise<void> {
    console.error("[ToolExecutor] Initializing...");

    // Fetch available tools from MCP
    const mcpTools = await this.config.mcpClient.listTools();
    console.error(`[ToolExecutor] Received ${mcpTools.length} tools from MCP`);

    // Convert to Anthropic format (just property rename)
    this.availableTools = mapMCPToAnthropic(mcpTools);

    console.error("[ToolExecutor] Available tools:");
    this.availableTools.forEach((tool) => {
      console.error(`  - ${tool.name}: ${tool.description}`);
    });

    console.error("[ToolExecutor] Ready");
  }

  /**
   * Execute a user message with tool support
   * Main agentic loop: Claude → tool_use → execute → repeat
   */
  async executeWithTools(
    userMessage: string,
    conversationHistory: Message[] = []
  ): Promise<ExecutionResult> {
    // Reset abort state
    this.isAborted = false;
    this.abortController = new AbortController();

    const messages: Message[] = [...conversationHistory, { role: "user", content: userMessage }];

    let toolRound = 0;
    let stopReason: string | undefined;
    const totalUsage = {
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    };

    while (toolRound < this.config.maxToolRounds) {
      // Check if aborted
      if (this.isAborted) {
        console.error("[ToolExecutor] Generation aborted by user");
        throw new Error("Generation aborted by user");
      }

      console.error(`[ToolExecutor] Round ${toolRound + 1}`);

      // Call Claude with tools
      const response = await this.callClaudeWithTools(messages);

      // Check if aborted during call
      if (this.isAborted) {
        console.error("[ToolExecutor] Generation aborted during API call");
        throw new Error("Generation aborted by user");
      }

      // Accumulate usage
      totalUsage.inputTokens += response.usage.input_tokens;
      totalUsage.outputTokens += response.usage.output_tokens;
      const extendedUsage = response.usage as Anthropic.Messages.Message["usage"] & {
        cache_read_input_tokens?: number;
        cache_creation_input_tokens?: number;
      };
      if (extendedUsage.cache_read_input_tokens) {
        totalUsage.cacheReadTokens += extendedUsage.cache_read_input_tokens;
      }
      if (extendedUsage.cache_creation_input_tokens) {
        totalUsage.cacheWriteTokens += extendedUsage.cache_creation_input_tokens;
      }

      stopReason = response.stop_reason || undefined;

      // Extract tool calls from response
      const toolCalls = extractToolCalls(response.content);

      // Add Claude's response to conversation (before checking for no tools)
      // This ensures we preserve the final assistant message even when no tools are called
      messages.push({
        role: "assistant",
        content: response.content,
      });

      if (toolCalls.length === 0) {
        console.error("[ToolExecutor] No tools called, ending loop");
        break;
      }

      console.error(`[ToolExecutor] Claude requested ${toolCalls.length} tool(s)`);

      // Execute tools in parallel
      const toolResults = await this.executeToolCalls(toolCalls);

      // Check if aborted after tool execution
      if (this.isAborted) {
        console.error("[ToolExecutor] Generation aborted after tool execution");
        throw new Error("Generation aborted by user");
      }

      // Add tool results as user message
      messages.push({
        role: "user",
        content: toolResults as Anthropic.ContentBlock[],
      });

      toolRound++;
    }

    if (toolRound >= this.config.maxToolRounds) {
      console.warn("[ToolExecutor] WARNING: Max tool rounds reached");
    }

    // Clean up abort controller
    this.abortController = null;

    return {
      messages,
      stopReason,
      toolRounds: toolRound,
      usage: totalUsage,
    };
  }

  /**
   * Call Claude with streaming + tools
   * Supports both API key and CLI subscription modes
   */
  private async callClaudeWithTools(messages: Message[]): Promise<Anthropic.Message> {
    console.error("[ToolExecutor] Calling Claude API...");

    // Check auth mode
    const authStatus = await this.config.claudeClient.getAuthStatus();

    if (authStatus.mode === "api_key") {
      // Use Anthropic SDK directly for API mode
      const apiClient = this.config.claudeClient.apiClient;
      if (!apiClient) {
        throw new Error("API client not initialized");
      }

      return await this.callClaudeAPI(apiClient, messages);
    } else if (authStatus.mode === "claude_cli") {
      // Use Claude CLI for subscription mode
      return await this.callClaudeCLI(messages);
    } else {
      throw new Error("No authentication configured for Claude");
    }
  }

  /**
   * Call Claude via Anthropic SDK (API key mode)
   */
  private async callClaudeAPI(
    apiClient: Anthropic,
    messages: Message[]
  ): Promise<Anthropic.Message> {
    const stream = apiClient.messages.stream({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      tools: this.availableTools,
      messages: messages.map((m) => ({
        role: m.role,
        content: typeof m.content === "string" ? m.content : m.content,
      })),
    });

    // Accumulators
    const fullContent: Anthropic.ContentBlock[] = [];
    let currentTextBlock = "";
    let currentToolUse: {
      type: "tool_use";
      id: string;
      name: string;
      inputJson: string;
      input?: Record<string, unknown>;
    } | null = null;

    // Process stream events
    for await (const event of stream) {
      switch (event.type) {
        case "content_block_start":
          if (event.content_block.type === "text") {
            // Start new text block
            currentTextBlock = "";
          } else if (event.content_block.type === "tool_use") {
            // Start new tool use block
            currentToolUse = {
              type: "tool_use",
              id: event.content_block.id,
              name: event.content_block.name,
              inputJson: "", // Will accumulate as JSON
            };
          }
          break;

        case "content_block_delta":
          if (event.delta.type === "text_delta") {
            // Stream text to UI
            currentTextBlock += event.delta.text;

            // Emit to UI immediately
            this.config.onEvent({
              type: "content_delta",
              delta: event.delta.text,
            });
          } else if (event.delta.type === "input_json_delta") {
            // Accumulate tool input JSON
            if (currentToolUse) {
              currentToolUse.inputJson += event.delta.partial_json;
            }
          }
          break;

        case "content_block_stop":
          if (currentTextBlock !== "") {
            // Finalize text block
            fullContent.push({
              type: "text",
              text: currentTextBlock,
            } as Anthropic.TextBlock);
            currentTextBlock = "";
          } else if (currentToolUse !== null) {
            // Finalize tool use block
            try {
              currentToolUse.input = JSON.parse(currentToolUse.inputJson) as Record<
                string,
                unknown
              >;
            } catch (error) {
              console.error("[ToolExecutor] Failed to parse tool input JSON:", error);
              currentToolUse.input = {};
            }

            delete currentToolUse.inputJson;

            fullContent.push(currentToolUse as Anthropic.ToolUseBlock);

            // Emit tool call started event
            this.config.onEvent({
              type: "tool_call_started",
              toolId: currentToolUse.id,
              tool: currentToolUse.name,
              input: currentToolUse.input,
            });

            currentToolUse = null;
          }
          break;

        case "message_stop":
          // End of stream
          break;
      }
    }

    // Get final message metadata
    const finalMessage = await stream.finalMessage();

    return {
      ...finalMessage,
      content: fullContent,
    };
  }

  /**
   * Call Claude via CLI (subscription mode)
   * The CLI handles tool use internally and returns complete responses
   */
  private async callClaudeCLI(messages: Message[]): Promise<Anthropic.Message> {
    // Import CLI process helpers
    const { runClaudeCode } = await import("./claude-cli-process");

    // Build system prompt with available tools
    const systemPrompt = `You have access to the following tools via MCP:\n\n${this.availableTools
      .map(
        (tool) =>
          `- ${tool.name}: ${tool.description}\n  Input: ${JSON.stringify(tool.input_schema)}`
      )
      .join("\n\n")}`;

    // Convert our message format to Anthropic format
    const anthropicMessages = messages.map(
      (m) =>
        ({
          role: m.role,
          content: typeof m.content === "string" ? m.content : m.content,
        }) as Anthropic.Messages.MessageParam
    );

    // Accumulators for parsing CLI output
    const fullContent: Anthropic.ContentBlock[] = [];
    let usage = {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    };
    let stopReason: string | undefined;

    // Stream from Claude CLI
    for await (const chunk of runClaudeCode({
      systemPrompt,
      messages: anthropicMessages,
      model: "claude-sonnet-4-20250514",
      maxOutputTokens: 4096,
    })) {
      if (typeof chunk === "string") {
        // Shouldn't happen with stream-json, but handle it
        continue;
      }

      if (chunk.type === "assistant" && "message" in chunk) {
        const message = chunk.message;

        // Process content blocks
        for (const block of message.content) {
          if (block.type === "text") {
            // Stream text deltas to UI
            this.config.onEvent({
              type: "content_delta",
              delta: block.text,
            });

            fullContent.push(block);
          } else if (block.type === "tool_use") {
            // CLI has made a tool call!
            fullContent.push(block as Anthropic.ToolUseBlock);

            // Emit tool call started event
            this.config.onEvent({
              type: "tool_call_started",
              toolId: block.id,
              tool: block.name,
              input: block.input,
            });
          }
        }

        // Update usage
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

  /**
   * Execute multiple tool calls in parallel
   */
  private async executeToolCalls(toolCalls: ToolCall[]): Promise<ToolResult[]> {
    console.error(`[ToolExecutor] Executing ${toolCalls.length} tool(s) in parallel`);

    const results = await Promise.all(
      toolCalls.map(async (toolCall) => {
        const startTime = Date.now();

        // Emit tool_call_started event
        this.config.onEvent({
          type: "tool_call_started",
          toolId: toolCall.id,
          tool: toolCall.name,
          input: toolCall.input,
        });

        try {
          // Strip MCP server prefix if present (e.g., "mcp__pb-kb__search_knowledge" -> "search_knowledge")
          const toolName = toolCall.name.replace(/^mcp__[^_]+__/, "");
          console.error(
            `[ToolExecutor] Calling MCP tool: ${toolName} (original: ${toolCall.name})`
          );

          // Preprocess input to handle Claude's JSON string serialization quirk
          const processedInput = this.preprocessToolInput(toolCall.input);

          // Call MCP
          const mcpResult = await this.config.mcpClient.callTool(toolName, processedInput);

          const executionTime = Date.now() - startTime;

          console.error(`[ToolExecutor] Tool ${toolCall.name} completed in ${executionTime}ms`);

          // Generate diff for file editing tools
          let diff: string | undefined = undefined;
          if (toolName === "file_write" && mcpResult && !mcpResult.isError) {
            try {
              // Parse the result to get file info
              const content = mcpResult.content as Array<{ text?: string }> | undefined;
              const resultText = content && content[0] ? content[0].text : undefined;
              if (resultText) {
                const parsedResult = JSON.parse(resultText) as Record<string, unknown>;
                const generatedDiff = await generateFileWriteDiff(
                  processedInput,
                  parsedResult,
                  process.cwd()
                );
                // Convert null to undefined for type safety
                diff = generatedDiff ?? undefined;
              }
            } catch (error) {
              console.warn("[ToolExecutor] Failed to generate diff:", error);
            }
          }

          // Check if MCP returned an error result
          if (mcpResult.isError) {
            // Extract error message from MCP result
            const content = mcpResult.content as Array<{ text?: string }> | undefined;
            const errorMessage =
              (content && content[0] ? content[0].text : undefined) || "Tool execution failed";

            // Emit error event
            this.config.onEvent({
              type: "tool_call_completed",
              toolId: toolCall.id,
              result: null,
              error: errorMessage as string,
              executionTime,
            });

            // Return error result to Claude
            return createErrorResult(toolCall.id, new Error(errorMessage));
          }

          // Emit success event
          this.config.onEvent({
            type: "tool_call_completed",
            toolId: toolCall.id,
            result: mcpResult,
            executionTime,
            diff: diff as string | undefined,
          });

          // Convert to Anthropic format
          return createToolResult(toolCall.id, mcpResult, false);
        } catch (error: unknown) {
          const executionTime = Date.now() - startTime;
          const errorMessage = error instanceof Error ? error.message : String(error);

          console.error(`[ToolExecutor] Tool ${toolCall.name} failed:`, errorMessage);

          // Emit error event
          this.config.onEvent({
            type: "tool_call_completed",
            toolId: toolCall.id,
            result: null,
            error: errorMessage,
            executionTime,
          });

          // Return error result
          return createErrorResult(
            toolCall.id,
            error instanceof Error ? error : new Error(String(error))
          );
        }
      })
    );

    return results;
  }

  /**
   * Preprocess tool input to fix Claude's JSON string serialization
   *
   * Claude sometimes serializes arrays/objects as JSON strings, e.g.:
   *   { "paths": "[\"file.ts\"]" }  -> { "paths": ["file.ts"] }
   */
  private preprocessToolInput(input: Record<string, unknown>): Record<string, unknown> {
    const processed: Record<string, unknown> = {};

    for (const [key, value] of Object.entries(input)) {
      if (typeof value === "string" && (value.startsWith("[") || value.startsWith("{"))) {
        // Looks like a JSON string, try to parse it
        try {
          processed[key] = JSON.parse(value);
          console.error(`[ToolExecutor] Preprocessed ${key}: parsed JSON string to native type`);
        } catch {
          // Not valid JSON, keep as string
          processed[key] = value;
        }
      } else {
        processed[key] = value;
      }
    }

    return processed;
  }

  /**
   * Get usage statistics
   */
  getUsage() {
    return { ...this.totalUsage };
  }
}
