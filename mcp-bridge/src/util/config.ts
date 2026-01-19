/**
 * Configuration management for Dolphin MCP Bridge
 *
 * This module provides centralized configuration handling with validation,
 * TOML config parsing, and configuration limits for the parallel
 * snippet fetching feature.
 */
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { parse as parseToml } from "@iarna/toml";

/**
 * Configuration limits and validation constants
 */
export const CONFIG_LIMITS = {
  MIN_CONCURRENT: 1,
  RECOMMENDED_CONCURRENT: 8,
  MAX_CONCURRENT: 12, // Upper bound (FastAPI can handle more)
  MIN_TIMEOUT: 500,
  MAX_TIMEOUT: 10000,
  MIN_RETRIES: 0,
  MAX_RETRIES: 3,
  MIN_TOP_K_MAX: 1,
  MAX_TOP_K_MAX: 1000,
  MIN_SNIPPET_CHAR_CAP: 0,
  MAX_SNIPPET_CHAR_CAP: 10000,
  MIN_PAYLOAD_CAP_BYTES: 1024,
  MAX_PAYLOAD_CAP_BYTES: 1024 * 1024,
  MIN_SNIPPET_FLOOR: 0,
  MAX_SNIPPET_FLOOR: 5000,
  MIN_SHRUNK_SNIPPET_CHAR_CAP: 0,
  MAX_SHRUNK_SNIPPET_CHAR_CAP: 10000,
} as const;

const DEFAULTS = {
  API_URL: "http://127.0.0.1:7777",
  SERVER_NAME: "dolphin-mcp",
  SERVER_VERSION: "1.0.0",
  LOG_LEVEL: "info",
  MCP_LIMITS: {
    TOP_K_MAX: 100,
    SNIPPET_CHAR_CAP: 1000,
    PAYLOAD_CAP_BYTES: 70 * 1024,
  },
  SNIPPET_FETCH: {
    MAX_CONCURRENT: CONFIG_LIMITS.RECOMMENDED_CONCURRENT,
    TIMEOUT_MS: 1500,
    RETRY_ATTEMPTS: 1,
  },
  LOGGING: {
    MAX_LOG_BYTES: 5 * 1024 * 1024,
    MAX_ROTATIONS: 3,
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
} as const;

type McpConfig = {
  api_url?: string;
  server_name?: string;
  server_version?: string;
  log_level?: string;
  limits?: {
    top_k_max?: number;
    snippet_char_cap?: number;
    payload_cap_bytes?: number;
  };
  snippet_fetch?: {
    max_concurrent?: number;
    timeout_ms?: number;
    retry_attempts?: number;
  };
  logging?: {
    max_log_bytes?: number;
    max_rotations?: number;
  };
  response?: {
    shrunk_snippet_char_cap?: number;
    min_snippet_char_floor?: number;
  };
  search?: {
    include_graph_context_default?: boolean;
    context_lines_before_default?: number;
    context_lines_after_default?: number;
    include_prompt_ready_default?: boolean;
    include_resource_text_default?: boolean;
  };
};

type GlobalConfig = {
  mcp?: McpConfig;
};

function coerceNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function coerceString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function coerceBoolean(value: unknown): boolean | undefined {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const lowered = value.trim().toLowerCase();
    if (["true", "1", "yes"].includes(lowered)) return true;
    if (["false", "0", "no"].includes(lowered)) return false;
  }
  return undefined;
}

function readToml(path: string): GlobalConfig | null {
  if (!existsSync(path)) {
    return null;
  }
  try {
    const raw = readFileSync(path, "utf-8");
    return parseToml(raw) as GlobalConfig;
  } catch {
    return null;
  }
}

function resolveString(envValue: unknown, tomlValue: unknown, fallback: string): string {
  return coerceString(envValue) ?? coerceString(tomlValue) ?? fallback;
}

function resolveBoolean(envValue: unknown, tomlValue: unknown, fallback: boolean): boolean {
  return coerceBoolean(envValue) ?? coerceBoolean(tomlValue) ?? fallback;
}

