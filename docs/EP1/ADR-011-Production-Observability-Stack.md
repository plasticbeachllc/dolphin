# ADR-011: Production Observability Stack

**Status:** ✅ Accepted  
**Date:** November 10, 2025  
**Context:** EP-1 Implementation  
**Decision Makers:** Platform Team

---

## Context

Dolphin requires comprehensive observability across its 4-layer architecture (VSCode Extension, Agent Core, MCP Bridge, Knowledge Bank API) to:

1. **Monitor production health**: Detect and diagnose issues proactively
2. **Optimize performance**: Identify bottlenecks with distributed tracing
3. **Control costs**: Track Claude API and embedding expenses
4. **Support debugging**: Correlate logs, metrics, and traces
5. **Respect privacy**: Ensure telemetry is opt-in and anonymous

We need to decide on:
- Metrics collection and storage
- Distributed tracing backend
- Log aggregation
- Dashboard and alerting
- Instrumentation approach

---

## Decision

Implement a **self-hosted, open-source observability stack** based on the CNCF ecosystem:

### Stack Components

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Metrics** | Prometheus | Industry standard, efficient TSDB, powerful PromQL, wide adoption |
| **Tracing** | Jaeger | CNCF graduated, native OpenTelemetry support, excellent UI |
| **Logging** | Loki | Lightweight, Grafana integration, cost-effective indexing |
| **Dashboards** | Grafana | Best-in-class visualization, supports all data sources |
| **Alerting** | Alertmanager | Built into Prometheus, flexible routing, Slack/PagerDuty support |
| **Instrumentation** | OpenTelemetry | Vendor-neutral, future-proof, standardized APIs |

### Telemetry Philosophy

- **Opt-in by default**: Users must explicitly enable telemetry
- **Anonymous always**: No PII collection, no code content
- **Transparent**: Users can view telemetry events in VSCode output channel
- **Self-hosted**: No third-party SaaS dependencies

---

## Alternatives Considered

### Alternative 1: Cloud-Based SaaS (Datadog, New Relic)

**Pros:**
- Minimal setup, fully managed
- Advanced features (APM, RUM, synthetic monitoring)
- Better UX for non-technical users

**Cons:**
- ❌ Vendor lock-in
- ❌ High cost at scale ($50-200/host/month)
- ❌ Privacy concerns (data sent to third-party)
- ❌ Not suitable for self-hosted deployments

**Decision:** Rejected due to cost, privacy, and vendor lock-in concerns.

---

### Alternative 2: Elastic Stack (ELK)

**Pros:**
- Mature ecosystem
- Powerful log search (Elasticsearch)
- Good community support

**Cons:**
- ❌ High resource usage (Elasticsearch is memory-hungry)
- ❌ Complex to operate (5+ components)
- ❌ License changes (not fully open source)
- ❌ Overkill for Dolphin's scale

**Decision:** Rejected in favor of lighter-weight alternatives.

---

### Alternative 3: Cloud-Native Alternatives (Grafana Cloud, Honeycomb)

**Pros:**
- Open-source compatible
- Free tiers available
- Good balance of features and cost

**Cons:**
- ⚠️ Still SaaS (privacy concerns for some users)
- ⚠️ Free tiers have limits
- ⚠️ Not ideal for offline/air-gapped deployments

**Decision:** Offer as **optional upgrade** for users who prefer managed services, but default to self-hosted.

---

### Alternative 4: Custom Metrics + SQLite

**Pros:**
- Minimal dependencies
- Full control
- No external services

**Cons:**
- ❌ Reinventing the wheel
- ❌ Poor scalability
- ❌ No ecosystem integrations
- ❌ Limited query capabilities

**Decision:** Rejected. Use proven tools instead of building custom.

---

## Rationale

### Why Prometheus?

1. **Industry Standard**: De facto standard for metrics in cloud-native apps
2. **Efficient Storage**: Time-series database optimized for metrics
3. **Powerful Querying**: PromQL enables complex aggregations
4. **Pull-Based**: Resilient to service failures (no data loss if app crashes)
5. **Wide Adoption**: Used by Kubernetes, many OSS projects

