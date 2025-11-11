#!/bin/bash
# Dolphin Observability Stack Management Script
#
# Usage: ./manage.sh [command]
#
# Commands:
#   start   - Start all observability services
#   stop    - Stop all observability services
#   restart - Restart all observability services
#   status  - Show service status
#   logs    - Follow logs from all services
#   clean   - Stop services and remove volumes (WARNING: deletes all data)
#   urls    - Show service URLs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detect docker command (docker compose vs docker-compose)
if command -v docker &> /dev/null && docker compose version &> /dev/null 2>&1; then
    DOCKER_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_CMD="docker-compose"
else
    echo "❌ Error: Neither 'docker compose' nor 'docker-compose' found"
    echo "Please install Docker Compose and try again"
    exit 1
fi

cmd_start() {
    echo "🚀 Starting Dolphin Observability Stack..."
    echo ""

    $DOCKER_CMD up -d

    echo ""
    echo "⏳ Waiting for services to be healthy..."
    sleep 5

    cmd_status

    echo ""
    echo "✨ Observability stack is ready!"
    echo ""
    cmd_urls
}

cmd_stop() {
    echo "🛑 Stopping Dolphin Observability Stack..."
    $DOCKER_CMD down
    echo "✅ All services stopped"
}

cmd_restart() {
    echo "🔄 Restarting Dolphin Observability Stack..."
    $DOCKER_CMD restart
    echo "✅ All services restarted"
    echo ""
    cmd_status
}

cmd_status() {
    echo "📊 Service Status:"
    echo ""
    $DOCKER_CMD ps

    echo ""
    echo "🔍 Health Checks:"

    # Check Prometheus
    if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
        echo "  ✅ Prometheus   http://localhost:9090"
    else
        echo "  ❌ Prometheus   http://localhost:9090 (not responding)"
    fi

    # Check Grafana
    if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
        echo "  ✅ Grafana      http://localhost:3000"
    else
        echo "  ❌ Grafana      http://localhost:3000 (not responding)"
    fi

    # Check Jaeger
    if curl -sf http://localhost:16686/ > /dev/null 2>&1; then
        echo "  ✅ Jaeger       http://localhost:16686"
    else
        echo "  ❌ Jaeger       http://localhost:16686 (not responding)"
    fi

    # Check Loki
    if curl -sf http://localhost:3100/ready > /dev/null 2>&1; then
        echo "  ✅ Loki         http://localhost:3100"
    else
        echo "  ❌ Loki         http://localhost:3100 (not responding)"
    fi
}

cmd_logs() {
    echo "📜 Following logs from all services (Ctrl+C to exit)..."
    echo ""
    $DOCKER_CMD logs -f
}

cmd_clean() {
    echo "⚠️  WARNING: This will stop all services and delete all data!"
    echo ""
    read -p "Are you sure? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "🗑️  Cleaning up..."
        $DOCKER_CMD down -v
        echo "✅ All services stopped and volumes deleted"
    else
        echo "❌ Cancelled"
    fi
}

cmd_urls() {
    echo "📊 Service URLs:"
    echo ""
    echo "  🎨 Grafana (Debugging Dashboard):"
    echo "     http://localhost:3000"
    echo "     Username: admin"
    echo "     Password: admin"
    echo ""
    echo "  🔍 Jaeger (Distributed Traces):"
    echo "     http://localhost:16686"
    echo ""
    echo "  📈 Prometheus (Metrics):"
    echo "     http://localhost:9090"
    echo ""
    echo "  📝 Loki (Logs):"
    echo "     http://localhost:3100"
    echo ""
    echo "💡 Tip: Start KB API with 'uv run kb-api' to begin collecting metrics"
}

cmd_help() {
    echo "Dolphin Observability Stack Management"
    echo ""
    echo "Usage: ./manage.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start   - Start all observability services"
    echo "  stop    - Stop all observability services"
    echo "  restart - Restart all observability services"
    echo "  status  - Show service status and health"
    echo "  logs    - Follow logs from all services"
    echo "  clean   - Stop services and remove volumes (deletes all data)"
    echo "  urls    - Show service URLs"
    echo "  help    - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./manage.sh start          # Start the stack"
    echo "  ./manage.sh status         # Check if services are running"
    echo "  ./manage.sh logs           # View logs"
    echo "  ./manage.sh restart        # Restart all services"
    echo ""
}

# Main command dispatcher
case "${1:-help}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    clean)
        cmd_clean
        ;;
    urls)
        cmd_urls
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo ""
        cmd_help
        exit 1
        ;;
esac
