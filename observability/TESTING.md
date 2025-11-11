# EP-1 Testing Guide

## Testing Status: ⚠️ UNTESTED IN RUNTIME

**Important**: This implementation has been validated for syntax and configuration correctness, but has **NOT been runtime tested** yet. This document provides a comprehensive testing plan.

## What Has Been Validated ✅

### Static Analysis (Completed)
- ✅ All Python files pass syntax validation
- ✅ All YAML configs are valid (Docker Compose, Prometheus, Loki, Grafana)
- ✅ Grafana dashboard JSON is valid
- ✅ package.json files are valid

### What Has NOT Been Tested ❌

- ❌ Docker Compose stack actually starts
- ❌ Python dependencies install correctly
- ❌ TypeScript compiles with dependencies
- ❌ KB API starts with metrics middleware
- ❌ Prometheus successfully scrapes metrics
- ❌ Grafana can connect to datasources
- ❌ Metrics are actually collected
- ❌ Alerts fire correctly
- ❌ End-to-end integration

## Testing Plan

### Phase 1: Pre-Deployment Testing (30 minutes)

#### 1.1 Install Dependencies

```bash
# Python dependencies
cd /path/to/dolphin
uv pip install -e .

# Verify installation
python -c "from prometheus_client import Counter; print('✅ prometheus_client installed')"
python -c "from opentelemetry import trace; print('✅ opentelemetry installed')"
python -c "from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor; print('✅ opentelemetry-instrumentation-fastapi installed')"
```

#### 1.2 TypeScript Compilation

```bash
# Install Node dependencies
cd shared
npm install

# Verify compilation
npx tsc --noEmit

# Expected: No errors
```

#### 1.3 Start Observability Stack

```bash
cd observability
./start-stack.sh

# Expected output:
# ✅ Prometheus is healthy
# ✅ Grafana is healthy
# ✅ Jaeger is healthy
# ✅ Loki is healthy
```

**Manual verification:**
- Open http://localhost:3000 (Grafana) - Should show login page
- Open http://localhost:9090 (Prometheus) - Should show Prometheus UI
- Open http://localhost:16686 (Jaeger) - Should show Jaeger UI

### Phase 2: KB API Testing (20 minutes)

#### 2.1 Start KB API with Metrics

```bash
cd kb
python -m uvicorn api.server:app_with_lifespan --host 0.0.0.0 --port 8000
```

**Expected startup logs:**
```
✅ Search backend ready
✅ Ingestion pipeline ready
INFO:     Application startup complete.
```

**If it fails**, check:
- Python dependencies installed?
- `prometheus_client` import error?
- `opentelemetry` import error?
- Syntax errors in `kb/api/middleware/metrics.py`?

#### 2.2 Test Metrics Endpoint

```bash
# Test /metrics endpoint
curl http://localhost:8000/metrics

# Expected: Prometheus text format output
# kb_http_requests_total{...} 0.0
# kb_http_request_duration_seconds_bucket{...} 0
```

**If it fails**, check:
- Is middleware registered correctly in `server.py`?
- Are metrics being created without errors?
- Check server logs for exceptions

#### 2.3 Test Health Endpoint

```bash
curl http://localhost:8000/health

# Expected JSON:
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "timestamp": "...",
#   "components": {
#     "api": "healthy"
#   }
# }
```

#### 2.4 Generate Test Metrics

```bash
# Make some requests to generate metrics
for i in {1..10}; do
  curl http://localhost:8000/health
done

# Check metrics again
curl http://localhost:8000/metrics | grep kb_http_requests_total

# Expected: Should show counts > 0
```

### Phase 3: Prometheus Integration (15 minutes)

#### 3.1 Verify Prometheus is Scraping

Open http://localhost:9090/targets

**Expected:**
- Target `kb-api` shows state: **UP**
- Last scrape: Recent timestamp
- Labels: `job="kb-api"`

**If DOWN:**
1. Check Prometheus logs:
   ```bash
   docker-compose logs prometheus
   ```

2. Verify KB API is accessible from Prometheus container:
   ```bash
   docker exec dolphin-prometheus wget -O- http://host.docker.internal:8000/metrics
   ```

3. Check `prometheus/prometheus.yml` scrape config

#### 3.2 Query Metrics in Prometheus

