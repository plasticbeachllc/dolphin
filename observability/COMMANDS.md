# Observability Stack - Quick Command Reference

## Management Commands

```bash
cd observability

# Start all services
./manage.sh start

# Stop all services
./manage.sh stop

# Restart all services
./manage.sh restart

# Check service status
./manage.sh status

# View live logs
./manage.sh logs

# Show service URLs
./manage.sh urls

# Clean up (deletes all data!)
./manage.sh clean
```

## Individual Service Commands

```bash
# Restart just Grafana (e.g., to reload dashboards)
docker compose restart grafana

# View logs for specific service
docker compose logs -f grafana
docker compose logs -f prometheus
docker compose logs -f jaeger
docker compose logs -f loki

# Execute command in container
docker compose exec prometheus sh
```

## Service Access

| Service        | URL                    | Purpose                                |
| -------------- | ---------------------- | -------------------------------------- |
| **Grafana**    | http://localhost:3000  | Main debugging dashboard (admin/admin) |
| **Jaeger**     | http://localhost:16686 | View distributed traces                |
| **Prometheus** | http://localhost:9090  | Query metrics directly                 |
| **Loki**       | http://localhost:3100  | Log aggregation API                    |

## KB API Commands

```bash
# Start KB API (from project root)
uv run kb-api

# Check metrics endpoint
curl http://localhost:8000/metrics

# Check health endpoint
curl http://localhost:8000/health

# Test search (generates metrics)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "repo_name": "test-repo"}'
```

## MCP Bridge Commands

```bash
# Start MCP bridge (from repo root)
cd mcp-bridge
bun run --hot src/index.ts
```

## Indexing Commands

```bash
# Index a repository (from repo root)
uv run dolphin index <repo-name>
```

## Debugging Workflows

### View Request Latency

```bash
# 1. Start stack
./manage.sh start

# 2. Open Grafana
open http://localhost:3000

# 3. Go to "Dolphin Debugging Dashboard"
# 4. Generate some traffic
curl http://localhost:8000/health

# 5. See latency graph update in real-time
```

### Debug Errors

```bash
# 1. Check error logs in Grafana dashboard
# 2. Or query Loki directly
curl -G http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={job="dolphin"} |~ "ERROR"'

# 3. Or view logs from Docker
./manage.sh logs | grep ERROR
```

### Trace a Request

```bash
# 1. Make a request to KB API
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "repo_name": "dolphin"}'

# 2. Open Jaeger UI
open http://localhost:16686

# 3. Search for traces from "kb-api" service
# 4. Click trace to see detailed span breakdown
```

## Prometheus Queries

Access http://localhost:9090 and try:

```promql
# Request rate by endpoint
rate(kb_http_requests_total[1m])

# P95 latency
histogram_quantile(0.95, rate(kb_http_request_duration_seconds_bucket[1m]))

# Error rate
sum(rate(kb_http_requests_total{status_code=~"5.."}[1m]))

# Active connections
kb_http_requests_total

# Vector search latency
kb_vector_search_duration_seconds
```

## Grafana Dashboard

After starting Grafana, find the dashboard:

1. Click "Dashboards" (left sidebar)
2. Navigate to "Dolphin" folder
3. Click "Dolphin Debugging Dashboard"

Or use quick search: `Ctrl+K` → type "debugging"

## Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker ps

# Check ports aren't in use
lsof -i :3000  # Grafana
lsof -i :9090  # Prometheus
lsof -i :16686 # Jaeger

# View startup errors
./manage.sh logs
```

### Dashboard not showing in Grafana

```bash
# Restart Grafana to reload dashboards
docker compose restart grafana

# Check dashboard file exists
ls -l grafana/dashboards/debugging.json

# View Grafana logs
docker compose logs -f grafana
```

### No metrics in Prometheus

```bash
# Check Prometheus targets
open http://localhost:9090/targets

# Should show "kb-api" as UP
# If DOWN, check KB API is running:
curl http://localhost:8000/metrics
```

### No traces in Jaeger

```bash
# Verify Jaeger is running
curl http://localhost:16686/api/services

# Check if KB API is configured for tracing
# (Phase 2 - not yet implemented)
```

## Data Management

```bash
# View data volumes
docker volume ls | grep dolphin

# Backup Grafana dashboards
docker compose exec grafana \
  tar czf - /var/lib/grafana/dashboards > grafana-backup.tar.gz

# Clean up all data (WARNING: deletes everything!)
./manage.sh clean
```

## Common Tasks

### Daily Development

```bash
# 1. Start stack once
./manage.sh start

# 2. Start KB API
uv run kb-api

# 3. Open Grafana dashboard
open http://localhost:3000

# 4. Work on code, view metrics in real-time
# 5. At end of day (optional)
./manage.sh stop
```

### Performance Testing

```bash
# 1. Start stack
./manage.sh start

# 2. Generate load
for i in {1..100}; do
  curl -s http://localhost:8000/health > /dev/null
done

# 3. View latency breakdown in Grafana
# 4. Check Prometheus queries
open http://localhost:9090
```

### Debugging Production Issue

```bash
# 1. Start stack with same config
./manage.sh start

# 2. Reproduce issue locally
# 3. Check error logs in Grafana "Error Logs" panel
# 4. View trace in Jaeger to see where it failed
# 5. Query Prometheus for patterns
```

## Next Steps

- See [README.md](./README.md) for detailed usage
- See [TESTING.md](./TESTING.md) for testing procedures
- See [DEPLOYMENT.md](./DEPLOYMENT.md) for production deployment
