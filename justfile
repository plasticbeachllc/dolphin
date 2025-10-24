# justfile for building and running OpenWebUI and MCP servers with Python, Docker, and uv

# Load environment variables from .env file
set dotenv-load

# Variables
HOME := env('HOME')
OPENWEBUI_PORT := "3010"
OPENWEBUI_DOCKER_PORT := "8080"
MCP_PORT := "8010"

list:
	just -l

# ==============================================================================
# High-Level Commands
# ==============================================================================

# Clean generated files
clean: stop clean-openwebui clean-mcpo-config

# Start all services
run: start-openwebui start-mcp

# Set up the entire project
setup: setup-env setup-python setup-openwebui

# Stop all services
stop: stop-openwebui stop-mcp

# Run all tests
test: test-mcp

# ==============================================================================
# Environment Management
# ==============================================================================

# Check for .env file and required variables
setup-env:
	@# Check if .env file exists, if not, create it from the template
	@[ -f .env ] || (echo "Creating .env from .env.template..."; cp .env.template .env)
	@# Check if GITHUB_PERSONAL_ACCESS_TOKEN is set and not empty
	@test -n "${GITHUB_PERSONAL_ACCESS_TOKEN}" || (echo "❌ Error: GITHUB_PERSONAL_ACCESS_TOKEN is not set in .env file. Please add it and try again."; exit 1)
	@echo "✅ Environment is configured."

# Install Python dependencies from pyproject.toml
setup-python:
	uv sync

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
	@rm -f .mcpo.pid
	uv run mcpo --config ./mcpo_config.json --port {{MCP_PORT}} & echo $! > .mcpo.pid

# Stop the MCP server orchestrator
stop-mcp:
	@if [ -f .mcpo.pid ]; then \
		echo "Stopping MCP servers..."; \
		kill $(cat .mcpo.pid) || true; \
		rm .mcpo.pid; \
	fi

# ==============================================================================
# MCP Testing
# ==============================================================================

# Test all MCP servers
test-mcp: setup-python
	@echo "Ensuring no old MCP servers are running..."
	@just --quiet stop-mcp
	@just --quiet start-mcp
	@sleep 1 # Give the main server process a moment to start
	@echo "🧪 Running MCP server tests..."
	@# Ensure the test runner executes within the project's virtual environment
	@uv run python -m tests.run_tests http://localhost:{{MCP_PORT}}
	@echo "Stopping MCP servers after test run..."
	@just --quiet stop-mcp

clean-mcpo-config: 
	rm -f .mcpo.pid
	rm -f mcpo_config.json
