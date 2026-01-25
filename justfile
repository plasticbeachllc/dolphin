# justfile for Dolphin AI knowledge base with Python, Docker, and uv

# Load environment variables from .env file
set dotenv-load

# Variables
HOME := env('HOME')
BENCHMARK_RESULTS_DIR := "artifacts/benchmarks"

list:
	just -l

# ==============================================================================
# High-Level Commands
# ==============================================================================

# Set up the entire project
setup: setup-python

# ==============================================================================
# Environment Management
# ==============================================================================

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
	@bun prettier --write "**/*.{ts,tsx,js,jsx,json,md}" --ignore-unknown || (echo "   ❌ prettier failed"; exit 1)
	@echo "   ✅ prettier passed"
	@bun run lint:all || (echo "   ❌ linting failed"; exit 1)
	@echo "   ✅ linting  passed"

# ==============================================================================
# Testing - Unified Commands
# ==============================================================================

# Run tests (TYPE: unit, integration, e2e, or all)
test TYPE="all":
	@echo "🧪 Running {{TYPE}} tests..."
	@just _pytest {{TYPE}}
	# @just _bun-test agent-core {{TYPE}}
	@just _bun-test mcp-bridge {{TYPE}}
	@just _bun-test shared all
	@echo "✅ All {{TYPE}} tests passed!"

# Run Python (kb) tests only
test-kb TYPE="all":
	@echo "🐍 Running Python {{TYPE}} tests..."
	@just _pytest {{TYPE}}
	@echo "   ✅ Python {{TYPE}} tests passed"

# Run MCP Bridge tests only
test-mcp TYPE="all":
	@echo "🌉 Running MCP Bridge {{TYPE}} tests..."
	@if [ "{{TYPE}}" = "all" ]; then \
		just _bun-test mcp-bridge unit && \
		just _bun-test mcp-bridge integration; \
	else \
		just _bun-test mcp-bridge {{TYPE}}; \
	fi
	@echo "   ✅ MCP Bridge {{TYPE}} tests passed"

# Run all TypeScript tests
test-ts TYPE="all":
	@echo "📘 Running TypeScript {{TYPE}} tests..."
	@just _bun-test agent-core {{TYPE}}
	@just _bun-test mcp-bridge {{TYPE}}
	@just _bun-test shared all
	@echo "   ✅ TypeScript {{TYPE}} tests passed"

# Run tests with coverage (disable parallel execution for accurate coverage)
test-cov:
	@uv run pytest -n0 tests/ --cov=kb --cov-report=html --cov-report=term-missing

# Run tests for CORE modules (CI compatibility)
test-core:
	@echo "Testing core dolphin functions..."
	@just test-kb all
	@just test-mcp all
	@just _bun-test shared all
	@echo "✅ Core tests passed!"

# Run ALL tests across all projects
test-all:
	@echo "🚀 Running ALL tests..."
	@just test all
	@just test-webview
	@echo "✅ All tests passed!"

# ==============================================================================
# Testing - Internal Helpers
# ==============================================================================

# Internal: Generic pytest runner (TYPE: unit, integration, e2e, or all)
_pytest TYPE: setup-python
	#!/usr/bin/env bash
	set -euo pipefail
	case "{{TYPE}}" in
		all)         dir="tests/" ;;
		unit)        dir="tests/unit/" ;;
		integration) dir="tests/integration/" ;;
		e2e)         dir="tests/e2e/" ;;
		*)           echo "❌ Invalid TYPE: {{TYPE}}"; exit 1 ;;
	esac
	uv run pytest "$dir" -q --tb=short

# Internal: Generic bun test runner (PROJECT: agent-core, mcp-bridge, shared)
_bun-test PROJECT TYPE:
	#!/usr/bin/env bash
	set -euo pipefail
	if [ "{{PROJECT}}" = "shared" ]; then
		cd shared && bun test
		exit 0
	fi
	case "{{TYPE}}" in
		all)         dir="" ;;
		unit)        dir="tests/unit/" ;;
		integration|e2e) dir="tests/integration/" ;;
		*)           echo "❌ Invalid TYPE: {{TYPE}}"; exit 1 ;;
	esac
	if [ "{{PROJECT}}" = "mcp-bridge" ] && [ -n "$dir" ]; then
		dir="src/tests/${dir#tests/}"
	fi
	cd "{{PROJECT}}" && bun test $dir --bail

# ==============================================================================
# Testing - Per-Project Commands (aliases to internal helpers)
# ==============================================================================

