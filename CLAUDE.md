# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Dolphin

Dolphin is a semantic code search and knowledge management platform. It provides hybrid vector + keyword retrieval for large codebases via CLI, REST API, and MCP (Model Context Protocol).

**Data flow:** `MCP client → mcp-bridge (TS/Bun) → kb/api (Python/FastAPI) → SQLite + LanceDB`
**Indexing:** `repo → scan → chunk → embed → store`
**Search:** `query → embed → vector/BM25 → fuse/rerank → response`

## Commands

### Python — always use `uv run`

```bash
uv run pytest tests/unit/ -v              # unit tests
uv run pytest tests/integration/ -v       # integration tests
uv run pytest tests/unit/search/ -v       # domain-scoped tests
uv run pytest tests/unit/test_foo.py -v   # single file
uv run pytest -k "test_name" -v           # single test by name
uv run ruff check --fix                   # lint + autofix
uv run ruff format                        # format
uv run ty check                           # type check
uv run dolphin serve                      # start API (port 7777)
```

pytest runs with `-n auto` (xdist parallel) by default. Use `-n0` to disable parallelism (e.g. for coverage: `uv run pytest -n0 tests/ --cov=kb`).

### TypeScript/MCP Bridge — use `bun`

```bash
cd mcp-bridge && bun test                 # MCP bridge tests
cd shared && bun test                     # shared package tests
bun run lint:all                          # TS linting
```

### Just (task runner)

```bash
just test unit                            # all unit tests (Python + TS)
just test-kb unit                         # Python unit only
just test-mcp all                         # MCP bridge only
just check                                # all linting (Python + TS)
just check-python                         # ruff + ty
```

## Architecture

### Python backend (`kb/`)

| Directory | Purpose |
|-----------|---------|
| `kb/api/` | FastAPI app, routes, search backend, middleware |
| `kb/ingest/` | Indexing pipeline, scanner, parallel parser, CLI |
| `kb/chunkers/` | Language-aware AST chunkers (Python, TS, SQL, Svelte, Markdown) |
| `kb/store/` | SQLite metadata (`sqlite_meta.py` — largest file), LanceDB vectors, graph storage |
| `kb/search/` | Parallel search execution, adaptive ANN tuning |
| `kb/retrieval/` | Ranking, cross-encoder reranking, BM25 normalization, graph context |
| `kb/embeddings/` | OpenAI embedding provider, adaptive batching |
| `kb/cache/` | Query result caching with fingerprinting, AST cache |
| `kb/graph_intelligence/` | Knowledge graph: import/type extractors |
| `kb/config.py` | Config loading from `~/.dolphin/config.toml` |
| `kb/cli.py` | Unified CLI entry point (`dolphin` command) |

### TypeScript (`mcp-bridge/`, `shared/`)

- `mcp-bridge/src/index.ts` — MCP server exposing search/chunk/file tools to AI clients
- `shared/` — IPC, types, security, observability utilities shared across TS packages

### Tests (`tests/`)

- `tests/unit/` — fast, mocked, mirrors `kb/` structure
- `tests/integration/` — multi-component with temp DBs
- `tests/e2e/` — full system workflows
- Markers: `@slow`, `@integration`, `@unit`, `@e2e`, `@asyncio`, `@performance`

## Key conventions

- **Line length**: 120 (ruff)
- **Imports**: sorted by ruff/isort; `kb` is first-party
- **Entry points**: `dolphin` (main CLI), `kb` (ingest CLI), `kb-api` (API server)
- **Config**: loaded from `~/.dolphin/config.toml` or `./.dolphin/config.toml`
- **API key**: auto-generated at `~/.dolphin/kb_api_key`; override with `DOLPHIN_API_KEY` env var
- **Structured logging**: use `StructuredLogger` from `kb.observability`
- **Path security**: all user-controlled paths must go through `kb.security.path_validator`

## Before finalizing changes

```bash
uv run pytest tests/unit/ -v
uv run ruff check
uv run ty check
```

For changes touching MCP bridge or shared: `cd mcp-bridge && bun test && cd ../shared && bun test`
