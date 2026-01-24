# Release Plan — v0.2.0 (KB + MCP)

This document captures pre-release issues and recommended improvements for shipping Dolphin **v0.2.0** (Knowledge Bank + MCP Bridge).

## Scope

**In scope (release-targeted):**
- **Knowledge Bank (Python)**: `kb/` (indexing, storage, REST API)
- **MCP Bridge (TypeScript/Bun)**: `mcp-bridge/` (MCP tools + REST client)

**Out of scope (experimental):**
- `agent-core/`
- `vscode-extension/`

## Release Criteria (Exit Checklist)

- **Functionality**
  - Search results returned by `/v1/search` can be followed up via MCP tools:
    - `search` → `chunk.get` works for any returned `chunk_id`
    - `search` → `metadata.get` works for any returned `chunk_id`
    - `search` → `file.lines` works for any returned `{repo,path,start,end}`
  - Hybrid search fusion (vector + BM25) can truly fuse results (same “document id” across sources).
  - Incremental indexing preserves vector search quality when chunks move (no silent vector loss).
- **Performance**
  - `/v1/search` responses do not include raw embedding vectors.
  - MCP responses remain under the payload cap with typical `top_k` defaults.
- **Safety**
  - File endpoints reject invalid ranges and block path traversal attempts.
- **Quality**
  - Relevant suites pass:
    - `uv run pytest tests/unit/ -v`
    - `uv run pytest tests/integration/ -v`
    - `uv run pytest tests/e2e/workflows/ -v` (RC gate)
    - `cd mcp-bridge && bun test`
- **Docs + Changelog**
  - `CHANGELOG.md` and `mcp-bridge/CHANGELOG.md` reflect actual shipped behavior.
  - `docs/ARCHITECTURE.md` and `docs/TESTING.md` are internally consistent and don’t reference non-existent paths/files.

## Release Blockers (Must Fix Before Tagging)

### 1) `chunk_id` contract mismatch (KB ↔ MCP)

**Why this blocks release**
- The core MCP flow depends on `search` returning `chunk_id` values that `chunk.get` and `metadata.get` can fetch.
- Today, indexers generate colon-delimited LanceDB row IDs (e.g. `repo_id:file_id:embed_model:text_hash:start:end`), while `/v1/chunks/{chunk_id}` rejects colons and then also can’t hydrate content for row IDs.
- BM25 results return deterministic FTS IDs, so hybrid fusion cannot meaningfully fuse “the same” chunk across vector vs BM25 results.

**Evidence**
- Rejects colons: `kb/api/app.py` (`CHUNK_ID_PATTERN`)
- Row IDs emitted by indexing:
  - `kb/ingest/pipeline.py` (row_id format)
  - `kb/api/app.py` (file-sync indexing path uses same row_id format)
- BM25 returns deterministic FTS IDs: `kb/store/sqlite_meta.py` (`bm25_search`)
- MCP tools rely on `/v1/chunks/{chunk_id}`:
  - `mcp-bridge/src/mcp/tools/chunk_get.ts`
  - `mcp-bridge/src/mcp/tools/get_metadata.ts`

**Fix plan (recommended)**
- Define and document **one canonical `chunk_id`** for tool followups.
  - Recommendation: treat `chunk_id` as the LanceDB row ID (it uniquely identifies an occurrence and matches start/end lines).
- Update `/v1/chunks/{chunk_id}` to:
  - Accept row IDs (update validation) and
  - Hydrate content for row IDs by mapping to deterministic FTS content_id (parse row_id → `repo_id,file_id,text_hash` → `generate_fts_content_id(...)`) or by reading from disk via repo root + start/end.
- Ensure `/v1/search` returns `chunk_id` values that always work with `/v1/chunks/{chunk_id}`.
- Make hybrid fusion use a consistent ID field (so BM25 and vector results can fuse/merge).

**Acceptance tests**
- End-to-end: take any `chunk_id` returned by `/v1/search` and call `/v1/chunks/{chunk_id}` → 200 with non-empty `content`.
- MCP: `search` then `chunk.get` succeeds for returned `chunk_id` (no special casing).
- Hybrid: ensure at least one test asserts fusion of a result appearing in both BM25 and vector lists (same identifier).

