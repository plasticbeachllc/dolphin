# Dolphin Architecture

Technical architecture and implementation status for Dolphin.

**Version**: 0.2.2  
**Status**: Beta (KB + MCP release components)  
**Last Updated**: 2026-02-20

## Overview

Dolphin is a semantic code retrieval platform built around:

- A Python Knowledge Bank backend (indexing, storage, retrieval)
- A TypeScript MCP bridge for AI client integrations
- Shared TypeScript utilities

## System Architecture

```text
AI Client (MCP) / CLI / REST consumer
                |
                v
      MCP Bridge (TypeScript/Bun)
                |
                v
        REST API (Python/FastAPI)
                |
      +---------+----------+
      |                    |
      v                    v
   SQLite               LanceDB
 (metadata/fts)        (vectors)
```

## Core Components

### 1. Knowledge Bank API (`kb/`)

- FastAPI app exposing `/v1/*` APIs
- Ingestion/indexing pipeline
- Hybrid retrieval (vector + BM25/RRF)
- Optional reranking
- Cursor-based pagination and structured snippets

### 2. MCP Bridge (`mcp-bridge/`)

- MCP server implementation for tool-based retrieval
- Zod-validated request/response contracts
- Tooling: `search`, `chunk_get`, `file_lines`, `store_info`, `metadata_get`, `repos_list`, `health`, `open_ref`
- Structured trimming/logging for bounded responses

### 3. Shared TypeScript Package (`shared/`)

- Reusable IPC and utility modules used by TypeScript services

## Data Flow

### Indexing path

`Repository -> scanner -> chunkers -> embeddings -> SQLite/LanceDB`

### Retrieval path

`Query -> embed -> vector + BM25 -> fusion/rerank -> snippets -> API/MCP response`

## Metadata Schema Contract

- Metadata database tracks schema version in `schema_version` (singleton row).
- Startup runs pending schema migrations automatically before normal initialization.
- Canonical runtime schema is `v1`; this is the only supported runtime schema for the `0.2.2` release line.

## CLI Query UX

- `dolphin search` default output is compact and high-signal.
- `--verbose` enables expanded metadata/snippets.
- `--json` emits a stable, script-friendly result schema.
- Common query filters are normalized across local/remote modes:
  - `--repo`, `--path`, `--exclude-path`, `--exclude-pattern`, `--lang`

## Implementation Status

- ✅ Python KB backend: active
- ✅ MCP bridge: active
- ✅ Shared TS utilities: active

## Testing Surface

- Python: `tests/unit/`, `tests/integration/`, `tests/e2e/workflows/`
- MCP bridge: `mcp-bridge/src/tests/`
- Shared: `shared/tests/`

See `docs/TESTING.md` for canonical commands and pre-release checks.
