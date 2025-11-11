/**
 * Structured JSONL logger with trace context integration.
 * Provides consistent logging across all Dolphin services.
 */

import { trace, context, SpanContext } from '@opentelemetry/api';

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
}

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  component: string;
  trace_id?: string;
  span_id?: string;
  [key: string]: any;
}

export class Logger {
  constructor(private component: string) {}

  private formatEntry(level: LogLevel, message: string, meta: any = {}): string {
    const span = trace.getSpan(context.active());
    const spanContext = span?.spanContext();

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      component: this.component,
      ...(spanContext && {
        trace_id: spanContext.traceId,
        span_id: spanContext.spanId,
      }),
      ...this.sanitizeMeta(meta),
    };

    return JSON.stringify(entry);
  }

  /**
   * Sanitize metadata to remove potential PII and sensitive data.
   */
  private sanitizeMeta(meta: any): any {
    if (!meta) return {};

    const sanitized = { ...meta };

    // Remove potential API keys
    for (const key in sanitized) {
      if (typeof sanitized[key] === 'string') {
        // Redact API keys (sk-*, api-*, etc.)
        sanitized[key] = sanitized[key].replace(/sk-[a-zA-Z0-9]{32,}/g, 'sk-***');
        sanitized[key] = sanitized[key].replace(/api-[a-zA-Z0-9]{32,}/g, 'api-***');

        // Redact file paths (remove username)
        sanitized[key] = sanitized[key].replace(/\/Users\/[^\/]+/g, '/Users/***');
        sanitized[key] = sanitized[key].replace(/\/home\/[^\/]+/g, '/home/***');
        sanitized[key] = sanitized[key].replace(/C:\\Users\\[^\\]+/g, 'C:\\Users\\***');
      }
    }

    return sanitized;
  }

  debug(message: string, meta?: any) {
    console.log(this.formatEntry(LogLevel.DEBUG, message, meta));
  }

  info(message: string, meta?: any) {
    console.log(this.formatEntry(LogLevel.INFO, message, meta));
  }

  warn(message: string, meta?: any) {
    console.warn(this.formatEntry(LogLevel.WARN, message, meta));
  }

  error(message: string, error?: Error, meta?: any) {
    const errorMeta = error
      ? {
          error_message: error.message,
          error_stack: error.stack,
          error_name: error.name,
        }
      : {};

    console.error(
      this.formatEntry(LogLevel.ERROR, message, {
        ...errorMeta,
        ...meta,
      })
    );
  }
}

/**
 * Factory function to create a logger for a component.
 */
export function createLogger(component: string): Logger {
  return new Logger(component);
}
