# Dolphin: Improvement Opportunities

A comprehensive audit of code quality, UX, and performance across the Dolphin codebase.
Each section includes priority, effort estimate, and actionable guidance for implementers.

> **Notation**: `P0` = critical/do first, `P1` = high priority, `P2` = medium, `P3` = nice-to-have.
> Effort: `S` = small (< 1 day), `M` = medium (1–3 days), `L` = large (3+ days).
> Status badges: ✅ Done · 🔄 Partial · ⬜ Open

---

## Table of Contents

1. [Code Quality](#1-code-quality)
   - [1.1 Security](#11-security)
   - [1.2 Error Handling](#12-error-handling)
   - [1.3 Module Size & Cohesion](#13-module-size--cohesion)
   - [1.4 Type Safety](#14-type-safety)
   - [1.5 Concurrency & Thread Safety](#15-concurrency--thread-safety)
   - [1.6 Correctness Bugs](#16-correctness-bugs)
2. [UX & Documentation](#2-ux--documentation)
   - [2.1 Developer Onboarding](#21-developer-onboarding)
   - [2.2 CLI Experience](#22-cli-experience)
   - [2.3 Error Messages & Observability](#23-error-messages--observability)
   - [2.4 Configuration](#24-configuration)
3. [Performance](#3-performance)
   - [3.1 Memory](#31-memory)
   - [3.2 Latency](#32-latency)
   - [3.3 Stability & Resource Management](#33-stability--resource-management)
4. [Infrastructure & CI/CD](#4-infrastructure--cicd)
5. [Quickstart for Implementers](#5-quickstart-for-implementers)

---

## 1. Code Quality

### 1.1 Security

#### ✅ P0/S — API key comparison is timing-vulnerable

> **Status**: Done (Sprint 1) — `kb/api/app.py` now uses `hmac.compare_digest()`.

**File**: `kb/api/app.py:108`

```python
if not api_key or api_key != expected_key:
```

Direct string comparison leaks timing information. Replace with:

```python
import hmac
if not api_key or not hmac.compare_digest(api_key, expected_key or ""):
```

Also missing:

- **Rate limiting** on failed auth attempts (brute-force is trivial).
- **Audit logging** of 401s (no record of who tried what).

#### ✅ P1/S — Foreign key pragma silently swallowed

> **Status**: Done (Sprint 1) — now logs at `error` level with `exc_info=True` and re-raises.

**File**: `kb/store/sqlite_meta.py:151–154`

```python
try:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
except Exception:
    pass  # FK enforcement silently disabled
```

If this fails, the entire referential integrity layer is gone — orphaned chunks, dangling file references, etc.
Fix: log at `error` level and raise; the database is not trustworthy without FK enforcement.

#### ✅ P1/S — CORS allows credentials with wildcard methods

> **Status**: Done (Sprint 1) — tightened to `["GET", "POST", "DELETE", "OPTIONS"]` and `["X-API-Key", "Content-Type", "Accept"]`.

**File**: `kb/api/app.py:80–88`

`allow_credentials=True` combined with `allow_methods=["*"]` and `allow_headers=["*"]` is overly permissive even for `localhost:3000`. Tighten to specific methods (`GET`, `POST`, `DELETE`) and specific headers (`X-API-Key`, `Content-Type`).

#### ⬜ P2/S — Path validation allows symlinks by default

**File**: `kb/api/utils.py:52`

```python
validator = PathValidator(base_dir=repo_root, allow_symlinks=True)
```

Symlinks can escape the repo root. Consider `allow_symlinks=False` as the default, with an opt-in flag for repos that need it.

---

### 1.2 Error Handling

#### 🔄 P1/M — 171 bare `except Exception` handlers across 36 files

> **Status**: Phase 1 done (Sprint 2) — all bare handlers in the top offending files now log with
> `exc_info=True`. Phase 2 (narrow to specific exception types) and Phase 3 (defensive decorator)
> remain open.

The single largest code quality issue. Breakdown of the top offenders:

| File                        | Count | Impact                         |
| --------------------------- | ----- | ------------------------------ |
| `kb/store/lancedb_store.py` | 26    | Vector ops silently fail       |
| `kb/api/app.py`             | 24    | Request-level failures hidden  |
| `kb/ingest/pipeline.py`     | 12    | Indexing errors swallowed      |
| `kb/store/sqlite_meta.py`   | 11    | DB integrity issues masked     |
| `kb/ingest/watcher.py`      | 9     | File-watch failures undetected |
| `kb/ingest/cli.py`          | 9     | CLI errors lost                |

**Recommended approach** (incremental, not big-bang):

1. ✅ **Phase 1**: Add `_log.warning(...)` with `exc_info=True` to every bare handler that currently does `pass`, `continue`, or `return None`. This is a mechanical change.
2. ⬜ **Phase 2**: Replace the most impactful catch-alls (LanceDB, SQLite, pipeline) with specific exception types (`lancedb.LanceDBError`, `sqlite3.OperationalError`, etc.).
3. ⬜ **Phase 3**: Introduce a `@defensive` decorator or context manager for the intentionally-broad handlers, making the intent explicit.

#### ⬜ P2/S — Deduplicator returns empty set on error, causing re-embedding

**File**: `kb/ingest/dedup.py:27–43`

When the SQLite hash lookup fails, the fallback is `set()` — meaning every chunk is treated as new, re-embedded, and re-stored. This is wasteful and can cause duplicate vectors. Better to propagate the error and let the pipeline retry or skip the file.

---

### 1.3 Module Size & Cohesion

Several modules have grown past the point of easy comprehension:

| File                       | Lines | Concern                                                     |
| -------------------------- | ----- | ----------------------------------------------------------- |
| `kb/store/sqlite_meta.py`  | 3,073 | Metadata, FTS, sessions, snapshots, migrations — everything |
| `kb/api/app.py`            | 1,862 | Routes, enrichment, indexing logic, task processing         |
| `kb/ingest/pipeline.py`    | 1,499 | Scanning, chunking, embedding, graph extraction             |
| `kb/api/search_backend.py` | 1,338 | Search orchestration, caching, BM25, vector search          |
| `kb/ingest/cli.py`         | 986   | CLI commands with business logic interleaved                |

**Suggested decompositions**:

- **`sqlite_meta.py`** → split into `sqlite_meta.py` (CRUD), `fts_index.py` (FTS5 ops), `session_manager.py` (indexing sessions), `snapshot_store.py` (file snapshots).
- **`app.py`** → extract `_process_index_task` and snippet enrichment into `kb/api/indexing.py` and `kb/api/snippets.py`. Keep routes thin.
- **`pipeline.py`** → the graph extraction helpers are already partly in `graph_helpers.py`; move the remaining orchestration into smaller stage functions.

Priority: **P2/L** — do this opportunistically when touching these files, not as a standalone refactor.

---

### 1.4 Type Safety

- **158 uses of `Any`** across 25 files. The worst offenders: `cache.py` (17), `structured_logger.py` (16), `rankers.py` (14), `sqlite_meta.py` (21).
- **17 `# type: ignore` comments**, most without justification. The `provider.py:255,316` ignores hide a real mismatch between declared return types and actual returns.
- Search backend uses a `Protocol` class but the return-type contract is loose — `search()` may return `list[dict]`, `dict` with a `"hits"` key, or a `tuple`. Callers (app.py:559–570) must handle all three.

**Recommendation** (P2/M): Define a `SearchResult` dataclass as the canonical return type, and have all backends conform. Eliminate the tuple/dict polymorphism.

> **Status**: Done (Sprint 4) — `SearchResultSet(NamedTuple)` with `hits` and `next_cursor` fields defined in `app.py`; `SearchBackend` Protocol updated; `_EmptySearchBackend` and `KnowledgeSearchBackend` both return `SearchResultSet`. Supports tuple unpacking for backward compatibility.

---

### 1.5 Concurrency & Thread Safety

#### ⬜ P1/S — Global mutable state without locks

**File**: `kb/api/app.py:114–150`

```python
_sql_store = None
_lance_store = None
_pipeline = None
```

These module-level globals are mutated by `set_stores()` / `set_pipeline()` and read by every request handler. FastAPI runs on an async event loop, but `asyncio.to_thread()` calls and background tasks introduce real concurrency. A `threading.Lock` (or using FastAPI's dependency injection with `Depends`) would be safer.

#### ✅ P2/S — Rate limiter lists grow unbounded

> **Status**: Done (Sprint 3) — both tracking collections are now `deque(maxlen=initial_rpm)`; `_enforce_limits` uses `popleft()` for O(k) pruning instead of O(n) list-comprehension reassignment.

**File**: `kb/ingest/async_embedder.py:57–58`

```python
self.request_times: list[float] = []
self.token_usage: list[tuple[float, float]] = []
```

These rolling-window lists are appended to on every request but pruning only happens inside `_enforce_limits()`. If the pruning window is large or the load is bursty, these can grow significantly. Use `collections.deque(maxlen=...)` instead.

---

### 1.6 Correctness Bugs

#### ✅ P1/S — Snippet truncation is a no-op

> **Status**: Done (Sprint 1) — truncation now implemented: match text has first priority on the
> token budget, remaining budget is split evenly between context_before/context_after.

**File**: `kb/api/app.py:236–242`

```python
if estimated_tokens > max_tokens:
    truncated = True
    pass  # Returns full content despite truncation flag!
```

The `truncated` flag is set but the content is never actually truncated. Downstream consumers (MCP clients, CLI) that trust this flag will receive unexpectedly large payloads. Either implement the truncation or remove the flag.

#### ⬜ P2/S — Token estimation is inaccurate

**Files**: `kb/api/app.py:234` and `kb/ingest/async_embedder.py:67`

Two different estimation heuristics:

- `total_chars / 4.0` (app.py — character-based)
- `len(t.split()) * 1.3` (async_embedder.py — word-based)

Both undercount for code (punctuation, camelCase, symbols). Since tiktoken is already a dependency (mocked in tests), use it for accurate counts where precision matters (rate limiting, snippet truncation).

---

## 2. UX & Documentation

### 2.1 Developer Onboarding

#### ✅ P1/S — No `.env.example` file

> **Status**: Done (Sprint 2) — `.env.example` created at repo root with all documented env vars.

New contributors must read source code to discover which environment variables exist. Create a `.env.example`:

```bash
# Required for embedding operations
OPENAI_API_KEY=sk-your-key-here

# Optional: override auto-generated API key
# DOLPHIN_API_KEY=

# Optional: override config location
# DOLPHIN_CONFIG_PATH=

# Logging
# DOLPHIN_LOG_LEVEL=INFO
# DOLPHIN_LOG_TRACEBACK=0

# Watcher timeouts
# DOLPHIN_WATCH_SHUTDOWN_TIMEOUT=15
# DOLPHIN_WATCH_CANCEL_TIMEOUT=5

# BM25 tuning
# DOLPHIN_BM25_STATS_PATH=
# DOLPHIN_FORCE_BM25_NORMALIZER=
```

#### ✅ P2/S — No production deployment guide

> **Status**: Done (Sprint 4) — `docs/DEPLOYMENT.md` created covering reverse proxy (nginx/Caddy), process management (systemd/launchd), TLS, auth hardening, Redis configuration, and observability stack setup.

`README.md` covers local development. There's no guide for deploying Dolphin as a shared service (reverse proxy setup, process management, TLS, auth hardening, Redis configuration). A `docs/DEPLOYMENT.md` would prevent each team from reinventing this.

#### ⬜ P2/S — CHANGELOG version mismatch

`pyproject.toml` says `0.2.2`, `FastAPI(version="0.2.1")` in `app.py:30`. These should stay in sync — ideally generated from a single source of truth.

---

### 2.2 CLI Experience

#### ✅ P2/S — Silent failures during `dolphin index`

> **Status**: Done (Sprint 4) — pipeline now tracks `files_skipped_ignored` and `files_error` counters; both sequential and parallel modes print a summary; `cli.py` formats a friendly one-liner: `"Indexed N files (X chunks). Skipped: Y ignored, Z errors."`.

When files are skipped (binary, ignored, permission error), the CLI provides no summary. Add a post-index summary:

```
Indexed 142 files (3,201 chunks). Skipped: 12 binary, 3 ignored, 1 error.
```

#### ⬜ P3/S — `dolphin search` truncates at 8 lines with no override

The `MAX_SNIPPET_LINES = 8` constant in `cli.py` is hardcoded. Add a `--max-lines` flag for power users who want more context.

---

### 2.3 Error Messages & Observability

#### ✅ P1/S — Silent reranker degradation

> **Status**: Done (Sprint 2) — `cross_encoder_rerank.py` stores `load_error` when the model fails
> to load; `dolphin status` shows reranking state; search responses include a `warnings` field when
> reranking is configured but unavailable.

**File**: `kb/retrieval/cross_encoder_rerank.py:52–65`

If the cross-encoder model fails to load, reranking is silently disabled (`self.enabled = False`). The user ran `uv pip install "pb-dolphin[reranking]"` explicitly for this. Surface a warning in `dolphin status` and in search responses (e.g., a `warnings` field).

#### ⬜ P2/S — Cache invalidation failures are swallowed

**File**: `kb/api/app.py:339–347`

Failed cache invalidation means stale results are served after reindex. At minimum, log at `error` level (not `warning`) and include it in the `/v1/health?check=deep` response.

---

### 2.4 Configuration

#### ⬜ P2/S — OpenAI API key validation is existence-only

**File**: `kb/config.py` (config check) and `kb/embeddings/provider.py`

The key is checked with `os.environ.get(...)` — an empty string passes. The provider creates both sync and async OpenAI clients but never validates the key until the first API call, which may happen minutes later during indexing. Add a lightweight validation at startup (format check + a test embed call with a short string).

#### ⬜ P3/S — Config deep-merge has no depth limit

**File**: `kb/config.py` (`_deep_merge`)

Recursive merge with no depth limit. Not a practical issue today, but a malformed config could cause a stack overflow. Cap at a reasonable depth (e.g., 10).

---

## 3. Performance

### 3.1 Memory

#### ✅ P1/M — In-memory cache has no size bound

> **Status**: Done (Sprint 2) — `QueryCache` now accepts `max_memory_entries` (default 10,000).
> `_evict_memory_cache()` runs a two-phase eviction: first removes expired entries, then trims
> soonest-to-expire entries until at 90 % of capacity.

**File**: `kb/cache/cache.py:55–58`

```python
self._memory_cache: dict[str, tuple[Any, float]] = {}
self._repo_index: dict[str, set[str]] = {}
self._key_repos: dict[str, set[str]] = {}
```

When Redis is unavailable (the default for most local users), all cache entries live in unbounded dicts. A long-running `dolphin serve` with many queries will leak memory indefinitely. The `_repo_index` and `_key_repos` dicts never expire entries — TTL is only checked on read for values.

**Fix**: Use `functools.lru_cache` or a bounded LRU dict (e.g., `cachetools.TTLCache`). Add a `max_memory_entries` config knob with a sensible default (e.g., 10,000).

#### ✅ P2/S — Both sync and async OpenAI clients instantiated

> **Status**: Done (Sprint 3) — clients are now created on first use via `_get_client()` / `_get_async_client()`; only the path actually exercised (sync CLI or async API server) ever allocates a client.

**File**: `kb/embeddings/provider.py`

The `OpenAIEmbeddingProvider` creates both `self.client` and `self.async_client` at init time. If only one path is used (typical for CLI = sync, API = async), the other is wasted memory and connections.
Lazy-initialize each on first use.

#### ⬜ P2/S — File lines cached per-request, not shared

**File**: `kb/api/app.py:158`

`file_lines_cache` is a local dict scoped to each call of `_enrich_hits_with_snippets`. If the same file appears in multiple search requests within a short window, it's re-read each time. Consider a short-lived module-level LRU cache (TTL ~30s) for hot files.

---

### 3.2 Latency

#### ✅ P2/M — Search fallback chain adds unnecessary overhead

> **Status**: Done (Sprint 3) — `_make_search_fn()` resolves the callable once when `set_search_backend()` is called; `search()` now makes a single `await search_fn(request)` call.

**File**: `kb/api/app.py:420–475`

The search dispatch logic tries `search_async`, then `search`, then `asyncio.to_thread(search)`, then checks `isawaitable()` on the result. This four-step dispatch runs on every request. Since the backend type is known at startup, resolve the dispatch once during initialization and store a single callable.

#### ⬜ P2/S — LanceDB connection not pooled

**File**: `kb/store/lancedb_store.py:35–50`

A single cached connection is shared. For concurrent requests this serializes vector lookups. Investigate whether LanceDB supports connection pooling or if concurrent access on the same connection is safe. If not, implement a connection pool similar to `SQLiteConnectionPool`.

#### ⬜ P3/S — Token estimation heuristic in rate limiter

**File**: `kb/ingest/async_embedder.py:67`

```python
est_tokens = sum(len(t.split()) * 1.3 for t in texts)
```

Underestimates tokens for code (which has many symbols). This causes the rate limiter to under-count usage, leading to unexpected 429s from OpenAI followed by backoffs. Use tiktoken for accurate counts in the rate-limiting path (it's already a dependency).

---

### 3.3 Stability & Resource Management

#### ✅ P1/S — Server startup crashes if backend init fails

> **Status**: Done (Sprint 3) — lifespan now catches all `Exception` types, logs at `error` level with `exc_info=True`, prints a clear failure message, and re-raises so the server process exits cleanly instead of crashing with a raw traceback.

**File**: `kb/api/server.py` (startup lifespan)

`initialize_search_backend()` can raise on startup. There's no try/except wrapping the lifespan startup, so the entire server process dies. Wrap in a try/except, log the error, and start in a degraded mode (health check reports unhealthy, search returns 503).

#### ⬜ P2/S — Watcher thread pool executor never fully awaited

**File**: `kb/ingest/watcher.py:48`

```python
self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
```

On shutdown, `_executor.shutdown(wait=True)` should be called. If the watcher is stopped abruptly, in-flight indexing tasks may be interrupted mid-write, leaving partial state in SQLite and LanceDB.

#### ✅ P3/S — SQLite transaction boundaries worth auditing

> **Status**: Done (Sprint 3) — `rebuild_fts5_table` now uses a single `BEGIN IMMEDIATE`/`COMMIT` to make DROP + CREATE atomic (requires `isolation_level=None` to suppress Python's DDL auto-commit); `sync_locations_for_content_row`, `prune_invalidated_content_for_file`, and `ensure_content_rows_for_file` open with explicit `BEGIN IMMEDIATE` for deterministic isolation across all Python sqlite3 versions.

**File**: `kb/store/sqlite_meta.py` (throughout)

The code pattern is `with self._connect() as conn` (the connection pool's context manager) — this yields the raw `sqlite3.Connection` and releases it back to the pool, but does **not** invoke `sqlite3.Connection` as a context manager, which is what provides automatic `BEGIN`/`COMMIT`/`ROLLBACK`. Python's `sqlite3` module does provide implicit transactions for DML in its default isolation mode, but this is a global per-connection setting rather than an explicit per-operation guarantee. For any method that executes multiple write statements that must be atomic, it is worth auditing whether the implicit transaction boundaries are sufficient or whether an explicit `BEGIN`/`COMMIT` block would make the intent clearer and the behaviour more robust.

---

## 4. Infrastructure & CI/CD

#### ✅ P1/S — Docker images use `:latest` tags

> **Status**: Done (Sprint 1) — all five services pinned to specific versions in
> `observability/docker-compose.yml`.

**File**: `observability/docker-compose.yml`

All five services (Prometheus, Jaeger, Loki, Promtail, Grafana) use `:latest`. Pin to specific versions for reproducible deployments.

#### ✅ P1/S — Grafana default credentials hardcoded

> **Status**: Done (Sprint 1) — credentials moved to `${VAR:?error}` env-var syntax; an
> `observability/.env.example` documents the required vars.

**File**: `observability/docker-compose.yml:85–86`

```yaml
GF_SECURITY_ADMIN_USER: admin
GF_SECURITY_ADMIN_PASSWORD: admin
```

Move to environment variables or a `.env` file excluded from version control.

#### ⬜ P2/S — Loki auth disabled

**File**: `observability/loki/loki-config.yml`

`auth_enabled: false` means anyone with network access to port 3100 can read application logs. Enable auth for anything beyond local development.

#### ✅ P2/S — Known CVE acknowledged but undocumented

> **Status**: Done (Sprint 2) — `docs/SECURITY_EXCEPTIONS.md` created, documenting CVE-2026-0994
> and GHSA-7gcm-g887-7qv7 with rationale, upstream status, accepted risk, and re-evaluation dates.

**File**: `.github/workflows/security-scan.yml:28`

`CVE-2026-0994` (protobuf DoS, confirmed in `.github/workflows/security-scan.yml:26`) and `GHSA-7gcm-g887-7qv7` are ignored in CI. The workflow already has an inline comment for the protobuf CVE; neither exception has a dedicated rationale document. Add a `docs/SECURITY_EXCEPTIONS.md` that records the advisory, the upstream status, the accepted risk, and a target date for re-evaluation.

#### ⬜ P3/S — No application Dockerfile

There's no Dockerfile for the Dolphin application itself — only for the observability stack. For teams wanting to deploy Dolphin as a container, provide a multi-stage Dockerfile with:

1. A build stage (uv + bun)
2. A slim runtime stage
3. Health check instruction
4. Non-root user

---

## 5. Quickstart for Implementers

### Where to start

The improvements above are ordered by priority within each section. Here's a suggested attack plan:

#### ✅ Sprint 1: Security & Correctness — Complete

1. ✅ `kb/api/app.py:108` — Replace string comparison with `hmac.compare_digest()`.
2. ✅ `kb/store/sqlite_meta.py:151–154` — Log + raise on FK pragma failure.
3. ✅ `kb/api/app.py:236–242` — Implement actual snippet truncation.
4. ✅ `kb/api/app.py:80–88` — Tighten CORS to specific methods/headers.
5. ✅ `observability/docker-compose.yml` — Pin image versions, externalize Grafana credentials.

#### ✅ Sprint 2: Observability & Error Handling — Complete

1. ✅ Audit bare `except Exception` handlers — Phase 1 done: all top-file handlers now log with `exc_info=True`; `print()` calls in `graph_helpers.py` and `lancedb_store.py` converted to `_log.warning()`.
2. ✅ `kb/retrieval/cross_encoder_rerank.py` — `load_error` attribute added; reranker status surfaced in `dolphin status` and search response `warnings`.
3. ✅ `kb/cache/cache.py` — Bounded size (`max_memory_entries=10_000`) with two-phase TTL eviction.
4. ✅ Create `.env.example` at repo root.
5. ✅ `docs/SECURITY_EXCEPTIONS.md` — CVE-2026-0994 and GHSA-7gcm-g887-7qv7 documented.

#### ✅ Sprint 3: Performance & Stability — Complete

1. ✅ `kb/api/server.py` — Startup now catches all `Exception` types after `FileNotFoundError`; logs at `error` level with full traceback and re-raises so the server exits cleanly with a clear message instead of crashing mid-traceback or silently starting broken.
2. ✅ `kb/api/app.py` — `_make_search_fn()` resolves the dispatch strategy once when `set_search_backend()` is called; `search()` uses the cached callable instead of a four-step per-request probe.
3. ✅ `kb/embeddings/provider.py` — `OpenAIEmbeddingProvider` defers client creation to first use via `_get_client()` / `_get_async_client()`; only the path actually taken (sync CLI or async API) ever allocates a client.
4. ✅ `kb/ingest/async_embedder.py` — `request_times` and `token_usage` are now `deque(maxlen=initial_rpm)`; `_enforce_limits` uses `popleft()` instead of list-comprehension reassignment, preserving the deque and its bound.
5. ✅ `kb/store/sqlite_meta.py` — `rebuild_fts5_table` wraps DROP + CREATE in a single `BEGIN IMMEDIATE` / `COMMIT` transaction (using `isolation_level=None` to bypass Python's DDL auto-commit); `sync_locations_for_content_row`, `prune_invalidated_content_for_file`, and `ensure_content_rows_for_file` open with explicit `BEGIN IMMEDIATE` for deterministic isolation.

#### ✅ Sprint 4: Architecture & UX — Complete

1. ⬜ Begin decomposing `sqlite_meta.py` (3,073 lines) as it's touched for new features.
2. ✅ Standardize search return type to a `SearchResult` dataclass.
3. ✅ Improve CLI post-index summaries with skip/error counts.
4. ✅ Write `docs/DEPLOYMENT.md` for production use.

### Conventions for new code

When implementing fixes:

- **Error handling**: Catch the most specific exception possible. If you must catch `Exception`, add a comment explaining why and always log with `exc_info=True`.
- **Type safety**: Avoid `Any` — use `TypedDict`, dataclasses, or Pydantic models. If a `# type: ignore` is needed, suffix it with a reason: `# type: ignore[arg-type] — lancedb returns untyped`.
- **Testing**: Every bug fix should have a regression test. The project uses `pytest` with markers (`unit`, `integration`, `e2e`). Minimum coverage is 75%.
- **Config changes**: Add new settings to `kb/config_template.toml` and the relevant `@dataclass` in `kb/config.py`. Never hardcode values that a user might want to tune.

### Key file map

| Area                 | Primary File                | Lines | Notes                  |
| -------------------- | --------------------------- | ----- | ---------------------- |
| API routes           | `kb/api/app.py`             | 1,862 | Needs decomposition    |
| Search orchestration | `kb/api/search_backend.py`  | 1,338 | Complex async dispatch |
| SQLite metadata      | `kb/store/sqlite_meta.py`   | 3,073 | Largest module         |
| Vector store         | `kb/store/lancedb_store.py` | 632   | Bare exceptions logged |
| Ingestion pipeline   | `kb/ingest/pipeline.py`     | 1,499 | Core indexing flow     |
| Configuration        | `kb/config.py`              | 474   | Dataclass-based        |
| Caching              | `kb/cache/cache.py`         | 481   | Bounded in-memory      |
| Embeddings           | `kb/embeddings/provider.py` | ~320  | OpenAI + stub          |
| CLI                  | `kb/ingest/cli.py`          | 986   | User-facing entry      |
| File watcher         | `kb/ingest/watcher.py`      | ~400  | Async + threading      |

### Running checks

```bash
# Lint + format
python -m ruff check . && python -m ruff format --check .

# Unit tests
just test unit

# Full suite (requires OPENAI_API_KEY + Redis)
just test-full

# Coverage (75% minimum)
just test-cov
```
