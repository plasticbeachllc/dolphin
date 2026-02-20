#!/usr/bin/env bun
import { createServer } from "./mcp/server.js";
import { getOrCreateKbApiKey, resolveKbApiKey } from "../../shared/kb-auth";
import { stringify as tomlStringify } from "@iarna/toml";
import { CONFIG, loadConfig } from "./util/config.js";
import { KBClient } from "./rest/client.js";

const HELP_TEXT = `
Dolphin MCP Bridge

Usage:
  dolphin-mcp [--help] [--version]
  dolphin-mcp config --print [--format json|toml]
  dolphin-mcp doctor [--check-kb] [--timeout-ms N]

Options:
  -h, --help       Show this help message
  -v, --version    Print version and exit

Environment:
  DOLPHIN_API_URL / KB_REST_BASE_URL  Base URL for Dolphin KB (required)
  DOLPHIN_API_KEY / DOLPHIN_KB_API_KEY  API key for KB (required for secured KBs)
  LOG_LEVEL        debug | info | warn | error
  SERVER_NAME      MCP server name
  SERVER_VERSION   MCP server version
`;

const DOLPHIN_API_URL = CONFIG.DOLPHIN_API_URL;
const LOG_LEVEL = CONFIG.LOG_LEVEL;
const SERVER_NAME = CONFIG.SERVER_NAME;
const SERVER_VERSION = CONFIG.SERVER_VERSION;

const argv = process.argv.slice(2);
const wantsHelp = argv.includes("-h") || argv.includes("--help");
const wantsVersion = argv.includes("-v") || argv.includes("--version");
const command = argv[0];

if (wantsHelp) {
  console.log(HELP_TEXT.trim());
  process.exit(0);
}

if (wantsVersion) {
  console.log(SERVER_VERSION);
  process.exit(0);
}

function fail(message: string, details?: string[]): never {
  console.error(`❌ Error: ${message}`);
  if (details) {
    for (const detail of details) {
      console.error(`   ${detail}`);
    }
  }
  process.exit(1);
}

function parseFlagValue(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  if (index === -1) return undefined;
  return args[index + 1];
}

function printJson(payload: unknown) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

async function handleConfigCommand(args: string[]) {
  const format = parseFlagValue(args, "--format") ?? "json";
  const result = loadConfig();
  const ok = result.diagnostics.every((diag) => diag.level !== "error");
  if (format === "toml") {
    const tomlConfig = result.config as Parameters<typeof tomlStringify>[0];
    process.stdout.write(`${tomlStringify(tomlConfig)}\n`);
    return;
  }
  if (format !== "json") {
    fail(`Unsupported format: ${format}`, ["Supported: json, toml"]);
  }
  printJson({
    ok,
    config_path: result.configPath,
    config: result.config,
    sources: result.sources,
    diagnostics: result.diagnostics,
  });
}

