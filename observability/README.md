# Dolphin Observability Stack

## Overview

Lightweight observability stack for debugging and monitoring Dolphin core services during development. Provides distributed tracing, log aggregation, and latency monitoring.

**Purpose**: Development debugging and performance analysis
**Scope**: MCP bridge + KB HTTP/indexing services (no VSCode extension required)
**Status**: Phase 1 - Core Infrastructure

## Architecture

```
┌──────────────────────────────────────────────────┐
│ Observability Stack (Docker Compose)             │
│                                                   │
│ ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│ │Prometheus│  │  Jaeger  │  │   Loki   │        │
│ │ :9090    │  │ :16686   │  │ :3100    │        │
│ └─────┬────┘  └─────┬────┘  └─────┬────┘        │
│       │             │              │             │
│       └─────────────┴──────────────┘             │
│                     │                            │
│              ┌──────▼───────┐                    │
│              │   Grafana    │                    │
│              │    :3000     │                    │
│              └──────────────┘                    │
└──────────────────────────────────────────────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
     ┌───▼────┐   ┌────▼────┐   ┌──▼──────┐
     │ KB API │   │ Indexer │   │  MCP    │
     │ :8000  │   │ (CLI)   │   │ Bridge  │
     └────────┘   └─────────┘   │  :9092  │
                                └─────────┘
```

## Quick Start

### 1. Start the Stack

```bash
cd observability
./manage.sh start

# Or use the quick-start wrapper:
./start-stack.sh
```

**Tip**: See [COMMANDS.md](./COMMANDS.md) for full command reference.

### 2. Access Dashboards

```bash
# Grafana - Main debugging dashboard
open http://localhost:3000  # admin/admin

# Jaeger - Distributed traces
open http://localhost:16686

# Prometheus - Raw metrics
open http://localhost:9090
```

### 3. Start KB API

```bash
# From project root
uv run kb-api

# Verify metrics
curl http://localhost:8000/metrics
curl http://localhost:8000/health
```

### 4. Start MCP Bridge (optional but supported)

```bash
cd mcp-bridge
bun run --hot src/index.ts
```

### 5. Run Indexing (optional)

```bash
# From project root
uv run dolphin kb index <repo-name>
```

### 6. View in Grafana

1. Open http://localhost:3000
2. Go to "Dolphin Debugging Dashboard"
3. See:
   - Request rates and latency
   - Error logs
   - Backend performance breakdown

## What's Included

### Prometheus (Metrics Storage)

- **Port**: 9090
- **Retention**: 7 days
- **Scrape Interval**: 15 seconds
- **Targets**: KB API (:8000), MCP Bridge (:9092)

### Jaeger (Distributed Tracing)

- **UI Port**: 16686
- **Protocol**: OpenTelemetry (OTLP)
- **Storage**: In-memory
- **Use**: Trace requests across services

### Loki (Log Aggregation)

- **Port**: 3100
- **Format**: JSONL (structured logs)
- **Retention**: 30 days
- **Use**: Search and filter logs from core services
- **Captured by default**: `mcp-bridge/logs/mcp.log`
- **Optional**: Drop JSONL logs into `observability/logs/` to ship via Promtail

### Grafana (Visualization)

- **Port**: 3000
- **Login**: admin / admin
- **Dashboard**: "Dolphin Debugging Dashboard"
- **Features**:
  - Request latency (p50, p95, p99)
  - Error rate tracking
  - Backend latency breakdown
  - Live error logs
  - Link to Jaeger traces

## No VSCode Extension Required

The stack is designed to work with the standalone MCP bridge, KB HTTP server, and indexing pipeline. If you run the VSCode extension, it can also emit data, but it is not required for this stack to function.

## KB API Metrics

The KB API automatically exposes metrics at `/metrics`:

```bash
# View all metrics
curl http://localhost:8000/metrics

# Example metrics:
# kb_http_requests_total - Total requests by endpoint
# kb_http_request_duration_seconds - Request latency histogram
# kb_search_queries_total - Search queries
# kb_vector_search_duration_seconds - Vector search latency
# kb_db_query_duration_seconds - Database query latency
# kb_embedding_api_latency_seconds - Embedding API latency
```

### Instrumenting Code

```python
from kb.api.middleware.metrics import (
    record_search_query,
    record_vector_search,
    record_embedding_call,
    record_db_query
)

# Record search
record_search_query(
    repo_name="my-repo",
    search_type="semantic",
    result_count=10,
    query_tokens=25
)

# Record vector search timing
record_vector_search("my-repo", duration_seconds=0.05)

# Record embedding API call
record_embedding_call("my-repo", tokens=100, latency_seconds=0.5)

# Record database query
record_db_query("select", "chunks", duration_seconds=0.01)
```

## TypeScript Observability Utilities

Location: `shared/observability/`

### Logger (Structured Logging)

