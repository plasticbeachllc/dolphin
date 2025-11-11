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

# Test all components using pytest (parallel execution enabled by default in pytest.ini)
test: setup-python
	@echo "🧪 Running all tests with pytest (parallel)..."
	@uv run pytest -q

# Run unit tests only
test-unit: setup-python
	@echo "🧪 Running unit tests (parallel)..."
	@uv run pytest tests/unit/ -q

# Run integration tests only
test-integration: setup-python
	@echo "🧪 Running integration tests (parallel)..."
	@uv run pytest tests/integration/ -q

# Run tests sequentially (for debugging)
test-sequential: setup-python
	@echo "🧪 Running all tests sequentially..."
	@uv run pytest -q -n0

# Run tests with coverage reporting (note: coverage disables parallelization for accuracy)
test-coverage: setup-python
	@echo "🧪 Running tests with coverage..."
	@uv run pytest -n0 --cov=kb --cov-report=html --cov-report=term-missing

# Run specific test file
test-file: setup-python
	@echo "🧪 Running specific test file: $(file)"
	@uv run pytest $(file) -v

# Run tests with detailed output
test-verbose: setup-python
	@echo "🧪 Running tests with verbose output (parallel)..."
	@uv run pytest -v

# Run end-to-end tests across all platform domains
test-e2e:
	@echo "🚀 Running end-to-end platform tests across all domains..."
	@echo ""
	@echo "📋 Testing Domains:"
	@echo "  1. Python Backend (KB, API, Personas)"
	@echo "  2. TypeScript Agent Core"
	@echo "  3. MCP Bridge"
	@echo "  4. VSCode Extension"
	@echo "  5. Webview UI"
	@echo ""
	@just test-e2e-python
	@just test-e2e-agent-core
	@just test-e2e-mcp-bridge
	@just test-e2e-extension
	@just test-e2e-webview
	@echo ""
	@echo "✅ All end-to-end tests passed!"

# Run end-to-end tests with lenient mode (skip flaky tests)
test-e2e-lenient:
	@echo "🚀 Running end-to-end platform tests (lenient mode - skips flaky tests)..."
	@echo ""
	@echo "📋 Testing Domains:"
	@echo "  1. Python Backend (KB, API, Personas)"
	@echo "  2. TypeScript Agent Core (unit tests)"
	@echo "  3. MCP Bridge"
	@echo "  4. VSCode Extension"
	@echo "  5. Webview UI"
	@echo ""
	@just test-e2e-python
	@just test-e2e-agent-core-unit
	@just test-e2e-mcp-bridge
	@just test-e2e-extension
	@just test-e2e-webview
	@echo ""
	@echo "✅ All end-to-end tests passed (lenient mode)!"

# Test Python backend (KB, API, Personas)
test-e2e-python:
	@echo "🐍 [1/5] Testing Python Backend..."
	@uv run pytest tests/ -q --tb=short || (echo "   ❌ Python backend tests failed"; exit 1)
	@echo "   ✅ Python backend tests passed"

# Test Agent Core (TypeScript)
test-e2e-agent-core:
	@echo "🤖 [2/5] Testing Agent Core..."
	@cd agent-core && bun test --bail || (echo "   ❌ Agent core tests failed"; exit 1)
	@echo "   ✅ Agent core tests passed"

# Test Agent Core excluding flaky integration tests
test-e2e-agent-core-unit:
	@echo "🤖 [2/5] Testing Agent Core (unit tests only)..."
	@cd agent-core && bun test tests/ --exclude "**/llm/claude-client.test.ts" || (echo "   ❌ Agent core tests failed"; exit 1)
	@echo "   ✅ Agent core tests passed"

# Test MCP Bridge
test-e2e-mcp-bridge:
	@echo "🌉 [3/5] Testing MCP Bridge..."
	@cd mcp-bridge && bun test || (echo "   ❌ MCP bridge tests failed"; exit 1)
	@echo "   ✅ MCP bridge tests passed"

# Test VSCode Extension
test-e2e-extension:
	@echo "📦 [4/5] Testing VSCode Extension..."
	@cd vscode-extension && npm test || (echo "   ❌ Extension tests failed"; exit 1)
	@echo "   ✅ Extension tests passed"

# Test Webview UI
test-e2e-webview:
	@echo "🎨 [5/5] Testing Webview UI..."
	@cd vscode-extension/webview && bun test || (echo "   ❌ Webview tests failed"; exit 1)
	@echo "   ✅ Webview tests passed"

