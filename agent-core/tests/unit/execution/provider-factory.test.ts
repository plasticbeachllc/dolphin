import { describe, it, expect, afterEach } from "bun:test";
import { createChatProvider } from "../../../src/execution/provider-factory";
import { AnthropicProvider } from "../../../src/execution/anthropic-provider";
import { OpenAIProvider } from "../../../src/execution/openai-provider";
import type { MCPClient } from "../../../src/mcp/mcp-client";
import type { AuthStatus } from "../../../src/execution/chat-provider";
import type { AuthManager } from "../../../src/execution/anthropic-provider";

const stubMCP = {
  listTools: async () => [],
  callTool: async () => ({ content: [{ text: "{}" }], isError: false }),
} as unknown as MCPClient;

describe("createChatProvider", () => {
  const originalOpenAIKey = process.env.OPENAI_API_KEY;
  const originalProviderPref = process.env.DOLPHIN_PROVIDER;
  const originalCompatKey = process.env.DOLPHIN_OPENAI_API_KEY;
  const originalCompatBase = process.env.DOLPHIN_OPENAI_BASE_URL;

  afterEach(() => {
    if (originalOpenAIKey) {
      process.env.OPENAI_API_KEY = originalOpenAIKey;
    } else {
      delete process.env.OPENAI_API_KEY;
    }
    if (originalProviderPref) {
      process.env.DOLPHIN_PROVIDER = originalProviderPref;
    } else {
      delete process.env.DOLPHIN_PROVIDER;
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

  it("prefers Anthropic when authenticated", async () => {
    delete process.env.OPENAI_API_KEY;

    const mockAuthManager = {
      detectAuthStatus: async (): Promise<AuthStatus> => ({
        authenticated: true,
        mode: "subscription",
      }),
    } as AuthManager;

    const provider = await createChatProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      authManager: mockAuthManager,
      settings: {},
    });

    expect(provider).toBeInstanceOf(AnthropicProvider);
  });

  it("falls back to OpenAI when only OPENAI_API_KEY is set", async () => {
    process.env.OPENAI_API_KEY = "sk-test";

    const mockAuthManager = {
      detectAuthStatus: async (): Promise<AuthStatus> => ({
        authenticated: false,
        mode: "none",
      }),
    } as AuthManager;

    const provider = await createChatProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      authManager: mockAuthManager,
      settings: {},
    });

    expect(provider).toBeInstanceOf(OpenAIProvider);
  });

  it("throws when OpenAI is requested without API key", async () => {
    delete process.env.OPENAI_API_KEY;
    process.env.DOLPHIN_PROVIDER = "openai";

    await expect(async () => {
      await createChatProvider({
        workspaceRoot: "/tmp/workspace",
        mcpClient: stubMCP,
        settings: { provider: "openai" },
      });
    }).toThrow(/OPENAI_API_KEY/);
  });

  it("allows OpenAI preference when api key is provided via settings", async () => {
    delete process.env.OPENAI_API_KEY;
    delete process.env.DOLPHIN_OPENAI_API_KEY;
    const provider = await createChatProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      settings: { provider: "openai", openAIApiKey: "sk-config", openAIBaseUrl: "https://lab" },
    });

    expect(provider).toBeInstanceOf(OpenAIProvider);
  });

  it("applies the supplied defaultOpenAIModel when no explicit model is configured", async () => {
    const provider = await createChatProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      settings: { provider: "openai", openAIApiKey: "sk-config" },
      defaultOpenAIModel: "gpt-5.1-codex",
    });

    expect(provider.getProviderMetadata().model).toBe("gpt-5.1-codex");
  });

  it("does not override a configured model with defaultOpenAIModel", async () => {
    const provider = await createChatProvider({
      workspaceRoot: "/tmp/workspace",
      mcpClient: stubMCP,
      settings: { provider: "openai", openAIApiKey: "sk-config", model: "gpt-5.1" },
      defaultOpenAIModel: "gpt-5.1-codex",
    });

    expect(provider.getProviderMetadata().model).toBe("gpt-5.1");
  });
});
