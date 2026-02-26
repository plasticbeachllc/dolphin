import { describe, it, expect } from "bun:test";
import { createServer } from "../../mcp/server.js";

describe("createServer", () => {
  it("uses CONFIG server name/version", async () => {
    let captured: { info?: unknown; opts?: unknown } = {};
    let logCalled = false;

    await createServer({
      config: {
        SERVER_NAME: "test-server",
        SERVER_VERSION: "1.2.3",
        MCP_PROTOCOL_VERSION: "2025-11-25",
      },
      getConfigSummary: () => ({ mocked: true }),
      validateConfig: () => [],
      initLogger: async () => {},
      logInfo: () => {
        logCalled = true;
      },
      logWarn: () => {},
      McpServerClass: class {
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
      TransportClass: class {},
      toolList: [],
    });

    expect(captured.info).toEqual({ name: "test-server", version: "1.2.3" });
    expect(logCalled).toBe(true);
  });

  it("registers tools with bound server context", async () => {
    let registerCalls = 0;

    await createServer({
      config: {
        SERVER_NAME: "test-server",
        SERVER_VERSION: "1.2.3",
        MCP_PROTOCOL_VERSION: "2025-11-25",
      },
      getConfigSummary: () => ({ mocked: true }),
      validateConfig: () => [],
      initLogger: async () => {},
      logInfo: () => {},
      logWarn: () => {},
      McpServerClass: class {
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
      TransportClass: class {},
      toolList: [
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
    });

    expect(registerCalls).toBeGreaterThan(0);
  });
});
