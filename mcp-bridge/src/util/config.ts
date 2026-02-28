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
import { z } from "zod";

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
  SERVER_VERSION: "0.2.3",
  MCP_PROTOCOL_VERSION: "2025-11-25",
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
} as const;

const LOG_LEVELS = ["debug", "info", "warn", "error"] as const;
const LOG_LEVEL_SCHEMA = z.enum(LOG_LEVELS);
const URL_SCHEMA = z.string().url();

type McpConfigRaw = {
  api_url?: unknown;
  server_name?: unknown;
  server_version?: unknown;
  protocol_version?: unknown;
  log_level?: unknown;
  limits?: {
    top_k_max?: unknown;
    snippet_char_cap?: unknown;
    payload_cap_bytes?: unknown;
  };
  snippet_fetch?: {
    max_concurrent?: unknown;
    timeout_ms?: unknown;
    retry_attempts?: unknown;
  };
  logging?: {
    max_log_bytes?: unknown;
    max_rotations?: unknown;
  };
  response?: {
    shrunk_snippet_char_cap?: unknown;
    min_snippet_char_floor?: unknown;
  };
  search?: {
    top_k_default?: unknown;
    snippets_top_n_default?: unknown;
    top_context_n_default?: unknown;
    include_hits_json_default?: unknown;
    include_warnings_in_text_default?: unknown;
    include_abs_paths_default?: unknown;
    include_vscode_uris_default?: unknown;
    include_graph_context_default?: unknown;
    context_lines_before_default?: unknown;
    context_lines_after_default?: unknown;
    include_prompt_ready_default?: unknown;
    include_resource_text_default?: unknown;
  };
};

type GlobalConfigRaw = {
  mcp?: McpConfigRaw;
};

type McpConfigParsed = {
  api_url?: string;
  server_name?: string;
  server_version?: string;
  protocol_version?: string;
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
    top_k_default?: number;
    snippets_top_n_default?: number;
    top_context_n_default?: number;
    include_hits_json_default?: boolean;
    include_warnings_in_text_default?: boolean;
    include_abs_paths_default?: boolean;
    include_vscode_uris_default?: boolean;
    include_graph_context_default?: boolean;
    context_lines_before_default?: number;
    context_lines_after_default?: number;
    include_prompt_ready_default?: boolean;
    include_resource_text_default?: boolean;
  };
};

type GlobalConfigParsed = {
  mcp?: McpConfigParsed;
};

export type ConfigSource = "env" | "toml" | "default";
export type ConfigDiagnosticLevel = "error" | "warn" | "info";
export type ConfigDiagnostic = {
  level: ConfigDiagnosticLevel;
  code: string;
  message: string;
  path?: string;
  source?: ConfigSource;
  remediation?: string;
  details?: Record<string, unknown>;
};

export type ConfigSources = {
  DOLPHIN_API_URL: ConfigSource;
  SERVER_NAME: ConfigSource;
  SERVER_VERSION: ConfigSource;
  MCP_PROTOCOL_VERSION: ConfigSource;
  LOG_LEVEL: ConfigSource;
  LOG_MAX_BYTES: ConfigSource;
  LOG_MAX_ROTATIONS: ConfigSource;
  MAX_CONCURRENT_SNIPPET_FETCH: ConfigSource;
  SNIPPET_FETCH_TIMEOUT_MS: ConfigSource;
  SNIPPET_FETCH_RETRY_ATTEMPTS: ConfigSource;
  MCP_LIMITS: {
    TOP_K_MAX: ConfigSource;
    SNIPPET_CHAR_CAP: ConfigSource;
    PAYLOAD_CAP_BYTES: ConfigSource;
  };
  RESPONSE_LIMITS: {
    SHRUNK_SNIPPET_CHAR_CAP: ConfigSource;
    MIN_SNIPPET_CHAR_FLOOR: ConfigSource;
  };
  SEARCH_DEFAULTS: {
    TOP_K: ConfigSource;
    SNIPPETS_TOP_N: ConfigSource;
    TOP_CONTEXT_N: ConfigSource;
    INCLUDE_HITS_JSON: ConfigSource;
    INCLUDE_WARNINGS_IN_TEXT: ConfigSource;
    INCLUDE_ABS_PATHS: ConfigSource;
    INCLUDE_VSCODE_URIS: ConfigSource;
    INCLUDE_GRAPH_CONTEXT: ConfigSource;
    CONTEXT_LINES_BEFORE: ConfigSource;
    CONTEXT_LINES_AFTER: ConfigSource;
    INCLUDE_PROMPT_READY: ConfigSource;
    INCLUDE_RESOURCE_TEXT: ConfigSource;
  };
};

