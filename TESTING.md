# Testing Guide

This document describes the test structure and available test commands for the Dolphin project.

## Test Organization

Tests are organized into three categories:

### 1. Unit Tests (Fast)
Fast, isolated tests with no external dependencies. Use these for rapid feedback during development.

**Run all unit tests:**
```bash
just test-unit-all
```

**Run unit tests by domain:**
```bash
just test-unit-python          # Python unit tests
just test-unit-agent-core      # Agent Core unit tests
just test-unit-agent-core-v2   # Agent Core V2 unit tests
just test-unit-extension       # VSCode Extension unit tests
just test-unit-webview         # Webview unit tests
```

### 2. Integration Tests (Medium)
Tests that integrate components within a single domain. These may interact with external services or multiple modules.

**Run all integration tests:**
```bash
just test-integration-all
```

**Run integration tests by domain:**
```bash
just test-integration-python          # Python integration tests
just test-integration-agent-core      # Agent Core integration tests
just test-integration-agent-core-v2   # Agent Core V2 integration tests
just test-integration-extension       # VSCode Extension integration tests
just test-integration-mcp-bridge      # MCP Bridge integration tests
```

### 3. End-to-End Tests (Slow)
Full cross-domain integration tests that verify complete workflows.

**Run all e2e tests:**
```bash
just test-e2e-all
```

**Run e2e tests by domain:**
```bash
just test-e2e-extension-full   # VSCode Extension full E2E tests
just test-e2e-agent-core-v2    # Agent Core V2 E2E tests
```

## Legacy Commands

For backwards compatibility, the following commands are still available:

```bash
just test-e2e          # Run ALL tests (unit + integration + e2e) - SLOW!
just test-e2e-lenient  # Run tests with lenient mode (skip flaky tests)
```

**Note:** `just test-e2e` runs the comprehensive test suite (all tests). For faster testing, use the specific test category commands above.

## Test Structure by Domain

### Python Backend
- **Unit tests:** `tests/unit/` - Fast tests for individual modules
- **Integration tests:** `tests/integration/` - Tests for search, indexing, API endpoints

### TypeScript Agent Core
- **Unit tests:** Individual test files for storage, stores, diff generation, etc.
- **Integration tests:** Tests for Claude client, MCP client, KB manager

### TypeScript Agent Core V2
- **Unit tests:** `agent-core-v2/tests/unit/`
- **Integration tests:** `agent-core-v2/tests/integration/` (excluding E2E)
- **E2E tests:** `orchestrator-e2e.test.ts`, `editor-workflow.test.ts`

### VSCode Extension
- **Unit tests:** logger, configuration, diff handler, code actions, drift detector
- **Integration tests:** agent bridge, provider, commands, webview
- **E2E tests:** phase1/phase2 integration, conversations E2E, KB lifecycle

### MCP Bridge
- **Integration tests:** All tests in `mcp-bridge/src/tests/`

### Webview UI
- **Unit tests:** All tests in `vscode-extension/webview/src/`

## Recommended Workflow

1. **During development:** Run `just test-unit-all` for fast feedback
2. **Before committing:** Run `just test-integration-all` to catch integration issues
3. **Before merging:** Run `just test-e2e-all` for full E2E validation
4. **CI/CD:** Run `just test-e2e` for comprehensive validation

## Coverage Reports

Run tests with coverage:
```bash
just test-coverage       # Python tests with coverage
just test-e2e-coverage   # All tests with coverage reports
```
