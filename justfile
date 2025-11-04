# justfile for Dolphin AI knowledge base with Python, Docker, and uv

# Load environment variables from .env file
set dotenv-load

# Variables
HOME := env('HOME')
MCP_PORT := "8010"

list:
	just -l

# ==============================================================================
# High-Level Commands
# ==============================================================================

# Clean generated files
clean: stop

# Start all services
run: start

# Start all services (Ollama, MCP bridge) and wait for readiness
start:
	@echo "Starting all services..."
	@just --quiet ollama-start
	@echo "Waiting for Ollama to become ready..."
	@TIMEOUT=30; while ! just --quiet ollama-check >/dev/null 2>&1; do \
		sleep 1; TIMEOUT=$((TIMEOUT-1)); \
		if [ $TIMEOUT -le 0 ]; then echo "❌ Timed out waiting for Ollama"; exit 1; fi; \
	done
	@just --quiet start-mcp-bridge
	@echo "Waiting for MCP Bridge to listen on port 7777..."
	@TIMEOUT=30; while ! just --quiet mcp-bridge-check >/dev/null 2>&1; do \
		sleep 1; TIMEOUT=$((TIMEOUT-1)); \
		if [ $TIMEOUT -le 0 ]; then echo "❌ Timed out waiting for MCP Bridge"; exit 1; fi; \
	done
	@echo "✅ All services are up:"
	@echo " - Ollama API:       http://localhost:11434"
	@echo " - Dolphin API:      http://localhost:7777"
	@echo " - MCP Bridge:       http://localhost:8010"

# Set up the entire project
setup: setup-env setup-python

# Stop all services
stop: ollama-stop mcp-bridge-stop

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
# MCP Bridge Management
# ==============================================================================

# MCP Bridge readiness check
mcp-bridge-check:
	@lsof -nP -iTCP:7777 -sTCP:LISTEN >/dev/null 2>&1

# Start the MCP bridge
start-mcp-bridge:
	@echo "Starting MCP Bridge..."
	cd mcp-bridge && bun run src/index.ts &

# Stop the MCP bridge
mcp-bridge-stop:
	@pkill -f "bun run src/index.ts" || true

# Show MCP bridge status
show-mcp-bridge:
	lsof -i :7777

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
	@uv run pytest --cov=kb --cov-report=html --cov-report=term-missing

# Run specific test file
test-file: setup-python
	@echo "🧪 Running specific test file: $(file)"
	@uv run pytest $(file) -v

# Run tests with detailed output
test-verbose: setup-python
	@echo "🧪 Running tests with verbose output..."
	@uv run pytest -v

# ==============================================================================
# Centralized Dolphin CLI
# ==============================================================================

# Main Dolphin CLI (centralized interface)
dolphin:
	uv run dolphin $*

# --- Core Dolphin Commands ---

# Initialize Dolphin configuration (knowledge base init)
init:
	uv run dolphin init

# Initialize repo-specific configuration
init-repo:
	uv run dolphin init

# Show Dolphin configuration
config-show:
	uv run dolphin config --show

# --- Knowledge Base Management (via dolphin kb) ---

# Add repository to knowledge base
add-repo name:
	uv run dolphin kb add-repo {{name}} $(pwd) --default-embed-model large

# Index repository into knowledge base
index name:
	uv run dolphin kb index {{name}}

# Full reindex
reindex name:
	uv run dolphin kb index {{name}} --full --force

# Reset and reindex
reset name:
	uv run dolphin init
	uv run dolphin kb add-repo {{name}} $(pwd) --default-embed-model large
	uv run dolphin kb index {{name}} --full --force

# Show knowledge base status
kb-status:
	uv run dolphin kb status

# --- Persona Management (via dolphin personas) ---

# List available personas
personas-list:
	uv run dolphin personas preview --list

# Preview specific persona
personas-preview id:
	uv run dolphin personas preview --id {{id}} --verbose

# Generate KiloCode configuration
personas-kilocode:
	uv run dolphin personas generate --kilocode --verbose

# Generate Continue configuration
personas-continue:
	uv run dolphin personas generate --continue --verbose

# --- API Server ---

# Start the Dolphin API server
api:
	uv run dolphin serve

# Health check for API server
health:
	curl -s http://127.0.0.1:7777/v1/health || echo "API server not running"

