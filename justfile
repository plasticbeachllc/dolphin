# justfile for Dolphin AI knowledge base with Python, Docker, and uv

# Load environment variables from .env file
set dotenv-load

# Variables
HOME := env('HOME')

list:
	just -l

# ==============================================================================
# High-Level Commands
# ==============================================================================

# Clean generated files
clean: stop

# Start all services
run: start

# Start all services and wait for readiness
start:
	@echo "Starting all services..."
	@just --quiet start-mcp-bridge
	@echo "Waiting for MCP Bridge to listen on port 7777..."
	@TIMEOUT=30; while ! just --quiet mcp-bridge-check >/dev/null 2>&1; do \
		sleep 1; TIMEOUT=$((TIMEOUT-1)); \
		if [ $TIMEOUT -le 0 ]; then echo "❌ Timed out waiting for MCP Bridge"; exit 1; fi; \
	done
	@echo "✅ All services are up:"
	@echo " - Dolphin API:      http://localhost:7777"

# Set up the entire project
setup: setup-env setup-python

# Stop all services
stop: mcp-bridge-stop

# ==============================================================================
# Environment Management
# ==============================================================================

# Check for .env file and required variables
setup-env:
	@# Check if .env file exists, if not, create it from the template
	@[ -f .env ] || (echo "Creating .env from .env.template..."; cp .env.template .env)
	@# Check if OPENAI_API_KEY is set and not empty
	@test -n "${OPENAI_API_KEY}" || (echo "❌ Error: OPENAI_API_KEY is not set in .env file. Please add it and try again."; exit 1)
	@echo "✅ Environment is configured."

# Install Python dependencies from pyproject.toml
setup-python:
	uv sync --group test

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

# Run tests with coverage reporting
test-coverage: setup-python
	@echo "🧪 Running tests with coverage..."
	@uv run pytest --cov=kb --cov-report=html --cov-report=term-missing

# ==============================================================================
# Unit Tests - Fast, isolated tests with no external dependencies
# ==============================================================================

# Run ALL unit tests across all domains
test-unit-all:
	@echo "⚡ Running all unit tests across all domains..."
	@echo ""
	@just test-unit-python
	@just test-unit-agent-core
	@just test-unit-agent-core-v2
	@just test-unit-extension
	@just test-unit-webview
	@echo ""
	@echo "✅ All unit tests passed!"

# Run Python unit tests
test-unit-python: setup-python
	@echo "🐍 Testing Python unit tests..."
	@uv run pytest tests/unit/ -q --tb=short || (echo "   ❌ Python unit tests failed"; exit 1)
	@echo "   ✅ Python unit tests passed"

# Run Agent Core unit tests
test-unit-agent-core:
	@echo "🤖 Testing Agent Core unit tests..."
	@cd agent-core && bun test tests/conversation-store.test.ts tests/plan-store.test.ts tests/storage.test.ts tests/toml-writer.test.ts tests/llm/diff-generator.test.ts tests/llm/claude-tool-executor-diff.test.ts tests/llm/claude-cli-detector.test.ts tests/planner/basic-planner.test.ts --bail || (echo "   ❌ Agent Core unit tests failed"; exit 1)
	@echo "   ✅ Agent Core unit tests passed"

# Run Agent Core V2 unit tests
test-unit-agent-core-v2:
	@echo "🤖 Testing Agent Core V2 unit tests..."
	@cd agent-core-v2 && bun test tests/unit/ --bail || (echo "   ❌ Agent Core V2 unit tests failed"; exit 1)
	@echo "   ✅ Agent Core V2 unit tests passed"

# Run VSCode Extension unit tests
test-unit-extension:
	@echo "📦 Testing VSCode Extension unit tests..."
	@cd vscode-extension && npm test -- --grep "logger|configuration|diff-handler|code-actions|drift-detector|auto-sync-manager|file-watcher-sync" || (echo "   ❌ Extension unit tests failed"; exit 1)
	@echo "   ✅ Extension unit tests passed"

# Run Webview unit tests
test-unit-webview:
	@echo "🎨 Testing Webview unit tests..."
	@cd vscode-extension/webview && bun test || (echo "   ❌ Webview unit tests failed"; exit 1)
	@echo "   ✅ Webview unit tests passed"

# ==============================================================================
# Integration Tests - Tests that integrate components within a domain
# ==============================================================================