Open http://localhost:9090/graph

**Test queries:**
```promql
# Should return 1 (service is up)
up{job="kb-api"}

# Should show request count
kb_http_requests_total

# Should show request rate
rate(kb_http_requests_total[5m])
```

**Expected:** All queries return data

### Phase 4: Grafana Integration (15 minutes)

#### 4.1 Verify Datasources

Open http://localhost:3000

1. Login: admin / admin
2. Go to Configuration → Data Sources
3. Click on "Prometheus"
4. Click "Test" button

**Expected:** ✅ "Data source is working"

**If fails:**
- Check Prometheus URL in datasource config
- Verify Prometheus is accessible from Grafana container

#### 4.2 Test Dashboard

1. Go to Dashboards → Browse
2. Open "Dolphin System Health"

**Expected:**
- All panels load without errors
- "Request Rate" panel shows data (if requests were made)
- "Error Rate" shows 0%
- No "No data" errors

**If "No data":**
- Check time range (top right) - should include recent data
- Verify queries in panel inspector
- Check that metrics names match what's exposed by KB API

#### 4.3 Test Explore

1. Go to Explore
2. Select "Prometheus" datasource
3. Try query: `up`

**Expected:** Should show `up{job="kb-api"} 1`

### Phase 5: Alert Testing (10 minutes)

#### 5.1 Verify Alert Rules

Open http://localhost:9090/alerts

**Expected:** Should see all alert rules from `alerts.yml`:
- HighErrorRate
- HighLatency
- CostSpike
- ServiceDown
- etc.

#### 5.2 Fire Test Alert

```bash
# Send test alert to Alertmanager
curl -X POST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Test alert from testing"
    }
  }
]'
```

Open http://localhost:9093

**Expected:** Should see "TestAlert" in Alertmanager UI

### Phase 6: Integration Testing (20 minutes)

#### 6.1 End-to-End Request Flow

1. Make a real search request to KB API
2. Verify metrics are collected
3. Verify Prometheus scraped them
4. Verify Grafana shows the data

```bash
# Make a search request
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test query",
    "repos": ["test-repo"],
    "top_k": 5
  }'

# Wait 15-30 seconds for Prometheus to scrape

# Check in Grafana "Request Rate" panel
# Should show a spike
```

#### 6.2 Error Tracking

1. Make a request that causes an error
2. Verify error is tracked in metrics

```bash
# Force an error (adjust endpoint as needed)
curl http://localhost:8000/invalid-endpoint

# Check metrics
curl http://localhost:8000/metrics | grep 'status_code="404"'

# Should see count > 0
```

### Phase 7: Performance Testing (15 minutes)

#### 7.1 Measure Overhead

```bash
# Install Apache Bench or similar
# ab -n 1000 -c 10 http://localhost:8000/health

# Compare:
# 1. Before adding metrics middleware (baseline)
# 2. After adding metrics middleware

# Expected: <5ms additional latency
```

#### 7.2 Memory Usage

```bash
# Check memory before metrics
ps aux | grep "uvicorn" | awk '{print $6}'

# Run for 10 minutes with metrics collection
# Check memory again

# Expected: <50MB increase
```

## Known Issues & Resolutions

### Issue: Prometheus Cannot Scrape KB API

**Symptoms:**
- Prometheus target shows "DOWN"
- Error: "connection refused" or "no route to host"

**Resolution:**
1. Verify KB API is running: `curl http://localhost:8000/metrics`
2. Check Docker network: Use `host.docker.internal` instead of `localhost`
3. For Linux: May need to use host networking mode in docker-compose

### Issue: Grafana Shows "No Data"

**Symptoms:**
- Dashboard panels show "No Data"
- Explore shows empty results

**Resolution:**
1. Verify Prometheus datasource test passes
2. Check time range includes recent data
3. Verify metrics names in queries match exposed metrics
4. Check browser console for errors

### Issue: Python Import Errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'prometheus_client'
```

**Resolution:**
```bash
# Install dependencies
cd /path/to/dolphin
uv pip install -e .

# Or manually
pip install prometheus-client opentelemetry-api opentelemetry-sdk \
  opentelemetry-instrumentation-fastapi opentelemetry-exporter-jaeger