# Run Python tests
test-python TYPE="all": (_pytest TYPE)
	@echo "   ✅ Python {{TYPE}} tests passed"

# Run Python domain tests
test-python-domain DOMAIN TYPE="all": setup-python
	#!/usr/bin/env bash
	set -euo pipefail
	echo "🐍 Running Python {{DOMAIN}} {{TYPE}} tests..."
	case "{{TYPE}}" in
		all)         uv run pytest tests/unit/{{DOMAIN}}/ tests/integration/{{DOMAIN}}/ -v --tb=short 2>/dev/null || \
		             uv run pytest tests/unit/{{DOMAIN}}/ -v --tb=short 2>/dev/null || \
		             uv run pytest tests/integration/{{DOMAIN}}/ -v --tb=short ;;
		unit)        uv run pytest tests/unit/{{DOMAIN}}/ -v --tb=short ;;
		integration) uv run pytest tests/integration/{{DOMAIN}}/ -v --tb=short ;;
		e2e)         uv run pytest tests/e2e/{{DOMAIN}}/ -v --tb=short ;;
		*)           echo "❌ Invalid TYPE: {{TYPE}}"; exit 1 ;;
	esac
	echo "   ✅ {{DOMAIN}} {{TYPE}} tests passed"

# Run Agent Core tests
test-agent-core TYPE="all": (_bun-test "agent-core" TYPE)
	@echo "   ✅ Agent Core {{TYPE}} tests passed"

# Run Agent Core domain tests
test-agent-core-domain DOMAIN TYPE="all":
	#!/usr/bin/env bash
	set -euo pipefail
	echo "🤖 Running Agent Core {{DOMAIN}} {{TYPE}} tests..."
	case "{{TYPE}}" in
		all)         cd agent-core && (bun test tests/unit/{{DOMAIN}}/ tests/integration/{{DOMAIN}}/ --bail 2>/dev/null || \
		             bun test tests/unit/{{DOMAIN}}/ --bail 2>/dev/null || \
		             bun test tests/integration/{{DOMAIN}}/ --bail) ;;
		unit)        cd agent-core && bun test tests/unit/{{DOMAIN}}/ --bail ;;
		integration) cd agent-core && bun test tests/integration/{{DOMAIN}}/ --bail ;;
		*)           echo "❌ Invalid TYPE: {{TYPE}}"; exit 1 ;;
	esac
	echo "   ✅ {{DOMAIN}} {{TYPE}} tests passed"

# Run VSCode Extension tests
test-extension TYPE="all":
	#!/usr/bin/env bash
	set -euo pipefail
	echo "📦 Running VSCode Extension {{TYPE}} tests..."
	cd vscode-extension && npm run compile >/dev/null
	case "{{TYPE}}" in
		all)         npm run test:all ;;
		unit)        npm run test:unit ;;
		integration) npm run test:integration ;;
		e2e)         npm run test:e2e ;;
		*)           echo "❌ Invalid TYPE: {{TYPE}}"; exit 1 ;;
	esac
	echo "   ✅ Extension {{TYPE}} tests passed"

# Run VSCode Extension domain tests
test-extension-domain DOMAIN TYPE="all":
	#!/usr/bin/env bash
	set -euo pipefail
	echo "📦 Running Extension {{DOMAIN}} {{TYPE}} tests..."
	cd vscode-extension && npm run compile >/dev/null
	case "{{TYPE}}" in
		all)         target="out/test/suite" ;;
		unit)        target="out/test/suite/unit/{{DOMAIN}}" ;;
		integration) target="out/test/suite/integration/{{DOMAIN}}" ;;
		e2e)         target="out/test/suite/e2e/{{DOMAIN}}" ;;
		*)           echo "❌ Invalid TYPE: {{TYPE}}"; exit 1 ;;
	esac
	FILES=$(find "$target" -path "*{{DOMAIN}}*" -name '*.test.js' 2>/dev/null || true)
	[ -z "$FILES" ] && { echo "❌ No tests found for {{DOMAIN}}"; exit 1; }
	npm run test:{{TYPE}} -- --run $FILES
	echo "   ✅ {{DOMAIN}} {{TYPE}} tests passed"

# Run MCP Bridge tests
test-mcp-bridge: (_bun-test "mcp-bridge" "all")
	@echo "   ✅ MCP Bridge tests passed"

# Run shared package tests
test-shared: (_bun-test "shared" "all")
	@echo "   ✅ Shared package tests passed"

# Run Webview tests
test-webview:
	@cd vscode-extension/webview && bun test
	@echo "   ✅ Webview tests passed"