async function handleDoctorCommand(args: string[]) {
  const checkKb = args.includes("--check-kb");
  const timeoutMsRaw = parseFlagValue(args, "--timeout-ms");
  const timeoutMs = timeoutMsRaw ? Number(timeoutMsRaw) : 2000;
  const result = loadConfig();
  const diagnostics = result.diagnostics;

  const checks: Array<{
    name: string;
    status: "ok" | "warn" | "error";
    message: string;
    remediation?: string;
    details?: Record<string, unknown>;
  }> = [];

  if (!result.configFileExists) {
    checks.push({
      name: "config_file",
      status: "warn",
      message: "Config file not found; defaults + env will be used",
      remediation: `Create ${result.configPath} or set DOLPHIN_CONFIG_PATH`,
    });
  } else if (!result.configFileReadable) {
    checks.push({
      name: "config_file",
      status: "error",
      message: "Config file exists but could not be read or parsed",
      remediation: "Fix TOML syntax or file permissions",
    });
  } else {
    checks.push({
      name: "config_file",
      status: "ok",
      message: "Config file loaded",
    });
  }

  const errorDiagnostics = diagnostics.filter((diag) => diag.level === "error");
  const warnDiagnostics = diagnostics.filter((diag) => diag.level === "warn");
  if (errorDiagnostics.length > 0) {
    checks.push({
      name: "config_validation",
      status: "error",
      message: "Config validation errors detected",
      details: { errors: errorDiagnostics },
    });
  } else if (warnDiagnostics.length > 0) {
    checks.push({
      name: "config_validation",
      status: "warn",
      message: "Config validation warnings detected",
      details: { warnings: warnDiagnostics },
    });
  } else {
    checks.push({
      name: "config_validation",
      status: "ok",
      message: "Config validation clean",
    });
  }

  const kbKey = resolveKbApiKey({ readOnly: true });
  if (!kbKey) {
    checks.push({
      name: "kb_api_key",
      status: "warn",
      message: "KB API key not found (will auto-provision on start)",
      remediation: "Set DOLPHIN_API_KEY or create ~/.dolphin/kb_api_key",
    });
  } else {
    checks.push({
      name: "kb_api_key",
      status: "ok",
      message: "KB API key resolved",
    });
  }

  if (checkKb) {
    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(),
      Number.isFinite(timeoutMs) ? timeoutMs : 2000
    );
    const client = new KBClient({ baseUrl: result.config.DOLPHIN_API_URL });
    try {
      const health = await client.healthV1("shallow", controller.signal);
      checks.push({
        name: "kb_health",
        status: "ok",
        message: "KB health check succeeded",
        details: { status: health.status ?? "ok", version: health.version },
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      checks.push({
        name: "kb_health",
        status: "error",
        message: "KB health check failed",
        details: { error: msg },
        remediation: "Ensure KB is running and reachable at DOLPHIN_API_URL",
      });
    } finally {
      clearTimeout(timer);
    }
  }

  const ok = checks.every((check) => check.status !== "error");
  printJson({
    ok,
    config_path: result.configPath,
    api_url: result.config.DOLPHIN_API_URL,
    checks,
  });
  process.exit(ok ? 0 : 1);
}

if (command === "config") {
  await handleConfigCommand(argv.slice(1));
  process.exit(0);
}

if (command === "doctor") {
  await handleDoctorCommand(argv.slice(1));
  process.exit(0);
}

// Validate critical configuration
if (!DOLPHIN_API_URL || DOLPHIN_API_URL.trim() === "") {
  fail("DOLPHIN_API_URL or KB_REST_BASE_URL environment variable is required", [
    "Example: DOLPHIN_API_URL=http://127.0.0.1:7777",
    "Or set [mcp].api_url in ~/.dolphin/config.toml",
  ]);
}

// Validate URL format
try {
  new URL(DOLPHIN_API_URL);
} catch {
  fail("Invalid DOLPHIN_API_URL format", [
    `Current value: ${DOLPHIN_API_URL}`,
    "Expected format: http://127.0.0.1:7777 or https://api.example.com",
  ]);
}

// Ensure KB API key is available (official entry point for pure MCP setups)
if (!process.env.DOLPHIN_API_KEY && !process.env.DOLPHIN_KB_API_KEY) {
  try {
    const key = getOrCreateKbApiKey();
    process.env.DOLPHIN_API_KEY = key;
    process.env.DOLPHIN_KB_API_KEY = key;
  } catch (error: unknown) {
    fail("Missing DOLPHIN_API_KEY and failed to initialize a local key", [
      error instanceof Error ? error.message : String(error),
      "Set DOLPHIN_API_KEY (or DOLPHIN_KB_API_KEY) for secured KBs.",
      "Ensure ~/.dolphin is writable if relying on auto-generated keys.",
    ]);
  }
}

// Set process environment for the server
process.env.DOLPHIN_API_URL = DOLPHIN_API_URL;
process.env.LOG_LEVEL = LOG_LEVEL;
process.env.SERVER_NAME = SERVER_NAME;
process.env.SERVER_VERSION = SERVER_VERSION;

// Start the server
try {
  await createServer();
} catch (error: unknown) {
  const errorMessage = error instanceof Error ? error.message : String(error);
  console.error("❌ Failed to start Dolphin MCP server:", errorMessage);
  process.exit(1);
}
