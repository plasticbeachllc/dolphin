# Testing Guide

**Version**: 2.0.0
**Last Updated**: 2025-11-14

This document describes the test structure and available test commands for the Dolphin project. Tests are organized by domain and test type for easy navigation and execution.

## Quick Reference

**Run all tests:**

```bash
just test-all                    # All tests across all projects
just test-unit-all               # All unit tests
just test-integration-all        # All integration tests
just test-e2e-all                # All E2E tests
```

**Run tests by project:**

```bash
just test-python [TYPE]          # Python tests (TYPE: unit, integration, e2e, or all)
just test-agent-core [TYPE]      # Agent Core tests
just test-extension [TYPE]       # VSCode Extension tests
just test-mcp-bridge             # MCP Bridge tests (integration)
just test-webview                # Webview tests (unit)
```

**Run tests by domain:**

```bash
just test-python-domain DOMAIN [TYPE]       # e.g., search, ingest, api
just test-agent-core-domain DOMAIN [TYPE]   # e.g., architect, orchestrator
just test-extension-domain DOMAIN [TYPE]    # e.g., core, editor, sync
```

**Examples:**

```bash
just test-python unit                       # All Python unit tests
just test-python-domain search              # All search tests (unit + integration)
just test-python-domain search unit         # Only search unit tests
just test-agent-core integration            # All agent-core integration tests
just test-extension-domain core unit        # Only extension core unit tests
```

## Test Organization by Type

### Unit Tests (Fast)

Fast, isolated tests with no external dependencies. Use these for rapid feedback during development.

```bash
just test-unit-all                          # All unit tests across all projects
just test-python unit                       # Python unit tests only
just test-agent-core unit                   # Agent Core unit tests only
just test-extension unit                    # Extension unit tests only
just test-webview                           # Webview unit tests
```

### Integration Tests (Medium)

Tests that integrate components within a domain. These may interact with external services or multiple modules.

```bash
just test-integration-all                   # All integration tests
just test-python integration                # Python integration tests
just test-agent-core integration            # Agent Core integration tests
just test-extension integration             # Extension integration tests
just test-mcp-bridge                        # MCP Bridge integration tests
```

### End-to-End Tests (Slow)

Full cross-domain integration tests that verify complete workflows.

```bash
just test-e2e-all                           # All E2E tests
just test-python e2e                        # Python E2E tests
just test-agent-core e2e                    # Agent Core E2E tests
just test-extension e2e                     # Extension E2E tests
```

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

**Run specific domain tests:**

```bash
just test-python-domain search unit         # Search unit tests
just test-python-domain ingest unit         # Ingest unit tests
just test-python-domain api unit            # API unit tests

# Or directly with pytest:
uv run pytest tests/unit/search/            # Search domain
uv run pytest tests/unit/ingest/            # Ingest domain
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
just test-python-domain search integration              # Search integration tests
just test-python-domain graph_intelligence integration  # Graph integration tests
just test-python-domain ingest integration              # Ingest integration tests

# Or directly with pytest:
uv run pytest tests/integration/search/                 # Search integration
uv run pytest tests/integration/graph_intelligence/     # Graph integration
```

#### End-to-End Tests (`tests/e2e/`)

Full workflow tests:

- `workflows/` - Complete indexing and search workflow tests

**Run e2e tests:**

```bash
just test-python e2e                 # All Python E2E tests
uv run pytest tests/e2e/workflows/   # Directly with pytest
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
just test-agent-core unit                      # All agent-core unit tests
just test-agent-core-domain architect unit     # Architect domain only
just test-agent-core-domain orchestrator unit  # Orchestrator domain only
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
just test-agent-core integration                   # All agent-core integration tests
just test-agent-core-domain architect integration  # Architect integration tests
just test-agent-core-domain kb integration         # KB integration tests
```

**Run e2e tests:**

```bash
just test-agent-core e2e   # All agent-core E2E tests
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
just test-extension unit                    # All extension unit tests
just test-extension-domain core unit        # Core domain only
just test-extension-domain editor unit      # Editor domain only
just test-extension-domain sync unit        # Sync domain only
```

#### Integration Tests (`vscode-extension/src/test/suite/integration/`)

Tests that integrate components within a domain:

- `agent/` - Agent bridge, architect mode integration tests
- `ui/` - Provider, webview integration tests
- `commands/` - Commands integration tests
- `core/` - Extension activation tests

**Run specific domain integration tests:**

```bash
just test-extension integration                    # All extension integration tests
just test-extension-domain agent integration       # Agent integration tests
just test-extension-domain ui integration          # UI integration tests
```

#### End-to-End Tests (`vscode-extension/src/test/suite/e2e/`)

Full workflow tests:

- `conversations/` - Conversation lifecycle E2E tests
- `kb/` - Knowledge base lifecycle tests
- `workflows/` - Complete integration workflow tests

**Run e2e tests:**

```bash
just test-extension e2e                        # All extension E2E tests (Mocha harness + Playwright)
just test-extension-domain conversations e2e   # Conversations E2E only
just test-extension-domain kb e2e              # KB lifecycle E2E only
```

> **Playwright UX coverage:** The extension also ships a full VS Code UI automation suite under `vscode-extension/playwright/tests`. The root test flow (`npm run test:e2e` or `just test-extension e2e`) now runs the in-editor Mocha E2Es first and then executes the Playwright UX tests via `npm run test:extension:playwright`. Use that workspace directly (`npm run test --workspace vscode-extension/playwright`) when you want to exercise only the UI layer. First-time setup: `cd vscode-extension/playwright && npm install && npx playwright install --with-deps`.

### MCP Bridge

