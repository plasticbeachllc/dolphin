import { describe, it, expect } from "bun:test";
import { encoding_for_model } from "@dqbd/tiktoken";

import { TokenCounter } from "../../../src/utils/token-counter";

describe("TokenCounter provider awareness", () => {
  it("uses tiktoken for OpenAI models", async () => {
    const counter = new TokenCounter();
    const text = "Hello world";

    const encoder = encoding_for_model("gpt-3.5-turbo");
    const expectedTokens = encoder.encode(text).length;
    encoder.free();

    const result = await counter.countExact([text], {
      provider: "openai",
      model: "gpt-3.5-turbo",
    });

    expect(result.mode).toBe("exact");
    expect(result.totalTokens).toBe(expectedTokens);
  });

  it("falls back to heuristic when provider is not supported", async () => {
    const counter = new TokenCounter();
    const text = "123456789012"; // 12 chars

    const result = await counter.countExact([text], {
      provider: "custom-provider",
      model: "custom-model",
    });

    expect(result.mode).toBe("estimate");
    expect(result.totalTokens).toBe(Math.ceil(text.length / 4));
  });

  it("uses heuristic for OpenAI-compatible endpoints with custom base URLs", async () => {
    const counter = new TokenCounter();
    const text = "custom endpoint should fallback";

    const result = await counter.countExact([text], {
      provider: "openai",
      model: "gpt-3.5-turbo",
      baseUrl: "https://my-proxy.example.com/v1",
    });

    expect(result.mode).toBe("estimate");
    expect(result.totalTokens).toBe(Math.ceil(text.length / 4));
  });
});
