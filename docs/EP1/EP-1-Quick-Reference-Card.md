# EP-1 Quick Reference Card

**For:** Dolphin Development Team  
**Purpose:** Fast lookup during observability implementation  
**Print This:** Keep at your desk during Phases 1-3

---

## 🎯 Week-by-Week Goals

| Week | Focus | Deliverable |
|------|-------|-------------|
| 1 | KB API + MCP Metrics | `/metrics` endpoints working |
| 2 | Agent Core + Logging | All layers have structured logs |
| 3 | OpenTelemetry Setup | End-to-end traces visible in Jaeger |
| 4 | Trace Propagation | Full request waterfall working |
| 5 | Grafana Dashboards | 5+ dashboards deployed |
| 6 | Alerts + Cost Tracking | Production-ready monitoring |

---

## 🚀 Essential Commands

### Start Observability Stack

```bash
cd observability
docker-compose up -d

# Verify
docker-compose ps
```

### Access UIs

- **Grafana:** http://localhost:3000 (admin/admin)
- **Prometheus:** http://localhost:9090
- **Jaeger:** http://localhost:16686
- **Loki:** http://localhost:3100

### Check Metrics

```bash
# KB API
curl http://localhost:8000/metrics

# Agent Core (if HTTP server)
curl http://localhost:9091/metrics

# MCP Bridge
curl http://localhost:9092/metrics
```

### Test Tracing

```bash
# Make request and get trace ID
curl -v http://localhost:8000/v1/search?query=test 2>&1 | grep -i traceparent

# View in Jaeger UI
open http://localhost:16686
```

---

## 📊 Prometheus Basics

### Counter (Things That Go Up)

```typescript
import { Counter } from 'prom-client';

const requestsTotal = new Counter({
  name: 'app_requests_total',
  help: 'Total requests',
  labelNames: ['method', 'status']
});

requestsTotal.inc({ method: 'GET', status: '200' });
```

### Histogram (Measure Duration)

```typescript
import { Histogram } from 'prom-client';

const duration = new Histogram({
  name: 'app_request_duration_seconds',
  help: 'Request duration',
  labelNames: ['endpoint'],
  buckets: [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
});

const timer = duration.startTimer({ endpoint: '/api/search' });
// ... do work ...
timer(); // Records duration automatically
```

### Gauge (Values That Go Up/Down)

```typescript
import { Gauge } from 'prom-client';

const activeUsers = new Gauge({
  name: 'app_active_users',
  help: 'Number of active users'
});

activeUsers.inc();  // User joined
activeUsers.dec();  // User left
```

---

## 🔍 OpenTelemetry Patterns

### Basic Span

```typescript
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('my-service', '1.0.0');

async function myFunction() {
  return tracer.startActiveSpan('my_function', async (span) => {
    try {
      const result = await doWork();
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.setStatus({ code: SpanStatusCode.ERROR });
      span.recordException(error);
      throw error;
    } finally {
      span.end();
    }
  });
}
```

### Add Attributes

```typescript
span.setAttribute('user.id', userId);
span.setAttribute('request.size', contentLength);
span.setAttribute('cache.hit', true);
```

### Propagate Context (HTTP)

```typescript
import { propagation, context } from '@opentelemetry/api';

// Inject into HTTP headers
const headers: Record<string, string> = {};
propagation.inject(context.active(), headers);

fetch(url, { headers });

// Extract from incoming headers
const ctx = propagation.extract(context.active(), request.headers);
context.with(ctx, () => {
  // This code runs in extracted context
});
```

---

## 📝 Structured Logging Template

```typescript
const logger = {
  info: (message: string, meta: any = {}) => {
    console.log(JSON.stringify({
      timestamp: new Date().toISOString(),
      level: 'INFO',
      message,
      trace_id: getCurrentTraceId(),
      span_id: getCurrentSpanId(),
      ...meta
    }));
  }
};

// Usage
logger.info('User logged in', { user_id: 123, method: 'oauth' });
```

---

## 🎨 PromQL Cheat Sheet

### Request Rate