**Evidence from Reference Implementations:**
- Kilocode uses Prometheus-compatible metrics
- Cline's telemetry could easily export to Prometheus
- Aider uses minimal metrics, but Prometheus would scale

### Why Jaeger?

1. **OpenTelemetry Native**: Direct support for OTLP protocol
2. **Excellent UI**: Intuitive trace visualization with waterfall diagrams
3. **CNCF Graduated**: Production-ready, battle-tested
4. **Sampling Support**: Can handle high trace volume
5. **Storage Options**: Memory, Cassandra, Elasticsearch

**Dolphin-Specific Benefits:**
- Visualize full request flow: VSCode → Agent → MCP → KB
- Identify slow spans (e.g., LanceDB vector search)
- Debug multi-step plan execution

### Why Loki?

1. **Grafana Integration**: Seamless log correlation with metrics
2. **Cost-Effective**: Indexes only metadata, stores logs compressed
3. **Simple**: Single binary, easy to deploy
4. **LogQL**: Powerful query language similar to PromQL

**Alternative to Splunk/ELK:**
- 10x cheaper (no per-GB indexing cost)
- Easier to operate (no Elasticsearch cluster)
- Good enough for Dolphin's log volume (<1GB/day)

### Why OpenTelemetry?

1. **Vendor-Neutral**: Can switch backends without code changes
2. **Standardized**: W3C Trace Context propagation
3. **Community Support**: CNCF project, backed by major vendors
4. **Auto-Instrumentation**: Built-in for FastAPI, fetch, etc.

**Avoids Lock-In:**
- If we switch to Honeycomb later, just change exporter
- If we need Zipkin, just add Zipkin exporter
- If we want DataDog, use DataDog exporter

---

## Implementation Details

### Layer-Specific Instrumentation

#### Layer 1: VSCode Extension (Node.js)

```typescript
// Lightweight telemetry service
// No heavy instrumentation (VSCode already has telemetry APIs)
import * as vscode from 'vscode';

class TelemetryService {
  sendEvent(name: string, properties: Record<string, any>) {
    if (!this.enabled) return;
    
    // Log to output channel for transparency
    this.outputChannel.appendLine(JSON.stringify({
      timestamp: new Date().toISOString(),
      event: name,
      ...properties
    }));
    
    // Send to backend (optional, opt-in)
    if (this.remoteEnabled) {
      this.sendToBackend(name, properties);
    }
  }
}
```

**What We Track:**
- Command usage frequency
- Extension activation time
- Crash events (error type only)

**What We DON'T Track:**
- File paths
- Code content
- User identity

#### Layer 2: Agent Core (Bun)

```typescript
// Prometheus metrics + OpenTelemetry tracing
import { Counter, Histogram } from 'prom-client';
import { trace } from '@opentelemetry/api';

const conversationsTotal = new Counter({
  name: 'agent_conversations_total',
  help: 'Total conversations created',
  labelNames: ['mode']
});

const tracer = trace.getTracer('dolphin-agent-core');

async function handleConversation(message: UserMessage) {
  return tracer.startActiveSpan('conversation.handle', async (span) => {
    conversationsTotal.inc({ mode: 'editor' });
    // ... handle conversation
    span.end();
  });
}
```

**Key Metrics:**
- Conversation lifecycle
- Claude API usage (tokens, cost, latency)
- Plan execution duration
- MCP tool calls

#### Layer 3: MCP Bridge (Bun)

```typescript
// File operation metrics
const fileOpsTotal = new Counter({
  name: 'mcp_file_operations_total',
  help: 'Total file operations',
  labelNames: ['operation', 'status']
});

export async function fileWrite(path: string, content: string) {
  return recordToolInvocation('file_write', async () => {
    await Bun.write(path, content);
    fileOpsTotal.inc({ operation: 'write', status: 'success' });
  });
}
```

**Key Metrics:**
- File operations (read, write, diff)
- Command executions
- Rollback operations

#### Layer 4: Knowledge Bank API (Python)

