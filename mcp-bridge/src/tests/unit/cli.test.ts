import { describe, it, expect, mock } from "bun:test";

let createServerCalled = false;
const originalEnv = { ...process.env };

describe("cli", () => {
  it("starts server with config values", async () => {
    createServerCalled = false;
    mock.module("../../mcp/server.js", () => ({
      createServer: async () => {
        createServerCalled = true;
      },
    }));

    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
    delete process.env.KB_REST_BASE_URL;
    delete process.env.DOLPHIN_CONFIG_PATH;
    process.env.DOLPHIN_API_KEY = "test-key";
    process.env.DOLPHIN_API_URL = "http://127.0.0.1:9999";
    process.env.LOG_LEVEL = "warn";
    process.env.SERVER_NAME = "test-cli";
    process.env.SERVER_VERSION = "0.0.1";

    try {
      await import(`../../cli.ts?test=${Date.now()}`);

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