# ==============================================================================
# Logs & Development
# ==============================================================================

tail-mcp:
  tail -f mcp-bridge/logs/mcp.log

# ==============================================================================
# Cleanup (dangerous)
# ==============================================================================

store-clean:
  @echo "This will DELETE ~/.dolphin/knowledge_store"
  @echo "Press Ctrl-C to abort or wait 5 seconds to continue..."
  sleep 5
  rm -rf ~/.dolphin/knowledge_store

# ==============================================================================
# CLI Tool Development & Building
# ==============================================================================

# Install all CLI tools in development mode
install-cli-tools:
	@echo "Installing CLI tools in development mode..."
	@uv pip install -e .

# Build all CLI tools (creates standalone binaries/scripts)
build-cli-tools: build
	@echo "Building CLI tools for version {{VERSION}}..."
	@echo "✅ Using existing build from dist/ directory"

# Create standalone scripts for local development
create-scripts:
	@echo "Creating standalone scripts for local development..."
	@mkdir -p bin
	@# Create dolphin script
	@echo '#!/usr/bin/env bash' > bin/dolphin
	@echo 'set -e' >> bin/dolphin
	@echo 'cd "$(dirname "$0")/.."' >> bin/dolphin
	@echo 'exec uv run dolphin "$@"' >> bin/dolphin
	@chmod +x bin/dolphin
	@# Create kb script
	@echo '#!/usr/bin/env bash' > bin/kb
	@echo 'set -e' >> bin/kb
	@echo 'cd "$(dirname "$0")/.."' >> bin/kb
	@echo 'exec uv run kb "$@"' >> bin/kb
	@chmod +x bin/kb
	@# Create kb-api script
	@echo '#!/usr/bin/env bash' > bin/kb-api
	@echo 'set -e' >> bin/kb-api
	@echo 'cd "$(dirname "$0")/.."' >> bin/kb-api
	@echo 'exec uv run kb-api "$@"' >> bin/kb-api
	@chmod +x bin/kb-api
	@# Create personas script
	@echo '#!/usr/bin/env bash' > bin/personas
	@echo 'set -e' >> bin/personas
	@echo 'cd "$(dirname "$0")/.."' >> bin/personas
	@echo 'exec uv run personas "$@"' >> bin/personas
	@chmod +x bin/personas
	@echo "✅ Created standalone scripts in bin/ directory"

# Install MCP bridge dependencies
install-mcp-bridge:
	@echo "Installing MCP bridge dependencies..."
	@cd mcp-bridge && bun install

# Build MCP bridge
build-mcp-bridge:
	@echo "Building MCP bridge..."
	@cd mcp-bridge && bun build

# Reinstall all tools (full rebuild)
reinstall-all: install-cli-tools create-scripts install-mcp-bridge build-mcp-bridge
	@echo "✅ All CLI tools and MCP bridge reinstalled"

# ==============================================================================
# Deployment
# ==============================================================================

# Build Python packages for distribution
build:
	@echo "Building Python packages..."
	@uv build

# Check package integrity before uploading
deploy-check: build
	@echo "Checking package integrity..."
	@uv run twine check dist/*

# Build and upload to PyPI in one command
deploy-prod: build
	@echo "Checking packages and uploading to PyPI..."
	@echo "Deploying version: {{VERSION}}"
	uv run twine check dist/*
	uv run twine upload dist/pb_dolphin-{{VERSION}}*

# Build and upload to Test PyPI in one command
deploy-test: build
	@echo "Checking packages and uploading to Test PyPI..."
	@echo "Deploying version: {{VERSION}}"
	uv run twine check dist/*
	uv run twine upload --repository testpypi dist/pb_dolphin-{{VERSION}}*

# Clean build artifacts
clean-build:
	@echo "Cleaning build artifacts..."
	@rm -rf build/
	@rm -rf dist/
	@rm -rf *.egg-info/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

# Complete clean including build artifacts
clean-all: clean clean-build

# ==============================================================================
# Defaults and Variables
# ==============================================================================

# Extract version from pyproject.toml
VERSION := `grep version pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/'`

# Defaults (override on CLI: just NAME=myrepo ...)
NAME := "dolphin"
REPO_PATH := "$(pwd)"

# Show current version
version:
	@echo "Current version: {{VERSION}}"

default:
  @just --list