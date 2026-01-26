# KB Improvements (0.2.1 / 0.3.0 Ideas)

This document is a brainstorming scratchpad for **Knowledge Base (KB)** improvements only (Python backend: indexing, storage, retrieval, REST API). It’s intentionally biased toward **high-leverage quality-of-life and correctness work** that tends to pay off more than adding “new ranking algorithms”.

## Current Baseline (so we don’t re-suggest it)

These are already present in the repo (see `README.md`, `CHANGELOG.md`, and the referenced code):

- **Hybrid retrieval**: vector + BM25 with **RRF** fusion (`kb/api/search_backend.py`, `kb/store/sqlite_meta.py`, `kb/constants/retrieval_config.py`).
- **Optional cross-encoder reranking** (feature-flagged via deps/config): `kb/retrieval/cross_encoder_rerank.py`.
- **MMR** diversity pass (`kb/api/search_backend.py`, `kb/retrieval/rankers.py`).
- **Query/result caching** (in-memory + optional Redis) (`kb/cache/cache.py`) and a separate LRU/TTL cache implementation (`kb/cache/query_cache.py`).
- **Repo watching + incremental change capture** via `watchfiles` and a persisted `pending_changes` table (`kb/ingest/watcher.py`) plus branch switch handling.
- **Chunk/content dedup** based on `text_hash` and content/location separation (`kb/ingest/dedup.py`, `kb/store/sql_models.py`).
- **Graph context enrichment** can be included in search responses (`kb/api/app.py` request model).
- **API filters already supported**: `repos`, `path_prefix`, `exclude_paths`, `exclude_patterns`, ANN tuning params, snippet sizing, context lines, etc. (`kb/api/app.py`).

## 0.2.1 (Patch) — Low-Risk, High-Impact

### 1) Fix / harden cache invalidation semantics (Redis + in-memory)

**Why it matters**
- Serving stale results after reindex is a trust-killer.
- Today there are *two* caches (`kb/cache/cache.py` and `kb/cache/query_cache.py`) with different invalidation strategies; this makes it easy to “think you’re invalidating” when you aren’t.

**What to do**
- Make repo invalidation correct for Redis-backed result caching:
  - Current `QueryCache` result keys are hashed; scanning for patterns that “contain repo name” is not reliable.
  - Introduce a **repo → set(cache_key)** index (e.g., Redis `SET`) so invalidation is O(number_of_keys_for_repo).
- Decide on a single canonical cache for search results:
  - Either (a) promote `QueryResultCache` and delete/retire `QueryCache` result caching, or (b) fold `QueryResultCache` features (LRU, TTL, per-repo invalidation) into `QueryCache`.
- Add an integration test that proves “reindex invalidates cached search results” for both in-memory and Redis modes.

**Acceptance criteria**
- After `POST /v1/repos/{repo}/reindex` (or any indexing path), the next `/v1/search` against that repo does not return stale content.
- Cache invalidation is deterministic, unit tested, and covered in an integration test.

### 2) Add per-stage time budgets + partial-result degradation to search

**Why it matters**
- You already have config constants for timeouts (`kb/constants/retrieval_config.py`) and snippet fetch timeouts in MCP docs; enforcing them end-to-end prevents tail-latency spikes and “hung” tool calls.

**What to do**
- Introduce a “deadline” for each request and enforce it around:
  - query embedding
  - vector search
  - BM25 search
  - reranking
  - snippet hydration / graph context enrichment
- When the deadline is exceeded, return partial results with a machine-readable `meta`:
  - `meta.timed_out_stages: ["bm25", "rerank"]`
  - `meta.stage_ms: { "embed": 42, "vector": 80, ... }`

**Acceptance criteria**
- A forced timeout (test) returns a valid response shape with `meta.timed_out_stages` populated.
- No single stage can exceed the request time budget without being canceled/short-circuited.

### 3) “Debug explainability” mode for ranking

**Why it matters**
- When users say “KB results are wrong,” you need to answer *why* a hit ranked where it did.
- This is also essential for tuning and evaluating changes without guessing.

