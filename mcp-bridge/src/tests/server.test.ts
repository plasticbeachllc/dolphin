import { describe, it, expect, mock } from "bun:test";

let captured: { info?: unknown; opts?: unknown } = {};
let logCalled = false;

describe("createServer", () => {
  it("uses CONFIG server name/version", async () => {
    captured = {};
    logCalled = false;

    mock.module("@modelcontextprotocol/sdk/server/mcp.js", () => ({
      McpServer: class {
        constructor(info: unknown, opts: unknown) {
          captured = { info, opts };
        }
        registerTool() {
          // no-op
        }
        async connect() {
          return;
        }
      },
    }));

    mock.module("@modelcontextprotocol/sdk/server/stdio.js", () => ({
      StdioServerTransport: class {},
    }));

    mock.module("../util/logger.js", () => ({
      initLogger: async () => {},
      logDebug: () => {},
      logInfo: () => {
        logCalled = true;
      },
      logWarn: () => {},
      logError: () => {},
    }));

    mock.module("../util/config.js", () => ({
      CONFIG: {
        SERVER_NAME: "test-server",
        SERVER_VERSION: "1.2.3",
        MCP_PROTOCOL_VERSION: "2025-11-25",
        DOLPHIN_API_URL: "http://127.0.0.1:9999",
        LOG_LEVEL: "info",
        MCP_LIMITS: {
          TOP_K_MAX: 100,
          SNIPPET_CHAR_CAP: 1000,
          PAYLOAD_CAP_BYTES: 70 * 1024,
        },
        RESPONSE_LIMITS: {
          SHRUNK_SNIPPET_CHAR_CAP: 600,
          MIN_SNIPPET_CHAR_FLOOR: 300,
        },
      },
      getConfigSummary: () => ({ mocked: true }),
      validateConfig: () => [],
    }));

    mock.module("./tools/index.js", () => ({
      tools: [],
    }));

    try {
      const { createServer } = await import(`../mcp/server.js?test=${Date.now()}`);

      await createServer();

      expect(captured.info).toEqual({ name: "test-server", version: "1.2.3" });
      expect(logCalled).toBe(true);
    } finally {
      mock.restore();
    }
  });
});
