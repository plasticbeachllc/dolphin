# Dolphin Architecture

Technical architecture and implementation status for Dolphin.

**Version**: 0.2.2  
**Status**: Beta (KB + MCP release components)  
**Last Updated**: 2026-02-22

## Overview

Dolphin is a semantic code retrieval platform built around:

- A Python Knowledge Bank backend (indexing, storage, retrieval)
- A TypeScript MCP bridge for AI client integrations
- Shared TypeScript utilities

### 0.3.0 development path

The `develop` branch is replacing the bridge/API hop with a foreground Python stdio MCP runtime. Its prerelease lifecycle authority lives under `~/Library/Application Support/Dolphin/` and currently provides:

- one private SQLite authority for explicit worktree registrations, repository boundaries, operations, runtime owners, execution leases, and source-free checkpoints;
- capability-bearing runtime records with PID plus process-start identity, 15-second leases renewed every five seconds, and fail-closed stale-owner reconciliation;
- atomic operation claiming, pipeline-compatible resume, monotonic phase/counter checkpoints, and immediate graceful handoff on MCP shutdown; and
- aggregate runtime health in `status` plus durable checkpoint progress in `operation_status`.

The installed MCP process is intentionally recorded as non-executing until the new indexing adapter is connected. Consequently, `repo_add`, mutation tools, and search remain explicitly unavailable rather than accepting work that cannot progress. The TypeScript bridge and REST architecture below continue to describe the current 0.2.2 release while the clean-break 0.3.0 runtime is completed.

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

### Retrieval performance notes (2026-02)

- `/v1/search` dispatches synchronous backends via `asyncio.to_thread`, and prefers a backend `search_async` method when available to keep the FastAPI event loop non-blocking under load.
- `KnowledgeSearchBackend` now exposes `search_async`, which uses async embedding calls and preserves the existing synchronous `search` entrypoint for CLI and tests.
- Async and sync search paths now share cache-state evaluation to avoid duplicate cache lookups on async cache misses.
- Vector and BM25 branches execute concurrently inside `KnowledgeSearchBackend.search` to reduce end-to-end search latency.
- BM25 hydration now uses bulk metadata lookups keyed by FTS content IDs (`SQLiteMetadataStore.get_bm25_hydration_map`) instead of per-hit lookups.
- LanceDB vector indexes are managed explicitly and lazily per table in `LanceDBStore` (create once, reuse across queries).
- Search result caching now fingerprints the full effective request shape (filters, ANN/MMR knobs, graph-context flag, cursor) to prevent cross-request cache collisions.
- Repo reindex invalidation now clears both repo-scoped and global (unscoped) cached search entries to avoid stale cross-repo query results.

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
- ✅ Watcher shutdown path: startup-cancel cleanup and bounded server-side cancellation grace windows are active
- ✅ Chunking config model scope: embedding model selection is global (repo-level model overrides ignored)

## Testing Surface

- Python: `tests/unit/`, `tests/integration/`, `tests/e2e/workflows/`
- MCP bridge: `mcp-bridge/src/tests/`
- Shared: `shared/tests/`

See `docs/TESTING.md` for canonical commands and pre-release checks.
