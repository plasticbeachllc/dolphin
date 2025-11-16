import { describe, it, expect, afterEach } from "bun:test";
import type OpenAI from "openai";

import { OpenAIClient } from "../../../src/llm/openai-client";

describe("OpenAIClient", () => {
  const originalKey = process.env.OPENAI_API_KEY;
  const originalCompatKey = process.env.DOLPHIN_OPENAI_API_KEY;
  const originalBase = process.env.DOLPHIN_OPENAI_BASE_URL;

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
    if (originalBase) {
      process.env.DOLPHIN_OPENAI_BASE_URL = originalBase;
    } else {
      delete process.env.DOLPHIN_OPENAI_BASE_URL;
    }
  });

  it("throws when no API key is available", () => {
    delete process.env.OPENAI_API_KEY;
    delete process.env.DOLPHIN_OPENAI_API_KEY;

    expect(() => new OpenAIClient({ model: "gpt-test" })).toThrow(/OPENAI_API_KEY/);
  });

  it("prefers provided API key and base URL", () => {
    const calls: Array<{ apiKey: string; baseURL?: string }> = [];
    const factory = ((options: { apiKey: string; baseURL?: string }) => {
      calls.push(options);
      return {} as unknown as OpenAI;
    }) as (options: { apiKey: string; baseURL?: string }) => OpenAI;

    const client = new OpenAIClient(
      {
        model: "gpt-test",
        apiKey: "sk-config",
        baseUrl: "https://lab",
      },
      factory
    );

    expect(client).toBeDefined();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({ apiKey: "sk-config", baseURL: "https://lab" });
  });

  it("falls back to env vars for compat endpoints", () => {
    delete process.env.OPENAI_API_KEY;
    process.env.DOLPHIN_OPENAI_API_KEY = "sk-env";
    process.env.DOLPHIN_OPENAI_BASE_URL = "https://env";
    const calls: Array<{ apiKey: string; baseURL?: string }> = [];
    const factory = ((options: { apiKey: string; baseURL?: string }) => {
      calls.push(options);
      return {} as unknown as OpenAI;
    }) as (options: { apiKey: string; baseURL?: string }) => OpenAI;

    new OpenAIClient({ model: "gpt-test" }, factory);

    expect(calls[0]).toEqual({ apiKey: "sk-env", baseURL: "https://env" });
  });
});