function resolveNumber(envValue: unknown, tomlValue: unknown, fallback: number): number {
  return coerceNumber(envValue) ?? coerceNumber(tomlValue) ?? fallback;
}

function resolveInt(
  envValue: unknown,
  tomlValue: unknown,
  fallback: number,
  min: number,
  max: number
): number {
  const resolved = resolveNumber(envValue, tomlValue, fallback);
  const intValue = Number.isFinite(resolved) ? Math.trunc(resolved) : fallback;
  return Math.max(min, Math.min(max, intValue));
}

const GLOBAL_CONFIG_PATH = join(homedir(), ".dolphin", "config.toml");
const GLOBAL_CONFIG = readToml(GLOBAL_CONFIG_PATH);
const MCP_CONFIG = GLOBAL_CONFIG?.mcp ?? {};

const MCP_LIMITS = {
  TOP_K_MAX: resolveInt(
    undefined,
    MCP_CONFIG.limits?.top_k_max,
    DEFAULTS.MCP_LIMITS.TOP_K_MAX,
    CONFIG_LIMITS.MIN_TOP_K_MAX,
    CONFIG_LIMITS.MAX_TOP_K_MAX
  ),
  SNIPPET_CHAR_CAP: resolveInt(
    undefined,
    MCP_CONFIG.limits?.snippet_char_cap,
    DEFAULTS.MCP_LIMITS.SNIPPET_CHAR_CAP,
    CONFIG_LIMITS.MIN_SNIPPET_CHAR_CAP,
    CONFIG_LIMITS.MAX_SNIPPET_CHAR_CAP
  ),
  PAYLOAD_CAP_BYTES: resolveInt(
    undefined,
    MCP_CONFIG.limits?.payload_cap_bytes,
    DEFAULTS.MCP_LIMITS.PAYLOAD_CAP_BYTES,
    CONFIG_LIMITS.MIN_PAYLOAD_CAP_BYTES,
    CONFIG_LIMITS.MAX_PAYLOAD_CAP_BYTES
  ),
} as const;

const SNIPPET_FETCH = {
  MAX_CONCURRENT: resolveInt(
    undefined,
    MCP_CONFIG.snippet_fetch?.max_concurrent,
    DEFAULTS.SNIPPET_FETCH.MAX_CONCURRENT,
    CONFIG_LIMITS.MIN_CONCURRENT,
    CONFIG_LIMITS.MAX_CONCURRENT
  ),
  TIMEOUT_MS: resolveInt(
    undefined,
    MCP_CONFIG.snippet_fetch?.timeout_ms,
    DEFAULTS.SNIPPET_FETCH.TIMEOUT_MS,
    CONFIG_LIMITS.MIN_TIMEOUT,
    CONFIG_LIMITS.MAX_TIMEOUT
  ),
  RETRY_ATTEMPTS: resolveInt(
    undefined,
    MCP_CONFIG.snippet_fetch?.retry_attempts,
    DEFAULTS.SNIPPET_FETCH.RETRY_ATTEMPTS,
    CONFIG_LIMITS.MIN_RETRIES,
    CONFIG_LIMITS.MAX_RETRIES
  ),
} as const;

const LOGGING = {
  MAX_LOG_BYTES: resolveNumber(
    undefined,
    MCP_CONFIG.logging?.max_log_bytes,
    DEFAULTS.LOGGING.MAX_LOG_BYTES
  ),
  MAX_ROTATIONS: resolveInt(
    undefined,
    MCP_CONFIG.logging?.max_rotations,
    DEFAULTS.LOGGING.MAX_ROTATIONS,
    1,
    20
  ),
} as const;

const MIN_SNIPPET_CHAR_FLOOR = resolveInt(
  undefined,
  MCP_CONFIG.response?.min_snippet_char_floor,
  DEFAULTS.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR,
  CONFIG_LIMITS.MIN_SNIPPET_FLOOR,
  CONFIG_LIMITS.MAX_SNIPPET_FLOOR
);
const SHRUNK_SNIPPET_CHAR_CAP = resolveInt(
  undefined,
  MCP_CONFIG.response?.shrunk_snippet_char_cap,
  DEFAULTS.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP,
  CONFIG_LIMITS.MIN_SHRUNK_SNIPPET_CHAR_CAP,
  CONFIG_LIMITS.MAX_SHRUNK_SNIPPET_CHAR_CAP
);