```python
# FastAPI + Prometheus middleware
from prometheus_client import Counter, Histogram

http_requests_total = Counter(
    'kb_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    response = await call_next(request)
    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    return response
```

**Key Metrics:**
- API request latency (p50, p95, p99)
- Search performance
- Embedding costs
- Database query times

---

## Cost Analysis

### Self-Hosted (Recommended)

| Component | Infrastructure Cost | Setup Time |
|-----------|-------------------|------------|
| Prometheus | $10-20/month (1GB disk) | 2 hours |
| Jaeger | $15-30/month (2GB disk) | 2 hours |
| Loki | $10-20/month (1GB disk) | 2 hours |
| Grafana | $10-20/month (500MB disk) | 1 hour |
| **Total** | **$45-90/month** | **7 hours** |

**Assumptions:**
- DigitalOcean/AWS t3.medium instance
- 7 days retention (metrics/traces/logs)
- ~100K requests/day

### Cloud SaaS (Alternative)

| Service | Cost | Features |
|---------|------|----------|
| Grafana Cloud | Free tier: 10K series | Metrics + Dashboards |
| Honeycomb | Free tier: 20M events/month | Tracing + Analytics |
| Datadog | Starts $15/host/month | Full observability |
| New Relic | Starts $99/month | APM + Infrastructure |

**For Dolphin's Scale:**
- Grafana Cloud free tier likely sufficient
- Honeycomb free tier covers moderate usage
- Datadog/New Relic too expensive for open-source project

**Decision:** Offer cloud option for users who want managed, but default to self-hosted for cost control and privacy.

---

## Privacy Considerations

### GDPR Compliance

1. **Lawful Basis**: Consent (opt-in)
2. **Data Minimization**: Only collect necessary metrics
3. **Transparency**: Clear disclosure in settings and README
4. **Right to Erasure**: Telemetry is anonymous, no PII to erase
5. **Data Security**: HTTPS/TLS for all telemetry transmission

### PII Scrubbing

```typescript
// Automatic PII removal
function sanitize(log: LogEntry): LogEntry {
  return {
    ...log,
    // Remove file paths
    file_path: log.file_path?.replace(/\/Users\/[^/]+/, '/Users/***'),
    // Remove API keys
    message: log.message?.replace(/sk-[a-zA-Z0-9]+/, 'sk-***'),
  };
}
```

### User Control

- **Opt-in prompt** on first activation
- **Settings toggle**: `dolphin.telemetry.enabled`
- **Output channel**: Users can view exact telemetry events
- **Documentation**: Transparent TELEMETRY.md explaining what's collected

---

## Migration Path

### Phase 1: Metrics Only (Weeks 1-2)

- Add Prometheus metrics to all layers
- Deploy Prometheus + Grafana
- Create basic dashboards
- No breaking changes

### Phase 2: Add Tracing (Weeks 3-4)

- Integrate OpenTelemetry
- Deploy Jaeger
- Propagate trace context
- Minimal code changes (mostly middleware)

### Phase 3: Structured Logging (Weeks 5-6)

- Migrate to JSONL logs
- Deploy Loki
- Correlate logs with traces
- Refactor existing logging

### Phase 4: Alerting (Week 7+)

- Configure Alertmanager
- Set up Slack/PagerDuty
- Define SLOs and alert rules

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Coverage | 100% of components | All layers instrumented |
| Overhead | <5ms per request | Load testing |
| MTTR | 80% reduction | Time from alert to fix |
| User Opt-In | >30% | Telemetry enablement rate |
| False Positives | <10% | Invalid alerts / total |

---

## Consequences

### Positive

- ✅ **Production-Ready**: Battle-tested tools used by thousands of companies
- ✅ **Cost-Effective**: Self-hosted costs <$100/month
- ✅ **Privacy-First**: No data sent to third parties
- ✅ **Extensible**: Can add more exporters (Honeycomb, DataDog) later
- ✅ **Community Support**: Large ecosystems, many tutorials
- ✅ **No Vendor Lock-In**: Standard protocols (OTLP, Prometheus exposition format)

