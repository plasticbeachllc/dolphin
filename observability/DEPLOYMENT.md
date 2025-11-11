# EP-1 Deployment Guide

## Prerequisites

- Docker and Docker Compose installed
- Python 3.12+ (for KB API)
- Bun or Node.js 20+ (for TypeScript services)
- At least 4GB RAM for observability stack
- 10GB disk space for logs/metrics

## Installation Steps

### 1. Install Dependencies

#### Python (KB API)
```bash
cd /path/to/dolphin
uv pip install -e .
# Or with pip
pip install prometheus-client opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-exporter-jaeger
```

#### TypeScript (Shared utilities)
```bash
cd shared
npm install
# Or with bun
bun install
```

### 2. Start Observability Stack

```bash
cd observability
docker-compose up -d
```

**Verify all services are running:**
```bash
docker-compose ps
```

You should see:
- ✅ dolphin-prometheus (port 9090)
- ✅ dolphin-jaeger (port 16686)
- ✅ dolphin-loki (port 3100)
- ✅ dolphin-promtail
- ✅ dolphin-grafana (port 3000)
- ✅ dolphin-alertmanager (port 9093)

### 3. Access Web UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| Jaeger | http://localhost:16686 | - |
| Alertmanager | http://localhost:9093 | - |

### 4. Configure Grafana

Grafana datasources are auto-provisioned, but verify:

1. Open http://localhost:3000
2. Login with admin/admin (change password when prompted)
3. Go to Configuration → Data Sources
4. Verify you see:
   - ✅ Prometheus (default)
   - ✅ Loki
   - ✅ Jaeger

### 5. Import Dashboards

The "Dolphin System Health" dashboard is auto-provisioned in `grafana/dashboards/`.

To view it:
1. Go to Dashboards → Browse
2. Open "Dolphin System Health"

## Starting Dolphin Services

### KB API (with metrics)

```bash
cd kb
python -m uvicorn api.server:app_with_lifespan --host 0.0.0.0 --port 8000 --reload
```

**Verify metrics:**
```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/health
```

### Agent Core (when implemented)

```bash
cd agent-core
bun run src/main.ts
```

**Verify metrics:**
```bash
curl http://localhost:9091/metrics
curl http://localhost:9091/health
```

### MCP Bridge (when implemented)

```bash
cd mcp-bridge
bun run src/main.ts
```

**Verify metrics:**
```bash
curl http://localhost:9092/metrics
curl http://localhost:9092/health
```

## Verification

### Check Prometheus is Scraping

1. Open http://localhost:9090/targets
2. Verify all targets show "UP" status
3. If "DOWN", check:
   - Service is running
   - Port is correct
   - Firewall allows connection

### Check Metrics in Grafana

1. Open http://localhost:3000
2. Go to Explore
3. Select "Prometheus" datasource
4. Try query: `up`
5. You should see all services with `value=1`

### Test Alerting

```bash
# Fire a test alert
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Test alert from deployment"
    }
  }
]'
```

Check Alertmanager UI: http://localhost:9093

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Observability
JAEGER_ENDPOINT=http://localhost:14268/api/traces
PROMETHEUS_PUSHGATEWAY=http://localhost:9091
LOKI_URL=http://localhost:3100

# Cost tracking
DAILY_BUDGET_LIMIT=100.0

# Log level
LOG_LEVEL=INFO
```

### Customize Scrape Targets

Edit `observability/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'kb-api'
    static_configs:
      - targets: ['host.docker.internal:8000']  # Change port if needed
```

### Customize Alerts

Edit `observability/prometheus/alerts.yml` to add/modify alerts.

Reload Prometheus config:
```bash
curl -X POST http://localhost:9090/-/reload
```

### Configure Slack Alerts

Edit `observability/prometheus/alertmanager.yml`:

```yaml
receivers:
  - name: 'slack-critical'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
        title: '🚨 {{ .GroupLabels.alertname }}'
        text: |
          *Summary:* {{ .CommonAnnotations.summary }}
          *Description:* {{ .CommonAnnotations.description }}
