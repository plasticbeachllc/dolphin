#!/bin/bash
# Set up Prometheus and Grafana for performance monitoring
#
# Usage:
#   ./scripts/setup_monitoring.sh

set -e

echo "========================================="
echo "Setting up Performance Monitoring"
echo "========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
  echo "Error: Docker not found. Please install Docker first."
  exit 1
fi

# Create monitoring directories
mkdir -p monitoring/{prometheus,grafana}

# Create Prometheus config
cat > monitoring/prometheus/prometheus.yml <<EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'kb-api'
    static_configs:
      - targets: ['host.docker.internal:8420']
    metrics_path: '/metrics'
EOF

echo "✓ Created Prometheus configuration"

# Start Prometheus
echo ""
echo "Starting Prometheus..."
docker run -d \
  --name ep6-prometheus \
  -p 9090:9090 \
  -v "$(pwd)/monitoring/prometheus:/etc/prometheus" \
  prom/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.console.libraries=/usr/share/prometheus/console_libraries \
  --web.console.templates=/usr/share/prometheus/consoles

if [ $? -eq 0 ]; then
  echo "✓ Prometheus started on http://localhost:9090"
else
  echo "Note: Prometheus container may already be running"
fi

# Start Grafana
echo ""
echo "Starting Grafana..."
docker run -d \
  --name ep6-grafana \
  -p 3001:3000 \
  -v "$(pwd)/monitoring/grafana:/var/lib/grafana" \
  -e "GF_SECURITY_ADMIN_PASSWORD=admin" \
  grafana/grafana

if [ $? -eq 0 ]; then
  echo "✓ Grafana started on http://localhost:3001"
  echo "  Username: admin"
  echo "  Password: admin"
else
  echo "Note: Grafana container may already be running"
fi

# Create Grafana dashboard template
cat > monitoring/grafana/ep6-dashboard.json <<EOF
{
  "dashboard": {
    "title": "EP-6 Performance Optimization",
    "panels": [
      {
        "title": "Indexing Throughput (files/min)",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(kb_indexing_files_total[5m]) * 60"
          }
        ]
      },
      {
        "title": "Search Latency (p50, p95, p99)",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, kb_search_duration_seconds_bucket)"
          },
          {
            "expr": "histogram_quantile(0.95, kb_search_duration_seconds_bucket)"
          },
          {
            "expr": "histogram_quantile(0.99, kb_search_duration_seconds_bucket)"
          }
        ]
      },
      {
        "title": "Cache Hit Rate (%)",
        "type": "gauge",
        "targets": [
          {
            "expr": "(kb_cache_hits_total / (kb_cache_hits_total + kb_cache_misses_total)) * 100"
          }
        ]
      },
      {
        "title": "Database Size (GB)",
        "type": "graph",
        "targets": [
          {
            "expr": "kb_database_size_bytes / 1e9"
          }
        ]
      },
      {
        "title": "Resource Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "process_cpu_seconds_total"
          },
          {
            "expr": "process_resident_memory_bytes / 1e9"
          }
        ]
      }
    ]
  }
}
EOF

echo ""
echo "✓ Created Grafana dashboard template"

echo ""
echo "========================================="
echo "Setup Complete"
echo "========================================="
echo ""
echo "Access points:"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana: http://localhost:3001 (admin/admin)"
echo ""
echo "Next steps:"
echo "  1. Configure Prometheus data source in Grafana"
echo "  2. Import dashboard from monitoring/grafana/ep6-dashboard.json"
echo "  3. Add metrics instrumentation to KB API and MCP bridge"
echo ""
echo "To stop monitoring:"
echo "  docker stop ep6-prometheus ep6-grafana"
echo ""
echo "To remove monitoring:"
echo "  docker rm ep6-prometheus ep6-grafana"
echo ""
