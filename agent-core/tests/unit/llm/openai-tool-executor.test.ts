import { describe, it, expect } from "bun:test";
import type { AgentEvent } from "../../../../shared/types/events";
import type {
  OpenAIClient,
  OpenAIInputMessage,
  OpenAIResponse,
  OpenAIResponseTool,
} from "../../../src/llm/openai-client";
import {
  OpenAIToolExecutor,
  type OpenAIMessageContent,
} from "../../../src/llm/openai-tool-executor";
import type { MCPClient } from "../../../src/mcp/mcp-client";

const cloneMessages = (messages: OpenAIInputMessage[]): OpenAIInputMessage[] =>
  JSON.parse(JSON.stringify(messages)) as OpenAIInputMessage[];

describe("OpenAIToolExecutor", () => {
  it("maps MCP tools into OpenAI functions and streams deltas", async () => {
    const listedTools = [
      {
        name: "mcp__filesystem__read_file",
        description: "Read file contents",
        inputSchema: {
          type: "object",
          properties: { path: { type: "string" } },
          required: ["path"],
        },
      },
    ];

    const mcpClient = {
      listTools: async () => listedTools,
      callTool: async () => ({ content: [], isError: false }),
    } as unknown as MCPClient;

    const capturedTools: OpenAIResponseTool[][] = [];
    const capturedMessages: OpenAIInputMessage[][] = [];
    const events: AgentEvent[] = [];

    const client = {
      streamResponse: async (options: {
        messages: OpenAIInputMessage[];
        tools?: OpenAIResponseTool[];
        onTextChunk?: (chunk: string) => void;
      }): Promise<OpenAIResponse> => {
        capturedTools.push(options.tools ?? []);
        capturedMessages.push(cloneMessages(options.messages));
        options.onTextChunk?.("partial chunk");
        return {
          id: "resp_1",
          model: "gpt-5.1",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "Here you go" }],
            },
          ],
          usage: { input_tokens: 11, output_tokens: 7 },
          stop_reason: "end_turn",
        };
      },
    } as unknown as OpenAIClient;

    const executor = new OpenAIToolExecutor({
      client,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event) => events.push(event),
    });

    await executor.initialize();
    const userMessage: OpenAIMessageContent = [{ type: "text", text: "Describe README" }];
    const result = await executor.executeWithTools({ role: "user", content: userMessage });

    expect(capturedTools).toHaveLength(1);
    expect(capturedTools[0]).toEqual([
      {
        type: "function",
        function: {
          name: "mcp__filesystem__read_file",
          description: "Read file contents",
          parameters: listedTools[0].inputSchema,
        },
      },
    ]);
    expect(capturedMessages[0][0].content).toEqual(userMessage);
    expect(events).toContainEqual({ type: "content_delta", delta: "partial chunk" });
    expect(result.stopReason).toBe("end_turn");
    expect(result.toolRounds).toBe(0);
    expect(result.usage).toEqual({
      inputTokens: 11,
      outputTokens: 7,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    });
  });

  it("executes MCP tool calls and feeds the results back to the model", async () => {
    const listedTools = [
      {
        name: "mcp__filesystem__file_write",
        description: "Write a file",
        inputSchema: {
          type: "object",
          properties: {
            path: { type: "string" },
            content: { type: "string" },
          },
          required: ["path", "content"],
        },
      },
    ];

    const toolCallLogs: Array<{ name: string; args: unknown }> = [];
    const mcpClient = {
      listTools: async () => listedTools,
      callTool: async (name: string, args: unknown) => {
        toolCallLogs.push({ name, args });
        return {
          isError: false,
          content: [{ type: "text", text: '{"ok":true}' }],
        };
      },
    } as unknown as MCPClient;

    const responses: OpenAIResponse[] = [
      {
        id: "resp_tool",
        model: "gpt-5.1-codex",
        status: "in_progress",
        output: [
          {
            type: "tool_call",
            call_id: "call_1",
            name: "mcp__filesystem__file_write",
            arguments:
              '{"path":"agent-core/tests/tmp/out.txt","content":"{\\"status\\":\\"ok\\"}"}',
          },
        ],
        usage: { input_tokens: 5, output_tokens: 3 },
      },
      {
        id: "resp_final",
        model: "gpt-5.1-codex",
        status: "completed",
        output: [{ type: "message", role: "assistant", content: [{ type: "text", text: "done" }] }],
        usage: { input_tokens: 4, output_tokens: 2 },
        stop_reason: "end_turn",
      },
    ];

    const capturedMessages: OpenAIInputMessage[][] = [];
    const events: AgentEvent[] = [];
    let responseIndex = 0;
    const client = {
      streamResponse: async (options: {
        messages: OpenAIInputMessage[];
        tools?: OpenAIResponseTool[];
        onTextChunk?: (chunk: string) => void;
      }): Promise<OpenAIResponse> => {
        capturedMessages.push(cloneMessages(options.messages));
        if (responseIndex === 0) {
          options.onTextChunk?.("[tool-call]");
        }
        const response = responses[responseIndex];
        responseIndex += 1;
        return response;
      },
    } as unknown as OpenAIClient;

    const executor = new OpenAIToolExecutor({
      client,
      mcpClient,
      maxToolRounds: 2,
      onEvent: (event) => events.push(event),
    });

    await executor.initialize();
    const result = await executor.executeWithTools({
      role: "user",
      content: [{ type: "text", text: "Write file" }],
    });

    expect(toolCallLogs).toHaveLength(1);
    expect(toolCallLogs[0].name).toBe("file_write");
    expect(toolCallLogs[0].args).toEqual({
      path: "agent-core/tests/tmp/out.txt",
      content: { status: "ok" },
    });

    const toolEvents = events.filter(
      (event) => event.type === "tool_call_started" || event.type === "tool_call_completed"
    );
    expect(toolEvents[0]).toMatchObject({
      type: "tool_call_started",
      toolId: "call_1",
      tool: "mcp__filesystem__file_write",
    });
    expect(toolEvents[1]).toMatchObject({
      type: "tool_call_completed",
      toolId: "call_1",
    });
    expect((toolEvents[1] as { [key: string]: unknown }).error).toBeUndefined();

    const secondCallMessages = capturedMessages[1];
    const toolResultMessage = secondCallMessages[secondCallMessages.length - 1];
    expect(toolResultMessage.role).toBe("user");
    expect(toolResultMessage.content).toEqual([
      {
        type: "tool_result",
        tool_call_id: "call_1",
        output: [{ type: "output_text", text: '{"ok":true}' }],
        is_error: undefined,
      },
    ]);

    expect(result.toolRounds).toBe(1);
    expect(result.stopReason).toBe("end_turn");
    expect(result.usage).toEqual({
      inputTokens: 9,
      outputTokens: 5,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    });
  });
});
