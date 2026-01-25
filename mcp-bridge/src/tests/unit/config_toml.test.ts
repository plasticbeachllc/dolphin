import { describe, it, expect, afterEach, mock } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const originalEnv = { ...process.env };
let mockedHomeDir = "";

mock.module("node:os", () => ({
  homedir: () => mockedHomeDir,
}));

function resetEnv() {
  process.env = { ...originalEnv };
}

function importConfig() {
  const cacheBuster = `${Date.now()}-${Math.random()}`;
  return import(`../../util/config.js?test=${cacheBuster}`);
}

afterEach(() => {
  resetEnv();
});

describe("CONFIG TOML", () => {
  const writeConfig = (home: string, toml: string) => {
    const configDir = join(home, ".dolphin");
    mkdirSync(configDir, { recursive: true });
    writeFileSync(join(configDir, "config.toml"), toml, "utf-8");
  };

  it("loads global MCP config from ~/.dolphin/config.toml", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    writeConfig(
      home,
      `
[mcp]
api_url = "http://127.0.0.1:9999"
server_name = "test-mcp"
server_version = "9.9.9"
protocol_version = "2025-11-25"
log_level = "debug"

[mcp.limits]
top_k_max = 42
snippet_char_cap = 123
payload_cap_bytes = 2048

[mcp.search]
top_k_default = 25
snippets_top_n_default = 9
top_context_n_default = 4
include_hits_json_default = false
include_warnings_in_text_default = false
include_abs_paths_default = false
include_vscode_uris_default = false
include_prompt_ready_default = false
include_resource_text_default = true
context_lines_before_default = 2
context_lines_after_default = 3
`
    );

    process.env.HOME = home;
    delete process.env.DOLPHIN_API_URL;
    delete process.env.KB_REST_BASE_URL;

    const { CONFIG } = await importConfig();

    expect(CONFIG.DOLPHIN_API_URL).toBe("http://127.0.0.1:9999");
    expect(CONFIG.SERVER_NAME).toBe("test-mcp");
    expect(CONFIG.SERVER_VERSION).toBe("9.9.9");
    expect(CONFIG.MCP_PROTOCOL_VERSION).toBe("2025-11-25");
    expect(CONFIG.LOG_LEVEL).toBe("debug");
    expect(CONFIG.MCP_LIMITS.TOP_K_MAX).toBe(42);
    expect(CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP).toBe(123);
    expect(CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES).toBe(2048);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_K).toBe(25);
    expect(CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N).toBe(9);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N).toBe(4);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_HITS_JSON).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE).toBe(2);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER).toBe(3);
  });

  it("prefers env vars over TOML for primary settings", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    writeConfig(
      home,
      `
[mcp]
api_url = "http://127.0.0.1:9999"
server_name = "toml-mcp"
server_version = "9.9.9"
protocol_version = "2025-11-25"
log_level = "debug"
`
    );

    process.env.HOME = home;
    process.env.DOLPHIN_API_URL = "http://127.0.0.1:7771";
    process.env.LOG_LEVEL = "error";
    process.env.SERVER_NAME = "env-mcp";
    process.env.SERVER_VERSION = "1.2.3";
    process.env.MCP_PROTOCOL_VERSION = "2025-11-25";

    const { CONFIG } = await importConfig();

    expect(CONFIG.DOLPHIN_API_URL).toBe("http://127.0.0.1:7771");
    expect(CONFIG.SERVER_NAME).toBe("env-mcp");
    expect(CONFIG.SERVER_VERSION).toBe("1.2.3");
    expect(CONFIG.MCP_PROTOCOL_VERSION).toBe("2025-11-25");
    expect(CONFIG.LOG_LEVEL).toBe("error");
  });

  it("falls back to defaults when env and TOML are unset", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    process.env.HOME = home;
    delete process.env.DOLPHIN_API_URL;
    delete process.env.KB_REST_BASE_URL;
    delete process.env.LOG_LEVEL;
    delete process.env.SERVER_NAME;
    delete process.env.SERVER_VERSION;
    delete process.env.MCP_PROTOCOL_VERSION;

    const { CONFIG } = await importConfig();

    expect(CONFIG.DOLPHIN_API_URL).toBe("http://127.0.0.1:7777");
    expect(CONFIG.SERVER_NAME).toBe("dolphin-mcp");
    expect(CONFIG.SERVER_VERSION).toBe("0.2.0");
    expect(CONFIG.MCP_PROTOCOL_VERSION).toBe("2025-11-25");
    expect(CONFIG.LOG_LEVEL).toBe("info");
  });

  it("uses TOML overrides for nested limits and search defaults", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    writeConfig(
      home,
      `
[mcp.limits]
top_k_max = 77
snippet_char_cap = 555
payload_cap_bytes = 4096

[mcp.response]
shrunk_snippet_char_cap = 444
min_snippet_char_floor = 222

[mcp.search]
include_prompt_ready_default = false
include_resource_text_default = true
include_graph_context_default = false
context_lines_before_default = 4
context_lines_after_default = 5
`
    );

    process.env.HOME = home;
    delete process.env.DOLPHIN_API_URL;
    delete process.env.KB_REST_BASE_URL;

    const { CONFIG } = await importConfig();

    expect(CONFIG.MCP_LIMITS.TOP_K_MAX).toBe(77);
    expect(CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP).toBe(555);
    expect(CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES).toBe(4096);
    expect(CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP).toBe(444);
    expect(CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR).toBe(222);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_K).toBeGreaterThan(0);
    expect(CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N).toBeGreaterThan(0);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N).toBeGreaterThanOrEqual(0);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_HITS_JSON).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE).toBe(4);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER).toBe(5);
  });

  it("uses defaults for nested limits and search defaults when TOML is missing", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    process.env.HOME = home;
    delete process.env.DOLPHIN_API_URL;
    delete process.env.KB_REST_BASE_URL;

    const { CONFIG } = await importConfig();

    expect(CONFIG.MCP_LIMITS.TOP_K_MAX).toBe(100);
    expect(CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP).toBe(1000);
    expect(CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES).toBe(70 * 1024);
    expect(CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP).toBe(600);
    expect(CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR).toBe(300);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_K).toBe(20);
    expect(CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N).toBe(8);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N).toBe(3);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_HITS_JSON).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT).toBe(false);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE).toBe(2);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER).toBe(2);
  });

  it("clamps out-of-range TOML values to limits", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    writeConfig(
      home,
      `
[mcp.limits]
top_k_max = 0
snippet_char_cap = -10
payload_cap_bytes = 512

[mcp.search]
context_lines_before_default = -5
context_lines_after_default = 99
top_k_default = 0
snippets_top_n_default = -1
top_context_n_default = 9999
include_hits_json_default = "maybe"
include_warnings_in_text_default = "nope"
include_abs_paths_default = "nope"
include_vscode_uris_default = "nope"

[mcp.response]
min_snippet_char_floor = -20
shrunk_snippet_char_cap = -1
`
    );

    process.env.HOME = home;
    delete process.env.DOLPHIN_API_URL;
    delete process.env.KB_REST_BASE_URL;

    const { CONFIG } = await importConfig();

    expect(CONFIG.MCP_LIMITS.TOP_K_MAX).toBe(1);
    expect(CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP).toBe(0);
    expect(CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES).toBe(1024);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_K).toBe(1);
    expect(CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N).toBe(0);
    expect(CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N).toBeLessThanOrEqual(CONFIG.MCP_LIMITS.TOP_K_MAX);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_HITS_JSON).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS).toBe(true);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE).toBe(0);
    expect(CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER).toBe(10);
    expect(CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR).toBe(0);
    expect(CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP).toBe(0);
  });

  it("clamps to max limits and enforces shrunk floor", async () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-home-"));
    mockedHomeDir = home;
    writeConfig(
      home,
      `
[mcp.limits]
top_k_max = 5000
snippet_char_cap = 50000
payload_cap_bytes = 9999999

[mcp.response]
min_snippet_char_floor = 6000
shrunk_snippet_char_cap = 2000
`
    );

    process.env.HOME = home;
    delete process.env.DOLPHIN_API_URL;
    delete process.env.KB_REST_BASE_URL;

    const { CONFIG } = await importConfig();

    expect(CONFIG.MCP_LIMITS.TOP_K_MAX).toBe(1000);
    expect(CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP).toBe(10000);
    expect(CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES).toBe(1024 * 1024);
    expect(CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR).toBe(5000);
    expect(CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP).toBe(5000);
  });
});