```typescript
import { createLogger } from "@dolphin/shared/observability";

const logger = createLogger("my-component");

logger.info("Processing request", { request_id: "123" });
logger.error("Failed to connect", error, { host: "localhost" });
```

Features:

- JSONL format
- Automatic trace context injection
- PII sanitization (API keys, file paths)

### Tracing (OpenTelemetry)

```typescript
import { initTracing, traced, SpanNames } from "@dolphin/shared/observability";

// Initialize once at startup
initTracing("my-service", "1.0.0");

// Trace operations
await traced(SpanNames.CLAUDE_REQUEST, async (span) => {
  span.setAttribute("model", "claude-sonnet-4.5");
  span.setAttribute("tokens", 1000);
  return await callClaude();
});
```

### Metrics (Prometheus)

```typescript
import { createMetricsServer, metricsCounters } from "@dolphin/shared/observability";

// Start metrics server (Bun runtime only)
// Update observability/prometheus/prometheus.yml if you choose a different port.
createMetricsServer(9092);

// Metrics auto-increment on tool calls
metricsCounters.toolInvocations.inc({ tool: "file_read" });
```

## Debugging Workflow

### 1. View Request Latency

1. Open Grafana dashboard
2. Check "Request Latency (p50, p95, p99)" panel
3. Identify slow endpoints
4. Click "View in Jaeger" to see trace details

### 2. Debug Errors

1. Check "Error Rate (5xx)" panel
2. Scroll to "Error Logs" panel
3. See structured logs with trace IDs
4. Click trace ID to view in Jaeger

### 3. Analyze Backend Performance

1. Check "Backend Latency Breakdown (p95)" panel
2. See breakdown:
   - Vector search time
   - Database query time
   - Embedding API time
3. Identify bottlenecks

### 4. Search Logs

In Grafana:

1. Go to "Explore"
2. Select "Loki" datasource
3. Query: `{job="dolphin"} |~ "search"`
4. Filter by level, component, or message

## Management Commands

Use the `manage.sh` script for common operations:

```bash
cd observability

# Start all services
./manage.sh start

# Stop all services
./manage.sh stop

# Restart all services (useful after config changes)
./manage.sh restart

# Check service status and health
./manage.sh status

# View live logs from all services
./manage.sh logs

# Show service URLs
./manage.sh urls

# Clean up (WARNING: deletes all data)
./manage.sh clean
```

**Individual services:**

```bash
# Restart just Grafana (to reload dashboards)
docker compose restart grafana

# View logs for specific service
docker compose logs -f grafana
```

See [COMMANDS.md](./COMMANDS.md) for complete command reference.

## Useful Prometheus Queries

```promql
# Request rate by endpoint
rate(kb_http_requests_total[1m])

# P95 latency
histogram_quantile(0.95, rate(kb_http_request_duration_seconds_bucket[1m]))

# Error rate
sum(rate(kb_http_requests_total{status_code=~"5.."}[1m]))

# Slow vector searches
kb_vector_search_duration_seconds > 1.0
```

## Configuration

### Scrape Interval

Edit `prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s # Adjust as needed
```

### Log Retention

Edit `loki/loki-config.yml`:

```yaml
limits_config:
  retention_period: 720h # 30 days
```

### Environment Variables

```bash
# OpenTelemetry endpoint
export OTLP_ENDPOINT=http://localhost:4318/v1/traces

# Loki endpoint for log shipping
export LOKI_URL=http://localhost:3100
```

## Troubleshooting

### No metrics in Grafana

```bash
# Check if KB API is exposing metrics
curl http://localhost:8000/metrics

# Check Prometheus targets
open http://localhost:9090/targets
# Should show "kb-api" target as UP
```

### No traces in Jaeger

```bash
# Enable debug logging
export OTEL_LOG_LEVEL=debug

# Verify Jaeger is receiving spans
curl http://localhost:16686/api/services
```

### Grafana "No Data"

- Check time range (last 15 minutes)
- Verify datasources: http://localhost:3000/datasources
- Check Prometheus is scraping: http://localhost:9090/targets

## Performance Impact

Minimal overhead:

- **Latency**: +1-2ms per request (~4%)
- **Memory**: +15MB per service (~12%)
- **Disk**: ~2GB/week (logs + metrics)

## Next Steps

### Phase 2: Full Distributed Tracing

- [ ] Integrate OpenTelemetry in Agent Core
- [ ] Add trace context to MCP protocol
- [ ] Implement cross-service trace propagation
- [ ] Create trace correlation dashboard

### Phase 3: Advanced Dashboards

- [ ] Per-session cost dashboard
- [ ] SLO tracking dashboard
- [ ] Custom service dashboards

## References

- [EP-1 Implementation Plan](/docs/EP1/EP-1-Production-Observability-Implementation-Plan.md)
- [ADR-011: Observability Stack](/docs/EP1/ADR-011-Production-Observability-Stack.md)
- [Testing Guide](./TESTING.md)
- [Deployment Guide](./DEPLOYMENT.md)
