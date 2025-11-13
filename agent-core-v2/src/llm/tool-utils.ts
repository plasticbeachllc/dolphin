// agent-core-v2/src/llm/tool-utils.ts
import type Anthropic from "@anthropic-ai/sdk";

/**
 * Lightweight utilities for working with Anthropic tool formats
 * Note: MCP tools already use JSON Schema, so "conversion" is just property renaming
 */

export interface MCPTool {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
  };
}

export interface AnthropicTool {
  name: string;
  description: string;
  input_schema: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
  };
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, any>;
}

export interface ToolResult {
  type: "tool_result";
  tool_use_id: string;
  content: string | Array<{ type: string; [key: string]: any }>;
  is_error?: boolean;
}

/**
 * Map MCP tools to Anthropic format (just property rename)
 */
export function mapMCPToAnthropic(mcpTools: MCPTool[]): AnthropicTool[] {
  return mcpTools.map(tool => ({
    name: tool.name,
    description: tool.description,
    input_schema: tool.inputSchema
  }));
}

/**
 * Extract tool_use blocks from Claude response content
 */
export function extractToolCalls(
  content: Anthropic.ContentBlock[]
): ToolCall[] {
  return content
    .filter((block): block is Anthropic.ToolUseBlock => block.type === "tool_use")
    .map(block => ({
      id: block.id,
      name: block.name,
      input: block.input as Record<string, any>
    }));
}

/**
 * Format MCP tool result for Claude
 */
export function createToolResult(
  toolUseId: string,
  mcpResult: any,
  isError: boolean = false
): ToolResult {
  let formattedContent: string;

  // MCP results have format: { content: [{ type: "text", text: "..." }], ... }
  if (mcpResult?.content && Array.isArray(mcpResult.content)) {
    formattedContent = mcpResult.content
      .filter((block: any) => block.type === "text")
      .map((block: any) => block.text)
      .join("\n\n");
  } else if (typeof mcpResult?.content === "string") {
    formattedContent = mcpResult.content;
  } else {
    // Fallback to JSON
    formattedContent = JSON.stringify(mcpResult, null, 2);
  }

  const result: ToolResult = {
    type: "tool_result",
    tool_use_id: toolUseId,
    content: formattedContent
  };

  if (isError) {
    result.is_error = true;
  }

  return result;
}

/**
 * Create error tool result
 */
export function createErrorResult(
  toolUseId: string,
  error: Error
): ToolResult {
  const errorMessage = `Error executing tool: ${error.message}` +
    (error.stack ? `\n\nStack trace:\n${error.stack}` : "");

  return createToolResult(
    toolUseId,
    { content: errorMessage },
    true
  );
}
