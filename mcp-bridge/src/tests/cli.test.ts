import { describe, it, expect, mock } from "bun:test";

let createServerCalled = false;
const originalEnv = { ...process.env };

describe("cli", () => {
  it("starts server with config values", async () => {
    createServerCalled = false;
    mock.module("../mcp/server.js", () => ({
      createServer: async () => {
        createServerCalled = true;
      },
    }));

    mock.module("../util/config.js", () => ({
      CONFIG: {
        DOLPHIN_API_URL: "http://127.0.0.1:9999",
        LOG_LEVEL: "warn",
        SERVER_NAME: "test-cli",
        SERVER_VERSION: "0.0.1",
        MCP_LIMITS: {
          TOP_K_MAX: 100,
          SNIPPET_CHAR_CAP: 1000,
          PAYLOAD_CAP_BYTES: 70 * 1024,
        },
        RESPONSE_LIMITS: {
          SHRUNK_SNIPPET_CHAR_CAP: 600,
          MIN_SNIPPET_CHAR_FLOOR: 300,
        },
        SEARCH_DEFAULTS: {
          INCLUDE_GRAPH_CONTEXT: true,
          CONTEXT_LINES_BEFORE: 0,
          CONTEXT_LINES_AFTER: 0,
          INCLUDE_PROMPT_READY: true,
          INCLUDE_RESOURCE_TEXT: false,
        },
      },
    }));

    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
    process.env.DOLPHIN_API_KEY = "test-key";
    process.env.DOLPHIN_API_URL = "http://127.0.0.1:9999";
    process.env.LOG_LEVEL = "warn";
    process.env.SERVER_NAME = "test-cli";
    process.env.SERVER_VERSION = "0.0.1";

    try {
      await import(`../cli.ts?test=${Date.now()}`);

      expect(createServerCalled).toBe(true);
      expect(process.env.DOLPHIN_API_URL).toBe("http://127.0.0.1:9999");
      expect(process.env.SERVER_NAME).toBe("test-cli");
      expect(process.env.SERVER_VERSION).toBe("0.0.1");
      expect(process.env.LOG_LEVEL).toBe("warn");
      expect(process.env.DOLPHIN_API_KEY).toBe("test-key");
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
    }
  });
});