const RESPONSE_LIMITS = {
  SHRUNK_SNIPPET_CHAR_CAP: Math.max(MIN_SNIPPET_CHAR_FLOOR, SHRUNK_SNIPPET_CHAR_CAP),
  MIN_SNIPPET_CHAR_FLOOR,
} as const;

const SEARCH_DEFAULTS = {
  INCLUDE_GRAPH_CONTEXT: resolveBoolean(
    undefined,
    MCP_CONFIG.search?.include_graph_context_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT
  ),
  CONTEXT_LINES_BEFORE: resolveInt(
    undefined,
    MCP_CONFIG.search?.context_lines_before_default,
    DEFAULTS.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE,
    0,
    10
  ),
  CONTEXT_LINES_AFTER: resolveInt(
    undefined,
    MCP_CONFIG.search?.context_lines_after_default,
    DEFAULTS.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER,
    0,
    10
  ),
  INCLUDE_PROMPT_READY: resolveBoolean(
    undefined,
    MCP_CONFIG.search?.include_prompt_ready_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY
  ),
  INCLUDE_RESOURCE_TEXT: resolveBoolean(
    undefined,
    MCP_CONFIG.search?.include_resource_text_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT
  ),
} as const;

/**
 * Centralized configuration object
 */
export const CONFIG = {
  // API Configuration
  DOLPHIN_API_URL: resolveString(
    process.env.KB_REST_BASE_URL || process.env.DOLPHIN_API_URL,
    MCP_CONFIG.api_url,
    DEFAULTS.API_URL
  ),

  // Server Configuration
  SERVER_NAME: resolveString(process.env.SERVER_NAME, MCP_CONFIG.server_name, DEFAULTS.SERVER_NAME),
  SERVER_VERSION: resolveString(
    process.env.SERVER_VERSION,
    MCP_CONFIG.server_version,
    DEFAULTS.SERVER_VERSION
  ),

  // Logging Configuration
  LOG_LEVEL: resolveString(process.env.LOG_LEVEL, MCP_CONFIG.log_level, DEFAULTS.LOG_LEVEL),
  LOG_MAX_BYTES: LOGGING.MAX_LOG_BYTES,
  LOG_MAX_ROTATIONS: LOGGING.MAX_ROTATIONS,

  // Parallel Snippet Fetching Configuration
  MAX_CONCURRENT_SNIPPET_FETCH: SNIPPET_FETCH.MAX_CONCURRENT,
  SNIPPET_FETCH_TIMEOUT_MS: SNIPPET_FETCH.TIMEOUT_MS,
  SNIPPET_FETCH_RETRY_ATTEMPTS: SNIPPET_FETCH.RETRY_ATTEMPTS,

  // MCP Limits
  MCP_LIMITS,

  // Response shaping
  RESPONSE_LIMITS,

  // Search defaults
  SEARCH_DEFAULTS,
} as const;

/**
 * Validate current configuration and return any warnings
 */