### Negative

- ⚠️ **Operational Overhead**: Need to maintain Prometheus/Jaeger/Grafana
- ⚠️ **Learning Curve**: Team needs to learn PromQL, Grafana, Jaeger UI
- ⚠️ **Storage Management**: Need to configure retention policies
- ⚠️ **More Components**: 4+ services to deploy and monitor

### Mitigation Strategies

1. **Docker Compose**: Provide one-command deployment
2. **Documentation**: Comprehensive runbooks and troubleshooting guides
3. **Defaults**: Sensible retention policies (7 days) out of the box
4. **Automation**: Scripts for backup, restore, and maintenance
5. **Optional Cloud**: Offer Grafana Cloud as managed alternative

---

## Alternatives for Specific Use Cases

### For Enterprise Users (Need Compliance)

**Option:** Splunk or ELK with audit logging
- Better compliance features
- More expensive but acceptable for large orgs

### For Small Teams (Want Simplicity)

**Option:** Grafana Cloud free tier
- No infrastructure to manage
- Still respects privacy
- Free up to 10K series

### For Air-Gapped Deployments

**Option:** Same stack, but export to local storage
- Prometheus with long-term storage (Thanos/Cortex)
- Jaeger with local storage (Cassandra)
- Loki with S3-compatible backend

---

## References

### Tools

- [Prometheus](https://prometheus.io/)
- [Jaeger](https://www.jaegertracing.io/)
- [Grafana](https://grafana.com/)
- [Loki](https://grafana.com/oss/loki/)
- [OpenTelemetry](https://opentelemetry.io/)

### Inspiration

- [Kilocode](https://github.com/Kilo-Org/kilocode) - Multi-mode metrics
- [Cline](https://github.com/cline/cline) - Privacy-first telemetry
- [Aider](https://github.com/Aider-AI/aider) - Minimal instrumentation
- [Claude Code](https://github.com/anthropics/claude-code) - Enterprise observability

### Best Practices

- [SRE Book - Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Honeycomb Blog - Observability 101](https://www.honeycomb.io/blog/observability-101-terminology-and-concepts)
- [Grafana Labs - Observability Strategy](https://grafana.com/blog/2021/08/03/a-beginners-guide-to-the-observability-pillar-of-the-lgtm-stack/)

---

## Approval

**Approved By:** Platform Team  
**Date:** November 10, 2025  
**Review Date:** January 10, 2026 (2 months after deployment)

---

## Appendix: Deployment Checklist

### Infrastructure Setup

- [ ] Provision server/VM (2 CPU, 4GB RAM, 50GB disk)
- [ ] Install Docker & Docker Compose
- [ ] Configure firewall (allow ports 3000, 9090, 16686)
- [ ] Set up SSL/TLS certificates (Let's Encrypt)

### Observability Stack

- [ ] Deploy Prometheus
- [ ] Deploy Jaeger
- [ ] Deploy Loki + Promtail
- [ ] Deploy Grafana
- [ ] Configure Prometheus scrape targets
- [ ] Import Grafana dashboards
- [ ] Configure alerting rules
- [ ] Test alert delivery (Slack/email)

### Application Instrumentation

- [ ] Add Prometheus metrics to KB API
- [ ] Add Prometheus metrics to Agent Core
- [ ] Add Prometheus metrics to MCP Bridge
- [ ] Instrument with OpenTelemetry (all layers)
- [ ] Configure trace sampling (10%)
- [ ] Migrate to structured JSONL logging

### Testing

- [ ] Load test metrics overhead (<5ms)
- [ ] Verify end-to-end tracing works
- [ ] Test log aggregation
- [ ] Validate dashboard queries
- [ ] Trigger test alerts

### Documentation

- [ ] Update README with observability section
- [ ] Write TELEMETRY.md for transparency
- [ ] Create runbooks for common issues
- [ ] Document alert response procedures

---

**Document Status:** ✅ Accepted  
**Next ADR:** ADR-012 (Cost Management Strategy)  
**Last Updated:** November 10, 2025
