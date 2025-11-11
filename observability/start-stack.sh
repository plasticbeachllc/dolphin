#!/bin/bash
# Start Dolphin Observability Stack
#
# This script starts all observability services and verifies they are healthy.

set -e

echo "🚀 Starting Dolphin Observability Stack..."
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose is not installed. Please install it and try again."
    exit 1
fi

echo "📦 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check if all services are running
echo ""
echo "🔍 Checking service status..."
docker-compose ps

# Verify Prometheus
echo ""
echo "🧪 Testing Prometheus..."
if curl -f http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "✅ Prometheus is healthy"
else
    echo "⚠️  Prometheus may not be ready yet"
fi

# Verify Grafana
echo "🧪 Testing Grafana..."
if curl -f http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "✅ Grafana is healthy"
else
    echo "⚠️  Grafana may not be ready yet"
fi

# Verify Jaeger
echo "🧪 Testing Jaeger..."
if curl -f http://localhost:16686/ > /dev/null 2>&1; then
    echo "✅ Jaeger is healthy"
else
    echo "⚠️  Jaeger may not be ready yet"
fi

# Verify Loki
echo "🧪 Testing Loki..."
if curl -f http://localhost:3100/ready > /dev/null 2>&1; then
    echo "✅ Loki is healthy"
else
    echo "⚠️  Loki may not be ready yet"
fi

echo ""
echo "✨ Observability stack is ready!"
echo ""
echo "📊 Access the following services:"
echo "  • Grafana:       http://localhost:3000 (admin/admin)"
echo "  • Prometheus:    http://localhost:9090"
echo "  • Jaeger:        http://localhost:16686"
echo "  • Alertmanager:  http://localhost:9093"
echo ""
echo "📖 Next steps:"
echo "  1. Open Grafana and change the default password"
echo "  2. Import dashboards from grafana/dashboards/"
echo "  3. Start Dolphin services with metrics enabled"
echo "  4. Check Prometheus targets: http://localhost:9090/targets"
echo ""
echo "📚 For more information, see:"
echo "  • README.md - Overview and usage"
echo "  • DEPLOYMENT.md - Detailed deployment guide"
echo ""
