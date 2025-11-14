# Testing Guide

**Version**: 1.0.0
**Last Updated**: 2025-11-12

This document describes the test structure and available test commands for the Dolphin project. Tests are extensive and can take a while to complete; default to running only the tests about which you are concerned.

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
just test-unit-python                    # All Python unit tests
just test-unit-python-domain search      # Python search domain only
just test-unit-python-domain ingest      # Python ingest domain only
just test-unit-python-domain api         # Python API domain only
just test-unit-agent-core                # Agent Core unit tests
just test-unit-agent-core-v2             # Agent Core V2 unit tests
just test-unit-extension                 # VSCode Extension unit tests
just test-unit-webview                   # Webview unit tests
```

### 2. Integration Tests (Medium)

Tests that integrate components within a single domain. These may interact with external services or multiple modules.

**Run all integration tests:**

```bash
just test-integration-all
```

**Run integration tests by domain:**

```bash
just test-integration-python                        # All Python integration tests
just test-integration-python-domain search          # Python search integration tests
just test-integration-python-domain ingest          # Python ingest integration tests
just test-integration-python-domain graph_intelligence  # Python graph integration tests
just test-integration-agent-core                    # Agent Core integration tests
just test-integration-agent-core-v2                 # Agent Core V2 integration tests
just test-integration-extension                     # VSCode Extension integration tests
just test-integration-mcp-bridge                    # MCP Bridge integration tests
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

Python tests are now organized by domain within each test category. All test files follow the standard Python/pytest naming convention (`test_*.py`).

#### Unit Tests (`tests/unit/`)

Fast, isolated tests organized by domain:

- `api/` - API endpoint tests
- `cache/` - Caching layer tests (AST cache, query cache)
- `chunkers/` - Text chunking and parsing tests
- `cli/` - Command-line interface tests
- `config/` - Configuration and repo config tests
- `embeddings/` - Embedding provider and token utility tests
- `graph/` - Graph context and helpers tests
- `graph_intelligence/` - Graph intelligence and call graph tests
- `ingest/` - Scanner, hashing, and ingestion tests
- `logging/` - Structured logging tests
- `pipeline/` - Task queue and connection pool tests
- `retrieval/` - Adaptive batching and retrieval tests
- `search/` - Search backend, ANN, MMR, and ranking tests
- `store/` - Data store tests (LanceDB, SQLite)
- `constants/` - Configuration constants tests

**Run specific domain unit tests:**
```bash
uv run pytest tests/unit/search/     # Search domain only
uv run pytest tests/unit/ingest/    # Ingest domain only
uv run pytest tests/unit/api/       # API domain only
```

#### Integration Tests (`tests/integration/`)

Tests that integrate components within a domain:

- `cache/` - Cache integration and completion tests
- `cli/` - CLI workflow integration tests
- `graph_intelligence/` - Graph extraction and enriched search tests
- `ingest/` - Indexing and file sync integration tests
- `kb/` - Knowledge base auto-sync and token tests
- `pipeline/` - Pipeline orchestration and optimization tests
- `search/` - Search integration, hybrid search, and reranking tests

**Run specific domain integration tests:**
```bash
uv run pytest tests/integration/search/           # Search integration tests
uv run pytest tests/integration/graph_intelligence/  # Graph integration tests
uv run pytest tests/integration/ingest/          # Ingest integration tests
```

#### End-to-End Tests (`tests/e2e/`)

Full workflow tests:

- `workflows/` - Complete indexing and search workflow tests

**Run e2e tests:**
```bash
uv run pytest tests/e2e/workflows/   # All workflow E2E tests
```

### TypeScript Agent Core

TypeScript tests in agent-core are now organized by domain within each test category. All test files follow the naming convention `*.test.ts`.

#### Unit Tests (`agent-core/tests/unit/`)

Fast, isolated tests organized by domain:

- `architect/` - Architect workflow unit tests
- `orchestrator/` - Orchestrator unit tests
- `rpc/` - JSON-RPC communication tests
- `state/` - State store tests

**Run specific domain unit tests:**
```bash
just test-unit-agent-core                      # All agent-core unit tests
just test-unit-agent-core-domain architect     # Architect domain only
just test-unit-agent-core-domain orchestrator  # Orchestrator domain only
```

#### Integration Tests (`agent-core/tests/integration/`)

Tests that integrate components within a domain:

- `architect/` - Architect KB integration tests
- `auth/` - Claude authentication tests
- `editor/` - Editor workflow integration tests
- `kb/` - Knowledge base integration tests
- `e2e/` - Full end-to-end workflow tests

**Run specific domain integration tests:**
```bash
just test-integration-agent-core                   # All agent-core integration tests
just test-integration-agent-core-domain architect  # Architect integration tests
just test-integration-agent-core-domain kb         # KB integration tests
```

**Run e2e tests:**
```bash
just test-e2e-agent-core   # All agent-core E2E tests
```

### VSCode Extension

VSCode Extension tests are organized by test type and domain. All test files follow the naming convention `*.test.ts`.

#### Unit Tests (`vscode-extension/src/test/suite/unit/`)

Fast, isolated tests organized by domain:

- `core/` - Logger, configuration, error handling tests
- `editor/` - Diff handler, code actions tests
- `sync/` - Auto-sync manager, file watcher, drift detector tests
- `commands/` - Commands registry tests

**Run specific domain unit tests:**
```bash
just test-unit-extension                    # All extension unit tests
just test-unit-extension-domain core        # Core domain only
just test-unit-extension-domain editor      # Editor domain only
just test-unit-extension-domain sync        # Sync domain only
```

#### Integration Tests (`vscode-extension/src/test/suite/integration/`)

Tests that integrate components within a domain:

- `agent/` - Agent bridge, architect mode integration tests
- `ui/` - Provider, webview integration tests
- `commands/` - Commands integration tests
- `core/` - Extension activation tests

**Run specific domain integration tests:**
```bash
just test-integration-extension                    # All extension integration tests
just test-integration-extension-domain agent       # Agent integration tests
just test-integration-extension-domain ui          # UI integration tests
```

#### End-to-End Tests (`vscode-extension/src/test/suite/e2e/`)

Full workflow tests:

- `conversations/` - Conversation lifecycle E2E tests
- `kb/` - Knowledge base lifecycle tests
- `workflows/` - Complete integration workflow tests

**Run e2e tests:**
```bash
just test-e2e-extension-full                  # All extension E2E tests
just test-e2e-extension-domain conversations  # Conversations E2E only
just test-e2e-extension-domain kb             # KB lifecycle E2E only
```

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