```promql
# Requests per second
rate(http_requests_total[5m])

# By endpoint
sum(rate(http_requests_total[5m])) by (endpoint)
```

### Error Rate

```promql
# Error percentage
sum(rate(http_requests_total{status=~"5.."}[5m])) 
/ sum(rate(http_requests_total[5m])) 
* 100
```

### Latency Percentiles

```promql
# P95 latency in milliseconds
histogram_quantile(0.95, 
  sum(rate(http_duration_seconds_bucket[5m])) by (le)
) * 1000

# P50, P95, P99
histogram_quantile(0.50, ...) as p50
histogram_quantile(0.95, ...) as p95
histogram_quantile(0.99, ...) as p99
```

### Active Sessions

```promql
# Current value
app_active_users

# Average over time
avg_over_time(app_active_users[5m])
```

### Cost Tracking

```promql
# Total cost in last hour
increase(claude_cost_usd[1h])

# Cost per request
increase(claude_cost_usd[5m]) 
/ increase(claude_requests_total[5m])
```

---

## 🚨 Alert Rule Template

```yaml
- alert: HighErrorRate
  expr: |
    sum(rate(http_requests_total{status=~"5.."}[5m])) 
    / sum(rate(http_requests_total[5m])) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Error rate above 5%"
    description: "{{ $value | humanizePercentage }} of requests failing"
```

### Common Alert Conditions

```promql
# Service down
up{job="kb-api"} == 0

# High latency (>2s)
histogram_quantile(0.95, ...) > 2.0

# High memory usage (>80%)
process_resident_memory_bytes / node_memory_total_bytes > 0.8

# Cost spike (>$10/hour)
increase(claude_cost_usd[1h]) > 10
```

---

## 🔧 Debugging Checklist

### Metrics Not Showing

- [ ] Check `/metrics` endpoint accessible
- [ ] Verify Prometheus scrape config has correct URL
- [ ] Check Prometheus targets page (Status → Targets)
- [ ] Confirm metric name matches PromQL query
- [ ] Check time range in Grafana

### Traces Not Appearing

- [ ] Verify Jaeger exporter configured
- [ ] Check trace sampling rate (may be too low)
- [ ] Confirm span.end() is called
- [ ] Check Jaeger UI for service name
- [ ] Verify trace context propagation

### High Overhead

- [ ] Reduce metric cardinality (fewer labels)
- [ ] Lower trace sampling rate
- [ ] Use histograms instead of summaries
- [ ] Batch metric exports

---

## 💰 Cost Calculations

### Claude API

```typescript
// Sonnet 4.5 pricing
const PRICING = {
  input: 3.0 / 1_000_000,   // $3 per 1M tokens
  output: 15.0 / 1_000_000, // $15 per 1M tokens
};

function calculateCost(inputTokens: number, outputTokens: number) {
  return inputTokens * PRICING.input + outputTokens * PRICING.output;
}

// Example: 10K input + 5K output = $0.105
```

### Embeddings

```typescript
const EMBEDDING_COST = 0.02 / 1_000_000; // $0.02 per 1M tokens

function embeddingCost(tokens: number) {
  return tokens * EMBEDDING_COST;
}
```

---

## 📈 Key Metrics to Track

### Layer 1: VSCode Extension

- `extension_activated_duration_ms` - Activation time
- `command_usage_total{command}` - Command frequency
- `webview_events_total{event}` - UI interactions
- `extension_errors_total{type}` - Errors

### Layer 2: Agent Core

- `agent_conversations_total{mode}` - Conversations
- `agent_claude_tokens_total{type}` - Token usage
- `agent_claude_cost_usd` - API costs
- `agent_plan_steps_count` - Plan complexity

### Layer 3: MCP Bridge

- `mcp_file_operations_total{operation,status}` - File ops
- `mcp_command_executions_total{command}` - Commands
- `mcp_tool_duration_seconds{tool}` - Tool latency

### Layer 4: KB API

