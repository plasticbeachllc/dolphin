import { describe, it, expect, mock } from "bun:test";
import { TokenCounter } from "../../../src/utils/token-counter";
import type { TokenCounterConfig } from "../../../src/utils/token-counter";
import type { AnthropicTokenClient } from "../../../src/utils/token-counter";

describe("TokenCounter", () => {
  const baseConfig: Partial<TokenCounterConfig> = {
    cacheTTLms: 60_000,
    cacheMaxEntries: 10,
    calibrationWindow: 10,
  };

  it("caches exact counts for repeated inputs", async () => {
    const countTokens = mock(async () => 42);
    const fakeClient = {
      isReady: () => true,
      countTokens,
    } as unknown as AnthropicTokenClient;

    const counter = new TokenCounter(baseConfig, fakeClient);

    await counter.countExact(["function foo() {}"]);
    await counter.countExact(["function foo() {}"]);

    expect(countTokens.mock.calls.length).toBe(1);
  });

  it("falls back to heuristic estimates when the API call fails", async () => {
    const fakeClient = {
      isReady: () => true,
      countTokens: mock(async () => {
        throw new Error("nope");
      }),
    } as unknown as AnthropicTokenClient;

    const counter = new TokenCounter(baseConfig, fakeClient);
    const result = await counter.countExact(["console.log('error path')"]);

    expect(result.mode).toBe("estimate");
    expect(result.totalTokens).toBeGreaterThan(0);
  });

  it("calibrates estimation ratios based on exact counts", async () => {
    const fakeClient = {
      isReady: () => true,
      countTokens: mock(async (text: string) => Math.ceil(text.length / 2)),
    } as unknown as AnthropicTokenClient;

    const counter = new TokenCounter(baseConfig, fakeClient);
    await counter.countExact(["a".repeat(40)]);

    const metrics = counter.collectMetrics();
    expect(metrics.estimationCharsPerToken).toBeLessThan(4);
    expect(metrics.calibrationSamples).toBeGreaterThan(0);
  });
});
