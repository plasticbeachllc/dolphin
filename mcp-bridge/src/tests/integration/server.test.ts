import { describe, it, expect, mock } from "bun:test";

// Complete mock CONFIG matching EffectiveConfig shape so that mock.module
// does not leave other parallel test files with a partial CONFIG object.
const MOCK_CONFIG = {
  SERVER_NAME: "test-server",
  SERVER_VERSION: "1.2.3",
  MCP_PROTOCOL_VERSION: "2025-11-25",
  DOLPHIN_API_URL: "http://127.0.0.1:9999",
  LOG_LEVEL: "info",
  LOG_MAX_BYTES: 10_485_760,
  LOG_MAX_ROTATIONS: 3,
  MAX_CONCURRENT_SNIPPET_FETCH: 8,
  SNIPPET_FETCH_TIMEOUT_MS: 2000,
  SNIPPET_FETCH_RETRY_ATTEMPTS: 2,
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
    TOP_K: 20,
    SNIPPETS_TOP_N: 8,
    TOP_CONTEXT_N: 3,
    INCLUDE_HITS_JSON: true,
    INCLUDE_WARNINGS_IN_TEXT: true,
    INCLUDE_ABS_PATHS: true,
    INCLUDE_VSCODE_URIS: true,
    INCLUDE_GRAPH_CONTEXT: false,
    CONTEXT_LINES_BEFORE: 4,
    CONTEXT_LINES_AFTER: 5,
    INCLUDE_PROMPT_READY: false,
    INCLUDE_RESOURCE_TEXT: true,
  },
};

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

    mock.module("../../util/logger.js", () => ({
      initLogger: async () => {},
      logDebug: () => {},
      logInfo: () => {
        logCalled = true;
      },
      logWarn: () => {},
      logError: () => {},
    }));

    mock.module("../../util/config.js", () => ({
      CONFIG: MOCK_CONFIG,
      getConfigSummary: () => ({ mocked: true }),
      validateConfig: () => [],
    }));

    mock.module("../../mcp/tools/index.js", () => ({
      tools: [],
    }));

    try {
      const { createServer } = await import(`../../mcp/server.js?test=${Date.now()}`);

      await createServer();

      expect(captured.info).toEqual({ name: "test-server", version: "1.2.3" });
      expect(logCalled).toBe(true);
    } finally {
      mock.restore();
    }
  });

  it("registers tools with bound server context", async () => {
    let registerCalls = 0;

    mock.module("@modelcontextprotocol/sdk/server/mcp.js", () => ({
      McpServer: class {
        _registeredTools: string[] = [];
        registerTool(name: string) {
          if (!this._registeredTools) {
            throw new Error("missing registry");
          }
          this._registeredTools.push(name);
          registerCalls += 1;
        }
        async connect() {
          return;
        }
      },
    }));

    mock.module("@modelcontextprotocol/sdk/server/stdio.js", () => ({
      StdioServerTransport: class {},
    }));

    mock.module("../../util/logger.js", () => ({
      initLogger: async () => {},
      logDebug: () => {},
      logInfo: () => {},
      logWarn: () => {},
      logError: () => {},
    }));

    mock.module("../../util/config.js", () => ({
      CONFIG: MOCK_CONFIG,
      getConfigSummary: () => ({ mocked: true }),
      validateConfig: () => [],
    }));

    mock.module("../../mcp/tools/index.js", () => ({
      tools: [
        {
          definition: {
            name: "health",
            description: "Health check.",
            inputSchema: {},
            annotations: { title: "KB Health" },
          },
          handler: () => {},
        },
      ],
    }));

    try {
      const { createServer } = await import(`../../mcp/server.js?test=${Date.now()}`);

      await createServer();

      expect(registerCalls).toBeGreaterThan(0);
    } finally {
      mock.restore();
    }
  });
});