# Run ALL integration tests across all domains
test-integration-all:
	@echo "🔗 Running all integration tests across all domains..."
	@echo ""
	@just test-integration-python
	@just test-integration-agent-core
	@just test-integration-agent-core-v2
	@just test-integration-extension
	@just test-integration-mcp-bridge
	@echo ""
	@echo "✅ All integration tests passed!"

# Run Python integration tests
test-integration-python: setup-python
	@echo "🐍 Testing Python integration tests..."
	@uv run pytest tests/integration/ -q --tb=short || (echo "   ❌ Python integration tests failed"; exit 1)
	@echo "   ✅ Python integration tests passed"

# Run Agent Core integration tests
test-integration-agent-core:
	@echo "🤖 Testing Agent Core integration tests..."
	@cd agent-core && bun test tests/llm/claude-client.test.ts tests/mcp-client.integration.test.ts tests/kb/manager.test.ts tests/main.test.ts --bail || (echo "   ❌ Agent Core integration tests failed"; exit 1)
	@echo "   ✅ Agent Core integration tests passed"

# Run Agent Core V2 integration tests
test-integration-agent-core-v2:
	@echo "🤖 Testing Agent Core V2 integration tests..."
	@cd agent-core-v2 && bun test tests/integration/claude-auth.test.ts tests/integration/kb-integration.test.ts --bail || (echo "   ❌ Agent Core V2 integration tests failed"; exit 1)
	@echo "   ✅ Agent Core V2 integration tests passed"

# Run VSCode Extension integration tests
test-integration-extension:
	@echo "📦 Testing VSCode Extension integration tests..."
	@cd vscode-extension && npm test -- --grep "agent-bridge|provider|commands|webview|^extension" || (echo "   ❌ Extension integration tests failed"; exit 1)
	@echo "   ✅ Extension integration tests passed"

# Run MCP Bridge integration tests
test-integration-mcp-bridge:
	@echo "🌉 Testing MCP Bridge integration tests..."
	@cd mcp-bridge && bun test || (echo "   ❌ MCP bridge integration tests failed"; exit 1)
	@echo "   ✅ MCP bridge integration tests passed"

# ==============================================================================
# End-to-End Tests - Full cross-domain integration tests
# ==============================================================================

# Run ALL end-to-end tests
test-e2e-all:
	@echo "🚀 Running all end-to-end tests..."
	@echo ""
	@just test-e2e-extension-full
	@just test-e2e-agent-core-v2
	@echo ""
	@echo "✅ All end-to-end tests passed!"

# Run VSCode Extension full e2e tests
test-e2e-extension-full:
	@echo "📦 Testing VSCode Extension E2E tests..."
	@cd vscode-extension && npm test -- --grep "phase1-integration|phase2-integration|integration\.test|conversations-e2e|kb-lifecycle" || (echo "   ❌ Extension E2E tests failed"; exit 1)
	@echo "   ✅ Extension E2E tests passed"

# Run Agent Core V2 e2e tests
test-e2e-agent-core-v2:
	@echo "🤖 Testing Agent Core V2 E2E tests..."
	@cd agent-core-v2 && bun test tests/integration/orchestrator-e2e.test.ts tests/integration/editor-workflow.test.ts --bail || (echo "   ❌ Agent Core V2 E2E tests failed"; exit 1)
	@echo "   ✅ Agent Core V2 E2E tests passed"

# ==============================================================================
# Legacy E2E Commands (comprehensive test suite - runs EVERYTHING)
# ==============================================================================

# Run COMPREHENSIVE test suite across all domains (LEGACY - runs ALL tests)
# This is the original test-e2e that runs ALL tests (unit + integration + e2e)
# For faster testing, use test-unit-all, test-integration-all, or test-e2e-all instead
test-e2e:
	@echo "🚀 Running COMPREHENSIVE test suite across all domains..."
	@echo ""
	@echo "📋 This runs ALL tests (unit, integration, and e2e):"
	@echo "  1. Python Backend (unit + integration)"
	@echo "  2. TypeScript Agent Core (all tests)"
	@echo "  3. MCP Bridge (integration tests)"
	@echo "  4. VSCode Extension (all tests)"
	@echo "  5. Webview UI (unit tests)"
	@echo ""
	@echo "💡 TIP: For faster testing, use:"
	@echo "   - just test-unit-all        (fast unit tests only)"
	@echo "   - just test-integration-all (integration tests only)"
	@echo "   - just test-e2e-all         (e2e tests only)"
	@echo ""
	@just test-e2e-python
	@just test-e2e-agent-core
	@just test-e2e-mcp-bridge
	@just test-e2e-extension
	@just test-e2e-webview
	@echo ""
	@echo "✅ All comprehensive tests passed!"