# Run end-to-end tests with coverage
test-e2e-coverage:
	@echo "🚀 Running end-to-end platform tests with coverage..."
	@echo ""
	@echo "🐍 Python Backend (with coverage)..."
	@uv run pytest tests/ --cov=kb --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "🤖 Agent Core..."
	@cd agent-core && bun test --coverage
	@echo ""
	@echo "🌉 MCP Bridge..."
	@cd mcp-bridge && bun test --coverage
	@echo ""
	@echo "📦 VSCode Extension..."
	@cd vscode-extension && npm test -- --coverage
	@echo ""
	@echo "🎨 Webview UI..."
	@cd vscode-extension/webview && bun test --coverage
	@echo ""
	@echo "✅ All tests completed with coverage reports!"

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

# Show knowledge base status (with detailed repo listing)
kb-status:
	uv run dolphin kb status

# List all registered repositories
kb-list-repos:
	uv run dolphin kb list-repos

# Full system reset (removes ALL repos and data)
kb-reset-all:
	uv run dolphin kb reset-all

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
# Benchmarking & Evaluation
# ==============================================================================

# SWE-Bench Lite Evaluation
# ------------------------------------------------------------------------------

# Setup SWE-Bench test repos (clone and index)
swe-bench-setup:
	@echo "Setting up SWE-Bench Lite test repositories..."
	uv run python scripts/orchestrate_swe_bench.py setup

# Show SWE-Bench setup status
swe-bench-status:
	uv run python scripts/orchestrate_swe_bench.py status

# Run SWE-Bench Lite evaluation (file identification task)
eval-swe-bench REPOS="*" LIMIT="":
	@echo "Running SWE-Bench Lite evaluation..."
	@mkdir -p results
	uv run python scripts/eval_swe_bench.py \
		--dataset test-data/swe_bench_instances.json \
		{{if REPOS != "*" { "--repos " + REPOS } else { "" } }} \
		{{if LIMIT != "" { "--limit " + LIMIT } else { "" } }} \
		--output results/swe_bench_eval.json
	@echo "✅ Results saved to results/swe_bench_eval.json"

# Run SWE-Bench evaluation with verbose output
eval-swe-bench-verbose REPOS="*":
	@mkdir -p results
	uv run python scripts/eval_swe_bench.py \
		--dataset test-data/swe_bench_instances.json \
		{{if REPOS != "*" { "--repos " + REPOS } else { "" } }} \
		--output results/swe_bench_eval.json \
		--verbose

# Quick SWE-Bench smoke test (10 instances)
eval-swe-bench-quick:
	@echo "Running quick SWE-Bench smoke test..."
	@mkdir -p results
	uv run python scripts/eval_swe_bench.py \
		--dataset test-data/swe_bench_instances.json \
		--limit 10 \
		--output results/swe_bench_quick.json

# Golden Scenarios Evaluation (Flask)
# ------------------------------------------------------------------------------

# Run custom golden scenario evaluation
eval-golden SCENARIOS="golden-scenarios-flask":
	@echo "Running golden scenario evaluation..."
	@mkdir -p results
	uv run python scripts/eval_retrieval.py \
		--scenarios {{SCENARIOS}} \
		--output results/golden_eval.json
	@echo "✅ Results saved to results/golden_eval.json"

# Run golden scenarios with verbose output
eval-golden-verbose SCENARIOS="golden-scenarios-flask":
	@mkdir -p results
	uv run python scripts/eval_retrieval.py \
		--scenarios {{SCENARIOS}} \
		--output results/golden_eval.json \
		--verbose

# Setup Flask test repo for golden scenarios
flask-setup:
	@echo "Setting up Flask 2.3.0 test repository..."
	@mkdir -p test-repos
	@if [ ! -d "test-repos/flask" ]; then \
		git clone https://github.com/pallets/flask.git test-repos/flask; \
		cd test-repos/flask && git checkout 2.3.0; \
	fi
	@REPO_PATH="$(pwd)/test-repos/flask"; \
		echo "Registering and indexing Flask with large model (3072-dim for better quality)..."; \
		uv run python -m kb.cli add-repo pallets/flask "$$REPO_PATH" --default-embed-model large; \
		uv run python -m kb.cli index pallets/flask
	@echo "✅ Flask test repo ready"

# ANN Benchmarks (Existing)
# ------------------------------------------------------------------------------

# Run ANN parameter benchmarks
benchmark-ann QUERIES="50" ITERATIONS="50":
	@echo "Running ANN parameter benchmarks..."
	@mkdir -p results
	uv run python scripts/benchmark_ann.py \
		--queries {{QUERIES}} \
		--iterations {{ITERATIONS}} \
		--output results/ann_benchmark.json
	@echo "✅ Results saved to results/ann_benchmark.json"

