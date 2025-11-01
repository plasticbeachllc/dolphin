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
run: start

# Start all services (Ollama, OpenWebUI, MCP) and wait for readiness
start:
	@echo "Starting all services..."
	@just --quiet ollama-start
	@echo "Waiting for Ollama to become ready..."
	@TIMEOUT=30; while ! just --quiet ollama-check >/dev/null 2>&1; do \
		sleep 1; TIMEOUT=$((TIMEOUT-1)); \
		if [ $TIMEOUT -le 0 ]; then echo "❌ Timed out waiting for Ollama"; exit 1; fi; \
	done
	@just --quiet start-openwebui
	@echo "Waiting for OpenWebUI to become ready on port {{OPENWEBUI_PORT}}..."
	@TIMEOUT=60; while ! just --quiet openwebui-check >/dev/null 2>&1; do \
		sleep 2; TIMEOUT=$((TIMEOUT-1)); \
		if [ $TIMEOUT -le 0 ]; then echo "❌ Timed out waiting for OpenWebUI"; exit 1; fi; \
	done
	@just --quiet start-mcpo
	@echo "Waiting for MCP to listen on port {{MCP_PORT}}..."
	@TIMEOUT=30; while ! just --quiet mcp-check >/dev/null 2>&1; do \
		sleep 1; TIMEOUT=$((TIMEOUT-1)); \
		if [ $TIMEOUT -le 0 ]; then echo "❌ Timed out waiting for MCP"; exit 1; fi; \
	done
	@echo "✅ All services are up:"
	@echo " - Ollama API:       http://localhost:11434"
	@echo " - OpenWebUI:        http://localhost:{{OPENWEBUI_PORT}}"
	@echo " - MCP Orchestrator: http://localhost:{{MCP_PORT}}"

# Set up the entire project
setup: setup-env setup-python setup-openwebui

# Development setup (without OpenWebUI)
setup-dev: setup-env setup-python

# Stop all services
stop: stop-mcpo stop-openwebui ollama-stop

# Run all tests
# test: 

# ==============================================================================
# Environment Management
# ==============================================================================

# Check for .env file and required variables
setup-env:
	@# Check if .env file exists, if not, create it from the template
	@[ -f .env ] || (echo "Creating .env from .env.template..."; cp .env.template .env)
	@# Check if GITHUB_PERSONAL_ACCESS_TOKEN is set and not empty
	@test -n "${GITHUB_PERSONAL_ACCESS_TOKEN}" || (echo "❌ Error: GITHUB_PERSONAL_ACCESS_TOKEN is not set in .env file. Please add it and try again."; exit 1)
	@test -n "${OPENAI_API_KEY}" || (echo "❌ Error: OPENAI_API_KEY is not set in .env file. Please add it and try again."; exit 1)
	@echo "✅ Environment is configured."

# Install Python dependencies from pyproject.toml
setup-python:
	uv sync --group test

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

# Health check for OpenWebUI
openwebui-check:
	@curl -sSf http://localhost:{{OPENWEBUI_PORT}}/ >/dev/null

# ==============================================================================
# Ollama (Homebrew Services) Management
# ==============================================================================

# Start Ollama as a background macOS service
ollama-start:
	@echo "Starting Ollama via Homebrew services..."
	brew services start ollama

# Stop the Ollama service
ollama-stop:
	@echo "Stopping Ollama via Homebrew services..."
	brew services stop ollama

# Restart the Ollama service
ollama-restart:
	@echo "Restarting Ollama via Homebrew services..."
	brew services restart ollama

# Show Ollama service status and port
ollama-status:
	@echo "Ollama service status:"
	brew services list | grep -E '^ollama\s' || true
	@echo "Checking if port 11434 is listening:"
	lsof -nP -iTCP:11434 -sTCP:LISTEN || true

# Health check for the local Ollama API
ollama-check:
	@echo "Checking Ollama API at http://localhost:11434 ..."
	@curl -sSf http://localhost:11434/api/tags >/dev/null && echo "API reachable" || (echo "API not reachable"; exit 1)


# ==============================================================================
# Testing
# ==============================================================================


# Test all components using pytest
test: setup-python
	@echo "🧪 Running all tests with pytest..."
	@uv run pytest -q

