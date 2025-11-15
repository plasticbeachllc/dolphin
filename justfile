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

# Set up the entire project
setup: setup-env setup-python

# ==============================================================================
# Environment Management
# ==============================================================================

# Check for .env file and required variables
setup-env:
	@# Check if .env file exists, if not, create it from the template
	@[ -f .env ] || (echo "Creating .env from .env.template..."; cp .env.example .env)
	@# Check if OPENAI_API_KEY is set and not empty
	@test -n "${OPENAI_API_KEY}" || (echo "❌ Error: OPENAI_API_KEY is not set in .env file. Please add it and try again."; exit 1)
	@echo "✅ Environment is configured."

# Install Python dependencies from pyproject.toml
setup-python:
	uv sync --group test

# ==============================================================================
# Code Quality & Linting
# ==============================================================================

# Run all linting and type checking
check:
	@echo "🔍 Running code quality checks..."
	@echo ""
	@just check-python
	@just check-typescript
	@echo ""
	@echo "✅ All checks passed!"

# Check Python code quality
check-python:
	@echo "🐍 Checking Python code quality..."
	@uv run ruff check --fix --unsafe-fixes || (echo "   ❌ ruff check failed"; exit 1)
	@uv run ruff format
	@echo "   ✅ ruff formatting passed"
	@uv run ty check || (echo "   ❌ ty check failed"; exit 1)
	@echo "   ✅ ty check passed"

# Check TypeScript code quality
check-typescript:
	@echo "📘 Checking TypeScript code quality..."
	@bun prettier --write "**/*.{ts,tsx,js,jsx,json,md}" --ignore-path .gitignore --ignore-unknown || (echo "   ❌ prettier failed"; exit 1)
	@echo "   ✅ prettier passed"
	@bun run lint:all || (echo "   ❌ linting failed"; exit 1)
	@echo "   ✅ linting  passed"

# ==============================================================================
# Testing - Main Commands
# ==============================================================================

# Run ALL tests across all projects (unit + integration + e2e)
test-all:
	@echo "🚀 Running ALL tests across all projects..."
	@echo ""
	@just test-unit-all
	@just test-integration-all
	@just test-e2e-all
	@echo ""
	@echo "✅ All tests passed!"

# Run all unit tests across all projects
test-unit-all:
	@echo "⚡ Running all unit tests..."
	@echo ""
	@just test-python unit
	@just test-agent-core unit
	@just test-extension unit
	@just test-webview
	@echo ""
	@echo "✅ All unit tests passed!"

# Run all integration tests across all projects
test-integration-all:
	@echo "🔗 Running all integration tests..."
	@echo ""
	@just test-python integration
	@just test-agent-core integration
	@just test-extension integration
	@just test-mcp-bridge
	@echo ""
	@echo "✅ All integration tests passed!"

# Run all e2e tests across all projects
test-e2e-all:
	@echo "🎯 Running all E2E tests..."
	@echo ""
	@just test-python e2e
	@just test-agent-core e2e
	@just test-extension e2e
	@echo ""
	@echo "✅ All E2E tests passed!"

# ==============================================================================
# Testing - Per-Project Commands
# ==============================================================================

# Run Python tests (TYPE: unit, integration, e2e, or all)
test-python TYPE="all": setup-python
	@echo "🐍 Running Python {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		uv run pytest tests/ -q --tb=short || (echo "   ❌ Python tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "unit" ]; then \
		uv run pytest tests/unit/ -q --tb=short || (echo "   ❌ Python unit tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "integration" ]; then \
		uv run pytest tests/integration/ -q --tb=short || (echo "   ❌ Python integration tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "e2e" ]; then \
		uv run pytest tests/e2e/ -q --tb=short || (echo "   ❌ Python e2e tests failed"; exit 1); \
	else \
		echo "   ❌ Invalid TYPE: {{TYPE}}. Use: unit, integration, e2e, or all"; exit 1; \
	fi
	@echo "   ✅ Python {{TYPE}} tests passed"

# Run Python domain tests (TYPE: unit, integration, e2e, or all)
test-python-domain DOMAIN TYPE="all": setup-python
	@echo "🐍 Running Python {{DOMAIN}} {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		uv run pytest tests/unit/{{DOMAIN}}/ tests/integration/{{DOMAIN}}/ -v --tb=short 2>/dev/null || \
		uv run pytest tests/unit/{{DOMAIN}}/ -v --tb=short 2>/dev/null || \
		uv run pytest tests/integration/{{DOMAIN}}/ -v --tb=short || \
		(echo "   ❌ No tests found for domain {{DOMAIN}}"; exit 1); \
	elif [ "{{TYPE}}" = "unit" ]; then \
		uv run pytest tests/unit/{{DOMAIN}}/ -v --tb=short || (echo "   ❌ Unit tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "integration" ]; then \
		uv run pytest tests/integration/{{DOMAIN}}/ -v --tb=short || (echo "   ❌ Integration tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "e2e" ]; then \
		uv run pytest tests/e2e/{{DOMAIN}}/ -v --tb=short || (echo "   ❌ E2E tests failed"; exit 1); \
	else \
		echo "   ❌ Invalid TYPE: {{TYPE}}. Use: unit, integration, e2e, or all"; exit 1; \
	fi
	@echo "   ✅ {{DOMAIN}} {{TYPE}} tests passed"

# Run Agent Core tests (TYPE: unit, integration, e2e, or all)
test-agent-core TYPE="all":
	@echo "🤖 Running Agent Core {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		cd agent-core && bun test --bail || (echo "   ❌ Agent Core tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "unit" ]; then \
		cd agent-core && bun test tests/unit/ --bail || (echo "   ❌ Agent Core unit tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "integration" ]; then \
		cd agent-core && bun test tests/integration/ --bail || (echo "   ❌ Agent Core integration tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "e2e" ]; then \
		cd agent-core && bun test tests/integration/e2e/ --bail || (echo "   ❌ Agent Core e2e tests failed"; exit 1); \
	else \
		echo "   ❌ Invalid TYPE: {{TYPE}}. Use: unit, integration, e2e, or all"; exit 1; \
	fi
	@echo "   ✅ Agent Core {{TYPE}} tests passed"