```

Reload Alertmanager:
```bash
docker-compose restart alertmanager
```

## Troubleshooting

### Metrics not showing in Prometheus

**Problem**: `/metrics` endpoint returns data, but Prometheus shows no data.

**Solution**:
1. Check Prometheus targets: http://localhost:9090/targets
2. Verify scrape config in `prometheus/prometheus.yml`
3. For Mac/Windows Docker Desktop, use `host.docker.internal` instead of `localhost`
4. Check Prometheus logs: `docker-compose logs prometheus`

### Grafana shows "No data"

**Problem**: Dashboard panels show "No data".

**Solution**:
1. Check time range (top right) - should include recent data
2. Verify Prometheus datasource: Configuration → Data Sources → Prometheus → Test
3. Try a simple query in Explore: `up`
4. Check metric names match in panel queries

### Jaeger shows no traces

**Problem**: No traces appear in Jaeger UI.

**Solution**:
1. Verify `JAEGER_ENDPOINT` environment variable is set
2. Check if application has OpenTelemetry initialized
3. Verify trace sampling rate (default: 100% for development)
4. Check Jaeger logs: `docker-compose logs jaeger`

### High resource usage

**Problem**: Docker containers using too much CPU/memory.

**Solution**:
1. Reduce Prometheus retention:
   ```yaml
   # prometheus/prometheus.yml
   --storage.tsdb.retention.time=7d  # Reduce from 30d
   ```

2. Reduce Loki retention:
   ```yaml
   # loki/loki-config.yml
   retention_period: 168h  # 7 days instead of 30
   ```

3. Adjust scrape interval:
   ```yaml
   # prometheus/prometheus.yml
   global:
     scrape_interval: 30s  # Increase from 15s
   ```

### Port conflicts

**Problem**: Port already in use (e.g., 3000, 9090).

**Solution**:
Edit `docker-compose.yml` to change ports:
```yaml
services:
  grafana:
    ports:
      - "3001:3000"  # Change external port
```

## Production Deployment

### Security Hardening

1. **Change default passwords:**
   ```bash
   # Grafana
   docker-compose exec grafana grafana-cli admin reset-admin-password <new-password>
   ```

2. **Enable TLS:**
   - Add reverse proxy (nginx/traefik)
   - Configure SSL certificates
   - Update datasource URLs to use HTTPS

3. **Restrict access:**
   - Use firewall rules
   - Enable authentication on all services
   - Use VPN for internal access

### Persistent Storage

Add named volumes in `docker-compose.yml`:

```yaml
volumes:
  prometheus_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/prometheus
```

### Backup Configuration

```bash
# Backup Prometheus data
docker run --rm -v dolphin_prometheus_data:/data -v $(pwd):/backup alpine tar czf /backup/prometheus-backup.tar.gz /data

# Backup Grafana dashboards
docker-compose exec grafana grafana-cli admin export-dashboards > dashboards-backup.json
```

### High Availability

For production HA:
- Use Prometheus federation or Thanos for multi-cluster metrics
- Deploy Grafana with SQLite/PostgreSQL backend
- Use Jaeger with Cassandra/Elasticsearch storage
- Set up Loki with S3/GCS storage

## Monitoring the Monitors

Set up monitoring for the observability stack itself:

1. **Prometheus self-monitoring:**
   ```promql
   # Prometheus targets down
   up{job="prometheus"} == 0

   # Prometheus storage issues
   prometheus_tsdb_storage_blocks_bytes > 10e9
   ```

2. **Grafana health:**
   ```bash
   curl http://localhost:3000/api/health
   ```

3. **Disk usage alerts:**
   ```promql
   # Docker volume usage
   (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
   ```

## Maintenance

### Daily
- Check Alertmanager for firing alerts
- Review Grafana dashboards for anomalies

### Weekly
- Review Prometheus targets health
- Check disk usage for time-series data
- Verify backup processes

### Monthly
- Review and update alert rules
- Optimize dashboard queries
- Clean up old/unused metrics

## Upgrading

### Update Observability Stack

```bash
cd observability
docker-compose pull
docker-compose up -d
```

### Update Python Dependencies

```bash
uv pip install --upgrade prometheus-client opentelemetry-api
```

### Update TypeScript Dependencies

```bash
cd shared
npm update
```

## Support

For issues:
1. Check logs: `docker-compose logs <service>`
2. Review `/docs/EP1/` documentation
3. Create GitHub issue: https://github.com/plasticbeachllc/dolphin/issues

## Next Steps

After deployment:
1. ✅ Verify all services are healthy
2. ✅ Import Grafana dashboards
3. ✅ Configure alert channels (Slack/PagerDuty)
4. ✅ Set up backup processes
5. ✅ Document runbook procedures
6. ⏳ Implement Phase 2: Distributed Tracing
7. ⏳ Implement Phase 3: Advanced Dashboards
