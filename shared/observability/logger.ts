/**
 * Structured JSONL logger with trace context integration.
 * Provides consistent logging across all Dolphin services.
 */

import { trace, context, SpanContext } from "@opentelemetry/api";

export enum LogLevel {
  DEBUG = "DEBUG",
  INFO = "INFO",
  WARN = "WARN",
  ERROR = "ERROR",
}

/**
 * Allowed types for log metadata values.
 * Prevents accidentally logging complex objects or functions.
 */
export type LogMetadataValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | LogMetadataValue[]
  | { [key: string]: LogMetadataValue };

export type LogMetadata = { [key: string]: LogMetadataValue };

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  trace_id?: string;
  span_id?: string;
  context: LogMetadata;
  error?: {
    type: string;
    message: string;
    traceback?: string;
  };
  [key: string]: any;
}

export interface LoggerOptions {
  sink?: (line: string, level: LogLevel) => void;
  minLevel?: LogLevel;
}

const LEVEL_RANK: Record<LogLevel, number> = {
  [LogLevel.DEBUG]: 10,
  [LogLevel.INFO]: 20,
  [LogLevel.WARN]: 30,
  [LogLevel.ERROR]: 40,
};

function normalizeLevel(raw?: string): LogLevel {
  const normalized = (raw || "info").toLowerCase();
  switch (normalized) {
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

export class Logger {
  private sink: (line: string, level: LogLevel) => void;
  private minLevel: LogLevel;

  constructor(
    private component: string,
    opts: LoggerOptions = {}
  ) {
    this.sink = opts.sink ?? ((line, level) => this.writeToConsole(line, level));
    this.minLevel = opts.minLevel ?? normalizeLevel(process.env.LOG_LEVEL);
  }

  private shouldLog(level: LogLevel): boolean {
    return LEVEL_RANK[level] >= LEVEL_RANK[this.minLevel];
  }

  private writeToConsole(line: string, level: LogLevel) {
    if (level === LogLevel.WARN) {
      console.warn(line);
      return;
    }
    if (level === LogLevel.ERROR) {
      console.error(line);
      return;
    }
    console.log(line);
  }

  private formatEntry(
    level: LogLevel,
    message: string,
    meta: LogMetadata = {},
    error?: Error
  ): string {
    const span = trace.getSpan(context.active());
    const spanContext = span?.spanContext();

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...(spanContext && {
        trace_id: spanContext.traceId,
        span_id: spanContext.spanId,
      }),
      context: {
        component: this.component,
        ...this.sanitizeMeta(meta),
      },
    };

    if (error) {
      entry.error = {
        type: error.name,
        message: error.message,
        traceback: error.stack,
      };
    }

    return JSON.stringify(entry);
  }

  /**
   * Sanitize metadata to remove potential PII and sensitive data.
   * Also handles circular references gracefully.
   */
  private sanitizeMeta(meta: any): any {
    if (!meta) return {};

    try {
      // Check for circular references by attempting JSON stringify
      JSON.stringify(meta);
    } catch (e) {
      return { error: "Failed to sanitize metadata - circular reference detected" };
    }

    const sanitized = { ...meta };

    // Remove potential API keys
    for (const key in sanitized) {
      if (typeof sanitized[key] === "string") {
        // Redact API keys (sk-*, api-*, etc.)
        sanitized[key] = sanitized[key].replace(/sk-[a-zA-Z0-9]{32,}/g, "sk-***");
        sanitized[key] = sanitized[key].replace(/api-[a-zA-Z0-9]{32,}/g, "api-***");

        // Redact file paths (remove username)
        sanitized[key] = sanitized[key].replace(/\/Users\/[^\/]+/g, "/Users/***");
        sanitized[key] = sanitized[key].replace(/\/home\/[^\/]+/g, "/home/***");
        sanitized[key] = sanitized[key].replace(/C:\\Users\\[^\\]+/g, "C:\\Users\\***");
      }
    }

    return sanitized;
  }

  debug(message: string, meta?: LogMetadata) {
    if (!this.shouldLog(LogLevel.DEBUG)) return;
    this.sink(this.formatEntry(LogLevel.DEBUG, message, meta), LogLevel.DEBUG);
  }

  info(message: string, meta?: LogMetadata) {
    if (!this.shouldLog(LogLevel.INFO)) return;
    this.sink(this.formatEntry(LogLevel.INFO, message, meta), LogLevel.INFO);
  }

  warn(message: string, meta?: LogMetadata) {
    if (!this.shouldLog(LogLevel.WARN)) return;
    this.sink(this.formatEntry(LogLevel.WARN, message, meta), LogLevel.WARN);
  }

  error(message: string, error?: Error, meta?: LogMetadata) {
    if (!this.shouldLog(LogLevel.ERROR)) return;
    this.sink(this.formatEntry(LogLevel.ERROR, message, meta, error), LogLevel.ERROR);
  }
}

/**
 * Factory function to create a logger for a component.
 */
export function createLogger(component: string, options?: LoggerOptions): Logger {
  return new Logger(component, options);
}
