# Observability Stack Deployment Guide

## Prerequisites

- Docker and Docker Compose installed
- Python 3.12+ (for KB API)
- Bun (for TypeScript services)
- At least 2GB RAM for observability stack
- 5GB disk space for logs/metrics

## Installation Steps

### 1. Install Dependencies

#### Python (KB API)

```bash
cd /path/to/dolphin
uv pip install -e .
# Or with pip
pip install prometheus-client opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi
```

#### TypeScript (Shared utilities)

```bash
cd shared
bun install
```

### 2. Start Observability Stack

```bash
cd observability
./manage.sh start
```

**Verify all services are running:**

```bash
./manage.sh status
```

You should see:

- ✅ dolphin-prometheus (port 9090)
- ✅ dolphin-jaeger (port 16686)
- ✅ dolphin-loki (port 3100)
- ✅ dolphin-promtail
- ✅ dolphin-grafana (port 3000)

**Log shipping note**: Promtail watches `mcp-bridge/logs/*.log` and `observability/logs/*.jsonl` by default.

### 3. Access Web UIs

| Service    | URL                    | Credentials                                  |
| ---------- | ---------------------- | -------------------------------------------- |
| Grafana    | http://localhost:3000  | admin / admin (⚠️ **Change in production!**) |
| Prometheus | http://localhost:9090  | -                                            |
| Jaeger     | http://localhost:16686 | -                                            |

### 4. Configure Grafana

Grafana datasources and dashboards are auto-provisioned. After first login:

1. Change default password
2. Navigate to **Dashboards → Dolphin → Dolphin Debugging Dashboard**

### 5. Start KB API

```bash
# From project root
uv run kb-api
```

Verify metrics:

```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/health
```

### 6. Start MCP Bridge (optional but supported)

```bash
cd mcp-bridge
bun run --hot src/index.ts
```

### 7. Run Indexing (optional)

```bash
uv run dolphin kb index <repo-name>
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# OpenTelemetry endpoint
OTLP_ENDPOINT=http://localhost:4318/v1/traces

# Loki endpoint
LOKI_URL=http://localhost:3100

# Log level
LOG_LEVEL=INFO

# Optional: Secure Grafana credentials (recommended for production)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your_secure_password_here
```

## No IDE Extension Required

The observability stack is built to work with the core MCP bridge, KB HTTP server, and indexing pipeline. No IDE extension is required to collect metrics or logs.

### Customize Prometheus Scrape Targets

Edit `observability/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "kb-api"
    static_configs:
      - targets: ["host.docker.internal:8000"] # Change port if needed
    scrape_interval: 10s # Adjust scrape frequency
```

Restart Prometheus:

```bash
./manage.sh restart
```

### Customize Retention Periods

**Prometheus** (default: 7 days):

```yaml
# observability/prometheus/prometheus.yml
command:
  - "--storage.tsdb.retention.time=7d" # Adjust as needed
```

**Loki** (default: 30 days):

```yaml
# observability/loki/loki-config.yml
limits_config:
  retention_period: 720h # 30 days
```

## Security Considerations

### 🔒 Production Security Checklist

- [ ] **Change Grafana credentials** from default admin/admin
- [ ] **Restrict network access** to observability ports (use firewall/VPC)
- [ ] **Consider authentication** for /metrics endpoints (see below)
- [ ] **Use HTTPS/TLS** for external access
- [ ] **Limit log retention** based on compliance requirements
- [ ] **Review exposed metrics** for sensitive information

### Securing Metrics Endpoints

The `/metrics` endpoints are **unauthenticated by default** for simplicity. For production:

**Option 1: Network isolation** (recommended for internal tools)

```bash
# Only allow Prometheus to access metrics
iptables -A INPUT -p tcp --dport 8000 -s <prometheus_ip> -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j DROP
```

**Option 2: Add authentication middleware**