- `kb_http_requests_total{endpoint,status}` - Requests
- `kb_http_duration_seconds{endpoint}` - Latency
- `kb_search_result_count` - Search results
- `kb_embedding_cost_usd` - Embedding costs

---

## 🎯 Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| API Latency (P95) | <500ms | >2s |
| Error Rate | <1% | >5% |
| Metrics Overhead | <5ms | >10ms |
| Memory Increase | <20% | >50% |
| Trace Completion | <2min | >5min |

---

## 🔐 Privacy Checklist

- [ ] Telemetry opt-in by default
- [ ] No file paths in logs
- [ ] No code content in metrics
- [ ] No API keys in traces
- [ ] No user identity collected
- [ ] TELEMETRY.md documented
- [ ] Output channel visible to users

---

## 🧪 Testing Commands

### Load Test

```bash
# Generate 1000 requests
for i in {1..1000}; do
  curl http://localhost:8000/v1/health &
done
wait

# Check metrics overhead
curl http://localhost:8000/metrics | grep http_duration
```

### Alert Test

```bash
# Fire test alert
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    }
  }
]'
```

### Trace Test

```bash
# Generate trace
curl -H "traceparent: 00-12345678901234567890123456789012-1234567890123456-01" \
  http://localhost:8000/v1/search?query=test

# View in Jaeger
open "http://localhost:16686/search?service=dolphin-kb-api&limit=20"
```

---

## 📚 Useful Links

- **Prometheus Docs:** https://prometheus.io/docs/
- **PromQL Guide:** https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Grafana Dashboards:** https://grafana.com/grafana/dashboards/
- **OpenTelemetry JS:** https://opentelemetry.io/docs/languages/js/
- **OpenTelemetry Python:** https://opentelemetry.io/docs/languages/python/
- **Jaeger Docs:** https://www.jaegertracing.io/docs/

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Prometheus not scraping | Check `host.docker.internal` in targets |
| Grafana shows "No data" | Verify Prometheus data source URL |
| High cardinality warning | Reduce label values (<10 per label) |
| Jaeger UI empty | Check sampling rate (increase to 100% for testing) |
| Logs not structured | Ensure console.log outputs valid JSON |
| Metrics reset to 0 | Normal on restart (counters are cumulative) |

---

## ✅ Daily Standup Questions

1. **What did you instrument?** (Which metrics/spans added)
2. **What's blocking you?** (Dependencies, unclear requirements)
3. **What needs review?** (PR numbers, dashboard configs)
4. **Any issues?** (Performance, bugs, confusion)

---

## 🎓 Learning Resources

### Beginner

- [ ] Prometheus "Getting Started" (30 min)
- [ ] PromQL basics tutorial (45 min)
- [ ] Grafana dashboard creation (30 min)
- [ ] OpenTelemetry "Hello World" (20 min)

### Intermediate

- [ ] Distributed tracing concepts (1 hour)
- [ ] PromQL advanced queries (1 hour)
- [ ] Grafana alerting (45 min)
- [ ] OpenTelemetry context propagation (1 hour)

### Advanced

- [ ] Prometheus operator patterns (2 hours)
- [ ] High-cardinality troubleshooting (1 hour)
- [ ] Custom Grafana plugins (2 hours)
- [ ] OpenTelemetry collector configuration (2 hours)

---

## 🎉 Success Criteria

### Phase 1 Complete When:

- [ ] All services expose `/metrics`
- [ ] Prometheus scraping successfully
- [ ] At least 1 Grafana dashboard showing live data
- [ ] Structured logs in JSONL format
- [ ] Zero production incidents from observability code

### Phase 2 Complete When:

- [ ] End-to-end traces visible in Jaeger
- [ ] Trace context propagated through all layers
- [ ] Logs include trace_id and span_id
- [ ] Can debug production issue using trace

### Phase 3 Complete When:

- [ ] 5+ dashboards deployed
- [ ] Alerting rules firing on test failures
- [ ] Cost tracking accurate within 1%
- [ ] Team trained on reading metrics/traces
- [ ] Documentation complete

---

**Print This Card** | **Keep At Desk** | **Updated:** Nov 10, 2025