export function validateConfig(): string[] {
  const warnings: string[] = [];

  // Validate DOLPHIN_API_URL format
  try {
    new URL(CONFIG.DOLPHIN_API_URL);
  } catch {
    warnings.push(`Invalid DOLPHIN_API_URL format: ${CONFIG.DOLPHIN_API_URL}`);
  }

  // Validate LOG_LEVEL
  const validLogLevels = ["debug", "info", "warn", "error"];
  if (!validLogLevels.includes(CONFIG.LOG_LEVEL)) {
    warnings.push(`Invalid LOG_LEVEL: ${CONFIG.LOG_LEVEL}. Valid: ${validLogLevels.join(", ")}`);
  }

  // Validate concurrency settings
  if (CONFIG.MAX_CONCURRENT_SNIPPET_FETCH < CONFIG_LIMITS.MIN_CONCURRENT) {
    warnings.push(
      `MAX_CONCURRENT_SNIPPET_FETCH too low: ${CONFIG.MAX_CONCURRENT_SNIPPET_FETCH}. Min: ${CONFIG_LIMITS.MIN_CONCURRENT}`
    );
  }

  if (CONFIG.MAX_CONCURRENT_SNIPPET_FETCH > CONFIG_LIMITS.MAX_CONCURRENT) {
    warnings.push(
      `MAX_CONCURRENT_SNIPPET_FETCH too high: ${CONFIG.MAX_CONCURRENT_SNIPPET_FETCH}. Max: ${CONFIG_LIMITS.MAX_CONCURRENT}`
    );
  }

  // Validate timeout settings
  if (CONFIG.SNIPPET_FETCH_TIMEOUT_MS < CONFIG_LIMITS.MIN_TIMEOUT) {
    warnings.push(
      `SNIPPET_FETCH_TIMEOUT_MS too low: ${CONFIG.SNIPPET_FETCH_TIMEOUT_MS}. Min: ${CONFIG_LIMITS.MIN_TIMEOUT}ms`
    );
  }

  if (CONFIG.SNIPPET_FETCH_TIMEOUT_MS > CONFIG_LIMITS.MAX_TIMEOUT) {
    warnings.push(
      `SNIPPET_FETCH_TIMEOUT_MS too high: ${CONFIG.SNIPPET_FETCH_TIMEOUT_MS}. Max: ${CONFIG_LIMITS.MAX_TIMEOUT}ms`
    );
  }

  // Validate retry settings
  if (CONFIG.SNIPPET_FETCH_RETRY_ATTEMPTS < CONFIG_LIMITS.MIN_RETRIES) {
    warnings.push(
      `SNIPPET_FETCH_RETRY_ATTEMPTS too low: ${CONFIG.SNIPPET_FETCH_RETRY_ATTEMPTS}. Min: ${CONFIG_LIMITS.MIN_RETRIES}`
    );
  }

  if (CONFIG.SNIPPET_FETCH_RETRY_ATTEMPTS > CONFIG_LIMITS.MAX_RETRIES) {
    warnings.push(
      `SNIPPET_FETCH_RETRY_ATTEMPTS too high: ${CONFIG.SNIPPET_FETCH_RETRY_ATTEMPTS}. Max: ${CONFIG_LIMITS.MAX_RETRIES}`
    );
  }

  if (CONFIG.MCP_LIMITS.TOP_K_MAX < CONFIG_LIMITS.MIN_TOP_K_MAX) {
    warnings.push(
      `MCP top_k_max too low: ${CONFIG.MCP_LIMITS.TOP_K_MAX}. Min: ${CONFIG_LIMITS.MIN_TOP_K_MAX}`
    );
  }

  if (CONFIG.MCP_LIMITS.TOP_K_MAX > CONFIG_LIMITS.MAX_TOP_K_MAX) {
    warnings.push(
      `MCP top_k_max too high: ${CONFIG.MCP_LIMITS.TOP_K_MAX}. Max: ${CONFIG_LIMITS.MAX_TOP_K_MAX}`
    );
  }

  if (CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP < CONFIG_LIMITS.MIN_SNIPPET_CHAR_CAP) {
    warnings.push(
      `MCP snippet_char_cap too low: ${CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP}. Min: ${CONFIG_LIMITS.MIN_SNIPPET_CHAR_CAP}`
    );
  }

  if (CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP > CONFIG_LIMITS.MAX_SNIPPET_CHAR_CAP) {
    warnings.push(
      `MCP snippet_char_cap too high: ${CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP}. Max: ${CONFIG_LIMITS.MAX_SNIPPET_CHAR_CAP}`
    );
  }

  if (CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES < CONFIG_LIMITS.MIN_PAYLOAD_CAP_BYTES) {
    warnings.push(
      `MCP payload_cap_bytes too low: ${CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES}. Min: ${CONFIG_LIMITS.MIN_PAYLOAD_CAP_BYTES}`
    );
  }

  if (CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES > CONFIG_LIMITS.MAX_PAYLOAD_CAP_BYTES) {
    warnings.push(
      `MCP payload_cap_bytes too high: ${CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES}. Max: ${CONFIG_LIMITS.MAX_PAYLOAD_CAP_BYTES}`
    );
  }

  if (CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR < CONFIG_LIMITS.MIN_SNIPPET_FLOOR) {
    warnings.push(
      `MCP min_snippet_char_floor too low: ${CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR}. Min: ${CONFIG_LIMITS.MIN_SNIPPET_FLOOR}`
    );
  }

  if (CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR > CONFIG_LIMITS.MAX_SNIPPET_FLOOR) {
    warnings.push(
      `MCP min_snippet_char_floor too high: ${CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR}. Max: ${CONFIG_LIMITS.MAX_SNIPPET_FLOOR}`
    );
  }

  if (CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP < CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR) {
    warnings.push(
      `MCP shrunk_snippet_char_cap below floor: ${CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP}`
    );
  }

  if (
    CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP >
    CONFIG_LIMITS.MAX_SHRUNK_SNIPPET_CHAR_CAP
  ) {
    warnings.push(
      `MCP shrunk_snippet_char_cap too high: ${CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP}. Max: ${CONFIG_LIMITS.MAX_SHRUNK_SNIPPET_CHAR_CAP}`
    );
  }

  return warnings;
}

