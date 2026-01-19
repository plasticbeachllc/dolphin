import { mkdir, appendFile, stat, rename, access } from "node:fs/promises";
import { constants as FS_CONST } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createLogger, LogMetadata, LogLevel } from "../../../shared/observability/logger.js";
import { CONFIG } from "./config.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOG_DIR = join(__dirname, "../../logs");
const LOG_FILE = join(LOG_DIR, "mcp.log");

// Simple size-based rotation
const MAX_LOG_BYTES = CONFIG.LOG_MAX_BYTES;
const MAX_ROTATIONS = CONFIG.LOG_MAX_ROTATIONS;

let logDirReady = false;

async function exists(p: string): Promise<boolean> {
  try {
    await access(p, FS_CONST.F_OK);
    return true;
  } catch {
    return false;
  }
}

async function rotateIfNeeded(): Promise<void> {
  try {
    const s = await stat(LOG_FILE);
    if (s.size < MAX_LOG_BYTES) return;
  } catch {
    // no file yet; nothing to rotate
    return;
  }

  // Rotate: mcp.log.(MAX_ROTATIONS-1) -> .MAX_ROTATIONS, ..., mcp.log.1 -> .2, mcp.log -> .1
  for (let i = MAX_ROTATIONS - 1; i >= 1; i--) {
    const src = `${LOG_FILE}.${i}`;
    const dst = `${LOG_FILE}.${i + 1}`;
    if (await exists(src)) {
      try {
        await rename(src, dst);
      } catch {
        /* ignore */
      }
    }
  }
  // Base file to .1
  try {
    if (await exists(LOG_FILE)) {
      await rename(LOG_FILE, `${LOG_FILE}.1`);
    }
  } catch {
    // ignore
  }
}

async function ensureLogDir(): Promise<void> {
  if (logDirReady) {
    return;
  }
  await mkdir(LOG_DIR, { recursive: true });
  logDirReady = true;
}

async function writeLine(line: string): Promise<void> {
  await ensureLogDir();
  await rotateIfNeeded();
  await appendFile(LOG_FILE, `${line}\n`, { encoding: "utf8" });
}

export async function initLogger(): Promise<void> {
  await ensureLogDir();
}

function toLogLevel(raw: string | undefined): LogLevel {
  switch ((raw || "info").toLowerCase()) {
    case "debug":
      return LogLevel.DEBUG;
    case "warn":
      return LogLevel.WARN;
    case "error":
      return LogLevel.ERROR;
    default:
      return LogLevel.INFO;
  }
}

const logger = createLogger("mcp-bridge", {
  sink: (line) => {
    void writeLine(line).catch(() => undefined);
  },
  minLevel: toLogLevel(CONFIG.LOG_LEVEL),
});

function buildContext(
  event: string,
  meta?: Record<string, unknown>,
  context?: Record<string, unknown>
): LogMetadata {
  return {
    event,
    ...(context ?? {}),
    ...(meta ? { meta } : {}),
  } as LogMetadata;
}

export async function logInfo(
  event: string,
  message: string,
  meta?: Record<string, unknown>,
  context?: Record<string, unknown>
): Promise<void> {
  logger.info(message, buildContext(event, meta, context));
}

export async function logDebug(
  event: string,
  message: string,
  meta?: Record<string, unknown>,
  context?: Record<string, unknown>
): Promise<void> {
  logger.debug(message, buildContext(event, meta, context));
}

export async function logWarn(
  event: string,
  message: string,
  meta?: Record<string, unknown>,
  context?: Record<string, unknown>
): Promise<void> {
  logger.warn(message, buildContext(event, meta, context));
}

export async function logError(
  event: string,
  message: string,
  meta?: Record<string, unknown>,
  context?: Record<string, unknown>
): Promise<void> {
  const errorCandidate = meta && "error" in meta ? meta.error : undefined;
  const error = errorCandidate instanceof Error ? errorCandidate : undefined;
  logger.error(message, error, buildContext(event, meta, context));
}
