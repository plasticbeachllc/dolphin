import { describe, it, expect } from "bun:test";
import { ToolExecutorEngine, type ToolExecutorAdapter, type ToolExecutorMessage } from "../../../src/llm/tool-executor";
import type { MCPClient } from "../../../src/mcp/mcp-client";
import type { AgentEvent } from "../../../../shared/types/events";

interface MockResponse {
  toolCalls: number;
}

class SequenceAdapter implements ToolExecutorAdapter<string, string, MockResponse> {
  private readonly sequence: number[];
  private onEventCallback: ((event: AgentEvent) => void) | null = null;

  constructor(sequence: number[], onEvent?: (event: AgentEvent) => void) {
    this.sequence = [...sequence];
    this.onEventCallback = onEvent ?? null;
  }

  mapMCPTools(): string[] {
    return [];
  }

  async callModel(): Promise<{
    response: MockResponse;
    assistantMessage: ToolExecutorMessage<string>;
    usage: { inputTokens: number; outputTokens: number; cacheReadTokens: number; cacheWriteTokens: number };
    stopReason?: string;
  }> {
    const next = this.sequence.shift() ?? 0;
    return {
      response: { toolCalls: next },
      assistantMessage: { role: "assistant", content: "ok" },
      usage: { inputTokens: 1, outputTokens: 1, cacheReadTokens: 0, cacheWriteTokens: 0 },
      stopReason: next === 0 ? "end_turn" : undefined,
    };
  }

  extractToolCalls(response: MockResponse) {
    return Array.from({ length: response.toolCalls }).map((_, index) => ({
      id: `tool-${index}`,
      name: "mock_tool",
      input: {},
    }));
  }

  createToolResultMessage(): ToolExecutorMessage<string> {
    return { role: "user", content: "tool_result" };
  }

  onEvent(event: AgentEvent) {
    this.onEventCallback?.(event);
  }
}

const stubMCPClient = {
  async listTools() {
    return [];
  },
  async callTool() {
    return { content: [{ text: "done" }], isError: false };
  },
} as unknown as MCPClient;

describe("ToolExecutorEngine", () => {
  it("terminates after tool calls complete", async () => {
    const adapter = new SequenceAdapter([1, 0]);
    const engine = new ToolExecutorEngine<string, string, MockResponse>({
      adapter,
      mcpClient: stubMCPClient,
      maxToolRounds: 5,
    });

    await engine.initialize();
    const result = await engine.executeWithTools({ role: "user", content: "start" });

    expect(result.toolRounds).toBe(1);
    expect(result.usage.inputTokens).toBe(2);
    expect(result.stopReason).toBe("end_turn");
  });
});