# Run Agent Core domain tests (TYPE: unit, integration, or all)
test-agent-core-domain DOMAIN TYPE="all":
	@echo "🤖 Running Agent Core {{DOMAIN}} {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		cd agent-core && (bun test tests/unit/{{DOMAIN}}/ tests/integration/{{DOMAIN}}/ --bail 2>/dev/null || \
		bun test tests/unit/{{DOMAIN}}/ --bail 2>/dev/null || \
		bun test tests/integration/{{DOMAIN}}/ --bail) || (echo "   ❌ No tests found for domain {{DOMAIN}}"; exit 1); \
	elif [ "{{TYPE}}" = "unit" ]; then \
		cd agent-core && bun test tests/unit/{{DOMAIN}}/ --bail || (echo "   ❌ Unit tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "integration" ]; then \
		cd agent-core && bun test tests/integration/{{DOMAIN}}/ --bail || (echo "   ❌ Integration tests failed"; exit 1); \
	else \
		echo "   ❌ Invalid TYPE: {{TYPE}}. Use: unit, integration, or all"; exit 1; \
	fi
	@echo "   ✅ {{DOMAIN}} {{TYPE}} tests passed"

# Run VSCode Extension tests (TYPE: unit, integration, e2e, or all)
test-extension TYPE="all":
	@echo "📦 Running VSCode Extension {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		cd vscode-extension && npm test || (echo "   ❌ Extension tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "unit" ]; then \
		cd vscode-extension && npm test -- --grep "unit/" || (echo "   ❌ Extension unit tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "integration" ]; then \
		cd vscode-extension && npm test -- --grep "integration/" || (echo "   ❌ Extension integration tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "e2e" ]; then \
		cd vscode-extension && npm test -- --grep "e2e/" || (echo "   ❌ Extension e2e tests failed"; exit 1); \
	else \
		echo "   ❌ Invalid TYPE: {{TYPE}}. Use: unit, integration, e2e, or all"; exit 1; \
	fi
	@echo "   ✅ Extension {{TYPE}} tests passed"

# Run VSCode Extension domain tests (TYPE: unit, integration, e2e, or all)
test-extension-domain DOMAIN TYPE="all":
	@echo "📦 Running Extension {{DOMAIN}} {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		cd vscode-extension && npm test -- --grep "{{DOMAIN}}" || (echo "   ❌ Tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "unit" ]; then \
		cd vscode-extension && npm test -- --grep "unit/{{DOMAIN}}/" || (echo "   ❌ Unit tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "integration" ]; then \
		cd vscode-extension && npm test -- --grep "integration/{{DOMAIN}}/" || (echo "   ❌ Integration tests failed"; exit 1); \
	elif [ "{{TYPE}}" = "e2e" ]; then \
		cd vscode-extension && npm test -- --grep "e2e/{{DOMAIN}}/" || (echo "   ❌ E2E tests failed"; exit 1); \
	else \
		echo "   ❌ Invalid TYPE: {{TYPE}}. Use: unit, integration, e2e, or all"; exit 1; \
	fi
	@echo "   ✅ {{DOMAIN}} {{TYPE}} tests passed"

# Run MCP Bridge tests (all are integration tests)
test-mcp-bridge:
	@echo "🌉 Running MCP Bridge tests..."
	@cd mcp-bridge && bun test || (echo "   ❌ MCP Bridge tests failed"; exit 1)
	@echo "   ✅ MCP Bridge tests passed"

# Run Webview tests (all are unit tests)
test-webview:
	@echo "🎨 Running Webview tests..."
	@cd vscode-extension/webview && bun test || (echo "   ❌ Webview tests failed"; exit 1)
	@echo "   ✅ Webview tests passed"

# ==============================================================================
# Testing - Utility Commands
# ==============================================================================

# Run specific test file
test-file FILE: setup-python
	@echo "🧪 Running specific test file: {{FILE}}"
	@uv run pytest {{FILE}} -v

# Run Python tests with coverage
test-coverage: setup-python
	@echo "🧪 Running Python tests with coverage..."
	@uv run pytest -n0 --cov=kb --cov-report=html --cov-report=term-missing


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