# Run unit tests only
test-unit: setup-python
	@echo "🧪 Running unit tests..."
	@uv run pytest tests/unit/ -q

# Run integration tests only
test-integration: setup-python
	@echo "🧪 Running integration tests..."
	@uv run pytest tests/integration/ -q

# Run tests with coverage reporting
test-coverage: setup-python
	@echo "🧪 Running tests with coverage..."
	@uv run pytest --cov=src/pb_kb --cov-report=html --cov-report=term-missing

# Run specific test file
test-file: setup-python
	@echo "🧪 Running specific test file: $(file)"
	@uv run pytest $(file) -v

# Run tests with detailed output
test-verbose: setup-python
	@echo "🧪 Running tests with verbose output..."
	@uv run pytest -v

# ==============================================================================
# MCP(o)
# ==============================================================================

# MCP readiness check
mcpo-check:
	@lsof -nP -iTCP:{{MCP_PORT}} -sTCP:LISTEN >/dev/null 2>&1

# Start the MCP server orchestrator
start-mcpo:
	@echo "Generating MCP config from template..."
	@# Using '|' as a separator for sed to avoid issues with paths containing '/'
	@sed 's|__HOME__|{{HOME}}|g' mcpo_config.template.json > mcpo_config.json
	@echo "Starting MCP servers..."
	@rm -f .mcpo.pid
	uv run mcpo --config ./mcpo_config.json --port {{MCP_PORT}} & echo $! > .mcpo.pid

# Stop the MCP server orchestrator
stop-mcpo:
	@if [ -f .mcpo.pid ]; then \
		echo "Stopping MCP servers..."; \
		kill $(cat .mcpo.pid) || true; \
		rm .mcpo.pid; \
	fi

show-mcpo:
	lsof -i :{{MCP_PORT}}

clean-mcpo-config: 
	rm -f .mcpo.pid
	rm -f mcpo_config.json

# ==============================================================================
# Personas CLI
# ==============================================================================

# Wrap the Typer CLI commands from personas/scripts/personas.py
personas-preview:
	uv run python -m personas.scripts.personas preview $*

personas-generate:
	uv run python -m personas.scripts.personas generate $*

personas-list:
	uv run python -m personas.scripts.personas preview --list

# ==============================================================================
# KB Pipeline Development
# ==============================================================================

# Run KB pipeline CLI
kb:
	uv run python -m pb_kb.ingest.cli $*

# Run KB API server
kb-api:
	uv run python -m pb_kb.api.app $*


# Defaults (override on CLI: just NAME=myrepo ...)
NAME := "dolphin"
REPO_PATH := "$(pwd)"

default:
  @just --list

# --- Environment & Setup ---

venv:
  python3 -m venv .venv
  . .venv/bin/activate && pip install -U pip
  . .venv/bin/activate && pip install -e .[dev]

bun-install:
  cd mcp-bridge && bun install

# --- Services ---

api:
  uv run kb-api

mcp:
  bun run mcp-bridge/src/index.ts

# --- Ingestion ---

init:
  uv run kb init

add-repo name:
  uv run kb add-repo {{name}} $(pwd) --default-embed-model large

index name:
  uv run kb index {{name}}

reindex name:
  uv run kb index {{name}} --full --force

reset name:
  just init
  just add-repo {{name}} $(pwd)
  just reindex {{name}}

# --- Search & Tools ---

repos:
  ./bin/kb-search repos

info:
  ./bin/kb-search info

health:
  ./bin/kb-search health

search query:
  ./bin/kb-search search "{{query}}"

chunk id:
  ./bin/kb-search chunk {{id}}

lines repo path start end:
  ./bin/kb-search lines {{repo}} {{path}} {{start}} {{end}}

curl-search query:
  ./bin/kb-search curl-search "{{query}}"

# --- Logs ---

tail-mcp:
  tail -f mcp-bridge/logs/mcp.log

# --- Clean (dangerous) ---

store-clean:
  @echo "This will DELETE ~/.dolphin/knowledge_store"
  @echo "Press Ctrl-C to abort or wait 5 seconds to continue..."
  sleep 5
  rm -rf ~/.dolphin/knowledge_store

