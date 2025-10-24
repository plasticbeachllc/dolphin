# justfile for building and running OpenWebUI and MCP servers with Python, Docker, and uv

# Variables
HOME := env('HOME')
OPENWEBUI_PORT := "3010"
OPENWEBUI_DOCKER_PORT := "8080"

list:
    just -l

# ==============================================================================
# High-Level Commands
# ==============================================================================

# Start all services
run: start-openwebui start-mcp

# Stop all services
stop: stop-openwebui

# ==============================================================================
# OpenWebUI Management
# ==============================================================================

# Pull OpenWebUI Docker image
pull-openwebui:
    docker pull ghcr.io/open-webui/open-webui:main

# Start OpenWebUI container
start-openwebui:
    @echo "Starting OpenWebUI..."
    docker run -d -p {{OPENWEBUI_PORT}}:{{OPENWEBUI_DOCKER_PORT}} --add-host=host.docker.internal:host-gateway -e WEBUI_AUTH=False -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
    @echo "✅ OpenWebUI started and available at http://localhost:{{OPENWEBUI_PORT}}"

# Stop and remove OpenWebUI container if running
stop-openwebui:
    @echo "Stopping OpenWebUI..."
    docker stop open-webui || true
    docker rm open-webui || true

# Set up OpenWebUI (pull, build, start)
setup-openwebui: stop-openwebui pull-openwebui start-openwebui

# Clean all OpenWebUI images and volumes
clean-openwebui:
    docker image rm ghcr.io/open-webui/open-webui:main || true
    docker volume rm open-webui || true

# ==============================================================================
# MCP (Multi-tool Caching Proxy) Management
# ==============================================================================

# Start the MCP server orchestrator
start-mcp:
    @echo "Generating MCP config from template..."
    @# Using '|' as a separator for sed to avoid issues with paths containing '/'
    @sed 's|__HOME__|{{HOME}}|g' mcpo_config.template.json > mcpo_config.json
    @echo "Starting MCP servers..."
    uvx mcpo --config ./mcpo_config.json

# Clean generated files
clean:
    rm -f mcpo_config.json