export type EffectiveConfig = {
  DOLPHIN_API_URL: string;
  SERVER_NAME: string;
  SERVER_VERSION: string;
  MCP_PROTOCOL_VERSION: string;
  LOG_LEVEL: string;
  LOG_MAX_BYTES: number;
  LOG_MAX_ROTATIONS: number;
  MAX_CONCURRENT_SNIPPET_FETCH: number;
  SNIPPET_FETCH_TIMEOUT_MS: number;
  SNIPPET_FETCH_RETRY_ATTEMPTS: number;
  MCP_LIMITS: {
    TOP_K_MAX: number;
    SNIPPET_CHAR_CAP: number;
    PAYLOAD_CAP_BYTES: number;
  };
  RESPONSE_LIMITS: {
    SHRUNK_SNIPPET_CHAR_CAP: number;
    MIN_SNIPPET_CHAR_FLOOR: number;
  };
  SEARCH_DEFAULTS: {
    TOP_K: number;
    SNIPPETS_TOP_N: number;
    TOP_CONTEXT_N: number;
    INCLUDE_HITS_JSON: boolean;
    INCLUDE_WARNINGS_IN_TEXT: boolean;
    INCLUDE_ABS_PATHS: boolean;
    INCLUDE_VSCODE_URIS: boolean;
    INCLUDE_GRAPH_CONTEXT: boolean;
    CONTEXT_LINES_BEFORE: number;
    CONTEXT_LINES_AFTER: number;
    INCLUDE_PROMPT_READY: boolean;
    INCLUDE_RESOURCE_TEXT: boolean;
  };
};

export type ConfigLoadResult = {
  config: EffectiveConfig;
  sources: ConfigSources;
  diagnostics: ConfigDiagnostic[];
  configPath: string;
  configFileExists: boolean;
  configFileReadable: boolean;
};

const DEFAULT_CONFIG_PATH = join(homedir(), ".dolphin", "config.toml");

const GlobalTomlSchemaStrict = z
  .object({
    mcp: z
      .object({
        api_url: z.any().optional(),
        server_name: z.any().optional(),
        server_version: z.any().optional(),
        protocol_version: z.any().optional(),
        log_level: z.any().optional(),
        limits: z
          .object({
            top_k_max: z.any().optional(),
            snippet_char_cap: z.any().optional(),
            payload_cap_bytes: z.any().optional(),
          })
          .strict()
          .optional(),
        snippet_fetch: z
          .object({
            max_concurrent: z.any().optional(),
            timeout_ms: z.any().optional(),
            retry_attempts: z.any().optional(),
          })
          .strict()
          .optional(),
        logging: z
          .object({
            max_log_bytes: z.any().optional(),
            max_rotations: z.any().optional(),
          })
          .strict()
          .optional(),
        response: z
          .object({
            shrunk_snippet_char_cap: z.any().optional(),
            min_snippet_char_floor: z.any().optional(),
          })
          .strict()
          .optional(),
        search: z
          .object({
            top_k_default: z.any().optional(),
            snippets_top_n_default: z.any().optional(),
            top_context_n_default: z.any().optional(),
            include_hits_json_default: z.any().optional(),
            include_warnings_in_text_default: z.any().optional(),
            include_abs_paths_default: z.any().optional(),
            include_vscode_uris_default: z.any().optional(),
            include_graph_context_default: z.any().optional(),
            context_lines_before_default: z.any().optional(),
            context_lines_after_default: z.any().optional(),
            include_prompt_ready_default: z.any().optional(),
            include_resource_text_default: z.any().optional(),
          })
          .strict()
          .optional(),
      })
      .strict()
      .optional(),
  })
  .strict();

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

function addDiagnostic(
  diagnostics: ConfigDiagnostic[],
  diagnostic: ConfigDiagnostic
): ConfigDiagnostic[] {
  diagnostics.push(diagnostic);
  return diagnostics;
}

function pathToString(path: (string | number)[]): string {
  if (!path.length) return "";
  return path.map((segment) => (typeof segment === "number" ? `[${segment}]` : segment)).join(".");
}

function attachZodIssues(
  diagnostics: ConfigDiagnostic[],
  result: z.ZodSafeParseResult<unknown>,
  source: ConfigSource,
  basePath: string
) {
  if (result.success) return;
  for (const issue of result.error.issues) {
    const path = [basePath, ...issue.path].filter((x) => x !== undefined && x !== "") as (
      | string
      | number
    )[];
    if (issue.code === "unrecognized_keys") {
      addDiagnostic(diagnostics, {
        level: "warn",
        code: "unknown_key",
        message: `Unknown keys in ${basePath || "config"}: ${issue.keys.join(", ")}`,
        path: pathToString(path),
        source,
        details: { keys: issue.keys },
      });
    } else {
      addDiagnostic(diagnostics, {
        level: "warn",
        code: "schema_validation",
        message: `Schema validation issue at ${pathToString(path)}: ${issue.message}`,
        path: pathToString(path),
        source,
        details: { code: issue.code },
      });
    }
  }
}

