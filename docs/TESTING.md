# Testing Guide

**Version**: 2.1.0  
**Last Updated**: 2025-11-21

This repository has a single, canonical testing reference. Use this file for all suites (Python backend, Agent Core, VS Code extension, MCP bridge, shared packages, and observability).

## Post-merge verification checklist

1. **Sync tooling**: `uv sync` for Python, `npm install`/`bun install` per workspace if dependencies changed.
2. **Lint everything**: `npm run lint:all` for TypeScript/JavaScript; `uv run ruff check` for Python.
3. **Run the test matrix** (at minimum before tagging or publishing):
   - Python backend: `uv run pytest tests/unit/` and `uv run pytest tests/integration/` (use `uv run pytest tests/e2e/workflows/` for release candidates).
   - Agent Core: `cd agent-core && bun test`.
   - VS Code extension: `cd vscode-extension && bun test` (runs unit + integration) and `npm run test --workspace vscode-extension/playwright` for UX automation when CI resources allow.
   - MCP bridge: `cd mcp-bridge && bun test`.
4. **Update docs and changelog**: Reflect coverage/behavior changes here and in `CHANGELOG.md`.
5. **Archive results**: Attach failing logs to the PR if anything is unstable; do not merge with red checks.

## Quick commands

```bash
just test-all                    # All tests across all projects
just test-unit-all               # All unit tests
just test-integration-all        # All integration tests
just test-e2e-all                # All E2E tests

just test-python [TYPE]          # Python tests (TYPE: unit, integration, e2e, or all)
just test-agent-core [TYPE]      # Agent Core tests
just test-extension [TYPE]       # VSCode Extension tests
just test-mcp-bridge             # MCP Bridge tests (integration)
just test-webview                # Webview tests (unit)
```

## Suite map

### Python backend

- **Unit**: `tests/unit/` (domains: api, cache, chunkers, cli, config, embeddings, graph, ingest, logging, pipeline, retrieval, search, store, constants)
- **Integration**: `tests/integration/` (domains: cache, cli, graph_intelligence, ingest, kb, pipeline, search)
- **End-to-end**: `tests/e2e/workflows/` (indexing and search workflows)
- **Run**: `uv run pytest tests/unit/ -v`, `uv run pytest tests/integration/ -v`, `uv run pytest tests/e2e/workflows/ -v`

### TypeScript Agent Core

- **Unit**: `agent-core/tests/unit/` (architect, orchestrator, rpc, state)
- **Integration/E2E**: `agent-core/tests/integration/` and `agent-core/tests/integration/e2e/`
- **Run**: `cd agent-core && bun test`

### VS Code extension

- **Unit**: `vscode-extension/src/test/suite/unit/`
- **Integration**: `vscode-extension/src/test/suite/integration/`
- **E2E (Mocha + Playwright)**: `vscode-extension/src/test/suite/e2e/` then `vscode-extension/playwright/tests/`
- **Run**: `cd vscode-extension && bun test` (Mocha suites) then `npm run test --workspace vscode-extension/playwright`

### MCP bridge

- **Integration**: `mcp-bridge/src/tests/`
- **Run**: `cd mcp-bridge && bun test`

### Webview UI

- **Unit**: `vscode-extension/webview/src/`
- **Run**: `cd vscode-extension/webview && bun test`

### Shared packages

- **Unit**: `shared/tests/`
- **Run**: `cd shared && bun test`

## Python backend specifics

### Tokenization parity

- **Unit tests** always use `MockTiktokenEncoding` (`tests/conftest.py`) to keep runs offline and deterministic.
- **Integration/e2e** suites require the real `cl100k_base` encoding. They will download once and then validate the cached copy. Failures indicate production would fail too—refresh with `TIKTOKEN_FORCE_REFRESH=1 uv run pytest tests/integration/`.

### Cache validation quick hits

- Cache correctness lives in `tests/unit/test_cache.py`; use `uv run pytest tests/unit/test_cache.py -v` to exercise embedding/result caches, key stability, stats, and invalidation.
- Integration flows in `tests/integration/cache/` cover Redis/LanceDB interplay; run them when changing cache wiring.

## Observability stack

- Current status: configs are validated, but runtime is **untested**. Treat the steps below as required before enabling alerts or dashboards in production.
- **Smoke flow**:
  1. Start the stack: `cd observability && ./start-stack.sh` (expects Prometheus/Grafana/Jaeger/Loki healthy).
  2. Boot the KB API with metrics: `cd kb && uv run python -m uvicorn api.server:app_with_lifespan --host 0.0.0.0 --port 8000`.
  3. Verify `/metrics` and `/v1/health` respond, then confirm Prometheus shows the `kb-api` target as `UP` at http://localhost:9090/targets.
  4. Run Grafana queries/dashboards once data is flowing; fix scrape errors before merging.

## Known gaps to close

1. MCP bridge has unit/integration coverage (Bun); expand contract-focused tests (schema versioning, strict validation, trimming edge cases).
2. E2E workflows cover indexing and search; consider adding “search → chunk_get/file_lines followups” assertions using returned identifiers.
3. Observability smoke tests are manual; convert the flow above into a `just observability-smoke` target when time permits.