# Run end-to-end tests with lenient mode (skip flaky tests)
test-e2e-lenient:
	@echo "🚀 Running end-to-end platform tests (lenient mode - skips flaky tests)..."
	@echo ""
	@just test-e2e-python
	@just test-e2e-agent-core-unit
	@just test-e2e-mcp-bridge
	@just test-e2e-extension
	@just test-e2e-webview
	@echo ""
	@echo "✅ All end-to-end tests passed (lenient mode)!"

# ==============================================================================
# Legacy Per-Domain Test Commands
# ==============================================================================

# Test Python backend (KB, API) - ALL Python tests
test-e2e-python:
	@echo "🐍 Testing Python Backend (all tests)..."
	@uv run pytest tests/ -q --tb=short || (echo "   ❌ Python backend tests failed"; exit 1)
	@echo "   ✅ Python backend tests passed"

# Test Agent Core (TypeScript) - ALL Agent Core tests
test-e2e-agent-core:
	@echo "🤖 Testing Agent Core (all tests)..."
	@cd agent-core && bun test --bail || (echo "   ❌ Agent core tests failed"; exit 1)
	@echo "   ✅ Agent core tests passed"

# Test Agent Core excluding flaky integration tests
test-e2e-agent-core-unit:
	@echo "🤖 Testing Agent Core (unit tests only)..."
	@cd agent-core && bun test tests/ --exclude "**/llm/claude-client.test.ts" || (echo "   ❌ Agent core tests failed"; exit 1)
	@echo "   ✅ Agent core tests passed"

# Test MCP Bridge - ALL MCP Bridge tests
test-e2e-mcp-bridge:
	@echo "🌉 Testing MCP Bridge (all tests)..."
	@cd mcp-bridge && bun test || (echo "   ❌ MCP bridge tests failed"; exit 1)
	@echo "   ✅ MCP bridge tests passed"

# Test VSCode Extension - ALL Extension tests
test-e2e-extension:
	@echo "📦 Testing VSCode Extension (all tests)..."
	@cd vscode-extension && npm test || (echo "   ❌ Extension tests failed"; exit 1)
	@echo "   ✅ Extension tests passed"

# Test Webview UI - ALL Webview tests
test-e2e-webview:
	@echo "🎨 Testing Webview UI (all tests)..."
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
# Performance Profiling
# ==============================================================================

# Profile indexing performance (small/medium/large)
profile-index SIZE="small":
	@echo "🔬 Profiling indexing performance ({{SIZE}} repository)..."
	sudo -E ./scripts/profile_indexing.sh {{SIZE}}

# Profile search performance (cold/warm/concurrent)
profile-search TYPE="cold":
	@echo "🔍 Profiling search performance ({{TYPE}} cache)..."
	sudo -E ./scripts/profile_search.sh {{TYPE}}

# Profile both indexing and search on same repository
profile-combined SIZE="small":
	@echo "🚀 Profiling combined workflow ({{SIZE}} repository)..."
	sudo -E ./scripts/profile_combined.sh {{SIZE}}

# Keep repository after profiling for debugging
profile-combined-keep SIZE="small":
	@echo "🚀 Profiling combined workflow with --keep-repo flag..."
	sudo -E ./scripts/profile_combined.sh {{SIZE}} --keep-repo

# View profiling results in speedscope
profile-view RESULT:
	@echo "📊 Opening {{RESULT}} in browser..."
	@open https://speedscope.app || echo "Visit https://speedscope.app and upload {{RESULT}}"

# Clean profiling results
profile-clean:
	@echo "🧹 Cleaning profiling results..."
	@rm -rf profiling_results/
	@echo "✅ Profiling results cleaned"

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

# ANN Benchmarks
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

# Install MCP bridge dependencies
install-mcp-bridge:
	@echo "Installing MCP bridge dependencies..."
	@cd mcp-bridge && bun install

# Build MCP bridge
build-mcp-bridge:
	@echo "Building MCP bridge..."
	@cd mcp-bridge && bun build

# Reinstall all tools (full rebuild)
reinstall-all: install-cli-tools install-mcp-bridge build-mcp-bridge
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