function parseStringField(
  value: unknown,
  diagnostics: ConfigDiagnostic[],
  path: string,
  source: ConfigSource
): string | undefined {
  if (value === undefined) return undefined;
  const str = coerceString(value);
  if (!str) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "invalid_type",
      message: `Expected non-empty string at ${path}`,
      path,
      source,
    });
    return undefined;
  }
  return str;
}

function parseUrlField(
  value: unknown,
  diagnostics: ConfigDiagnostic[],
  path: string,
  source: ConfigSource
): string | undefined {
  if (value === undefined) return undefined;
  const str = coerceString(value);
  if (!str) {
    addDiagnostic(diagnostics, {
      level: "error",
      code: "invalid_url",
      message: `Expected URL string at ${path}`,
      path,
      source,
    });
    return undefined;
  }
  const parsed = URL_SCHEMA.safeParse(str);
  if (!parsed.success) {
    addDiagnostic(diagnostics, {
      level: "error",
      code: "invalid_url",
      message: `Invalid URL at ${path}: ${parsed.error.issues[0]?.message ?? "invalid"}`,
      path,
      source,
      details: { value: str },
    });
    return undefined;
  }
  return str;
}

function parseEnumField(
  value: unknown,
  diagnostics: ConfigDiagnostic[],
  path: string,
  source: ConfigSource
): string | undefined {
  if (value === undefined) return undefined;
  const str = coerceString(value);
  if (!str) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "invalid_type",
      message: `Expected string enum at ${path}`,
      path,
      source,
    });
    return undefined;
  }
  const parsed = LOG_LEVEL_SCHEMA.safeParse(str);
  if (!parsed.success) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "invalid_enum",
      message: `Invalid value for ${path}: ${str}`,
      path,
      source,
      remediation: `Valid values: ${LOG_LEVELS.join(", ")}`,
    });
    return undefined;
  }
  return str;
}

function parseBooleanField(
  value: unknown,
  diagnostics: ConfigDiagnostic[],
  path: string,
  source: ConfigSource
): boolean | undefined {
  if (value === undefined) return undefined;
  const boolVal = coerceBoolean(value);
  if (boolVal === undefined) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "invalid_type",
      message: `Expected boolean at ${path}`,
      path,
      source,
    });
    return undefined;
  }
  return boolVal;
}

function parseNumberField(
  value: unknown,
  diagnostics: ConfigDiagnostic[],
  path: string,
  source: ConfigSource,
  min: number,
  max: number
): number | undefined {
  if (value === undefined) return undefined;
  const num = coerceNumber(value);
  if (num === undefined) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "invalid_type",
      message: `Expected number at ${path}`,
      path,
      source,
    });
    return undefined;
  }
  const intValue = Math.trunc(num);
  if (intValue < min || intValue > max) {
    const clamped = Math.max(min, Math.min(max, intValue));
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "out_of_range",
      message: `Value out of range at ${path}; clamped to ${clamped}`,
      path,
      source,
      details: { value: intValue, min, max, clamped },
    });
    return clamped;
  }
  return intValue;
}

