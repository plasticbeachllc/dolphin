import { describe, it, expect, afterEach } from "bun:test";
import { OpenAIProvider } from "../../../src/execution/openai-provider";
import type { MCPClient } from "../../../src/mcp/mcp-client";
import type { OpenAIClient, OpenAIResponse } from "../../../src/llm/openai-client";

const stubMCP = {
  listTools: async () => [],
  callTool: async () => ({ content: [{ text: "{}" }], isError: false }),
} as unknown as MCPClient;

describe("OpenAIProvider", () => {
  const originalKey = process.env.OPENAI_API_KEY;

  afterEach(() => {
    if (originalKey) {
      process.env.OPENAI_API_KEY = originalKey;
    } else {
      delete process.env.OPENAI_API_KEY;
    }
  });

  it("propagates errors from the OpenAI client", async () => {
    const failingClient = {
      streamResponse: async () => {
        throw new Error("OpenAI request failed");
      },
    } as unknown as OpenAIClient;

    const provider = new OpenAIProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      openAIClient: failingClient,
    });

    await provider.initialize();
    await expect(async () => {
      await provider.execute({ message: "hello" });
    }).toThrow(/OpenAI request failed/);
  });

  it("reports missing authentication when no API key is set", async () => {
    delete process.env.OPENAI_API_KEY;

    const okClient = {
      streamResponse: async () => ({
        id: "resp_1",
        model: "test",
        status: "completed",
        output: [],
        usage: { input_tokens: 0, output_tokens: 0 },
      }) as OpenAIResponse,
    } as unknown as OpenAIClient;

    const provider = new OpenAIProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      openAIClient: okClient,
    });

    const status = await provider.detectAuthStatus();
    expect(status.authenticated).toBe(false);
    expect(status.error).toContain("OpenAI is not authenticated");
  });
});
