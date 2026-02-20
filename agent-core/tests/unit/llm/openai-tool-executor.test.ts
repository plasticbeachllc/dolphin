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
import type { MCPTool } from "../../../src/llm/tool-utils";

const cloneMessages = (messages: OpenAIInputMessage[]): OpenAIInputMessage[] =>
  JSON.parse(JSON.stringify(messages)) as OpenAIInputMessage[];

describe("OpenAIToolExecutor", () => {
  describe("Tool Mapping", () => {
    it("maps MCP tools into OpenAI function format", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__filesystem__read_file",
          description: "Read file contents",
          inputSchema: {
            type: "object",
            properties: { path: { type: "string" } },
            required: ["path"],
          },
        },
        {
          name: "mcp__filesystem__write_file",
          description: "Write file contents",
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

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const capturedTools: OpenAIResponseTool[][] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
          tools?: OpenAIResponseTool[];
        }): Promise<OpenAIResponse> => {
          capturedTools.push(options.tools ?? []);
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Done" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      expect(capturedTools).toHaveLength(1);
      expect(capturedTools[0]).toHaveLength(2);
      expect(capturedTools[0][0]).toEqual({
        type: "function",
        function: {
          name: "mcp__filesystem__read_file",
          description: "Read file contents",
          parameters: listedTools[0].inputSchema,
        },
      });
      expect(capturedTools[0][1]).toEqual({
        type: "function",
        function: {
          name: "mcp__filesystem__write_file",
          description: "Write file contents",
          parameters: listedTools[1].inputSchema,
        },
      });
    });

    it("filters out tools without names", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "valid_tool",
          description: "Valid tool",
          inputSchema: { type: "object", properties: {} },
        },
        {
          name: "",
          description: "Invalid tool - empty name",
          inputSchema: { type: "object", properties: {} },
        },
        {
          name: "   ",
          description: "Invalid tool - whitespace name",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const capturedTools: OpenAIResponseTool[][] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
          tools?: OpenAIResponseTool[];
        }): Promise<OpenAIResponse> => {
          capturedTools.push(options.tools ?? []);
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Done" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      expect(capturedTools[0]).toHaveLength(1);
      expect(capturedTools[0][0].function.name).toBe("valid_tool");
    });

    it("handles empty tool lists", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const capturedTools: (OpenAIResponseTool[] | undefined)[] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
          tools?: OpenAIResponseTool[];
        }): Promise<OpenAIResponse> => {
          capturedTools.push(options.tools);
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Done" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      // When tools array is empty, it should be passed as undefined
      expect(capturedTools[0]).toBeUndefined();
    });
  });

  describe("Message Handling", () => {
    it("sends messages in correct format", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const capturedMessages: OpenAIInputMessage[][] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
        }): Promise<OpenAIResponse> => {
          capturedMessages.push(cloneMessages(options.messages));
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Response" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();
      const userMessage: OpenAIMessageContent = [{ type: "text", text: "Hello, world!" }];
      await executor.executeWithTools({ role: "user", content: userMessage });

      expect(capturedMessages).toHaveLength(1);
      expect(capturedMessages[0]).toHaveLength(1);
      expect(capturedMessages[0][0]).toEqual({
        role: "user",
        content: userMessage,
      });
    });

    it("includes conversation history in messages", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const capturedMessages: OpenAIInputMessage[][] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
        }): Promise<OpenAIResponse> => {
          capturedMessages.push(cloneMessages(options.messages));
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Response" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();

      const history = [
        { role: "user" as const, content: [{ type: "text", text: "First message" }] },
        { role: "assistant" as const, content: [{ type: "text", text: "First response" }] },
      ];

      await executor.executeWithTools(
        { role: "user", content: [{ type: "text", text: "Second message" }] },
        history
      );

      expect(capturedMessages[0]).toHaveLength(3);
      expect(capturedMessages[0][0].content).toEqual(history[0].content);
      expect(capturedMessages[0][1].content).toEqual(history[1].content);
      expect(capturedMessages[0][2].content).toEqual([{ type: "text", text: "Second message" }]);
    });
  });

  describe("Streaming and Events", () => {
    it("emits content_delta events during streaming", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const events: AgentEvent[] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
          onTextChunk?: (chunk: string) => void;
        }): Promise<OpenAIResponse> => {
          options.onTextChunk?.("Hello");
          options.onTextChunk?.(" ");
          options.onTextChunk?.("world");
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Hello world" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
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
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      const deltaEvents = events.filter((e) => e.type === "content_delta");
      expect(deltaEvents).toHaveLength(3);
      expect(deltaEvents[0]).toEqual({ type: "content_delta", delta: "Hello" });
      expect(deltaEvents[1]).toEqual({ type: "content_delta", delta: " " });
      expect(deltaEvents[2]).toEqual({ type: "content_delta", delta: "world" });
    });

    it("does not emit events for non-string chunks", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const events: AgentEvent[] = [];
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
          onTextChunk?: (chunk: string) => void;
        }): Promise<OpenAIResponse> => {
          options.onTextChunk?.("valid");
          // @ts-expect-error - testing invalid input
          options.onTextChunk?.(null);
          // @ts-expect-error - testing invalid input
          options.onTextChunk?.(undefined);
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "valid" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
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
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      const deltaEvents = events.filter((e) => e.type === "content_delta");
      expect(deltaEvents).toHaveLength(1);
      expect(deltaEvents[0]).toEqual({ type: "content_delta", delta: "valid" });
    });
  });

  describe("Tool Execution", () => {
    it("executes MCP tool calls and feeds results back to the model", async () => {
      const listedTools: MCPTool[] = [
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
          model: "gpt-4",
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
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
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

    it("handles multiple tool calls in a single round", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool_a",
          description: "Tool A",
          inputSchema: { type: "object", properties: {} },
        },
        {
          name: "mcp__test__tool_b",
          description: "Tool B",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const toolCallLogs: string[] = [];
      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async (name: string) => {
          toolCallLogs.push(name);
          return {
            isError: false,
            content: [{ type: "text", text: `${name} result` }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__tool_a",
              arguments: "{}",
            },
            {
              type: "tool_call",
              call_id: "call_2",
              name: "mcp__test__tool_b",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "Both tools executed" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      let responseIndex = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 2,
        onEvent: () => {},
      });

      await executor.initialize();
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Execute both tools" }],
      });

      expect(toolCallLogs).toHaveLength(2);
      expect(toolCallLogs).toContain("tool_a");
      expect(toolCallLogs).toContain("tool_b");
      expect(result.toolRounds).toBe(1);
    });

    it("handles tool execution errors", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__failing_tool",
          description: "A tool that fails",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: true,
            content: [{ type: "text", text: "Tool execution failed: permission denied" }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__failing_tool",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "I encountered an error" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      const events: AgentEvent[] = [];
      let responseIndex = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
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
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Execute failing tool" }],
      });

      const errorEvents = events.filter((e) => e.type === "tool_call_completed");
      expect(errorEvents).toHaveLength(1);
      expect((errorEvents[0] as { error?: string }).error).toBe(
        "Tool execution failed: permission denied"
      );
    });

    it("parses JSON string arguments in tool input", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__json_tool",
          description: "Tool with JSON args",
          inputSchema: {
            type: "object",
            properties: {
              config: { type: "string" },
              data: { type: "string" },
            },
          },
        },
      ];

      const capturedArgs: unknown[] = [];
      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async (_name: string, args: unknown) => {
          capturedArgs.push(args);
          return {
            isError: false,
            content: [{ type: "text", text: "ok" }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__json_tool",
              arguments: '{"config":"{\\"key\\":\\"value\\"}","data":"[1,2,3]"}',
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      let responseIndex = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 2,
        onEvent: () => {},
      });

      await executor.initialize();
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test JSON parsing" }],
      });

      expect(capturedArgs).toHaveLength(1);
      expect(capturedArgs[0]).toEqual({
        config: { key: "value" },
        data: [1, 2, 3],
      });
    });

    it("handles malformed JSON in tool arguments gracefully", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool",
          description: "Test tool",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: false,
            content: [{ type: "text", text: "ok" }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__tool",
              arguments: "not valid json {{{",
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      let responseIndex = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 2,
        onEvent: () => {},
      });

      await executor.initialize();
      // Should not throw
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      expect(result.toolRounds).toBe(1);
    });
  });

  describe("Usage Tracking", () => {
    it("accumulates usage stats across multiple rounds", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool",
          description: "Test tool",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: false,
            content: [{ type: "text", text: "ok" }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__tool",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 100, output_tokens: 50 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_2",
              name: "mcp__test__tool",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 200, output_tokens: 75 },
        },
        {
          id: "resp_3",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
          usage: { input_tokens: 150, output_tokens: 25 },
          stop_reason: "end_turn",
        },
      ];

      let responseIndex = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 5,
        onEvent: () => {},
      });

      await executor.initialize();
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      expect(result.usage).toEqual({
        inputTokens: 450, // 100 + 200 + 150
        outputTokens: 150, // 50 + 75 + 25
        cacheReadTokens: 0,
        cacheWriteTokens: 0,
      });
      expect(result.toolRounds).toBe(2);
    });

    it("tracks cumulative usage across multiple executions", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [{ type: "text", text: "Response" }],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();

      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "First" }],
      });

      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Second" }],
      });

      const totalUsage = executor.getUsage();
      expect(totalUsage).toEqual({
        inputTokens: 20,
        outputTokens: 10,
        cacheReadTokens: 0,
        cacheWriteTokens: 0,
      });
    });
  });

  describe("Response Extraction", () => {
    it("extracts assistant content from message blocks", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [
              {
                type: "message",
                role: "assistant",
                content: [
                  { type: "text", text: "Hello" },
                  { type: "text", text: " world" },
                ],
              },
            ],
            usage: { input_tokens: 10, output_tokens: 5 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      const assistantMessage = result.messages.find((m) => m.role === "assistant");
      expect(assistantMessage?.content).toEqual([
        { type: "text", text: "Hello" },
        { type: "text", text: " world" },
      ]);
    });

    it("returns empty content when no message block exists", async () => {
      const mcpClient = {
        listTools: async () => [],
        callTool: async () => ({ content: [], isError: false }),
      } as unknown as MCPClient;

      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          return {
            id: "resp_1",
            model: "gpt-4",
            status: "completed",
            output: [],
            usage: { input_tokens: 10, output_tokens: 0 },
            stop_reason: "end_turn",
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 1,
        onEvent: () => {},
      });

      await executor.initialize();
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      const assistantMessage = result.messages.find((m) => m.role === "assistant");
      expect(assistantMessage?.content).toEqual([{ type: "output_text", text: "" }]);
    });
  });

  describe("Tool Result Formatting", () => {
    it("formats string content in tool results", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool",
          description: "Test tool",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: false,
            content: [{ type: "text", text: "Simple string result" }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__tool",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      const capturedMessages: OpenAIInputMessage[][] = [];
      let responseIndex = 0;
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
        }): Promise<OpenAIResponse> => {
          capturedMessages.push(cloneMessages(options.messages));
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 2,
        onEvent: () => {},
      });

      await executor.initialize();
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      const toolResultMessage = capturedMessages[1][capturedMessages[1].length - 1];
      expect(toolResultMessage.content).toEqual([
        {
          type: "tool_result",
          tool_call_id: "call_1",
          output: [{ type: "output_text", text: "Simple string result" }],
          is_error: undefined,
        },
      ]);
    });

    it("stringifies object content in tool results", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool",
          description: "Test tool",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: false,
            content: [{ type: "text", text: '{"status":"success","data":[1,2,3]}' }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__tool",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      const capturedMessages: OpenAIInputMessage[][] = [];
      let responseIndex = 0;
      const client = {
        streamResponse: async (options: {
          messages: OpenAIInputMessage[];
        }): Promise<OpenAIResponse> => {
          capturedMessages.push(cloneMessages(options.messages));
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 2,
        onEvent: () => {},
      });

      await executor.initialize();
      await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      const toolResultMessage = capturedMessages[1][capturedMessages[1].length - 1];
      const resultContent = toolResultMessage.content[0] as {
        output: Array<{ text: string }>;
      };
      expect(resultContent.output[0].text).toBe('{"status":"success","data":[1,2,3]}');
    });
  });

  describe("Max Tool Rounds", () => {
    it("stops execution after reaching max tool rounds", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool",
          description: "Test tool",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: false,
            content: [{ type: "text", text: "ok" }],
          };
        },
      } as unknown as MCPClient;

      let callCount = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          callCount++;
          // Always return a tool call
          return {
            id: `resp_${callCount}`,
            model: "gpt-4",
            status: "in_progress",
            output: [
              {
                type: "tool_call",
                call_id: `call_${callCount}`,
                name: "mcp__test__tool",
                arguments: "{}",
              },
            ],
            usage: { input_tokens: 5, output_tokens: 3 },
          };
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 3,
        onEvent: () => {},
      });

      await executor.initialize();
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      expect(result.toolRounds).toBe(3);
      expect(callCount).toBe(3);
    });

    it("terminates early when model stops requesting tools", async () => {
      const listedTools: MCPTool[] = [
        {
          name: "mcp__test__tool",
          description: "Test tool",
          inputSchema: { type: "object", properties: {} },
        },
      ];

      const mcpClient = {
        listTools: async () => listedTools,
        callTool: async () => {
          return {
            isError: false,
            content: [{ type: "text", text: "ok" }],
          };
        },
      } as unknown as MCPClient;

      const responses: OpenAIResponse[] = [
        {
          id: "resp_1",
          model: "gpt-4",
          status: "in_progress",
          output: [
            {
              type: "tool_call",
              call_id: "call_1",
              name: "mcp__test__tool",
              arguments: "{}",
            },
          ],
          usage: { input_tokens: 5, output_tokens: 3 },
        },
        {
          id: "resp_2",
          model: "gpt-4",
          status: "completed",
          output: [
            {
              type: "message",
              role: "assistant",
              content: [{ type: "text", text: "done" }],
            },
          ],
          usage: { input_tokens: 4, output_tokens: 2 },
          stop_reason: "end_turn",
        },
      ];

      let responseIndex = 0;
      const client = {
        streamResponse: async (): Promise<OpenAIResponse> => {
          const response = responses[responseIndex];
          responseIndex += 1;
          return response;
        },
      } as unknown as OpenAIClient;

      const executor = new OpenAIToolExecutor({
        client,
        mcpClient,
        maxToolRounds: 10,
        onEvent: () => {},
      });

      await executor.initialize();
      const result = await executor.executeWithTools({
        role: "user",
        content: [{ type: "text", text: "Test" }],
      });

      expect(result.toolRounds).toBe(1);
      expect(responseIndex).toBe(2);
    });
  });
});