function parseTomlConfig(path: string): {
  config: GlobalConfigParsed;
  diagnostics: ConfigDiagnostic[];
  exists: boolean;
  readable: boolean;
} {
  const diagnostics: ConfigDiagnostic[] = [];
  if (!existsSync(path)) {
    return { config: {}, diagnostics, exists: false, readable: false };
  }
  let raw: unknown;
  try {
    const content = readFileSync(path, "utf-8");
    raw = parseToml(content) as GlobalConfigRaw;
  } catch (error: unknown) {
    addDiagnostic(diagnostics, {
      level: "error",
      code: "toml_parse_error",
      message: "Failed to parse config TOML",
      path: "config.toml",
      source: "toml",
      details: { error: error instanceof Error ? error.message : String(error) },
      remediation: "Fix syntax errors in the TOML file.",
    });
    return { config: {}, diagnostics, exists: true, readable: false };
  }

  const strictResult = GlobalTomlSchemaStrict.safeParse(raw);
  attachZodIssues(diagnostics, strictResult, "toml", "config");

  const parsed = (raw ?? {}) as GlobalConfigRaw;
  const mcpRaw = parsed.mcp ?? {};
  const mcp: McpConfigParsed = {};

  mcp.api_url = parseUrlField(mcpRaw.api_url, diagnostics, "mcp.api_url", "toml");
  mcp.server_name = parseStringField(mcpRaw.server_name, diagnostics, "mcp.server_name", "toml");
  mcp.server_version = parseStringField(
    mcpRaw.server_version,
    diagnostics,
    "mcp.server_version",
    "toml"
  );
  mcp.protocol_version = parseStringField(
    mcpRaw.protocol_version,
    diagnostics,
    "mcp.protocol_version",
    "toml"
  );
  mcp.log_level = parseEnumField(mcpRaw.log_level, diagnostics, "mcp.log_level", "toml");

  if (mcpRaw.limits) {
    mcp.limits = {
      top_k_max: parseNumberField(
        mcpRaw.limits.top_k_max,
        diagnostics,
        "mcp.limits.top_k_max",
        "toml",
        CONFIG_LIMITS.MIN_TOP_K_MAX,
        CONFIG_LIMITS.MAX_TOP_K_MAX
      ),
      snippet_char_cap: parseNumberField(
        mcpRaw.limits.snippet_char_cap,
        diagnostics,
        "mcp.limits.snippet_char_cap",
        "toml",
        CONFIG_LIMITS.MIN_SNIPPET_CHAR_CAP,
        CONFIG_LIMITS.MAX_SNIPPET_CHAR_CAP
      ),
      payload_cap_bytes: parseNumberField(
        mcpRaw.limits.payload_cap_bytes,
        diagnostics,
        "mcp.limits.payload_cap_bytes",
        "toml",
        CONFIG_LIMITS.MIN_PAYLOAD_CAP_BYTES,
        CONFIG_LIMITS.MAX_PAYLOAD_CAP_BYTES
      ),
    };
  }

  if (mcpRaw.snippet_fetch) {
    mcp.snippet_fetch = {
      max_concurrent: parseNumberField(
        mcpRaw.snippet_fetch.max_concurrent,
        diagnostics,
        "mcp.snippet_fetch.max_concurrent",
        "toml",
        CONFIG_LIMITS.MIN_CONCURRENT,
        CONFIG_LIMITS.MAX_CONCURRENT
      ),
      timeout_ms: parseNumberField(
        mcpRaw.snippet_fetch.timeout_ms,
        diagnostics,
        "mcp.snippet_fetch.timeout_ms",
        "toml",
        CONFIG_LIMITS.MIN_TIMEOUT,
        CONFIG_LIMITS.MAX_TIMEOUT
      ),
      retry_attempts: parseNumberField(
        mcpRaw.snippet_fetch.retry_attempts,
        diagnostics,
        "mcp.snippet_fetch.retry_attempts",
        "toml",
        CONFIG_LIMITS.MIN_RETRIES,
        CONFIG_LIMITS.MAX_RETRIES
      ),
    };
  }

  if (mcpRaw.logging) {
    mcp.logging = {
      max_log_bytes: parseNumberField(
        mcpRaw.logging.max_log_bytes,
        diagnostics,
        "mcp.logging.max_log_bytes",
        "toml",
        1,
        Number.MAX_SAFE_INTEGER
      ),
      max_rotations: parseNumberField(
        mcpRaw.logging.max_rotations,
        diagnostics,
        "mcp.logging.max_rotations",
        "toml",
        1,
        20
      ),
    };
  }

  if (mcpRaw.response) {
    mcp.response = {
      shrunk_snippet_char_cap: parseNumberField(
        mcpRaw.response.shrunk_snippet_char_cap,
        diagnostics,
        "mcp.response.shrunk_snippet_char_cap",
        "toml",
        CONFIG_LIMITS.MIN_SHRUNK_SNIPPET_CHAR_CAP,
        CONFIG_LIMITS.MAX_SHRUNK_SNIPPET_CHAR_CAP
      ),
      min_snippet_char_floor: parseNumberField(
        mcpRaw.response.min_snippet_char_floor,
        diagnostics,
        "mcp.response.min_snippet_char_floor",
        "toml",
        CONFIG_LIMITS.MIN_SNIPPET_FLOOR,
        CONFIG_LIMITS.MAX_SNIPPET_FLOOR
      ),
    };
  }

  if (mcpRaw.search) {
    mcp.search = {
      top_k_default: parseNumberField(
        mcpRaw.search.top_k_default,
        diagnostics,
        "mcp.search.top_k_default",
        "toml",
        1,
        CONFIG_LIMITS.MAX_TOP_K_MAX
      ),
      snippets_top_n_default: parseNumberField(
        mcpRaw.search.snippets_top_n_default,
        diagnostics,
        "mcp.search.snippets_top_n_default",
        "toml",
        0,
        CONFIG_LIMITS.MAX_TOP_K_MAX
      ),
      top_context_n_default: parseNumberField(
        mcpRaw.search.top_context_n_default,
        diagnostics,
        "mcp.search.top_context_n_default",
        "toml",
        0,
        CONFIG_LIMITS.MAX_TOP_K_MAX
      ),
      include_hits_json_default: parseBooleanField(
        mcpRaw.search.include_hits_json_default,
        diagnostics,
        "mcp.search.include_hits_json_default",
        "toml"
      ),
      include_warnings_in_text_default: parseBooleanField(
        mcpRaw.search.include_warnings_in_text_default,
        diagnostics,
        "mcp.search.include_warnings_in_text_default",
        "toml"
      ),
      include_abs_paths_default: parseBooleanField(
        mcpRaw.search.include_abs_paths_default,
        diagnostics,
        "mcp.search.include_abs_paths_default",
        "toml"
      ),
      include_vscode_uris_default: parseBooleanField(
        mcpRaw.search.include_vscode_uris_default,
        diagnostics,
        "mcp.search.include_vscode_uris_default",
        "toml"
      ),
      include_graph_context_default: parseBooleanField(
        mcpRaw.search.include_graph_context_default,
        diagnostics,
        "mcp.search.include_graph_context_default",
        "toml"
      ),
      context_lines_before_default: parseNumberField(
        mcpRaw.search.context_lines_before_default,
        diagnostics,
        "mcp.search.context_lines_before_default",
        "toml",
        0,
        10
      ),
      context_lines_after_default: parseNumberField(
        mcpRaw.search.context_lines_after_default,
        diagnostics,
        "mcp.search.context_lines_after_default",
        "toml",
        0,
        10
      ),
      include_prompt_ready_default: parseBooleanField(
        mcpRaw.search.include_prompt_ready_default,
        diagnostics,
        "mcp.search.include_prompt_ready_default",
        "toml"
      ),
      include_resource_text_default: parseBooleanField(
        mcpRaw.search.include_resource_text_default,
        diagnostics,
        "mcp.search.include_resource_text_default",
        "toml"
      ),
    };
  }

  return {
    config: { mcp },
    diagnostics,
    exists: true,
    readable: true,
  };
}