**What to do**
- Add a `debug: bool = False` request flag (API + CLI) that returns:
  - BM25 raw score + normalized score (if applicable)
  - vector distance / similarity
  - RRF rank positions and computed RRF score
  - rerank score (if used)
  - applied boosts/penalties (config-file penalty, path filters, etc.)
- Keep the default payload unchanged (debug off by default).

**Acceptance criteria**
- `debug=true` returns stable, documented fields.
- Debug fields are never present unless requested.

### 4) Cursor-based pagination for `/v1/search`

**Why it matters**
- `top_k` is fine for “show me 8,” but clients (MCP, VS Code, agents) often want “give me more” without redoing the full search or duplicating results.

**What to do**
- Add `cursor: str | None` to `SearchRequest` and return `next_cursor` in `meta`.
- Cursor should encode:
  - query + normalized params hash
  - the last returned stable sort key(s) (score + tiebreaker like `chunk_id`)
- Keep deterministic ordering: `(score desc, chunk_id asc)` or similar.

**Acceptance criteria**
- Repeated “page 2, page 3” calls do not repeat hits.
- Cursor is opaque and validated server-side.

### 5) Tighten “negative filtering” and path normalization semantics

**Why it matters**
- You already support `exclude_paths` and `exclude_patterns`, which is great; correctness and consistency here saves a lot of user frustration.

**What to do**
- Ensure path normalization is consistent across:
  - ingestion (stored paths)
  - API filtering
  - CLI filtering
- Document the exact matching semantics (prefix vs glob) in `README.md` (small update).

## 0.3.0 (Minor) — Bigger Wins / Some Schema & API Evolution

### 6) Stable chunk identifiers (align “chunk_id”, “content_id”, and URLs)

**Why it matters**
- Stable IDs are the backbone for:
  - pagination cursors
  - caching
  - “shareable” KB links
  - downstream annotation (“this hit was good/bad”)
- Today, FTS5 content IDs have a deterministic migration (`kb/migrations/001_migrate_fts5_content_ids.py`), but `chunk_content.id` is a UUID in the SQLModel schema (`kb/store/sql_models.py`).

**What to do**
- Make `chunk_content.id` deterministic (or introduce a stable external ID) based on:
  - `(repo_id, file_id, text_hash, embed_model)` for embedding-backed content rows
- Keep `chunk_locations` keyed by that stable ID.
- Decide on one “public identifier” name in API responses:
  - e.g., always return `chunk_id` = stable `chunk_content.id`
  - keep any LanceDB row IDs internal-only

**Acceptance criteria**
- If a chunk is removed and later re-added with identical identity inputs, its ID is the same.
- `/v1/chunks/{id}` works with the same ID across reindex cycles.

### 7) Add a first-class query language (without breaking plain queries)

**Why it matters**
- Power users naturally try `repo:foo path:src auth -test` and get annoyed when it doesn’t work.
- Doing this safely (and predictably) also reduces the need to keep adding one-off request fields.

**What to do**
- Add a tiny query parser that supports:
  - `repo:<name>` (multi-allowed), `-repo:<name>`
  - `path:<prefix>` and `-path:<prefix>`
  - `glob:<pattern>` and `-glob:<pattern>` (maps to `exclude_patterns`)
  - `lang:<language>` / `ext:<.py>`
  - quoted phrases
- Translate parsed directives into existing `SearchRequest` fields where possible.
- Expose the same behavior in CLI (`dolphin search ...`) so API and CLI match.

**Acceptance criteria**
- Plain queries behave exactly as today.
- Parsed directives are validated and cannot trigger SQL/FTS injection.

### 8) Snippet payloads with structured spans (for better UI + agent use)

**Why it matters**
- Agents and UIs want “just enough context,” but also need precise provenance:
  - start/end lines in file
  - included context lines before/after
  - (optionally) highlight ranges

**What to do**
- Standardize a `snippet` object in hits:
  - `{ start_line, end_line, text, truncated, context_before, context_after }`
