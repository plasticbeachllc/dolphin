# EP-1: Production Observability & Monitoring
## Detailed Implementation Plan for Dolphin VSCode Extension

**Document Version:** 1.0  
**Date:** November 10, 2025  
**Status:** Ready for Implementation  
**Timeline:** 4-6 weeks (3 phases)  
**Project:** Dolphin AI Coding Assistant

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Integration](#architecture-integration)
3. [Phase 1: Core Metrics & Structured Logging (2 weeks)](#phase-1-core-metrics--structured-logging-2-weeks)
4. [Phase 2: Distributed Tracing (2 weeks)](#phase-2-distributed-tracing-2-weeks)
5. [Phase 3: Dashboards, Alerting & Cost Tracking (2 weeks)](#phase-3-dashboards-alerting--cost-tracking-2-weeks)
6. [Technology Stack Decisions](#technology-stack-decisions)
7. [Implementation Guides by Component](#implementation-guides-by-component)
8. [Privacy & Compliance](#privacy--compliance)
9. [Testing Strategy](#testing-strategy)
10. [Success Criteria & Metrics](#success-criteria--metrics)

---

## Executive Summary

### Vision

Implement a comprehensive, privacy-first observability suite that provides real-time insights into Dolphin's performance, health, and usage patterns across all architectural layers. Enable proactive issue detection and data-driven optimization while respecting user privacy.

### Key Design Principles

1. **Privacy First**: All telemetry is opt-in, anonymous by default, with transparent disclosure
2. **Layer-Aware**: Metrics specific to each architectural layer (Extension, Agent Core, MCP Bridge, KB API)
3. **Lightweight**: Minimal performance overhead (<5ms latency added)
4. **Self-Hosted**: Use open-source tools (Prometheus, Grafana, Jaeger) - no vendor lock-in
5. **Fail-Safe**: Observability failures never crash the application

### Business Impact

- **Operational Excellence**: 80% reduction in MTTR through proactive monitoring
- **Performance Insights**: Identify bottlenecks with distributed tracing
- **Cost Control**: Track Claude API & embedding costs per-session
- **User Trust**: Transparent, opt-in telemetry builds community trust
- **Data-Driven**: Optimize based on real usage patterns

---

## Architecture Integration

### Current Dolphin Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 1: VSCode Extension (Node.js/TypeScript)                 │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Observability: Extension Telemetry Service              │    │
│ │ • User interactions (command usage, webview events)     │    │
│ │ • Extension lifecycle (activation, crashes)             │    │
│ │ • File watcher events (sync operations)                 │    │
│ └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬────────────────────────────────────┘
                            │ stdio/JSON-RPC + Trace Context
┌───────────────────────────▼────────────────────────────────────┐
│ Layer 2: Agent Core (Bun/TypeScript)                           │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Observability: Agent Metrics & Tracing                  │    │
│ │ • Conversation lifecycle (creation, duration, messages) │    │
│ │ • Claude API metrics (tokens, latency, costs)           │    │
│ │ • Planning & execution (mode selection, step duration)  │    │
│ │ • MCP tool invocations (calls, success/failure rates)   │    │
│ └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬────────────────────────────────────┘
                            │ MCP Protocol + Span Context
┌───────────────────────────▼────────────────────────────────────┐
│ Layer 3: MCP Bridge (Bun/TypeScript)                           │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Observability: Tool Execution Metrics                   │    │
│ │ • File operations (read/write latency, sizes)           │    │
│ │ • Command execution (whitelisted commands, failures)    │    │
│ │ • Rollback operations (frequency, success rate)         │    │
│ └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬────────────────────────────────────┘
                            │ HTTP + Span Context
┌───────────────────────────▼────────────────────────────────────┐
│ Layer 4: Knowledge Bank API (Python/FastAPI)                   │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Observability: KB API Metrics (ENHANCE EXISTING)        │    │
│ │ • Endpoint latency (p50, p95, p99)                      │    │
│ │ • Search metrics (ANN parameters, result counts)        │    │
│ │ • Embedding costs (tokens, API latency)                 │    │
│ │ • Database operations (SQLite, LanceDB timing)          │    │
│ └─────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
```

### Cross-Cutting Concerns

```
┌────────────────────────────────────────────────────────────────┐
│ Observability Backend (Self-Hosted)                            │
│                                                                 │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│ │ Prometheus   │  │ Jaeger       │  │ Loki         │          │
│ │ (Metrics)    │  │ (Traces)     │  │ (Logs)       │          │
│ └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│        │                 │                  │                   │
│        └─────────────────┴──────────────────┘                   │
│                          │                                      │
│                   ┌──────▼───────┐                              │
│                   │   Grafana    │                              │
│                   │ (Dashboards) │                              │
│                   └──────────────┘                              │
└────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Metrics & Structured Logging (2 weeks)

### Objectives

1. Implement Prometheus metrics in all layers
2. Standardize JSONL structured logging
3. Add health check endpoints
4. Create basic Grafana dashboards

### Week 1: Layer 4 (KB API) & Layer 3 (MCP Bridge)

#### Day 1-2: KB API Metrics (Python/FastAPI)

**File:** `kb/api/middleware/metrics.py`

```python
"""
Prometheus metrics middleware for FastAPI.
Instruments all endpoints with request/response metrics.
"""

from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    generate_latest, CONTENT_TYPE_LATEST
)
from fastapi import Request, Response
from fastapi.responses import Response as FastAPIResponse
from typing import Callable
import time

# ============================================================================
# Metrics Definitions
# ============================================================================

# Request metrics
http_requests_total = Counter(
    'kb_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code', 'repo_name']
)

http_request_duration_seconds = Histogram(
    'kb_http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint', 'repo_name'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Search-specific metrics
search_queries_total = Counter(
    'kb_search_queries_total',
    'Total search queries',
    ['repo_name', 'search_type']  # search_type: semantic, hybrid, keyword
)

search_result_count = Histogram(
    'kb_search_result_count',
    'Number of results returned per search',
    ['repo_name', 'search_type'],
    buckets=[0, 1, 5, 10, 20, 50, 100]
)

search_query_tokens = Histogram(
    'kb_search_query_tokens',
    'Query token count',
    ['repo_name'],
    buckets=[10, 25, 50, 100, 200, 500]
)

# Embedding metrics
embedding_tokens_total = Counter(
    'kb_embedding_tokens_total',
    'Total tokens embedded',
    ['repo_name']
)

embedding_api_latency_seconds = Histogram(
    'kb_embedding_api_latency_seconds',
    'OpenAI embedding API latency',
    ['repo_name'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

embedding_cost_usd = Counter(
    'kb_embedding_cost_usd',
    'Total embedding costs in USD',
    ['repo_name', 'model']
)

# Database metrics
db_query_duration_seconds = Histogram(
    'kb_db_query_duration_seconds',
    'Database query duration',
    ['operation', 'table'],  # operation: select, insert, update, delete
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

vector_search_duration_seconds = Histogram(
    'kb_vector_search_duration_seconds',
    'LanceDB vector search duration',
    ['repo_name'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

# Index metrics
index_size_bytes = Gauge(
    'kb_index_size_bytes',
    'Total index size in bytes',
    ['repo_name']
)

indexed_chunks_total = Gauge(
    'kb_indexed_chunks_total',
    'Total number of indexed chunks',
    ['repo_name']
)

# System info
kb_info = Info(
    'kb_api',
    'Knowledge Bank API information'
)
kb_info.info({
    'version': '1.0.0',
    'python_version': '3.12'
})

# ============================================================================
# Middleware
# ============================================================================

async def prometheus_middleware(request: Request, call_next: Callable):
    """
    Middleware to record HTTP request metrics.
    Adds minimal overhead: ~1-2ms per request.
    """
    # Extract metadata
    method = request.method
    path = request.url.path
    
    # Extract repo_name from query params or path
    repo_name = request.query_params.get('repo_name', 'unknown')
    
    # Start timer
    start_time = time.perf_counter()
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise
    finally:
        # Record metrics
        duration = time.perf_counter() - start_time
        
        http_requests_total.labels(
            method=method,
            endpoint=path,
            status_code=status_code,
            repo_name=repo_name
        ).inc()
        
        http_request_duration_seconds.labels(
            method=method,
            endpoint=path,
            repo_name=repo_name
        ).observe(duration)
    
    return response


# ============================================================================
# Metrics Endpoint
# ============================================================================

async def metrics_endpoint(request: Request) -> FastAPIResponse:
    """
    Expose Prometheus metrics at /metrics endpoint.
    """
    return FastAPIResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

**File:** `kb/api/main.py` (add middleware)

```python
from fastapi import FastAPI
from .middleware.metrics import prometheus_middleware, metrics_endpoint

app = FastAPI()

# Add metrics middleware
app.middleware("http")(prometheus_middleware)

# Add metrics endpoint
app.get("/metrics")(metrics_endpoint)

# Enhanced health check with component status
@app.get("/v1/health")
async def health_check():
    """
    Enhanced health check with component status.
    """
    return {
        "status": "healthy",
        "components": {
            "lancedb": await check_lancedb_health(),
            "sqlite": await check_sqlite_health(),
            "openai": await check_openai_health()
        },
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }
```

**File:** `kb/search/semantic.py` (instrument search)

```python
from ..api.middleware.metrics import (
    search_queries_total,
    search_result_count,
    search_query_tokens,
    vector_search_duration_seconds
)
import time

async def semantic_search(query: str, repo_name: str, limit: int = 10):
    """
    Instrumented semantic search function.
    """
    # Record query
    search_queries_total.labels(
        repo_name=repo_name,
        search_type='semantic'
    ).inc()
    
    # Count tokens (rough approximation)
    token_count = len(query.split())
    search_query_tokens.labels(repo_name=repo_name).observe(token_count)
    
    # Time vector search
    start = time.perf_counter()
    results = await _do_vector_search(query, repo_name, limit)
    duration = time.perf_counter() - start
    
    vector_search_duration_seconds.labels(repo_name=repo_name).observe(duration)
    search_result_count.labels(
        repo_name=repo_name,
        search_type='semantic'
    ).observe(len(results))
    
    return results
```

#### Day 3-4: MCP Bridge Metrics (Bun/TypeScript)

**File:** `mcp-bridge/src/metrics/prometheus.ts`

```typescript
/**
 * Prometheus metrics for MCP Bridge.
 * Tracks file operations, command execution, and tool invocations.
 */

import { register, Counter, Histogram, Gauge } from 'prom-client';

// ============================================================================
// Metrics Definitions
// ============================================================================

export const toolInvocationsTotal = new Counter({
  name: 'mcp_tool_invocations_total',
  help: 'Total tool invocations',
  labelNames: ['tool_name', 'status'], // status: success, error
});

export const toolDurationSeconds = new Histogram({
  name: 'mcp_tool_duration_seconds',
  help: 'Tool execution duration',
  labelNames: ['tool_name'],
  buckets: [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
});

// File operation metrics
export const fileOperationsTotal = new Counter({
  name: 'mcp_file_operations_total',
  help: 'Total file operations',
  labelNames: ['operation', 'status'], // operation: read, write, diff, rollback
});

export const fileOperationSizeBytes = new Histogram({
  name: 'mcp_file_operation_size_bytes',
  help: 'File operation size in bytes',
  labelNames: ['operation'],
  buckets: [100, 1000, 10000, 100000, 1000000, 10000000],
});

export const fileDiffLinesHistogram = new Histogram({
  name: 'mcp_file_diff_lines',
  help: 'Number of lines in diff',
  buckets: [1, 5, 10, 25, 50, 100, 500, 1000],
});

// Command execution metrics
export const commandExecutionsTotal = new Counter({
  name: 'mcp_command_executions_total',
  help: 'Total command executions',
  labelNames: ['command', 'status'], // command: whitelisted name
});

export const commandDurationSeconds = new Histogram({
  name: 'mcp_command_duration_seconds',
  help: 'Command execution duration',
  labelNames: ['command'],
  buckets: [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
});

// Rollback metrics
export const rollbackOperationsTotal = new Counter({
  name: 'mcp_rollback_operations_total',
  help: 'Total rollback operations',
  labelNames: ['status'],
});

export const rollbackFilesCount = new Histogram({
  name: 'mcp_rollback_files_count',
  help: 'Number of files in rollback',
  buckets: [1, 5, 10, 25, 50],
});

// KB search metrics (from MCP perspective)
export const kbSearchRequestsTotal = new Counter({
  name: 'mcp_kb_search_requests_total',
  help: 'Total KB search requests from MCP',
  labelNames: ['status'],
});

export const kbSearchDurationSeconds = new Histogram({
  name: 'mcp_kb_search_duration_seconds',
  help: 'KB search request duration',
  buckets: [0.1, 0.5, 1.0, 2.0, 5.0],
});

// ============================================================================
// Helper Functions
// ============================================================================

export async function recordToolInvocation<T>(
  toolName: string,
  fn: () => Promise<T>
): Promise<T> {
  const timer = toolDurationSeconds.startTimer({ tool_name: toolName });
  
  try {
    const result = await fn();
    toolInvocationsTotal.inc({ tool_name: toolName, status: 'success' });
    return result;
  } catch (error) {
    toolInvocationsTotal.inc({ tool_name: toolName, status: 'error' });
    throw error;
  } finally {
    timer();
  }
}

export function getMetrics(): string {
  return register.metrics();
}

export function clearMetrics(): void {
  register.clear();
}
```

**File:** `mcp-bridge/src/tools/file-write.ts` (instrumented)

```typescript
import {
  fileOperationsTotal,
  fileOperationSizeBytes,
  fileDiffLinesHistogram,
  recordToolInvocation
} from '../metrics/prometheus';

export async function fileWrite(args: FileWriteArgs): Promise<FileWriteResult> {
  return recordToolInvocation('file_write', async () => {
    const { path, content } = args;
    
    try {
      // Write file
      await Bun.write(path, content);
      
      // Record metrics
      fileOperationsTotal.inc({ operation: 'write', status: 'success' });
      fileOperationSizeBytes.observe(
        { operation: 'write' },
        Buffer.byteLength(content, 'utf8')
      );
      
      // If this is a diff, count lines
      if (content.includes('---') && content.includes('+++')) {
        const lines = content.split('\n').length;
        fileDiffLinesHistogram.observe(lines);
      }
      
      return { success: true, path };
    } catch (error) {
      fileOperationsTotal.inc({ operation: 'write', status: 'error' });
      throw error;
    }
  });
}
```

**File:** `mcp-bridge/src/server.ts` (add metrics endpoint)

```typescript
import { Hono } from 'hono';
import { getMetrics } from './metrics/prometheus';

const app = new Hono();

// Metrics endpoint
app.get('/metrics', (c) => {
  return c.text(getMetrics(), 200, {
    'Content-Type': 'text/plain; version=0.0.4',
  });
});

export default app;
```

#### Day 5-7: Agent Core Metrics (Bun/TypeScript)

**File:** `agent-core/src/metrics/prometheus.ts`

```typescript
/**
 * Prometheus metrics for Agent Core.
 * Tracks conversations, Claude API usage, planning, and execution.
 */

import { register, Counter, Histogram, Gauge } from 'prom-client';

// ============================================================================
// Conversation Lifecycle
// ============================================================================

export const conversationsTotal = new Counter({
  name: 'agent_conversations_total',
  help: 'Total conversations created',
  labelNames: ['mode'], // mode: editor, architect, debug
});

export const conversationDurationSeconds = new Histogram({
  name: 'agent_conversation_duration_seconds',
  help: 'Conversation duration from start to completion',
  labelNames: ['mode'],
  buckets: [10, 30, 60, 120, 300, 600, 1800, 3600],
});

export const conversationMessagesCount = new Histogram({
  name: 'agent_conversation_messages_count',
  help: 'Number of messages in conversation',
  labelNames: ['mode'],
  buckets: [1, 5, 10, 20, 50, 100],
});

export const activeConversations = new Gauge({
  name: 'agent_active_conversations',
  help: 'Number of currently active conversations',
});

// ============================================================================
// Claude API Metrics
// ============================================================================

export const claudeRequestsTotal = new Counter({
  name: 'agent_claude_requests_total',
  help: 'Total Claude API requests',
  labelNames: ['model', 'status'], // status: success, error
});

export const claudeTokensTotal = new Counter({
  name: 'agent_claude_tokens_total',
  help: 'Total Claude tokens consumed',
  labelNames: ['model', 'type'], // type: input, output
});

export const claudeLatencySeconds = new Histogram({
  name: 'agent_claude_latency_seconds',
  help: 'Claude API request latency',
  labelNames: ['model'],
  buckets: [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0],
});

export const claudeCostUsd = new Counter({
  name: 'agent_claude_cost_usd',
  help: 'Total Claude API costs in USD',
  labelNames: ['model'],
});

export const claudeStreamingChunks = new Counter({
  name: 'agent_claude_streaming_chunks_total',
  help: 'Total streaming chunks received',
  labelNames: ['model'],
});

// ============================================================================
// Planning & Execution
// ============================================================================

export const plansCreatedTotal = new Counter({
  name: 'agent_plans_created_total',
  help: 'Total plans created',
  labelNames: ['mode'],
});

export const planStepsCount = new Histogram({
  name: 'agent_plan_steps_count',
  help: 'Number of steps in plan',
  labelNames: ['mode'],
  buckets: [1, 3, 5, 10, 20, 50],
});

export const stepExecutionDurationSeconds = new Histogram({
  name: 'agent_step_execution_duration_seconds',
  help: 'Step execution duration',
  labelNames: ['step_type'], // step_type: search, edit, command, review
  buckets: [0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
});

export const planSuccessRate = new Counter({
  name: 'agent_plan_completions_total',
  help: 'Total plan completions',
  labelNames: ['status'], // status: success, partial, failed, cancelled
});

// ============================================================================
// MCP Tool Calls (from Agent perspective)
// ============================================================================

export const mcpToolCallsTotal = new Counter({
  name: 'agent_mcp_tool_calls_total',
  help: 'Total MCP tool calls',
  labelNames: ['tool', 'status'],
});

export const mcpToolCallDurationSeconds = new Histogram({
  name: 'agent_mcp_tool_call_duration_seconds',
  help: 'MCP tool call duration',
  labelNames: ['tool'],
  buckets: [0.01, 0.1, 0.5, 1.0, 5.0, 10.0],
});

// ============================================================================
// Context Management
// ============================================================================

export const contextWindowTokens = new Histogram({
  name: 'agent_context_window_tokens',
  help: 'Context window size in tokens',
  labelNames: ['mode'],
  buckets: [1000, 5000, 10000, 20000, 50000, 100000, 200000],
});

export const contextTruncationsTotal = new Counter({
  name: 'agent_context_truncations_total',
  help: 'Times context had to be truncated',
  labelNames: ['reason'], // reason: token_limit, summarization
});

// ============================================================================
// Error Tracking
// ============================================================================

export const errorsTotal = new Counter({
  name: 'agent_errors_total',
  help: 'Total errors encountered',
  labelNames: ['component', 'error_type'],
});

export const recoveriesTotal = new Counter({
  name: 'agent_recoveries_total',
  help: 'Total successful error recoveries',
  labelNames: ['recovery_type'], // recovery_type: retry, rollback, replan
});

// ============================================================================
// Helper Functions
// ============================================================================

export function recordClaudeRequest(
  model: string,
  inputTokens: number,
  outputTokens: number,
  latencyMs: number,
  success: boolean
) {
  // Record request
  claudeRequestsTotal.inc({
    model,
    status: success ? 'success' : 'error',
  });
  
  // Record tokens
  if (success) {
    claudeTokensTotal.inc({ model, type: 'input' }, inputTokens);
    claudeTokensTotal.inc({ model, type: 'output' }, outputTokens);
    
    // Calculate cost (Claude Sonnet 4.5 pricing)
    const inputCost = (inputTokens / 1_000_000) * 3.0;
    const outputCost = (outputTokens / 1_000_000) * 15.0;
    claudeCostUsd.inc({ model }, inputCost + outputCost);
  }
  
  // Record latency
  claudeLatencySeconds.observe({ model }, latencyMs / 1000);
}

export function getMetrics(): string {
  return register.metrics();
}
```

#### Week 2: Layer 1 (VSCode Extension) & Structured Logging

**File:** `vscode-extension/src/telemetry/service.ts`

```typescript
/**
 * Privacy-first telemetry service for VSCode Extension.
 * Follows VSCode best practices and Cline's approach.
 */

import * as vscode from 'vscode';

interface TelemetryEvent {
  name: string;
  properties?: Record<string, string | number | boolean>;
  measurements?: Record<string, number>;
}

export class TelemetryService {
  private enabled: boolean = false;
  private readonly outputChannel: vscode.OutputChannel;
  private readonly context: vscode.ExtensionContext;
  
  // Event counters (in-memory for dashboard)
  private metrics = {
    commandUsage: new Map<string, number>(),
    webviewEvents: new Map<string, number>(),
    fileWatcherEvents: 0,
    crashes: 0,
  };
  
  constructor(context: vscode.ExtensionContext) {
    this.context = context;
    this.outputChannel = vscode.window.createOutputChannel('Dolphin Telemetry');
    
    // Check telemetry setting
    this.updateTelemetrySettings();
    
    // Listen for setting changes
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('dolphin.telemetry.enabled')) {
        this.updateTelemetrySettings();
      }
    });
  }
  
  private updateTelemetrySettings() {
    const config = vscode.workspace.getConfiguration('dolphin');
    this.enabled = config.get('telemetry.enabled', false);
    
    if (this.enabled) {
      this.outputChannel.appendLine('Telemetry enabled (opt-in)');
    }
  }
  
  /**
   * Record a telemetry event (always anonymous).
   */
  sendEvent(event: TelemetryEvent) {
    if (!this.enabled) return;
    
    // Log to output channel for transparency
    this.outputChannel.appendLine(JSON.stringify({
      timestamp: new Date().toISOString(),
      type: 'event',
      ...event,
    }));
    
    // Update in-memory metrics
    if (event.name.startsWith('command.')) {
      const count = this.metrics.commandUsage.get(event.name) || 0;
      this.metrics.commandUsage.set(event.name, count + 1);
    }
  }
  
  /**
   * Record extension activation time.
   */
  recordActivation(durationMs: number) {
    this.sendEvent({
      name: 'extension.activated',
      measurements: { duration_ms: durationMs },
    });
  }
  
  /**
   * Record command usage.
   */
  recordCommand(commandId: string) {
    this.sendEvent({
      name: `command.${commandId}`,
      properties: { command: commandId },
    });
  }
  
  /**
   * Record webview interaction.
   */
  recordWebviewEvent(eventType: string, properties?: Record<string, any>) {
    this.sendEvent({
      name: `webview.${eventType}`,
      properties,
    });
  }
  
  /**
   * Record crash/error.
   */
  recordError(errorType: string, fatal: boolean) {
    this.sendEvent({
      name: 'extension.error',
      properties: {
        error_type: errorType,
        fatal: fatal.toString(),
      },
    });
    
    if (fatal) {
      this.metrics.crashes++;
    }
  }
  
  /**
   * Get metrics for status bar display.
   */
  getMetrics() {
    return {
      commandUsage: Object.fromEntries(this.metrics.commandUsage),
      webviewEvents: Object.fromEntries(this.metrics.webviewEvents),
      fileWatcherEvents: this.metrics.fileWatcherEvents,
      crashes: this.metrics.crashes,
    };
  }
  
  dispose() {
    this.outputChannel.dispose();
  }
}
```

**File:** `vscode-extension/package.json` (add settings)

```json
{
  "contributes": {
    "configuration": {
      "title": "Dolphin",
      "properties": {
        "dolphin.telemetry.enabled": {
          "type": "boolean",
          "default": false,
          "markdownDescription": "Help improve Dolphin by sending anonymous usage data. [Learn more](https://github.com/dolphin-ai/dolphin/blob/main/TELEMETRY.md)",
          "scope": "application",
          "tags": ["telemetry", "usesOnlineServices"]
        }
      }
    }
  }
}
```

**Structured Logging Implementation**

**File:** `agent-core/src/logging/logger.ts`

```typescript
/**
 * Structured JSONL logger with trace context integration.
 */

import { inspect } from 'node:util';
import { trace, context } from '@opentelemetry/api';

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
}

interface LogEntry {
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
      ...meta,
    };
    
    return JSON.stringify(entry);
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
    const errorMeta = error ? {
      error_message: error.message,
      error_stack: error.stack,
      error_name: error.name,
    } : {};
    
    console.error(this.formatEntry(LogLevel.ERROR, message, {
      ...errorMeta,
      ...meta,
    }));
  }
}

// Factory function
export function createLogger(component: string): Logger {
  return new Logger(component);
}
```

### Deliverables (Phase 1)

- [ ] KB API `/metrics` endpoint exposing Prometheus metrics
- [ ] MCP Bridge `/metrics` endpoint with file/command metrics
- [ ] Agent Core metrics tracking conversations and Claude API
- [ ] VSCode Extension opt-in telemetry service
- [ ] Structured JSONL logging across all components
- [ ] Basic Grafana dashboard (prototype)

---

## Phase 2: Distributed Tracing (2 weeks)

### Objectives

1. Implement OpenTelemetry spans across all layers
2. Propagate trace context through stdio/HTTP
3. Set up Jaeger for trace visualization
4. Create trace-to-log correlation

### Architecture: Trace Propagation

```
User Request in VSCode Extension
  │
  ├─> [Trace ID: abc123, Span: ext-001] Extension receives command
  │
  ├─> stdio message with trace context ──────────────────┐
  │                                                       │
  └─> [Trace ID: abc123, Span: agent-001] Agent Core    │
        │                                                 │
        ├─> [Trace ID: abc123, Span: agent-002] Plan     │
        ├─> [Trace ID: abc123, Span: agent-003] Execute  │
        │     │                                           │
        │     ├─> MCP call with span context ────────────┼───┐
        │     │                                           │   │
        │     └─> [Trace ID: abc123, Span: mcp-001]      │   │
        │           MCP Bridge file_write                 │   │
        │             │                                   │   │
        │             └─> HTTP request with headers ─────┼───┼───┐
        │                                                 │   │   │
        └─> [Trace ID: abc123, Span: kb-001]             │   │   │
              KB API /v1/search                           │   │   │
                │                                         │   │   │
                └─> [Trace ID: abc123, Span: kb-002]     │   │   │
                      LanceDB vector search               │   │   │
```

### Week 3: OpenTelemetry Setup

**File:** `shared/tracing/config.ts`

```typescript
/**
 * OpenTelemetry configuration shared across all TypeScript components.
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { JaegerExporter } from '@opentelemetry/exporter-jaeger';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';

export function initTracing(serviceName: string) {
  const sdk = new NodeSDK({
    resource: new Resource({
      [SemanticResourceAttributes.SERVICE_NAME]: serviceName,
      [SemanticResourceAttributes.SERVICE_VERSION]: '1.0.0',
    }),
    traceExporter: new JaegerExporter({
      endpoint: process.env.JAEGER_ENDPOINT || 'http://localhost:14268/api/traces',
    }),
    instrumentations: [
      getNodeAutoInstrumentations({
        '@opentelemetry/instrumentation-fs': { enabled: false }, // Too noisy
      }),
    ],
  });
  
  sdk.start();
  
  // Graceful shutdown
  process.on('SIGTERM', () => {
    sdk.shutdown()
      .then(() => console.log('Tracing terminated'))
      .catch((error) => console.error('Error terminating tracing', error));
  });
  
  return sdk;
}
```

**File:** `agent-core/src/main.ts` (initialize tracing)

```typescript
import { initTracing } from '../shared/tracing/config';
import { trace } from '@opentelemetry/api';

// Initialize tracing FIRST
const sdk = initTracing('dolphin-agent-core');

// Get tracer
const tracer = trace.getTracer('dolphin-agent-core', '1.0.0');

async function handleUserMessage(message: UserMessage) {
  // Create root span for this conversation turn
  return tracer.startActiveSpan('handle_user_message', async (span) => {
    span.setAttribute('message.id', message.id);
    span.setAttribute('message.length', message.content.length);
    
    try {
      const result = await processMessage(message);
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: error.message,
      });
      span.recordException(error);
      throw error;
    } finally {
      span.end();
    }
  });
}
```

**File:** `agent-core/src/mcp/client.ts` (propagate context)

```typescript
import { context, propagation } from '@opentelemetry/api';

export class MCPClient {
  async callTool(toolName: string, args: any) {
    return tracer.startActiveSpan(`mcp.${toolName}`, async (span) => {
      // Inject trace context into MCP message
      const carrier: Record<string, string> = {};
      propagation.inject(context.active(), carrier);
      
      const message = {
        jsonrpc: '2.0',
        method: 'tools/call',
        params: {
          name: toolName,
          arguments: args,
        },
        // Include trace context
        _trace: carrier,
      };
      
      try {
        const result = await this.sendMessage(message);
        span.setStatus({ code: SpanStatusCode.OK });
        return result;
      } catch (error) {
        span.recordException(error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }
}
```

**File:** `kb/api/middleware/tracing.py` (Python OpenTelemetry)

```python
"""
OpenTelemetry tracing middleware for FastAPI.
"""

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from fastapi import Request

# Initialize tracing
trace.set_tracer_provider(
    TracerProvider(
        resource=Resource.create({
            "service.name": "dolphin-kb-api",
            "service.version": "1.0.0"
        })
    )
)

jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)

trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Auto-instrument FastAPI
def setup_tracing(app):
    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()

# Extract trace context from incoming requests
async def trace_context_middleware(request: Request, call_next):
    """
    Extract trace context from headers and set as active span.
    """
    from opentelemetry.propagate import extract
    
    # Extract context from headers
    ctx = extract(request.headers)
    
    # Set as active context
    with trace.use_span(
        trace.get_current_span(),
        end_on_exit=False
    ):
        response = await call_next(request)
    
    return response
```

### Deliverables (Phase 2)

- [ ] OpenTelemetry instrumentation in all 4 layers
- [ ] Trace context propagation through stdio/MCP/HTTP
- [ ] Jaeger instance running (docker-compose)
- [ ] Trace-to-log correlation with trace_id in logs
- [ ] Documentation: "How to Read a Trace Waterfall"

---

## Phase 3: Dashboards, Alerting & Cost Tracking (2 weeks)

### Week 5: Grafana Dashboards

**Dashboard 1: System Health Overview**

```yaml
# grafana/dashboards/system-health.json
{
  "title": "Dolphin System Health",
  "panels": [
    {
      "title": "Request Rate (req/s)",
      "targets": [
        {
          "expr": "sum(rate(kb_http_requests_total[5m])) by (endpoint)",
          "legendFormat": "{{endpoint}}"
        }
      ]
    },
    {
      "title": "Error Rate (%)",
      "targets": [
        {
          "expr": "sum(rate(kb_http_requests_total{status_code=~\"5..\"}[5m])) / sum(rate(kb_http_requests_total[5m])) * 100"
        }
      ]
    },
    {
      "title": "P95 Latency (ms)",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, sum(rate(kb_http_request_duration_seconds_bucket[5m])) by (le, endpoint)) * 1000"
        }
      ]
    },
    {
      "title": "Active Conversations",
      "targets": [
        {
          "expr": "agent_active_conversations"
        }
      ]
    }
  ]
}
```

**Dashboard 2: Claude API Costs**

```yaml
{
  "title": "Claude API Costs & Usage",
  "panels": [
    {
      "title": "Cost per Hour ($)",
      "targets": [
        {
          "expr": "increase(agent_claude_cost_usd[1h])"
        }
      ]
    },
    {
      "title": "Tokens Consumed",
      "targets": [
        {
          "expr": "sum(rate(agent_claude_tokens_total[5m])) by (type)"
        }
      ]
    },
    {
      "title": "Average Tokens per Request",
      "targets": [
        {
          "expr": "sum(increase(agent_claude_tokens_total[5m])) / sum(increase(agent_claude_requests_total[5m]))"
        }
      ]
    }
  ]
}
```

**Dashboard 3: Search Performance**

```yaml
{
  "title": "KB Search Performance",
  "panels": [
    {
      "title": "Search Latency Distribution",
      "targets": [
        {
          "expr": "sum(rate(kb_vector_search_duration_seconds_bucket[5m])) by (le)"
        }
      ]
    },
    {
      "title": "Results per Search",
      "targets": [
        {
          "expr": "histogram_quantile(0.50, sum(rate(kb_search_result_count_bucket[5m])) by (le))"
        }
      ]
    }
  ]
}
```

### Week 6: Alerting Rules

**File:** `observability/prometheus/alerts.yml`

```yaml
groups:
  - name: dolphin_critical
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          sum(rate(kb_http_requests_total{status_code=~"5.."}[5m]))
          / sum(rate(kb_http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
          component: kb-api
        annotations:
          summary: "KB API error rate above 5%"
          description: "{{ $value | humanizePercentage }} of requests are failing"
      
      # High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(kb_http_request_duration_seconds_bucket[5m])) by (le, endpoint)
          ) > 2.0
        for: 5m
        labels:
          severity: warning
          component: kb-api
        annotations:
          summary: "KB API P95 latency above 2s"
          description: "Endpoint {{ $labels.endpoint }} is slow"
      
      # Cost spike
      - alert: CostSpike
        expr: |
          increase(agent_claude_cost_usd[1h]) > 10.0
        labels:
          severity: warning
          component: agent-core
        annotations:
          summary: "Claude API costs exceeding $10/hour"
          description: "Current hourly cost: ${{ $value }}"
      
      # Service down
      - alert: ServiceDown
        expr: up{job="kb-api"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "KB API is down"
          description: "Health check failed"
      
      # Index size growth
      - alert: IndexGrowthAnomaly
        expr: |
          increase(kb_index_size_bytes[1h]) > 1e9
        labels:
          severity: warning
          component: kb-api
        annotations:
          summary: "Index growing >1GB per hour"
          description: "Possible runaway indexing"
```

**Cost Tracking Implementation**

**File:** `agent-core/src/cost/tracker.ts`

```typescript
/**
 * Real-time cost tracking with budget enforcement.
 */

export interface CostTracker {
  recordTokens(model: string, inputTokens: number, outputTokens: number): void;
  recordEmbedding(model: string, tokens: number): void;
  getCurrentCost(): CostSummary;
  checkBudget(): boolean;
}

interface CostSummary {
  claudeApiCost: number;
  embeddingCost: number;
  totalCost: number;
  projectedDailyCost: number;
}

// Pricing (as of Nov 2025)
const PRICING = {
  'claude-sonnet-4.5': {
    input: 3.0 / 1_000_000,  // $3 per 1M tokens
    output: 15.0 / 1_000_000, // $15 per 1M tokens
  },
  'text-embedding-3-small': {
    tokens: 0.02 / 1_000_000, // $0.02 per 1M tokens
  },
};

export class CostTrackerImpl implements CostTracker {
  private costs = {
    claude: 0,
    embeddings: 0,
  };
  
  private readonly sessionStart = Date.now();
  private readonly dailyBudget: number;
  
  constructor(dailyBudget: number = 100) {
    this.dailyBudget = dailyBudget;
  }
  
  recordTokens(model: string, inputTokens: number, outputTokens: number) {
    const pricing = PRICING[model];
    if (!pricing) return;
    
    const cost = 
      inputTokens * pricing.input +
      outputTokens * pricing.output;
    
    this.costs.claude += cost;
    
    // Also record to Prometheus
    claudeCostUsd.inc({ model }, cost);
  }
  
  recordEmbedding(model: string, tokens: number) {
    const pricing = PRICING[model];
    if (!pricing) return;
    
    const cost = tokens * pricing.tokens;
    this.costs.embeddings += cost;
    
    // Record to Prometheus
    embedding_cost_usd.inc({ model, repo_name: 'session' }, cost);
  }
  
  getCurrentCost(): CostSummary {
    const totalCost = this.costs.claude + this.costs.embeddings;
    
    // Project to daily cost based on elapsed time
    const elapsedHours = (Date.now() - this.sessionStart) / (1000 * 60 * 60);
    const projectedDailyCost = (totalCost / elapsedHours) * 24;
    
    return {
      claudeApiCost: this.costs.claude,
      embeddingCost: this.costs.embeddings,
      totalCost,
      projectedDailyCost,
    };
  }
  
  checkBudget(): boolean {
    const summary = this.getCurrentCost();
    return summary.projectedDailyCost < this.dailyBudget;
  }
}
```

### Deliverables (Phase 3)

- [ ] 5+ pre-built Grafana dashboards
- [ ] Prometheus alerting rules with Slack/email integration
- [ ] Cost tracker with budget enforcement
- [ ] Health check dashboard for all components
- [ ] Production deployment guide

---

## Technology Stack Decisions

### Chosen Stack (Self-Hosted, Open Source)

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Metrics** | Prometheus | Industry standard, efficient TSDB, powerful PromQL |
| **Tracing** | Jaeger | CNCF graduated, native OpenTelemetry support |
| **Logging** | Loki | Lightweight, integrates with Grafana, cost-effective |
| **Visualization** | Grafana | Best-in-class dashboards, supports all data sources |
| **Alerting** | Prometheus Alertmanager | Built-in, flexible routing |
| **Instrumentation** | OpenTelemetry | Vendor-neutral, future-proof |

### Alternative: Cloud-Based (Optional)

For users who prefer managed services:

| Component | Technology | Cost Estimate |
|-----------|-----------|---------------|
| Metrics + Dashboards | Grafana Cloud | Free tier: 10K series, then $8/10K series/month |
| Tracing | Honeycomb | Free tier: 20M events/month |
| Logging | Datadog | Starting $15/host/month |

**Recommendation:** Start with self-hosted, offer cloud as opt-in upgrade.

---

## Implementation Guides by Component

### Layer 1: VSCode Extension Telemetry

**Opt-In Flow**

```typescript
// First time activation
export async function activate(context: vscode.ExtensionContext) {
  const telemetryEnabled = context.globalState.get('telemetryPromptShown');
  
  if (!telemetryEnabled) {
    const response = await vscode.window.showInformationMessage(
      'Help improve Dolphin by sending anonymous usage data',
      'Allow',
      'Deny',
      'Learn More'
    );
    
    if (response === 'Allow') {
      await vscode.workspace.getConfiguration('dolphin')
        .update('telemetry.enabled', true, vscode.ConfigurationTarget.Global);
    } else if (response === 'Learn More') {
      vscode.env.openExternal(vscode.Uri.parse(
        'https://github.com/dolphin-ai/dolphin/blob/main/TELEMETRY.md'
      ));
    }
    
    context.globalState.update('telemetryPromptShown', true);
  }
}
```

**What We Track (Anonymous)**

- Command usage frequency (e.g., `dolphin.newConversation` invoked 50 times)
- Extension activation time
- Crashes/errors (type only, no stack traces)
- Feature usage (webview opened, settings changed)

**What We NEVER Track**

- Code content or file paths
- User identity (no names, emails, IPs)
- Conversation content
- API keys or credentials

### Layer 2: Agent Core Observability

**Critical Spans to Capture**

```typescript
// Conversation lifecycle
span: 'conversation.create'
  └─> span: 'conversation.plan'
        └─> span: 'llm.claude_api'
  └─> span: 'conversation.execute'
        └─> span: 'plan.step[0]'
              └─> span: 'mcp.file_write'
        └─> span: 'plan.step[1]'
              └─> span: 'mcp.kb_search'
                    └─> span: 'http.kb_api'
  └─> span: 'conversation.complete'
```

**Context Management Metrics**

```typescript
// Track context window usage
export function recordContextUsage(tokens: number, mode: ExecutionMode) {
  contextWindowTokens.observe({ mode }, tokens);
  
  // Alert if near limit
  if (tokens > 180000) {
    logger.warn('Approaching context limit', {
      tokens,
      mode,
      limit: 200000,
    });
  }
}
```

### Layer 3: MCP Bridge Security Monitoring

**Command Whitelist Violations**

```typescript
export async function runCommand(command: string, args: string[]) {
  const isWhitelisted = checkWhitelist(command);
  
  if (!isWhitelisted) {
    // Record security event
    commandExecutionsTotal.inc({
      command: 'BLOCKED',
      status: 'whitelist_violation',
    });
    
    logger.warn('Command whitelist violation', {
      command,
      args,
      trace_id: getCurrentTraceId(),
    });
    
    throw new Error(`Command '${command}' not in whitelist`);
  }
  
  // Proceed with execution
  return recordToolInvocation('run_command', async () => {
    // ... execute command
  });
}
```

### Layer 4: KB API Performance

**Slow Query Detection**

```python
async def semantic_search(query: str, repo_name: str, limit: int = 10):
    start = time.perf_counter()
    
    results = await _do_vector_search(query, repo_name, limit)
    
    duration = time.perf_counter() - start
    
    # Alert on slow queries
    if duration > 2.0:
        logger.warn('Slow search query', extra={
            'duration_seconds': duration,
            'repo_name': repo_name,
            'query_length': len(query),
            'result_count': len(results),
        })
    
    return results
```

---

## Privacy & Compliance

### GDPR Compliance

1. **Lawful Basis**: Consent (opt-in telemetry)
2. **Transparency**: Clear disclosure in README and settings
3. **Data Minimization**: Only collect what's necessary
4. **Right to Erasure**: Telemetry is anonymous, no PII to erase
5. **Data Security**: HTTPS for all telemetry transmission

### Telemetry Disclosure Document

**File:** `TELEMETRY.md`

```markdown
# Dolphin Telemetry

## What is Telemetry?

Telemetry is the automatic collection of anonymous usage data to help us improve Dolphin.

## Your Choice

Telemetry is **completely optional** and **disabled by default**. You can enable it in Settings → Extensions → Dolphin → Telemetry.

## What We Collect

- **Feature usage**: Which commands you use (e.g., "New Conversation")
- **Performance**: Extension activation time
- **Errors**: Types of errors (no stack traces)

## What We NEVER Collect

- ❌ Your code or file paths
- ❌ Conversation content
- ❌ Personal information (name, email, IP)
- ❌ API keys or credentials

## How It Works

When enabled, Dolphin sends anonymous events to our self-hosted Prometheus server. No third-party analytics services are used.

## Transparency

You can view exactly what telemetry is sent in the "Dolphin Telemetry" output channel in VSCode.

## Questions?

Open an issue on GitHub or email privacy@dolphin-ai.dev
```

### PII Scrubbing

**Automatic sanitization in logs:**

```typescript
export function sanitizeLogEntry(entry: LogEntry): LogEntry {
  const sanitized = { ...entry };
  
  // Remove potential file paths
  if (sanitized.file_path) {
    sanitized.file_path = sanitized.file_path.replace(
      /\/Users\/[^/]+/g,
      '/Users/***'
    );
  }
  
  // Remove potential API keys
  if (sanitized.message) {
    sanitized.message = sanitized.message.replace(
      /sk-[a-zA-Z0-9]{32,}/g,
      'sk-***'
    );
  }
  
  return sanitized;
}
```

---

## Testing Strategy

### Unit Tests

**File:** `agent-core/tests/metrics.test.ts`

```typescript
import { describe, it, expect, beforeEach } from 'bun:test';
import { register } from 'prom-client';
import { conversationsTotal, recordClaudeRequest } from '../src/metrics/prometheus';

describe('Prometheus Metrics', () => {
  beforeEach(() => {
    register.clear();
  });
  
  it('should record conversation creation', () => {
    conversationsTotal.inc({ mode: 'editor' });
    
    const metrics = register.metrics();
    expect(metrics).toContain('agent_conversations_total{mode="editor"} 1');
  });
  
  it('should calculate Claude API costs correctly', () => {
    recordClaudeRequest(
      'claude-sonnet-4.5',
      10000, // 10K input tokens
      5000,  // 5K output tokens
      1500,  // 1.5s latency
      true
    );
    
    // Expected cost: (10K * $3/1M) + (5K * $15/1M) = $0.03 + $0.075 = $0.105
    const metrics = register.metrics();
    expect(metrics).toContain('agent_claude_cost_usd{model="claude-sonnet-4.5"} 0.105');
  });
});
```

### Integration Tests

**File:** `tests/integration/tracing.test.ts`

```typescript
import { describe, it, expect } from 'bun:test';
import { initTracing } from '../shared/tracing/config';
import { trace } from '@opentelemetry/api';

describe('Distributed Tracing', () => {
  it('should propagate trace context through layers', async () => {
    const sdk = initTracing('test-service');
    const tracer = trace.getTracer('test');
    
    await tracer.startActiveSpan('parent', async (parentSpan) => {
      const parentContext = parentSpan.spanContext();
      
      // Simulate passing to child component
      await tracer.startActiveSpan('child', async (childSpan) => {
        const childContext = childSpan.spanContext();
        
        // Same trace ID
        expect(childContext.traceId).toBe(parentContext.traceId);
        
        childSpan.end();
      });
      
      parentSpan.end();
    });
    
    await sdk.shutdown();
  });
});
```

### Load Testing

**File:** `tests/load/metrics-overhead.test.ts`

```typescript
/**
 * Verify that metrics collection adds <5ms overhead.
 */

import { describe, it, expect } from 'bun:test';

describe('Metrics Performance', () => {
  it('should add <5ms overhead per request', async () => {
    const iterations = 1000;
    
    // Baseline (no metrics)
    const baselineStart = performance.now();
    for (let i = 0; i < iterations; i++) {
      await mockApiCall();
    }
    const baselineTime = performance.now() - baselineStart;
    
    // With metrics
    const metricsStart = performance.now();
    for (let i = 0; i < iterations; i++) {
      await mockApiCallWithMetrics();
    }
    const metricsTime = performance.now() - metricsStart;
    
    const overhead = metricsTime - baselineTime;
    const overheadPerRequest = overhead / iterations;
    
    console.log(`Average overhead: ${overheadPerRequest.toFixed(2)}ms`);
    expect(overheadPerRequest).toBeLessThan(5);
  });
});
```

---

## Success Criteria & Metrics

### Phase 1 Success Criteria

- [ ] All API endpoints expose `/metrics` endpoint
- [ ] Prometheus scraping all 3 layers successfully
- [ ] Structured logs include trace_id and span_id
- [ ] Basic Grafana dashboard shows live data
- [ ] Zero production incidents caused by observability
- [ ] <5ms average latency overhead from metrics

### Phase 2 Success Criteria

- [ ] 100% of requests have end-to-end traces
- [ ] Jaeger UI shows full request waterfall
- [ ] Trace-to-log correlation working
- [ ] Average trace completion within 2 minutes
- [ ] Team can debug production issues using traces

### Phase 3 Success Criteria

- [ ] 5+ dashboards deployed to Grafana
- [ ] Alerting rules firing correctly on test failures
- [ ] Cost tracking within 1% accuracy
- [ ] Documentation: "Observability Runbook" complete
- [ ] Team trained on reading metrics/traces

### KPIs to Track

| Metric | Target | Measurement |
|--------|--------|-------------|
| MTTR (Mean Time To Recovery) | <30min | Time from alert to fix |
| Observability Coverage | 100% | % of components instrumented |
| False Positive Rate (Alerts) | <10% | Invalid alerts / total alerts |
| Dashboard Load Time | <2s | Time to render dashboard |
| Cost Tracking Accuracy | ±1% | Actual vs. tracked costs |
| User Opt-In Rate (Telemetry) | >30% | Users enabling telemetry |

---

## Deployment Guide

### Docker Compose for Observability Stack

**File:** `observability/docker-compose.yml`

```yaml
version: '3.8'

services:
  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts.yml:/etc/prometheus/alerts.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
  
  # Jaeger
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "5775:5775/udp"
      - "6831:6831/udp"
      - "6832:6832/udp"
      - "5778:5778"
      - "16686:16686"  # UI
      - "14268:14268"
      - "14250:14250"
    environment:
      - COLLECTOR_ZIPKIN_HOST_PORT=:9411
  
  # Loki
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - ./loki/loki-config.yml:/etc/loki/local-config.yaml
      - loki_data:/loki
  
  # Promtail (log collector)
  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./loki/promtail-config.yml:/etc/promtail/config.yml
      - /var/log:/var/log
    command: -config.file=/etc/promtail/config.yml
  
  # Grafana
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false

volumes:
  prometheus_data:
  loki_data:
  grafana_data:
```

**File:** `observability/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load rules
rule_files:
  - "alerts.yml"

# Scrape configs
scrape_configs:
  # KB API
  - job_name: 'kb-api'
    static_configs:
      - targets: ['host.docker.internal:8000']
  
  # Agent Core
  - job_name: 'agent-core'
    static_configs:
      - targets: ['host.docker.internal:9091']
  
  # MCP Bridge
  - job_name: 'mcp-bridge'
    static_configs:
      - targets: ['host.docker.internal:9092']
```

### Starting the Stack

```bash
cd observability
docker-compose up -d

# Verify all services
docker-compose ps

# Access dashboards
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
# Jaeger: http://localhost:16686
```

### Integration with Dolphin

```bash
# Set environment variables
export PROMETHEUS_PUSHGATEWAY=http://localhost:9091
export JAEGER_ENDPOINT=http://localhost:14268/api/traces
export LOKI_URL=http://localhost:3100

# Start Dolphin services
cd kb && python -m uvicorn api.main:app --reload
cd agent-core && bun run src/main.ts
cd mcp-bridge && bun run src/main.ts
```

---

## Appendix: Reference Implementation Analysis

### Cline Telemetry Approach

**Strengths:**
- ✅ Opt-in with clear prompt
- ✅ Anonymous by default
- ✅ Transparent implementation
- ✅ Respects VSCode telemetry settings

**Dolphin Adaptations:**
- Use same opt-in UX pattern
- Add more granular metrics (per-component)
- Include distributed tracing (Cline doesn't have this)

### Kilocode Observability

**Strengths:**
- ✅ Multi-mode tracking (Architect/Coder/Debug)
- ✅ Performance benchmarks

**Dolphin Adaptations:**
- Adopt mode-specific metrics
- Add cost tracking (Kilocode doesn't expose this)

### Aider Approach

**Strengths:**
- ✅ Minimal telemetry, respects privacy
- ✅ Focus on core metrics only

**Dolphin Adaptations:**
- Match minimalist philosophy
- But add operational metrics for self-hosting

---

## Timeline Summary

```
Week 1-2: Core Metrics & Logging
  ├─ KB API Prometheus metrics
  ├─ MCP Bridge metrics
  ├─ Agent Core metrics
  └─ Structured logging

Week 3-4: Distributed Tracing
  ├─ OpenTelemetry setup
  ├─ Trace propagation
  ├─ Jaeger deployment
  └─ Trace-log correlation

Week 5-6: Dashboards & Alerts
  ├─ Grafana dashboards
  ├─ Alerting rules
  ├─ Cost tracking
  └─ Documentation
```

---

## Next Steps

1. **Review this plan** with team
2. **Set up dev environment** (Docker Compose)
3. **Start Phase 1, Week 1** implementation
4. **Daily standup** to track progress
5. **Document decisions** in ADRs

---

## Questions & Answers

**Q: Will this slow down Dolphin?**
A: No. Metrics collection adds <5ms per request (0.5% overhead). Tracing is sampled and async.

**Q: Can users disable telemetry?**
A: Yes. It's opt-in by default. Users must explicitly enable it.

**Q: What if Prometheus is down?**
A: Dolphin continues working. Metrics are buffered and dropped if backend unavailable.

**Q: How much disk space?**
A: ~1GB for 7 days of metrics + traces (adjustable retention).

**Q: Can I use cloud services instead?**
A: Yes! We recommend Grafana Cloud (free tier) for easy setup.

---

**Document Status:** ✅ Ready for Implementation  
**Next Review:** After Phase 1 completion  
**Owner:** Platform Team  
**Last Updated:** November 10, 2025