function parseEnvConfig(env: NodeJS.ProcessEnv): {
  config: GlobalConfigParsed;
  diagnostics: ConfigDiagnostic[];
  configPath?: string;
  apiUrlSource?: "KB_REST_BASE_URL" | "DOLPHIN_API_URL";
} {
  const diagnostics: ConfigDiagnostic[] = [];
  const config: GlobalConfigParsed = { mcp: {} };

  const configPath = parseStringField(
    env.DOLPHIN_CONFIG_PATH,
    diagnostics,
    "env.DOLPHIN_CONFIG_PATH",
    "env"
  );

  const kbRestUrl = parseUrlField(env.KB_REST_BASE_URL, diagnostics, "env.KB_REST_BASE_URL", "env");
  const dolphinApiUrl = parseUrlField(
    env.DOLPHIN_API_URL,
    diagnostics,
    "env.DOLPHIN_API_URL",
    "env"
  );
  if (kbRestUrl) {
    config.mcp!.api_url = kbRestUrl;
  } else if (dolphinApiUrl) {
    config.mcp!.api_url = dolphinApiUrl;
  }

  config.mcp!.server_name = parseStringField(
    env.SERVER_NAME,
    diagnostics,
    "env.SERVER_NAME",
    "env"
  );
  config.mcp!.server_version = parseStringField(
    env.SERVER_VERSION,
    diagnostics,
    "env.SERVER_VERSION",
    "env"
  );
  config.mcp!.protocol_version = parseStringField(
    env.MCP_PROTOCOL_VERSION,
    diagnostics,
    "env.MCP_PROTOCOL_VERSION",
    "env"
  );
  config.mcp!.log_level = parseEnumField(env.LOG_LEVEL, diagnostics, "env.LOG_LEVEL", "env");

  config.mcp!.snippet_fetch = {
    max_concurrent: parseNumberField(
      env.MAX_CONCURRENT_SNIPPET_FETCH,
      diagnostics,
      "env.MAX_CONCURRENT_SNIPPET_FETCH",
      "env",
      CONFIG_LIMITS.MIN_CONCURRENT,
      CONFIG_LIMITS.MAX_CONCURRENT
    ),
    timeout_ms: parseNumberField(
      env.SNIPPET_FETCH_TIMEOUT_MS,
      diagnostics,
      "env.SNIPPET_FETCH_TIMEOUT_MS",
      "env",
      CONFIG_LIMITS.MIN_TIMEOUT,
      CONFIG_LIMITS.MAX_TIMEOUT
    ),
    retry_attempts: parseNumberField(
      env.SNIPPET_FETCH_RETRY_ATTEMPTS,
      diagnostics,
      "env.SNIPPET_FETCH_RETRY_ATTEMPTS",
      "env",
      CONFIG_LIMITS.MIN_RETRIES,
      CONFIG_LIMITS.MAX_RETRIES
    ),
  };

  const apiUrlSource = kbRestUrl
    ? "KB_REST_BASE_URL"
    : dolphinApiUrl
      ? "DOLPHIN_API_URL"
      : undefined;

  return { config, diagnostics, configPath, apiUrlSource };
}

