# Testing Guide

**Version**: 2.2.0
**Last Updated**: 2026-02-20

This repository's canonical test reference covers the Python backend, MCP bridge, shared TypeScript package, and observability checks.

## Post-merge verification checklist

1. Sync tooling: `uv sync --group test` and `bun install`.
2. Lint everything: `bun run lint:all`, `uv run ruff check`, and `uv run ruff format`.
3. Run the test matrix before tagging/publishing:
   - Python backend: `uv run pytest tests/unit/` and `uv run pytest tests/integration/` (use `uv run pytest tests/e2e/workflows/` for release candidates).
   - MCP bridge: `cd mcp-bridge && bun test`.
   - Shared package: `cd shared && bun test`.
4. Update docs/changelog when behavior or coverage changes.
5. Attach failing logs to PRs; do not merge with red checks.

## Quick commands

```bash
just test-all
just test-kb all
just test-mcp all
just test-shared
```

## Suite map

### Python backend

- Unit: `tests/unit/`
- Integration: `tests/integration/`
- End-to-end: `tests/e2e/workflows/`
- Run: `uv run pytest tests/unit/ -v`, `uv run pytest tests/integration/ -v`, `uv run pytest tests/e2e/workflows/ -v`

### MCP bridge

- Integration: `mcp-bridge/src/tests/`
- Run: `cd mcp-bridge && bun test`

### Shared package

- Unit: `shared/tests/`
- Run: `cd shared && bun test`

## Python backend specifics

### Tokenization parity

- Unit tests use `MockTiktokenEncoding` (`tests/conftest.py`) to keep runs deterministic/offline.
- Integration/E2E suites use real `cl100k_base` encoding and validate cached copies. Use `TIKTOKEN_FORCE_REFRESH=1 uv run pytest tests/integration/` if needed.

### Cache validation quick hits

- Unit cache tests: `uv run pytest tests/unit/test_cache.py -v`
- Integration cache flows: `tests/integration/cache/`

## Observability stack

- Current status: config validated; runtime smoke testing remains required before production alerts.
- Smoke flow:
  1. `cd observability && ./start-stack.sh`
  2. `cd kb && uv run python -m uvicorn api.server:app_with_lifespan --host 0.0.0.0 --port 8000`
  3. Verify `/metrics` and `/v1/health`, then confirm `kb-api` target is `UP` at `http://localhost:9090/targets`.
  4. Validate dashboard queries in Grafana after data is flowing.

## Known gaps

1. Expand MCP bridge contract-focused tests (schema versioning, strict validation, trimming edges).
2. Add E2E assertions for `search` followups into `chunk_get`/`file_lines`.
3. Convert manual observability smoke checks into a `just` target.