```python
# kb/api/middleware/auth.py
from fastapi import Security, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

async def verify_metrics_auth(credentials: HTTPBasicCredentials = Security(security)):
    if credentials.username != "metrics" or credentials.password != "secret":
        raise HTTPException(status_code=401)
    return credentials

# In server.py
@app.get("/metrics", dependencies=[Depends(verify_metrics_auth)])
async def metrics_endpoint():
    return metrics.metrics_endpoint()
```

**Option 3: API key header**

```python
async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != os.getenv("METRICS_API_KEY"):
        raise HTTPException(status_code=403)
```

### Securing Grafana

**Use environment variables for credentials:**

```yaml
# observability/docker-compose.yml
grafana:
  environment:
    - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
```

Then set in `.env`:

```bash
GRAFANA_ADMIN_USER=your_admin_user
GRAFANA_ADMIN_PASSWORD=your_secure_password
```

## Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
docker ps

# Check port conflicts
lsof -i :3000  # Grafana
lsof -i :9090  # Prometheus
lsof -i :16686 # Jaeger

# View error logs
./manage.sh logs
```

### No Metrics in Prometheus

```bash
# Check Prometheus targets
open http://localhost:9090/targets

# Should show "kb-api" as UP
# If DOWN, verify KB API is running:
curl http://localhost:8000/metrics
```

### Dashboard Not Showing in Grafana

```bash
# Restart Grafana to reload dashboards
docker compose restart grafana

# Check dashboard file exists
ls -l grafana/dashboards/debugging.json

# View Grafana provisioning logs
docker compose logs grafana | grep provision
```

### High Memory Usage

Observability stack uses ~2GB RAM by default. To reduce:

1. **Lower Prometheus retention:**

   ```yaml
   --storage.tsdb.retention.time=3d
   ```

2. **Reduce scrape frequency:**

   ```yaml
   scrape_interval: 30s # Instead of 10s
   ```

3. **Limit Loki retention:**
   ```yaml
   retention_period: 168h # 7 days instead of 30
   ```

### Disk Space Issues

```bash
# Check volume sizes
docker system df -v

# Clean up old data
./manage.sh clean  # WARNING: Deletes all data!

# Or manually remove old data
docker volume rm dolphin_prometheus_data
docker volume rm dolphin_loki_data
```

## Performance Impact

Expected overhead from observability:

| Component          | Baseline | With Observability | Overhead    |
| ------------------ | -------- | ------------------ | ----------- |
| KB API Latency     | 45ms     | 47ms               | +2ms (4%)   |
| Memory per Service | 120MB    | 135MB              | +15MB (12%) |
| Disk Usage         | -        | ~2GB/week          | -           |

**Recommendations:**

- Acceptable for development and production
- Monitor disk usage and adjust retention
- Consider sampling for high-throughput services

## Backup and Recovery

### Backup Grafana Dashboards

```bash
docker compose exec grafana \
  tar czf - /var/lib/grafana/dashboards > grafana-backup.tar.gz
```

### Restore Grafana Dashboards

```bash
docker compose exec grafana \
  tar xzf - -C /var/lib/grafana/dashboards < grafana-backup.tar.gz

docker compose restart grafana
```

### Export Prometheus Data

```bash
# Snapshot Prometheus data
docker compose exec prometheus \
  promtool tsdb create-blocks-from rules
```

## Monitoring the Observability Stack

Monitor the observability stack itself:

```bash
# Prometheus self-monitoring
curl http://localhost:9090/metrics | grep prometheus_

# Grafana metrics
curl http://localhost:3000/metrics

# Jaeger health
curl http://localhost:16686/
```

## Next Steps

- See [README.md](./README.md) for usage guide
- See [COMMANDS.md](./COMMANDS.md) for command reference
- See [TESTING.md](./TESTING.md) for testing procedures

## References

- [Prometheus Security Best Practices](https://prometheus.io/docs/operating/security/)
- [Grafana Security Guide](https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