function resolveValue<T>(
  envValue: T | undefined,
  tomlValue: T | undefined,
  fallback: T
): { value: T; source: ConfigSource } {
  if (envValue !== undefined) return { value: envValue, source: "env" };
  if (tomlValue !== undefined) return { value: tomlValue, source: "toml" };
  return { value: fallback, source: "default" };
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ConfigLoadResult {
  const envParsed = parseEnvConfig(env);
  const configPath = envParsed.configPath ?? DEFAULT_CONFIG_PATH;
  const tomlParsed = parseTomlConfig(configPath);

  const diagnostics: ConfigDiagnostic[] = [...envParsed.diagnostics, ...tomlParsed.diagnostics];

  const mcpEnv = envParsed.config.mcp ?? {};
  const mcpToml = tomlParsed.config.mcp ?? {};

  const apiUrlResolved = resolveValue(mcpEnv.api_url, mcpToml.api_url, DEFAULTS.API_URL);
  const serverNameResolved = resolveValue(
    mcpEnv.server_name,
    mcpToml.server_name,
    DEFAULTS.SERVER_NAME
  );
  const serverVersionResolved = resolveValue(
    mcpEnv.server_version,
    mcpToml.server_version,
    DEFAULTS.SERVER_VERSION
  );
  const protocolVersionResolved = resolveValue(
    mcpEnv.protocol_version,
    mcpToml.protocol_version,
    DEFAULTS.MCP_PROTOCOL_VERSION
  );
  const logLevelResolved = resolveValue(mcpEnv.log_level, mcpToml.log_level, DEFAULTS.LOG_LEVEL);

  const topKMaxResolved = resolveValue(
    mcpEnv.limits?.top_k_max,
    mcpToml.limits?.top_k_max,
    DEFAULTS.MCP_LIMITS.TOP_K_MAX
  );
  const snippetCharCapResolved = resolveValue(
    mcpEnv.limits?.snippet_char_cap,
    mcpToml.limits?.snippet_char_cap,
    DEFAULTS.MCP_LIMITS.SNIPPET_CHAR_CAP
  );
  const payloadCapResolved = resolveValue(
    mcpEnv.limits?.payload_cap_bytes,
    mcpToml.limits?.payload_cap_bytes,
    DEFAULTS.MCP_LIMITS.PAYLOAD_CAP_BYTES
  );

  const maxConcurrentResolved = resolveValue(
    mcpEnv.snippet_fetch?.max_concurrent,
    mcpToml.snippet_fetch?.max_concurrent,
    DEFAULTS.SNIPPET_FETCH.MAX_CONCURRENT
  );
  const timeoutResolved = resolveValue(
    mcpEnv.snippet_fetch?.timeout_ms,
    mcpToml.snippet_fetch?.timeout_ms,
    DEFAULTS.SNIPPET_FETCH.TIMEOUT_MS
  );
  const retryResolved = resolveValue(
    mcpEnv.snippet_fetch?.retry_attempts,
    mcpToml.snippet_fetch?.retry_attempts,
    DEFAULTS.SNIPPET_FETCH.RETRY_ATTEMPTS
  );

  const logMaxBytesResolved = resolveValue(
    mcpEnv.logging?.max_log_bytes,
    mcpToml.logging?.max_log_bytes,
    DEFAULTS.LOGGING.MAX_LOG_BYTES
  );
  const logMaxRotationsResolved = resolveValue(
    mcpEnv.logging?.max_rotations,
    mcpToml.logging?.max_rotations,
    DEFAULTS.LOGGING.MAX_ROTATIONS
  );

  const minSnippetFloorResolved = resolveValue(
    mcpEnv.response?.min_snippet_char_floor,
    mcpToml.response?.min_snippet_char_floor,
    DEFAULTS.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR
  );
  const shrunkSnippetResolved = resolveValue(
    mcpEnv.response?.shrunk_snippet_char_cap,
    mcpToml.response?.shrunk_snippet_char_cap,
    DEFAULTS.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP
  );

  let shrunkSnippetCharCap = shrunkSnippetResolved.value;
  if (shrunkSnippetCharCap < minSnippetFloorResolved.value) {
    shrunkSnippetCharCap = minSnippetFloorResolved.value;
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "floor_adjusted",
      message: "shrunk_snippet_char_cap adjusted to min_snippet_char_floor",
      path: "mcp.response.shrunk_snippet_char_cap",
      source: shrunkSnippetResolved.source,
      details: {
        requested: shrunkSnippetResolved.value,
        min_floor: minSnippetFloorResolved.value,
      },
    });
  }

  if (minSnippetFloorResolved.value > snippetCharCapResolved.value) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "floor_exceeds_cap",
      message: "min_snippet_char_floor exceeds snippet_char_cap",
      path: "mcp.response.min_snippet_char_floor",
      source: minSnippetFloorResolved.source,
      details: {
        min_floor: minSnippetFloorResolved.value,
        snippet_cap: snippetCharCapResolved.value,
      },
    });
  }

  if (minSnippetFloorResolved.value > shrunkSnippetCharCap) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "floor_exceeds_shrunk_cap",
      message: "min_snippet_char_floor exceeds shrunk_snippet_char_cap",
      path: "mcp.response.min_snippet_char_floor",
      source: minSnippetFloorResolved.source,
      details: {
        min_floor: minSnippetFloorResolved.value,
        shrunk_cap: shrunkSnippetCharCap,
      },
    });
  }

  if (snippetCharCapResolved.value < shrunkSnippetCharCap) {
    addDiagnostic(diagnostics, {
      level: "warn",
      code: "cap_below_shrunk",
      message: "snippet_char_cap is less than shrunk_snippet_char_cap",
      path: "mcp.limits.snippet_char_cap",
      source: snippetCharCapResolved.source,
      details: {
        snippet_cap: snippetCharCapResolved.value,
        shrunk_cap: shrunkSnippetCharCap,
      },
    });
  }

  const topKDefaultResolved = resolveValue(
    mcpEnv.search?.top_k_default,
    mcpToml.search?.top_k_default,
    DEFAULTS.SEARCH_DEFAULTS.TOP_K
  );
  const snippetsTopNResolved = resolveValue(
    mcpEnv.search?.snippets_top_n_default,
    mcpToml.search?.snippets_top_n_default,
    DEFAULTS.SEARCH_DEFAULTS.SNIPPETS_TOP_N
  );
  const topContextResolved = resolveValue(
    mcpEnv.search?.top_context_n_default,
    mcpToml.search?.top_context_n_default,
    DEFAULTS.SEARCH_DEFAULTS.TOP_CONTEXT_N
  );
  const includeHitsResolved = resolveValue(
    mcpEnv.search?.include_hits_json_default,
    mcpToml.search?.include_hits_json_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_HITS_JSON
  );
  const includeWarningsResolved = resolveValue(
    mcpEnv.search?.include_warnings_in_text_default,
    mcpToml.search?.include_warnings_in_text_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT
  );
  const includeAbsPathsResolved = resolveValue(
    mcpEnv.search?.include_abs_paths_default,
    mcpToml.search?.include_abs_paths_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS
  );
  const includeVscodeUrisResolved = resolveValue(
    mcpEnv.search?.include_vscode_uris_default,
    mcpToml.search?.include_vscode_uris_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS
  );
  const includeGraphResolved = resolveValue(
    mcpEnv.search?.include_graph_context_default,
    mcpToml.search?.include_graph_context_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT
  );
  const contextBeforeResolved = resolveValue(
    mcpEnv.search?.context_lines_before_default,
    mcpToml.search?.context_lines_before_default,
    DEFAULTS.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE
  );
  const contextAfterResolved = resolveValue(
    mcpEnv.search?.context_lines_after_default,
    mcpToml.search?.context_lines_after_default,
    DEFAULTS.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER
  );
  const includePromptResolved = resolveValue(
    mcpEnv.search?.include_prompt_ready_default,
    mcpToml.search?.include_prompt_ready_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY
  );
  const includeResourceResolved = resolveValue(
    mcpEnv.search?.include_resource_text_default,
    mcpToml.search?.include_resource_text_default,
    DEFAULTS.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT
  );

  const clampResolved = (
    path: string,
    value: number,
    min: number,
    max: number,
    source: ConfigSource
  ): number => {
    if (value < min || value > max) {
      const clamped = Math.max(min, Math.min(max, value));
      addDiagnostic(diagnostics, {
        level: "warn",
        code: "out_of_range",
        message: `Value out of range at ${path}; clamped to ${clamped}`,
        path,
        source,
        details: { value, min, max, clamped },
      });
      return clamped;
    }
    return value;
  };

  const topKDefault = clampResolved(
    "mcp.search.top_k_default",
    topKDefaultResolved.value,
    1,
    topKMaxResolved.value,
    topKDefaultResolved.source
  );
  const snippetsTopN = clampResolved(
    "mcp.search.snippets_top_n_default",
    snippetsTopNResolved.value,
    0,
    topKMaxResolved.value,
    snippetsTopNResolved.source
  );
  const topContextN = clampResolved(
    "mcp.search.top_context_n_default",
    topContextResolved.value,
    0,
    topKMaxResolved.value,
    topContextResolved.source
  );

  const config: EffectiveConfig = {
    DOLPHIN_API_URL: apiUrlResolved.value,
    SERVER_NAME: serverNameResolved.value,
    SERVER_VERSION: serverVersionResolved.value,
    MCP_PROTOCOL_VERSION: protocolVersionResolved.value,
    LOG_LEVEL: logLevelResolved.value,
    LOG_MAX_BYTES: logMaxBytesResolved.value,
    LOG_MAX_ROTATIONS: logMaxRotationsResolved.value,
    MAX_CONCURRENT_SNIPPET_FETCH: maxConcurrentResolved.value,
    SNIPPET_FETCH_TIMEOUT_MS: timeoutResolved.value,
    SNIPPET_FETCH_RETRY_ATTEMPTS: retryResolved.value,
    MCP_LIMITS: {
      TOP_K_MAX: topKMaxResolved.value,
      SNIPPET_CHAR_CAP: snippetCharCapResolved.value,
      PAYLOAD_CAP_BYTES: payloadCapResolved.value,
    },
    RESPONSE_LIMITS: {
      SHRUNK_SNIPPET_CHAR_CAP: shrunkSnippetCharCap,
      MIN_SNIPPET_CHAR_FLOOR: minSnippetFloorResolved.value,
    },
    SEARCH_DEFAULTS: {
      TOP_K: topKDefault,
      SNIPPETS_TOP_N: snippetsTopN,
      TOP_CONTEXT_N: topContextN,
      INCLUDE_HITS_JSON: includeHitsResolved.value,
      INCLUDE_WARNINGS_IN_TEXT: includeWarningsResolved.value,
      INCLUDE_ABS_PATHS: includeAbsPathsResolved.value,
      INCLUDE_VSCODE_URIS: includeVscodeUrisResolved.value,
      INCLUDE_GRAPH_CONTEXT: includeGraphResolved.value,
      CONTEXT_LINES_BEFORE: contextBeforeResolved.value,
      CONTEXT_LINES_AFTER: contextAfterResolved.value,
      INCLUDE_PROMPT_READY: includePromptResolved.value,
      INCLUDE_RESOURCE_TEXT: includeResourceResolved.value,
    },
  };

  const sources: ConfigSources = {
    DOLPHIN_API_URL: apiUrlResolved.source,
    SERVER_NAME: serverNameResolved.source,
    SERVER_VERSION: serverVersionResolved.source,
    MCP_PROTOCOL_VERSION: protocolVersionResolved.source,
    LOG_LEVEL: logLevelResolved.source,
    LOG_MAX_BYTES: logMaxBytesResolved.source,
    LOG_MAX_ROTATIONS: logMaxRotationsResolved.source,
    MAX_CONCURRENT_SNIPPET_FETCH: maxConcurrentResolved.source,
    SNIPPET_FETCH_TIMEOUT_MS: timeoutResolved.source,
    SNIPPET_FETCH_RETRY_ATTEMPTS: retryResolved.source,
    MCP_LIMITS: {
      TOP_K_MAX: topKMaxResolved.source,
      SNIPPET_CHAR_CAP: snippetCharCapResolved.source,
      PAYLOAD_CAP_BYTES: payloadCapResolved.source,
    },
    RESPONSE_LIMITS: {
      SHRUNK_SNIPPET_CHAR_CAP: shrunkSnippetResolved.source,
      MIN_SNIPPET_CHAR_FLOOR: minSnippetFloorResolved.source,
    },
    SEARCH_DEFAULTS: {
      TOP_K: topKDefaultResolved.source,
      SNIPPETS_TOP_N: snippetsTopNResolved.source,
      TOP_CONTEXT_N: topContextResolved.source,
      INCLUDE_HITS_JSON: includeHitsResolved.source,
      INCLUDE_WARNINGS_IN_TEXT: includeWarningsResolved.source,
      INCLUDE_ABS_PATHS: includeAbsPathsResolved.source,
      INCLUDE_VSCODE_URIS: includeVscodeUrisResolved.source,
      INCLUDE_GRAPH_CONTEXT: includeGraphResolved.source,
      CONTEXT_LINES_BEFORE: contextBeforeResolved.source,
      CONTEXT_LINES_AFTER: contextAfterResolved.source,
      INCLUDE_PROMPT_READY: includePromptResolved.source,
      INCLUDE_RESOURCE_TEXT: includeResourceResolved.source,
    },
  };

  return {
    config,
    sources,
    diagnostics,
    configPath,
    configFileExists: tomlParsed.exists,
    configFileReadable: tomlParsed.readable,
  };
}