```

### Issue: TypeScript Compilation Errors

**Symptoms:**
```
Cannot find module '@opentelemetry/api'
```

**Resolution:**
```bash
cd shared
npm install
# or
bun install
```

### Issue: Docker Compose Fails to Start

**Symptoms:**
- Service fails to start
- Port conflicts
- Volume mount errors

**Resolution:**
1. Check ports are not in use: `lsof -i :3000` (etc.)
2. Verify Docker has enough resources (4GB RAM minimum)
3. Check Docker logs: `docker-compose logs <service>`

## Testing Checklist

### Pre-Deployment ✅
- [ ] Python syntax validates
- [ ] YAML configs validate
- [ ] JSON configs validate
- [ ] Dependencies documented

### Deployment ✅
- [ ] Observability stack starts
- [ ] All services healthy
- [ ] Web UIs accessible
- [ ] No error logs

### KB API Integration ✅
- [ ] API starts with metrics
- [ ] /metrics endpoint works
- [ ] /health endpoint works
- [ ] Metrics are generated on requests
- [ ] No performance degradation

### Observability Stack Integration ✅
- [ ] Prometheus scrapes KB API
- [ ] Metrics visible in Prometheus
- [ ] Grafana connects to Prometheus
- [ ] Dashboard loads and shows data
- [ ] Alerts are loaded

### End-to-End ✅
- [ ] Real requests generate metrics
- [ ] Metrics visible in Grafana
- [ ] Alerts can fire
- [ ] Logs are collected (when implemented)
- [ ] Traces work (when implemented)

## Automated Testing Script

```bash
#!/bin/bash
# test-ep1.sh - Automated EP-1 testing

set -e

echo "🧪 EP-1 Integration Testing"
echo "=========================="
echo

# 1. Check dependencies
echo "📦 Checking dependencies..."
python -c "from prometheus_client import Counter" || exit 1
echo "✅ Python dependencies OK"

# 2. Start observability stack
echo "🚀 Starting observability stack..."
cd observability
docker-compose up -d
sleep 15

# 3. Verify services
echo "🔍 Verifying services..."
curl -f http://localhost:9090/-/healthy || exit 1
curl -f http://localhost:3000/api/health || exit 1
curl -f http://localhost:16686/ || exit 1
echo "✅ All services healthy"

# 4. Start KB API (in background)
echo "🚀 Starting KB API..."
cd ../kb
python -m uvicorn api.server:app_with_lifespan --host 0.0.0.0 --port 8000 &
KB_PID=$!
sleep 5

# 5. Test endpoints
echo "🧪 Testing endpoints..."
curl -f http://localhost:8000/health || exit 1
curl -f http://localhost:8000/metrics || exit 1
echo "✅ KB API endpoints OK"

# 6. Generate test metrics
echo "📊 Generating test metrics..."
for i in {1..10}; do
  curl -s http://localhost:8000/health > /dev/null
done

# 7. Wait for Prometheus scrape
echo "⏳ Waiting for Prometheus scrape..."
sleep 20

# 8. Verify metrics in Prometheus
echo "🔍 Verifying Prometheus..."
METRICS=$(curl -s "http://localhost:9090/api/v1/query?query=up{job='kb-api'}" | grep -o '"value":\[.*\]')
if [[ $METRICS == *"1"* ]]; then
  echo "✅ Prometheus scraping successfully"
else
  echo "❌ Prometheus not scraping KB API"
  exit 1
fi

# 9. Clean up
echo "🧹 Cleaning up..."
kill $KB_PID
cd ../observability
docker-compose down

echo
echo "✅ All tests passed!"
echo "EP-1 implementation is working correctly."
```

## Next Steps After Testing

1. **If all tests pass:**
   - Document any configuration tweaks needed
   - Update README with any gotchas found
   - Consider PR ready for review

2. **If tests fail:**
   - Fix issues found
   - Update implementation
   - Re-test
   - Update documentation

3. **Performance concerns:**
   - Run extended load tests
   - Profile memory usage over time
   - Optimize if needed

4. **Security review:**
   - Verify no secrets in logs
   - Check PII sanitization works
   - Review alert configurations

## Support

If you encounter issues during testing:
1. Check logs: `docker-compose logs <service>`
2. Review this testing guide
3. See `DEPLOYMENT.md` for troubleshooting
4. Create GitHub issue with logs and error details
