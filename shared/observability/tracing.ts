/**
 * OpenTelemetry tracing configuration and utilities.
 * Provides distributed tracing across all Dolphin services.
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { SEMRESATTRS_SERVICE_NAME, SEMRESATTRS_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { trace, context, propagation, SpanStatusCode, Span, SpanAttributeValue } from '@opentelemetry/api';
import { createLogger } from './logger';

const logger = createLogger('tracing');

/**
 * Allowed types for span attributes.
 * Matches OpenTelemetry spec: string, number, boolean, or arrays thereof.
 */
export type SpanAttributes = Record<string, SpanAttributeValue>;

/**
 * Initialize OpenTelemetry tracing for a service.
 * Uses OTLP HTTP exporter (replaces deprecated Jaeger exporter).
 * Jaeger natively supports OTLP on port 4318.
 */
export function initTracing(serviceName: string, serviceVersion: string = '1.0.0') {
  const sdk = new NodeSDK({
    resource: new Resource({
      [SEMRESATTRS_SERVICE_NAME]: serviceName,
      [SEMRESATTRS_SERVICE_VERSION]: serviceVersion,
    }),
    traceExporter: new OTLPTraceExporter({
      // Jaeger OTLP HTTP endpoint (default: localhost:4318)
      url: process.env.OTLP_ENDPOINT || 'http://localhost:4318/v1/traces',
    }),
    instrumentations: [
      getNodeAutoInstrumentations({
        '@opentelemetry/instrumentation-fs': { enabled: false }, // Too noisy
      }),
    ],
  });

  sdk.start();

  // Graceful shutdown
  const shutdown = () => {
    sdk
      .shutdown()
      .then(() => logger.info('Tracing terminated'))
      .catch((error) => logger.error('Error terminating tracing', error instanceof Error ? error : undefined));
  };

  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);

  return sdk;
}

/**
 * Create a traced async function.
 */
export async function traced<T>(
  spanName: string,
  fn: (span: Span) => Promise<T>,
  attributes?: SpanAttributes
): Promise<T> {
  const tracer = trace.getTracer('dolphin');

  return tracer.startActiveSpan(spanName, async (span) => {
    // Add attributes
    if (attributes) {
      Object.entries(attributes).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          span.setAttribute(key, value);
        }
      });
    }

    try {
      const result = await fn(span);
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: error instanceof Error ? error.message : 'Unknown error',
      });
      span.recordException(error as Error);
      throw error;
    } finally {
      span.end();
    }
  });
}

/**
 * Get the current trace ID (useful for log correlation).
 */
export function getCurrentTraceId(): string | undefined {
  const span = trace.getSpan(context.active());
  return span?.spanContext().traceId;
}

/**
 * Get the current span ID (useful for log correlation).
 */
export function getCurrentSpanId(): string | undefined {
  const span = trace.getSpan(context.active());
  return span?.spanContext().spanId;
}

/**
 * Inject trace context into an object (for propagation).
 */
export function injectTraceContext(carrier: Record<string, string> = {}): Record<string, string> {
  propagation.inject(context.active(), carrier);
  return carrier;
}

/**
 * Extract trace context from an object (for propagation).
 */
export function extractTraceContext(carrier: Record<string, string>): void {
  const ctx = propagation.extract(context.active(), carrier);
  context.with(ctx, () => {
    // Set the extracted context as active
  });
}

/**
 * Semantic span names for consistent tracing.
 */
export const SpanNames = {
  // Conversations
  CONVERSATION_CREATE: 'conversation.create',
  CONVERSATION_PLAN: 'conversation.plan',
  CONVERSATION_EXECUTE: 'conversation.execute',
  CONVERSATION_COMPLETE: 'conversation.complete',

  // Planning
  MODE_SELECT: 'planner.select_mode',
  PLAN_GENERATE: 'planner.generate',
  PLAN_VALIDATE: 'planner.validate',

  // Execution
  STEP_EXECUTE: (stepType: string) => `step.${stepType}`,
  TOOL_CALL: (toolName: string) => `tool.${toolName}`,

  // LLM
  CLAUDE_REQUEST: 'llm.claude',
  CLAUDE_STREAM: 'llm.claude.stream',

  // Context
  CONTEXT_BUILD: 'context.build',
  CONTEXT_SUMMARIZE: 'context.summarize',

  // MCP
  MCP_FILE_READ: 'mcp.file_read',
  MCP_FILE_WRITE: 'mcp.file_write',
  MCP_COMMAND_EXEC: 'mcp.command_exec',
  MCP_KB_SEARCH: 'mcp.kb_search',
  MCP_ROLLBACK: 'mcp.rollback',
};