# Run Playwright UI/E2E tests
test-playwright:
	@cd vscode-extension/playwright && npm test
	@echo "   ✅ Playwright tests passed"

# ==============================================================================
# Testing - Utility Commands
# ==============================================================================

# Run specific test file
test-file FILE: setup-python
	@uv run pytest {{FILE}} -v



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
	curl -s http://127.0.0.1:7777/health || echo "API server not running"

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
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}
	uv run python scripts/eval_swe_bench.py \
		--dataset benchmarks/test-data/swe_bench_instances.json \
		{{if REPOS != "*" { "--repos " + REPOS } else { "" } }} \
		{{if LIMIT != "" { "--limit " + LIMIT } else { "" } }} \
		--output {{BENCHMARK_RESULTS_DIR}}/swe_bench_eval.json
	@echo "✅ Results saved to {{BENCHMARK_RESULTS_DIR}}/swe_bench_eval.json"

# Run SWE-Bench evaluation with verbose output
eval-swe-bench-verbose REPOS="*":
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}
	uv run python scripts/eval_swe_bench.py \
		--dataset benchmarks/test-data/swe_bench_instances.json \
		{{if REPOS != "*" { "--repos " + REPOS } else { "" } }} \
		--output {{BENCHMARK_RESULTS_DIR}}/swe_bench_eval.json \
		--verbose

# Quick SWE-Bench smoke test (10 instances)
eval-swe-bench-quick:
	@echo "Running quick SWE-Bench smoke test..."
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}
	uv run python scripts/eval_swe_bench.py \
		--dataset benchmarks/test-data/swe_bench_instances.json \
		--limit 10 \
		--output {{BENCHMARK_RESULTS_DIR}}/swe_bench_quick.json

# Golden Scenarios Evaluation (Flask)
# ------------------------------------------------------------------------------

# Run custom golden scenario evaluation
eval-golden SCENARIOS="benchmarks/golden-scenarios/evals/flask":
	@echo "Running golden scenario evaluation..."
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}
	uv run python scripts/eval_retrieval.py \
		--scenarios {{SCENARIOS}} \
		--output {{BENCHMARK_RESULTS_DIR}}/golden_eval.json
	@echo "✅ Results saved to {{BENCHMARK_RESULTS_DIR}}/golden_eval.json"

# Run golden scenarios with verbose output
eval-golden-verbose SCENARIOS="benchmarks/golden-scenarios/evals/flask":
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}
	uv run python scripts/eval_retrieval.py \
		--scenarios {{SCENARIOS}} \
		--output {{BENCHMARK_RESULTS_DIR}}/golden_eval.json \
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
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}
	uv run python scripts/benchmark_ann.py \
		--queries {{QUERIES}} \
		--iterations {{ITERATIONS}} \
		--output {{BENCHMARK_RESULTS_DIR}}/ann_benchmark.json
	@echo "✅ Results saved to {{BENCHMARK_RESULTS_DIR}}/ann_benchmark.json"

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
	@echo "   - SWE-Bench: {{BENCHMARK_RESULTS_DIR}}/swe_bench_quick.json"
	@echo "   - Golden: {{BENCHMARK_RESULTS_DIR}}/golden_eval.json"
	@echo "   - ANN: {{BENCHMARK_RESULTS_DIR}}/ann_benchmark.json"

# Quick benchmark for CI (fast smoke tests)
benchmark-quick:
	@echo "Running quick benchmark suite..."
	@just eval-swe-bench-quick
	@just benchmark-ann 10 10
	@echo "✅ Quick benchmark complete"

# Compare evaluations against baseline
compare-eval BASELINE="{{BENCHMARK_RESULTS_DIR}}/baseline_eval.json" CURRENT="{{BENCHMARK_RESULTS_DIR}}/golden_eval.json":
	@echo "Comparing evaluation results..."
	uv run python scripts/compare_eval.py \
		{{BASELINE}} \
		{{CURRENT}} \
		--threshold 3.0

# Save current results as baseline
save-baseline:
	@echo "Saving current results as baseline..."
	@mkdir -p {{BENCHMARK_RESULTS_DIR}}/baselines
	@cp {{BENCHMARK_RESULTS_DIR}}/golden_eval.json {{BENCHMARK_RESULTS_DIR}}/baselines/baseline_$(shell date +%Y%m%d_%H%M%S).json
	@cp {{BENCHMARK_RESULTS_DIR}}/golden_eval.json {{BENCHMARK_RESULTS_DIR}}/baseline_eval.json
	@echo "✅ Baseline saved"

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