# Combined Benchmarks
# ------------------------------------------------------------------------------

# Run full benchmark suite (SWE-Bench + Golden + ANN)
benchmark-full:
	@echo "Running full benchmark suite..."
	@echo ""
	@echo "1/3: SWE-Bench Lite evaluation..."
	@just eval-swe-bench-quick
	@echo ""
	@echo "2/3: Golden scenarios..."
	@just eval-golden
	@echo ""
	@echo "3/3: ANN benchmarks..."
	@just benchmark-ann 20 20
	@echo ""
	@echo "✅ Full benchmark complete!"
	@echo "   - SWE-Bench: results/swe_bench_quick.json"
	@echo "   - Golden: results/golden_eval.json"
	@echo "   - ANN: results/ann_benchmark.json"

# Quick benchmark for CI (fast smoke tests)
benchmark-quick:
	@echo "Running quick benchmark suite..."
	@just eval-swe-bench-quick
	@just benchmark-ann 10 10
	@echo "✅ Quick benchmark complete"

# Compare evaluations against baseline
compare-eval BASELINE="results/baseline_eval.json" CURRENT="results/golden_eval.json":
	@echo "Comparing evaluation results..."
	uv run python scripts/compare_eval.py \
		{{BASELINE}} \
		{{CURRENT}} \
		--threshold 3.0

# Save current results as baseline
save-baseline:
	@echo "Saving current results as baseline..."
	@mkdir -p results/baselines
	@cp results/golden_eval.json results/baselines/baseline_$(shell date +%Y%m%d_%H%M%S).json
	@cp results/golden_eval.json results/baseline_eval.json
	@echo "✅ Baseline saved"

# ==============================================================================
# Cleanup Commands
# ==============================================================================

# Clean all repositories and data (preserves config)
reset-all:
	@echo "⚠️  This will remove ALL repositories and data from the knowledge store."
	@echo "Configuration will be preserved."
	@echo ""
	uv run dolphin kb reset-all

# Force reset without confirmation (dangerous!)
reset-all-force:
	@echo "🔥 Force resetting ALL repositories..."
	uv run dolphin kb reset-all --force

# Nuclear option: Delete entire knowledge store directory
store-clean:
	@echo "💣 This will DELETE ~/.dolphin/knowledge_store"
	@echo "This removes EVERYTHING including configuration!"
	@echo "Press Ctrl-C to abort or wait 5 seconds to continue..."
	sleep 5
	rm -rf ~/.dolphin/knowledge_store
	@echo "✅ Knowledge store directory deleted."
	@echo "Run 'just init' to reinitialize."

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
# VSCode Extension Building
# ==============================================================================

# Build webview UI
ext-build-webview:
	@echo "🎨 Building webview UI..."
	@cd vscode-extension/webview && bun run build

# Compile extension TypeScript
ext-compile:
	@echo "📦 Compiling extension TypeScript..."
	@cd vscode-extension && npm run compile

# Bundle uv binaries for all platforms
ext-bundle-uv:
	@echo "🐍 Bundling uv binaries..."
	@bash scripts/bundle-uv.sh

# Build extension (webview + compile)
ext-build: ext-build-webview ext-compile
	@echo "✅ Extension built successfully"

# Build extension for production (includes bundled uv)
ext-build-prod: ext-bundle-uv ext-build
	@echo "✅ Extension built for production with bundled uv"

# Package extension for all platforms
ext-package: ext-build-prod
	@echo "📦 Packaging extension for all platforms..."
	@cd vscode-extension && npm run package

# Package extension for specific platform (darwin-arm64, darwin-x64, linux-x64, win32-x64)
ext-package-platform platform: ext-build-prod
	@echo "📦 Packaging extension for {{platform}}..."
	@cd vscode-extension && vsce package --target {{platform}}

# Clean extension build artifacts
ext-clean:
	@echo "🧹 Cleaning extension build artifacts..."
	@rm -rf vscode-extension/out
	@rm -rf vscode-extension/webview/build
	@rm -rf vscode-extension/dist/uv
	@rm -f vscode-extension/*.vsix

# Install extension dependencies
ext-install:
	@echo "📥 Installing extension dependencies..."
	@cd vscode-extension && npm install
	@cd vscode-extension/webview && bun install

# Full extension setup (install + build)
ext-setup: ext-install ext-build
	@echo "✅ Extension setup complete"

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