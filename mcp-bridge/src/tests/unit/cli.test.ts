import { describe, it, expect, mock } from "bun:test";

let createServerCalled = false;
const originalEnv = { ...process.env };
const originalArgv = [...process.argv];
const originalExit = process.exit;
const originalConsoleLog = console.log;
const originalConsoleError = console.error;
const originalStdoutWrite = process.stdout.write.bind(process.stdout);

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
      // Note: CONFIG is computed at module import time; in a full test run it may
      // already be cached from other tests. Compare CLI side effects against the
      // active CONFIG instance to avoid order-dependent failures.
      const { CONFIG } = await import("../../util/config.js");
      await import(`../../cli.ts?test=${Date.now()}-${Math.random()}`);

      expect(createServerCalled).toBe(true);
      expect(process.env.DOLPHIN_API_URL).toBe(CONFIG.DOLPHIN_API_URL);
      expect(process.env.SERVER_NAME).toBe(CONFIG.SERVER_NAME);
      expect(process.env.SERVER_VERSION).toBe(CONFIG.SERVER_VERSION);
      expect(process.env.LOG_LEVEL).toBe(CONFIG.LOG_LEVEL);
      expect(process.env.DOLPHIN_API_KEY).toBe("test-key");
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
      process.argv = [...originalArgv];
    }
  });

  it("prints help and exits 0", async () => {
    createServerCalled = false;
    mock.module("../../mcp/server.js", () => ({
      createServer: async () => {
        createServerCalled = true;
      },
    }));

    const logs: string[] = [];
    process.argv = [...originalArgv.slice(0, 2), "--help"];
    process.exit = ((code?: number) => {
      throw new Error(`exit:${code ?? 0}`);
    }) as any;
    console.log = (...args: unknown[]) => {
      logs.push(args.join(" "));
    };

    try {
      await import(`../../cli.ts?test=${Date.now()}-${Math.random()}`);
    } catch (error) {
      expect(String(error)).toContain("exit:0");
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
      process.argv = [...originalArgv];
      process.exit = originalExit;
      console.log = originalConsoleLog;
    }

    expect(createServerCalled).toBe(false);
    expect(logs.join("\n")).toContain("Usage:");
  });

  it("prints version and exits 0", async () => {
    createServerCalled = false;
    mock.module("../../mcp/server.js", () => ({
      createServer: async () => {
        createServerCalled = true;
      },
    }));

    const logs: string[] = [];
    process.argv = [...originalArgv.slice(0, 2), "--version"];
    process.exit = ((code?: number) => {
      throw new Error(`exit:${code ?? 0}`);
    }) as any;
    console.log = (...args: unknown[]) => {
      logs.push(args.join(" "));
    };

    try {
      await import(`../../cli.ts?test=${Date.now()}-${Math.random()}`);
    } catch (error) {
      expect(String(error)).toContain("exit:0");
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
      process.argv = [...originalArgv];
      process.exit = originalExit;
      console.log = originalConsoleLog;
    }

    expect(createServerCalled).toBe(false);
    expect(logs.length).toBe(1);
    expect(logs[0]).toMatch(/\d+\.\d+\.\d+/);
  });

  it("prints effective config as JSON", async () => {
    mock.module("../../util/config.js", () => ({
      CONFIG: {
        DOLPHIN_API_URL: "http://127.0.0.1:7777",
        LOG_LEVEL: "info",
        SERVER_NAME: "dolphin-mcp",
        SERVER_VERSION: "0.0.1",
      },
      loadConfig: () => ({
        config: {
          DOLPHIN_API_URL: "http://127.0.0.1:7777",
          SERVER_NAME: "dolphin-mcp",
          SERVER_VERSION: "0.0.1",
          MCP_PROTOCOL_VERSION: "2025-11-25",
          LOG_LEVEL: "info",
          LOG_MAX_BYTES: 1024,
          LOG_MAX_ROTATIONS: 3,
          MAX_CONCURRENT_SNIPPET_FETCH: 8,
          SNIPPET_FETCH_TIMEOUT_MS: 1500,
          SNIPPET_FETCH_RETRY_ATTEMPTS: 1,
          MCP_LIMITS: {
            TOP_K_MAX: 100,
            SNIPPET_CHAR_CAP: 1000,
            PAYLOAD_CAP_BYTES: 70000,
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
            INCLUDE_GRAPH_CONTEXT: true,
            CONTEXT_LINES_BEFORE: 2,
            CONTEXT_LINES_AFTER: 2,
            INCLUDE_PROMPT_READY: true,
            INCLUDE_RESOURCE_TEXT: false,
          },
        },
        sources: {
          DOLPHIN_API_URL: "default",
          SERVER_NAME: "default",
          SERVER_VERSION: "default",
          MCP_PROTOCOL_VERSION: "default",
          LOG_LEVEL: "default",
          LOG_MAX_BYTES: "default",
          LOG_MAX_ROTATIONS: "default",
          MAX_CONCURRENT_SNIPPET_FETCH: "default",
          SNIPPET_FETCH_TIMEOUT_MS: "default",
          SNIPPET_FETCH_RETRY_ATTEMPTS: "default",
          MCP_LIMITS: {
            TOP_K_MAX: "default",
            SNIPPET_CHAR_CAP: "default",
            PAYLOAD_CAP_BYTES: "default",
          },
          RESPONSE_LIMITS: {
            SHRUNK_SNIPPET_CHAR_CAP: "default",
            MIN_SNIPPET_CHAR_FLOOR: "default",
          },
          SEARCH_DEFAULTS: {
            TOP_K: "default",
            SNIPPETS_TOP_N: "default",
            TOP_CONTEXT_N: "default",
            INCLUDE_HITS_JSON: "default",
            INCLUDE_WARNINGS_IN_TEXT: "default",
            INCLUDE_ABS_PATHS: "default",
            INCLUDE_VSCODE_URIS: "default",
            INCLUDE_GRAPH_CONTEXT: "default",
            CONTEXT_LINES_BEFORE: "default",
            CONTEXT_LINES_AFTER: "default",
            INCLUDE_PROMPT_READY: "default",
            INCLUDE_RESOURCE_TEXT: "default",
          },
        },
        diagnostics: [],
        configPath: "/tmp/config.toml",
        configFileExists: false,
        configFileReadable: false,
      }),
    }));

    const output: string[] = [];
    process.argv = [...originalArgv.slice(0, 2), "config", "--print"];
    process.stdout.write = ((chunk: unknown) => {
      output.push(String(chunk));
      return true;
    }) as any;

    try {
      await import(`../../cli.ts?test=${Date.now()}-${Math.random()}`);
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
      process.argv = [...originalArgv];
      process.stdout.write = originalStdoutWrite;
    }

    const json = JSON.parse(output.join(""));
    expect(json.config_path).toBe("/tmp/config.toml");
    expect(json.config.SERVER_NAME).toBe("dolphin-mcp");
  });

  it("doctor exits non-zero on validation errors", async () => {
    mock.module("../../util/config.js", () => ({
      CONFIG: {
        DOLPHIN_API_URL: "http://127.0.0.1:7777",
        LOG_LEVEL: "info",
        SERVER_NAME: "dolphin-mcp",
        SERVER_VERSION: "0.0.1",
      },
      loadConfig: () => ({
        config: {
          DOLPHIN_API_URL: "http://127.0.0.1:7777",
          SERVER_NAME: "dolphin-mcp",
          SERVER_VERSION: "0.0.1",
          MCP_PROTOCOL_VERSION: "2025-11-25",
          LOG_LEVEL: "info",
          LOG_MAX_BYTES: 1024,
          LOG_MAX_ROTATIONS: 3,
          MAX_CONCURRENT_SNIPPET_FETCH: 8,
          SNIPPET_FETCH_TIMEOUT_MS: 1500,
          SNIPPET_FETCH_RETRY_ATTEMPTS: 1,
          MCP_LIMITS: {
            TOP_K_MAX: 100,
            SNIPPET_CHAR_CAP: 1000,
            PAYLOAD_CAP_BYTES: 70000,
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
            INCLUDE_GRAPH_CONTEXT: true,
            CONTEXT_LINES_BEFORE: 2,
            CONTEXT_LINES_AFTER: 2,
            INCLUDE_PROMPT_READY: true,
            INCLUDE_RESOURCE_TEXT: false,
          },
        },
        sources: {},
        diagnostics: [
          { level: "error", code: "invalid_url", message: "bad url", path: "mcp.api_url" },
        ],
        configPath: "/tmp/config.toml",
        configFileExists: true,
        configFileReadable: true,
      }),
    }));
    mock.module("../../../shared/kb-auth", () => ({
      resolveKbApiKey: () => undefined,
    }));

    const output: string[] = [];
    process.argv = [...originalArgv.slice(0, 2), "doctor"];
    process.exit = ((code?: number) => {
      throw new Error(`exit:${code ?? 0}`);
    }) as any;
    process.stdout.write = ((chunk: unknown) => {
      output.push(String(chunk));
      return true;
    }) as any;

    try {
      await import(`../../cli.ts?test=${Date.now()}-${Math.random()}`);
    } catch (error) {
      expect(String(error)).toContain("exit:1");
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
      process.argv = [...originalArgv];
      process.exit = originalExit;
      process.stdout.write = originalStdoutWrite;
    }

    const json = JSON.parse(output.join(""));
    expect(json.ok).toBe(false);
    expect(json.checks.find((check: any) => check.name === "config_validation")).toBeTruthy();
  });

  it("exits non-zero when API key cannot be initialized", async () => {
    createServerCalled = false;
    mock.module("../../mcp/server.js", () => ({
      createServer: async () => {
        createServerCalled = true;
      },
    }));
    mock.module("../../../shared/kb-auth", () => ({
      getOrCreateKbApiKey: () => {
        throw new Error("nope");
      },
    }));

    const errors: string[] = [];
    process.env = { ...originalEnv };
    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
    process.argv = [...originalArgv];
    process.exit = ((code?: number) => {
      throw new Error(`exit:${code ?? 0}`);
    }) as any;
    console.error = (...args: unknown[]) => {
      errors.push(args.join(" "));
    };

    try {
      await import(`../../cli.ts?test=${Date.now()}-${Math.random()}`);
    } catch (error) {
      expect(String(error)).toContain("exit:1");
    } finally {
      mock.restore();
      process.env = { ...originalEnv };
      process.argv = [...originalArgv];
      process.exit = originalExit;
      console.error = originalConsoleError;
    }

    expect(createServerCalled).toBe(false);
    expect(errors.join("\n")).toContain("Missing DOLPHIN_API_KEY");
  });

});
