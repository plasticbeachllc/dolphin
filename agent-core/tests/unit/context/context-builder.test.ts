import { describe, it, expect, mock, beforeAll, afterAll } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ContextBuilder } from "../../../src/context/context-builder";
import type { ContextBuilderConfig } from "../../../src/context/context-builder";
import type { TokenCounterLike, TokenCountResult } from "../../../src/utils/token-counter";

class StubTokenCounter implements TokenCounterLike {
  public countExact = mock(
    async (texts: string[]): Promise<TokenCountResult> => ({
      mode: "exact",
      model: "claude-sonnet-4-5-20250929",
      totalTokens: texts.length * 10,
      perInput: texts.map(() => 10),
      cacheHits: 0,
      cacheMisses: texts.length,
      usedCache: false,
      timestamp: Date.now(),
    })
  );

  estimate(texts: string[]): TokenCountResult {
    return {
      mode: "estimate",
      model: "claude-sonnet-4-5-20250929",
      totalTokens: texts.length * 5,
      perInput: texts.map(() => 5),
      cacheHits: 0,
      cacheMisses: 0,
      usedCache: false,
      timestamp: Date.now(),
    };
  }

  collectMetrics() {
    return {
      cacheSize: 0,
      cacheHits: 0,
      cacheMisses: 0,
      anthropicCalls: 0,
      anthropicErrors: 0,
      estimationCharsPerToken: 4,
      averageEstimationError: 0,
      calibrationSamples: 0,
      estimationSamples: 0,
      lastMode: "estimate" as const,
    };
  }
}

describe("ContextBuilder token integration", () => {
  let workspaceRoot: string;
  let builderConfig: ContextBuilderConfig;
  let stubCounter: StubTokenCounter;

  beforeAll(() => {
    workspaceRoot = mkdtempSync(join(tmpdir(), "context-builder-"));
    writeFileSync(join(workspaceRoot, "sample.txt"), "console.log('hello context builder');");
    stubCounter = new StubTokenCounter();
    builderConfig = {
      workspaceRoot,
      tokenCounter: stubCounter,
    };
  });

  afterAll(() => {
    rmSync(workspaceRoot, { recursive: true, force: true });
  });

  it("counts tokens for explicit files using the shared token counter", async () => {
    const builder = new ContextBuilder(builderConfig);

    const context = await builder.build({
      files: ["sample.txt"],
      maxTokens: 1000,
    });

    expect(stubCounter.countExact.mock.calls.length).toBeGreaterThan(0);
    expect(context.files[0]?.tokens).toBe(10);
    expect(context.totalTokens).toBe(10);
  });
});