const CONFIG_LOAD = loadConfig();

/**
 * Centralized configuration object
 */
export const CONFIG: EffectiveConfig = CONFIG_LOAD.config;
export const CONFIG_SOURCES = CONFIG_LOAD.sources;
export const CONFIG_DIAGNOSTICS = CONFIG_LOAD.diagnostics;

/**
 * Validate current configuration and return any warnings
 */
export function validateConfig(): string[] {
  return CONFIG_DIAGNOSTICS.filter((diag) => diag.level === "warn" || diag.level === "error").map(
    (diag) => `${diag.path ? `${diag.path}: ` : ""}${diag.message}`
  );
}

/**
 * Get configuration summary for logging
 */
export function getConfigSummary(): Record<string, unknown> {
  return {
    dolphin_api_url: CONFIG.DOLPHIN_API_URL,
    server_name: CONFIG.SERVER_NAME,
    server_version: CONFIG.SERVER_VERSION,
    protocol_version: CONFIG.MCP_PROTOCOL_VERSION,
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
    mcp_search_top_k_default: CONFIG.SEARCH_DEFAULTS.TOP_K,
    mcp_search_snippets_top_n_default: CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N,
    mcp_search_top_context_n_default: CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N,
    mcp_search_include_hits_json_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_HITS_JSON,
    mcp_search_include_warnings_in_text_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT,
    mcp_search_include_abs_paths_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS,
    mcp_search_include_vscode_uris_default: CONFIG.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS,
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
