/**
 * Prometheus metrics utilities for TypeScript/Bun services.
 * Provides helper functions for recording metrics consistently.
 */

import { register, Counter, Histogram, Gauge } from 'prom-client';

/**
 * Helper to record a tool invocation with automatic timing and error handling.
 */
export async function recordToolInvocation<T>(
  toolName: string,
  fn: () => Promise<T>,
  metricsCounters: {
    total: Counter<string>;
    duration: Histogram<string>;
  }
): Promise<T> {
  const timer = metricsCounters.duration.startTimer({ tool_name: toolName });

  try {
    const result = await fn();
    metricsCounters.total.inc({ tool_name: toolName, status: 'success' });
    return result;
  } catch (error) {
    metricsCounters.total.inc({ tool_name: toolName, status: 'error' });
    throw error;
  } finally {
    timer();
  }
}

/**
 * Get metrics in Prometheus text format.
 */
export function getMetrics(): Promise<string> {
  return register.metrics();
}

/**
 * Clear all metrics (useful for testing).
 */
export function clearMetrics(): void {
  register.clear();
}

/**
 * Create a basic HTTP server for metrics endpoint.
 */
export function createMetricsServer(port: number = 9091): void {
  const server = Bun.serve({
    port,
    async fetch(req) {
      const url = new URL(req.url);

      if (url.pathname === '/metrics') {
        const metrics = await getMetrics();
        return new Response(metrics, {
          headers: {
            'Content-Type': 'text/plain; version=0.0.4',
          },
        });
      }

      if (url.pathname === '/health') {
        return new Response(
          JSON.stringify({
            status: 'healthy',
            timestamp: new Date().toISOString(),
          }),
          {
            headers: {
              'Content-Type': 'application/json',
            },
          }
        );
      }

      return new Response('Not Found', { status: 404 });
    },
  });

  console.log(`Metrics server listening on http://localhost:${port}`);
}