### 2) Incremental indexing can silently drop vectors when chunks move

**Why this blocks release**
- Dedup is text-hash-only; unchanged chunks are not re-embedded (good).
- But row IDs include start/end lines; when a chunk moves, the row ID changes.
- Current logic can prune the old row IDs and *not* write new rows for unchanged hashes, causing those chunks to disappear from vector search after an incremental index.

**Evidence**
- Unchanged hashes skip vector writes, but pruning keeps only “desired” (new) row IDs:
  - `kb/ingest/pipeline.py` (vector persistence and pruning)
  - `kb/api/app.py` (same pattern in `/v1/index` file-sync path)
- Dedup behavior: `kb/ingest/dedup.py`

**Fix plan (recommended)**
- When a hash is unchanged but its occurrences (row IDs) change, reconstitute vectors for the new row IDs:
  - Option A: query LanceDB for an existing vector for `(repo,path,embed_model,text_hash)` and reuse it for new occurrences.
  - Option B: change LanceDB schema/ID strategy so vectors are keyed by `text_hash` (or stable content id) and occurrences reference them separately.
- Add a regression test: move a function in-file without changing its text; incremental index must preserve vector hits for that function.

### 3) Search API responses include raw embedding vectors

**Why this blocks release**
- LanceDB search results include a `vector` field; current formatting passes it through.
- This bloats `/v1/search` responses and makes MCP payload trimming more frequent/expensive; it also increases cache size.

**Evidence**
- `kb/api/search_backend.py` formats vector results without stripping `vector`.

**Fix plan (recommended)**
- Remove `vector` from API responses after ranking is complete (MMR can use vectors internally, but they should not be returned/cached).
- Add/adjust tests to assert no hit contains `vector`.

## High Priority (Should Fix Before Tagging)

### KB API correctness + hygiene

- `/v1/file` should validate ranges (e.g. reject `start > end`) rather than returning an empty slice.
- Remove or gate INFO-level debug logging:
  - `kb/api/app.py` contains `[DEBUG]` INFO logs in the `/v1/index` path.
  - `kb/ingest/dedup.py` logs `[DEBUG DEDUP]` at INFO.
- Consolidate duplicate `/health` handlers (defined in both `kb/api/app.py` and `kb/api/server.py`) to avoid ambiguous routing.
- Address LanceDB deprecation warnings (`table_names()` → `list_tables()`).

### MCP bridge consistency + packaging

- Align `mcp-bridge/CHANGELOG.md` with shipped behavior:
  - It claims JSON-RPC support and `file_write`/`read_files` tools, but the current MCP tool registry does not expose these.
- Remove or update the stale `mcp-bridge/kb-cli.ts` wrapper (it imports non-existent tools).
- Align the MCP→KB request contract:
  - MCP sends parameters such as `max_snippets`, `cursor`, `deadline_ms` that KB may ignore today; decide whether to implement these server-side or stop advertising them in schemas/docs.

## Docs Cleanups (Should Fix Before Tagging)

- Fix broken references in `docs/ARCHITECTURE.md` (e.g., references to `kb/src/` and `ACCESSIBILITY.md` that don’t exist in this repo layout).
- Update `docs/TESTING.md` “Known gaps” if those items are no longer true (search filtering E2Es are present and running).

## Pre-Tag Commands

Use this as the final “green gate” before tagging:

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
uv run pytest tests/e2e/workflows/ -v

cd mcp-bridge && bun test
```

Optional security regression run (recommended when touching path handling):

```bash
uv run python scripts/security-pentest.py
```

## Tagging / Publishing Notes

Publishing is tag-driven per `PUBLISH.md`:
- Python: `py-v0.2.0`
- MCP: `mcp-v0.2.0`

Confirm versions match:
- `pyproject.toml` (`0.2.0`)
- `mcp-bridge/package.json` (`0.2.0`)