- **Integration tests:** All tests in `mcp-bridge/src/tests/`

### Webview UI

- **Unit tests:** All tests in `vscode-extension/webview/src/`

## Utility Commands

**Run specific files:**

```bash
just test-file FILE                         # Run a specific test file
```

**Run tests with coverage:**

```bash
just test-coverage                          # Python tests with coverage report
```

**Run tests directly with pytest (Python):**

```bash
uv run pytest tests/unit/search/            # Run specific domain tests
uv run pytest tests/unit/ -v                # Run with verbose output
uv run pytest tests/unit/ -k "test_search"  # Run tests matching pattern
```

## Recommended Workflow

1. **During development:** Run domain-specific unit tests

   ```bash
   just test-python-domain search unit        # Fast feedback on your changes
   ```

2. **Before committing:** Run all unit tests

   ```bash
   just test-unit-all                         # Ensure nothing broke
   ```

3. **Before creating PR:** Run integration tests

   ```bash
   just test-integration-all                  # Catch integration issues
   ```

4. **CI/CD:** Run all tests
   ```bash
   just test-all                              # Comprehensive validation
   ```

## Current Coverage Evaluation (2025-05)

### Python backend

- **Unit + integration depth** – The Python suite spans every major KB domain (API, chunkers, ingest, search, cache, pipeline, etc.) across `tests/unit/` and `tests/integration/`, so the majority of business logic executes under pytest during CI.【F:tests/README.md†L31-L137】
- **End-to-end coverage** – `tests/e2e/workflows/test_indexing_workflow.py` drives a full repo lifecycle (registration, incremental indexing, ignore rules, error handling, and forced reindex), while `tests/e2e/workflows/test_search_workflow.py` covers indexing → search flows, query variance, ranking, semantic quality, and performance assertions.【F:tests/e2e/workflows/test_indexing_workflow.py†L1-L199】【F:tests/e2e/workflows/test_search_workflow.py†L1-L390】
- **Gap to note** – search filtering scenarios are still marked `@pytest.mark.skip`, so repo/path-based filtering currently lacks regression coverage.【F:tests/e2e/workflows/test_search_workflow.py†L392-L419】

### Agent Core (TypeScript)

- The Bun test harness exercises architect/orchestrator logic via domain-focused unit suites plus long-running orchestrator/architect E2Es that mock the workflows and persistence, validating streaming updates, cancellation, and concurrency scenarios.【F:agent-core/tests/integration/e2e/orchestrator-e2e.test.ts†L1-L120】
- Coverage largely stops at the workflow layer; RPC bridges and Claude adapters are mocked, so live Claude + KB integration is deferred to manual QA.

### VS Code extension & Webview

- Mocha-based suites (`vscode-extension/src/test/suite/*`) activate the extension against a mock KB server and assert command registration, mock HTTP plumbing, and KB workflow interactions end-to-end.【F:vscode-extension/src/test/suite/e2e/workflows/integration.test.ts†L1-L120】
- Playwright UX automation currently covers only the API-key acquisition flow by driving a real VS Code instance via Electron, so editor UX, chat, and KB browsing are untested at the UI layer.【F:vscode-extension/playwright/tests/api-keys.spec.ts†L1-L104】
- The Svelte webview bundle includes a smoke test component (`App.test.svelte`) but does not exercise real panels or stores yet.【F:vscode-extension/webview/src/App.test.svelte†L1-L34】

### MCP bridge & shared packages

- The bridge ships a single manual integration harness (`mcp-bridge/test-integration.ts`) that requires a running KB REST server, so it is rarely run in CI and lacks stubbed unit coverage for MCP tools or transport errors.【F:mcp-bridge/test-integration.ts†L1-L90】
- Shared TypeScript utilities only have coverage for `kb-auth.ts`, ensuring API-key persistence logic works across environments.【F:shared/tests/kb-auth.test.ts†L1-L60】

### Observability stack

- The observability package documents a thorough plan but explicitly calls out that nothing has been validated end-to-end yet, so dashboards, exporters, and alerting are untested in automation.【F:observability/TESTING.md†L1-L44】

### Lightweight improvement ideas

1. **Turn the skipped Python search filters into runnable cases** – After enabling repo/path filters in `KnowledgeSearchBackend`, re-enable `test_search_filter_by_file_type` and `test_search_filter_by_path` to prevent regressions and ensure CLI/UI consumers receive filtered results.【F:tests/e2e/workflows/test_search_workflow.py†L392-L419】
2. **Add stubbed MCP bridge tests** – Extract the REST client calls from `mcp-bridge/test-integration.ts` into injectable adapters and write Vitest-based unit tests that mock the HTTP responses so CI can validate tool payloads without a live KB server.【F:mcp-bridge/test-integration.ts†L1-L90】
3. **Expand Playwright smoke flows** – Build on the existing API-key automation by scripting one “index repo → search → inspect chunk” happy path inside VS Code, which would reuse the helper functions already present in `api-keys.spec.ts` for launching the editor.【F:vscode-extension/playwright/tests/api-keys.spec.ts†L1-L110】
4. **Add a minimal observability health check** – Convert the manual steps from `observability/TESTING.md` into a `just observability-smoke` task that boots the docker-compose stack, pings `/metrics`, and tears it down so we know metrics wiring stays healthy after config changes.【F:observability/TESTING.md†L1-L80】
5. **Cover shared IPC/security helpers** – Mirror the approach used in `shared/tests/kb-auth.test.ts` to add Bun unit tests for `shared/ipc` and `shared/security`, ensuring cross-project helpers remain stable.【F:shared/tests/kb-auth.test.ts†L1-L60】