/**
 * Get configuration summary for logging
 */
export function getConfigSummary(): Record<string, unknown> {
  return {
    dolphin_api_url: CONFIG.DOLPHIN_API_URL,
    server_name: CONFIG.SERVER_NAME,
    server_version: CONFIG.SERVER_VERSION,
    log_level: CONFIG.LOG_LEVEL,
    max_concurrent_snippet_fetch: CONFIG.MAX_CONCURRENT_SNIPPET_FETCH,
    snippet_fetch_timeout_ms: CONFIG.SNIPPET_FETCH_TIMEOUT_MS,
    snippet_fetch_retry_attempts: CONFIG.SNIPPET_FETCH_RETRY_ATTEMPTS,
    mcp_top_k_max: CONFIG.MCP_LIMITS.TOP_K_MAX,
    mcp_snippet_char_cap: CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP,
    mcp_payload_cap_bytes: CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES,
    mcp_log_max_bytes: CONFIG.LOG_MAX_BYTES,
    mcp_log_max_rotations: CONFIG.LOG_MAX_ROTATIONS,
    mcp_shrunk_snippet_char_cap: CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP,
    mcp_min_snippet_char_floor: CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR,
    mcp_include_graph_context_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT,
    mcp_context_lines_before_default: CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE,
    mcp_context_lines_after_default: CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER,
    mcp_include_prompt_ready_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY,
    mcp_include_resource_text_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT,
  };
}

/**
 * Configuration presets for different use cases
 */
export const CONFIG_PRESETS = {
  CONSERVATIVE: {
    MAX_CONCURRENT_SNIPPET_FETCH: 4,
    SNIPPET_FETCH_TIMEOUT_MS: 1500,
    SNIPPET_FETCH_RETRY_ATTEMPTS: 1,
  },

  RECOMMENDED: {
    MAX_CONCURRENT_SNIPPET_FETCH: CONFIG_LIMITS.RECOMMENDED_CONCURRENT,
    SNIPPET_FETCH_TIMEOUT_MS: 2000,
    SNIPPET_FETCH_RETRY_ATTEMPTS: 1,
  },

  PERFORMANCE: {
    MAX_CONCURRENT_SNIPPET_FETCH: 10,
    SNIPPET_FETCH_TIMEOUT_MS: 3000,
    SNIPPET_FETCH_RETRY_ATTEMPTS: 2,
  },
} as const;

/**
 * Type definitions for configuration
 */
export type Config = typeof CONFIG;
export type ConfigPreset = keyof typeof CONFIG_PRESETS;
