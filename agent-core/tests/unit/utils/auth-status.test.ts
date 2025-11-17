import { describe, it, expect, mock } from "bun:test";
import type { ChatProvider, AuthStatus } from "../../../src/execution/chat-provider";
import { buildProviderAuthStatuses } from "../../../src/utils/auth-status";

function createMockProvider(
  metadata: { provider: string; model: string },
  status: AuthStatus
): ChatProvider {
  return {
    initialize: async () => {},
    execute: async () => {
      throw new Error("not implemented");
    },
    abort: () => {},
    detectAuthStatus: mock(async () => status),
    ensureAuthenticated: async () => {},
    getUsage: () => ({ inputTokens: 0, outputTokens: 0, totalTokens: 0 }),
    getProviderMetadata: () => metadata,
  } as ChatProvider;
}

describe("buildProviderAuthStatuses", () => {
  it("maps provider metadata to auth payload", async () => {
    const providers: ChatProvider[] = [
      createMockProvider(
        { provider: "anthropic", model: "claude" },
        {
          authenticated: true,
          mode: "subscription",
          source: "cli",
        }
      ),
      createMockProvider(
        { provider: "openai", model: "gpt" },
        {
          authenticated: false,
          mode: "api_key",
          error: "missing",
        }
      ),
    ];

    const result = await buildProviderAuthStatuses(providers);
    expect(result).toEqual([
      {
        provider: "anthropic",
        authenticated: true,
        mode: "subscription",
        warning: undefined,
        error: undefined,
      },
      {
        provider: "openai",
        authenticated: false,
        mode: "api_key",
        warning: undefined,
        error: "missing",
      },
    ]);
  });
});