- Add optional `highlights`:
  - at minimum, token/word-level highlights from BM25 terms
  - potentially span alignment for exact identifier matches

**Acceptance criteria**
- Snippets are consistent across vector-only hits and BM25 hits.
- The server never returns more than `max_snippet_tokens` per snippet and respects `max_snippets`.

### 9) Make indexing sessions crash-safe and resumable (single-writer per repo)

**Why it matters**
- Indexing is the most operationally painful part of KB systems.
- You already persist pending changes; pairing that with strong session semantics eliminates “half indexed” states.

**What to do**
- Enforce one in-flight index per repo (lock + clear error if busy).
- Make session status transitions explicit and recoverable:
  - `running` → `succeeded` / `failed` / `aborted`
  - on startup, detect “stuck running” and mark as aborted with reason
- Add “resume” behavior for queued pending changes after restart.

**Acceptance criteria**
- After a forced kill mid-index, restart processes pending changes and does not corrupt metadata.

### 10) Retrieval tuning workflow: reproducible evals + CI regression gates

**Why it matters**
- The codebase already contains benchmarking/eval pieces; making it *repeatable and enforced* prevents silent regressions.

**What to do**
- Create a small, versioned “golden queries” dataset (checked in) for at least one representative repo fixture.
- Add a CI job that runs:
  - baseline search metrics (MRR/nDCG/Precision@k)
  - latency budgets (p50/p95)
- Require “debug explainability mode” fields (above) so regressions are diagnosable.

**Acceptance criteria**
- PRs that regress a key metric beyond a small threshold fail CI (or require an explicit override).

## Extra Ideas (If We Have Time)

- **Per-repo scoring policy**: configurable boosts/penalties for `tests/`, `vendor/`, generated files, etc., beyond the config-file penalty.
- **Better ANN knobs UX**: expose a small set of “profiles” (speed/accuracy/dev) rather than raw `nprobes/refine_factor` unless `debug=true`.
- **Reranker acceleration**: optional ONNX/quantized cross-encoder path to reduce the “2GB + slower” cost.
- **Storage hygiene commands**: explicit `dolphin kb vacuum`, `dolphin kb compact-vectors`, and retention policies for old sessions.

## MCP Tooling (dolphin-mcp) Improvements

These are suggestions specifically for the **MCP “dolphin” server** UX and ergonomics (not core KB retrieval quality).

### 0.2.1 (Patch) — Higher leverage UX fixes

- **Return snippets by default (small)**: `search` often returns results where `snippet_range.included=false`, forcing a follow-up `file_lines` call for basic inspection. Default to a short snippet (e.g., 3–8 lines) and allow callers to disable it.
- **Fix confusing snippet messaging**: avoid messages like “Showing snippets for top 0/N results” when snippets are disabled by config/params; instead report the reason (e.g., `max_snippets=0`) in `meta`.
- **Output shaping controls**: add `compact=true` and/or `fields=[...]` so callers can request just `{path, start_line, end_line, score, snippet}` to prevent large JSON payloads and truncation in downstream clients.
- **Stable identifiers in responses**: standardize what `chunk_id` represents across the MCP surface (SQL content id vs Lance row id vs FTS id), or return them as separate fields (`content_id`, `vector_id`, `fts_id`) to remove ambiguity.
- **Make followups always “copy/paste runnable”**: `search` already returns `followups`; ensure those followups never get truncated and are complete parameter objects so an agent can execute them verbatim.

### 0.3.0 (Minor) — New capabilities

- **Pagination for `search`**: add `cursor`/`next_cursor` so clients can fetch additional results without rerunning broad queries or re-downloading large payloads.
- **`open_uri` / `open_ref` tool**: accept a returned `kb://…` URI (or `chunk_id`) and return the relevant `file_lines` automatically, reducing glue logic and round-trips.
- **Explicit limit introspection in responses**: include effective snippet/timeout limits in `meta` (e.g., `max_snippets`, `snippet_fetch_timeout_ms`) so clients can adapt behavior without reading docs.
