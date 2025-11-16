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
  const originalCompatKey = process.env.DOLPHIN_OPENAI_API_KEY;
  const originalCompatBase = process.env.DOLPHIN_OPENAI_BASE_URL;

  afterEach(() => {
    if (originalKey) {
      process.env.OPENAI_API_KEY = originalKey;
    } else {
      delete process.env.OPENAI_API_KEY;
    }
    if (originalCompatKey) {
      process.env.DOLPHIN_OPENAI_API_KEY = originalCompatKey;
    } else {
      delete process.env.DOLPHIN_OPENAI_API_KEY;
    }
    if (originalCompatBase) {
      process.env.DOLPHIN_OPENAI_BASE_URL = originalCompatBase;
    } else {
      delete process.env.DOLPHIN_OPENAI_BASE_URL;
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
    delete process.env.DOLPHIN_OPENAI_API_KEY;

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

  it("detects authentication when api key is supplied via config", async () => {
    delete process.env.OPENAI_API_KEY;
    delete process.env.DOLPHIN_OPENAI_API_KEY;

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
      apiKey: "sk-config",
      baseUrl: "https://lab",
    });

    const status = await provider.detectAuthStatus();
    expect(status.authenticated).toBe(true);
    expect(status.source).toBe("provider.openai.api_key");
    expect(status.warning).toContain("custom OpenAI-compatible endpoint");
  });
});
