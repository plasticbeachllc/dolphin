import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import { OpenAIProvider } from "../../../src/execution/openai-provider";
import type { OpenAIClient } from "../../../src/llm/openai-client";
import type { MCPClient } from "../../../src/mcp/mcp-client";
import type { OpenAIToolExecutor } from "../../../src/llm/openai-tool-executor";

describe("OpenAI authentication integration", () => {
  const originalOpenAIKey = process.env.OPENAI_API_KEY;
  const originalDolphinOpenAIKey = process.env.DOLPHIN_OPENAI_API_KEY;
  const originalOpenAIBaseUrl = process.env.OPENAI_BASE_URL;
  const originalDolphinBaseUrl = process.env.DOLPHIN_OPENAI_BASE_URL;

  const mockExecutor = {
    initialize: async () => {},
    executeWithTools: async () => ({
      messages: [],
      toolRounds: 0,
      usage: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 },
    }),
    abort: () => {},
    getUsage: () => ({ inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 }),
  } as unknown as OpenAIToolExecutor;

  const mockClient = {
    streamResponse: async () => {
      throw new Error("streamResponse should not be called in auth tests");
    },
  } as unknown as OpenAIClient;

  const mockMcpClient = {
    listTools: async () => [],
    callTool: async () => ({}),
  } as unknown as MCPClient;

  afterEach(() => {
    if (originalOpenAIKey) {
      process.env.OPENAI_API_KEY = originalOpenAIKey;
    } else {
      delete process.env.OPENAI_API_KEY;
    }
    if (originalDolphinOpenAIKey) {
      process.env.DOLPHIN_OPENAI_API_KEY = originalDolphinOpenAIKey;
    } else {
      delete process.env.DOLPHIN_OPENAI_API_KEY;
    }
    if (originalOpenAIBaseUrl) {
      process.env.OPENAI_BASE_URL = originalOpenAIBaseUrl;
    } else {
      delete process.env.OPENAI_BASE_URL;
    }
    if (originalDolphinBaseUrl) {
      process.env.DOLPHIN_OPENAI_BASE_URL = originalDolphinBaseUrl;
    } else {
      delete process.env.DOLPHIN_OPENAI_BASE_URL;
    }
  });

  beforeEach(() => {
    delete process.env.OPENAI_API_KEY;
    delete process.env.DOLPHIN_OPENAI_API_KEY;
    delete process.env.OPENAI_BASE_URL;
    delete process.env.DOLPHIN_OPENAI_BASE_URL;
  });

  it("detects API key provided via settings", async () => {
    const provider = new OpenAIProvider({
      workspaceRoot: "/tmp/workspace",
      apiKey: "sk-config",
      openAIClient: mockClient,
      toolExecutor: mockExecutor,
      mcpClient: mockMcpClient,
      baseUrl: "https://custom.lab",
    });

    const status = await provider.detectAuthStatus();
    expect(status.authenticated).toBe(true);
    expect(status.mode).toBe("api_key");
    expect(status.source).toBe("provider.openai.api_key");
    expect(status.warning).toContain("custom OpenAI-compatible endpoint");
  });

  it("detects OPENAI_API_KEY from environment", async () => {
    process.env.OPENAI_API_KEY = "sk-env";
    const provider = new OpenAIProvider({
      workspaceRoot: "/tmp/workspace",
      openAIClient: mockClient,
      toolExecutor: mockExecutor,
      mcpClient: mockMcpClient,
    });

    const status = await provider.detectAuthStatus();
    expect(status.authenticated).toBe(true);
    expect(status.mode).toBe("api_key");
    expect(status.source).toBe("OPENAI_API_KEY");
  });

  it("prefers DOLPHIN_OPENAI_API_KEY over OPENAI_API_KEY", async () => {
    process.env.OPENAI_API_KEY = "sk-env";
    process.env.DOLPHIN_OPENAI_API_KEY = "sk-dolphin";
    const provider = new OpenAIProvider({
      workspaceRoot: "/tmp/workspace",
      openAIClient: mockClient,
      toolExecutor: mockExecutor,
      mcpClient: mockMcpClient,
    });

    const status = await provider.detectAuthStatus();
    expect(status.authenticated).toBe(true);
    expect(status.mode).toBe("api_key");
    expect(status.source).toBe("DOLPHIN_OPENAI_API_KEY");
  });

  it("throws when ensureAuthenticated is called without credentials", async () => {
    const provider = new OpenAIProvider({
      workspaceRoot: "/tmp/workspace",
      openAIClient: mockClient,
      toolExecutor: mockExecutor,
      mcpClient: mockMcpClient,
    });

    await expect(async () => {
      await provider.ensureAuthenticated();
    }).toThrow(/not authenticated/i);
  });
});
