# Sprint 5: Remaining Improvements — Implementation Plan

All outstanding items from `docs/IMPROVEMENTS.md`, grouped into phases by priority and dependency.
Items verified against current codebase state as of 2026-02-22.

> **Note**: The watcher executor shutdown (§3.3 P2/S) was listed as open but is already
> implemented — `_shutdown_executor()` calls `shutdown(wait=True, cancel_futures=True)`
> in a `finally` block. Marked as done below.

---

## Phase 1 — High Priority (P1) ✅ COMPLETE

### 1.1 ✅ Global mutable state without locks
**File**: `kb/api/app.py:114–150`

- [x] Added `import threading` and `_store_lock = threading.Lock()`
- [x] Wrapped `set_stores()`, `set_pipeline()`, `reset_pipeline()`, `reset_stores()` with `with _store_lock:`
- [x] Reads remain unlocked (occur post-startup on async event loop only)

### 1.2 ✅ Bare `except Exception` handlers — Phase 2
**Files**: `sqlite_meta.py`, `watcher.py`, `cli.py`, `pipeline.py`

Audit (64 total handlers across 6 key files):

| File | Handlers | Status |
|------|----------|--------|
| `lancedb_store.py` | 11 | ✅ Already Phase 2 ready |
| `app.py` | 12 | ✅ Already Phase 2 ready |
| `pipeline.py` | 14 | ✅ Fixed — 3 `print()` in except blocks → `logger.warning/error(..., exc_info=True)` |
| `sqlite_meta.py` | 14 | ✅ Fixed — 4 silent handlers now log with `logger.error(..., exc_info=True)` |
| `watcher.py` | 5 | ✅ Fixed — 3 handlers missing `exc_info=True` corrected |
| `cli.py` | 8 | ✅ Fixed — 3 handlers now log with `_log.error/warning(..., exc_info=True)` |

- [x] **sqlite_meta.py**: Added `logger.error(..., exc_info=True)` to handlers at lines ~2254, ~2512, ~2575, ~2868 (line ~1659 already re-raises correctly)
- [x] **watcher.py**: Added `exc_info=True` to handlers at lines ~86, ~100, ~184
- [x] **cli.py**: Added `_log.error/warning(..., exc_info=True)` at lines ~170, ~607, ~990
- [x] **pipeline.py**: Replaced `print()` in except blocks at lines ~253, ~262, ~346 with `logger.warning/error(..., exc_info=True)`

### 1.3 ✅ Bare `except Exception` handlers — Phase 3
**New file**: `kb/utils/defensive.py`

- [x] Created `kb/utils/__init__.py` and `kb/utils/defensive.py`
- [x] `defensive` works as both a function decorator (`@defensive(fallback=[], log_level="warning")`) and context manager (`with defensive(label="x"):`)
- [x] Always logs with `exc_info=True`; never swallows `KeyboardInterrupt` or `SystemExit`
- [x] Configurable: `fallback`, `log_level`, `label`, `logger`

---

## Phase 2 — Medium Priority (P2) ✅ COMPLETE

### 2.1 ✅ Path validation allows symlinks by default
**File**: `kb/api/utils.py:52`

- [x] Changed `allow_symlinks=True` → `allow_symlinks=False` in `validate_path_within_repo`
- [x] All symlinks now rejected regardless of target — eliminates symlink-race/TOCTOU vectors
- [x] Updated `test_accept_symlink_within_repo` → `test_reject_symlink_within_repo` with 403 assertion

### 2.2 ✅ Deduplicator returns empty set on error
**File**: `kb/ingest/dedup.py:27–43`

- [x] Removed `except Exception: return set()` — exceptions now propagate
- [x] `pipeline.py` parallel path catches dedup errors, increments `files_error`, and continues
- [x] Updated `test_hash_computation_failure_fallback` → `test_hash_computation_failure_propagates`

### 2.3 ✅ Token estimation is inaccurate
**Files**: `kb/api/app.py:234` and `kb/ingest/async_embedder.py:67`

- [x] Created `kb/utils/tokens.py` with `estimate_tokens()` / `estimate_tokens_batch()` (tiktoken `cl100k_base`, graceful fallback)
- [x] Replaced `total_chars / 4.0` in `app.py` with `estimate_tokens(combined_text)`
- [x] Replaced `len(t.split()) * 1.3` in `async_embedder.py` with `estimate_tokens_batch(texts)`

### 2.4 ✅ CHANGELOG version mismatch
**Files**: `pyproject.toml:7` vs `kb/api/app.py:33`

- [x] `app.py` now reads version via `importlib.metadata.version("pb-dolphin")` at import time
- [x] Falls back to `"0.0.0"` if package metadata is unavailable
- [x] Hardcoded `"0.2.1"` string removed

### 2.5 ✅ Cache invalidation failures are swallowed
**File**: `kb/api/app.py:339–347`

- [x] Logging changed from `_log.warning` → `_log.error(..., exc_info=True)`
- [x] Added `_cache_invalidation_healthy: bool = True` module-level flag
- [x] Deep health check now includes `"cache_invalidation"` key and returns `"degraded"` if flag is False

### 2.6 ✅ OpenAI API key validation is existence-only
**Files**: `kb/config.py` and `kb/embeddings/provider.py`

- [x] Format check added: key must start with `"sk-"` and be ≥ 20 characters
- [x] `_validate_api_key()` makes a real test call at startup (gated by `validate_key=True`)
- [x] All test keys updated to `"sk-test-key-1234567890"` format; `validate_key=False` used in unit tests

### 2.7 ✅ File lines cached per-request, not shared
**File**: `kb/api/app.py:158`

- [x] Module-level `_FILE_LINES_CACHE: dict[tuple[str, float], list[str]]` with `_FILE_LINES_CACHE_MAX = 256`
- [x] Keyed on `(path_str, mtime)` — stale files invalidated automatically
- [x] FIFO eviction when capacity reached; `_read_file_lines()` helper used by `_enrich_hits_with_snippets`

### 2.8 ✅ LanceDB connection not pooled
**File**: `kb/store/lancedb_store.py:35–50`

- [x] Researched: Lance format supports safe concurrent reads on a single connection
- [x] Implemented double-checked locking (`_connect_lock = threading.Lock()`) for thread-safe lazy init
- [x] Full connection pool not required; finding documented in code comment

### 2.9 🔄 Loki auth disabled
**File**: `observability/loki/loki-config.yml`

- [x] Added explanatory comment: `auth_enabled: false` is intentional for local development only
- [x] Comment includes instructions to enable auth for production (coordinate with Promtail + Grafana)
- [x] `docs/DEPLOYMENT.md` covers production observability hardening

### 2.10 ⬜ sqlite_meta.py decomposition (opportunistic)
**File**: `kb/store/sqlite_meta.py` (3,073 lines)
**Effort**: L

Not a standalone task — do incrementally as these areas are touched.

**Planned splits**:
- [ ] Extract FTS5 operations → `kb/store/fts_index.py`
- [ ] Extract indexing session management → `kb/store/session_manager.py`
- [ ] Extract file snapshot logic → `kb/store/snapshot_store.py`
- [ ] Keep core CRUD in `sqlite_meta.py`
- [ ] Ensure all imports/references updated across codebase
- [ ] Run full test suite after each extraction

---

## Phase 3 — Nice-to-Have (P3) ✅ COMPLETE

### 3.1 ✅ `dolphin search` truncates at 8 lines with no override
**File**: `kb/cli.py`

- [x] Added `--max-lines` option to `search` command (default: `MAX_SNIPPET_LINES_DISPLAY = 8`)
- [x] `_display_results` accepts `max_lines` parameter; guards against `< 1` via `max(1, max_lines)` at call site
- [x] Module-level constant retained as the default; `--help` documents the default value

### 3.2 ✅ Config deep-merge has no depth limit
**File**: `kb/config.py` (`_deep_merge`)

- [x] Added `_DEEP_MERGE_MAX_DEPTH = 10` constant and `_depth: int = 0` parameter
- [x] Raises `ValueError` with a clear message if `_depth >= 10`
- [x] Recursive calls increment `_depth + 1`

### 3.3 ✅ No application Dockerfile
**Files**: `Dockerfile`, `.dockerignore`

- [x] Two-stage build: `builder` stage installs deps with uv into `.venv`; `runtime` stage copies `.venv` into slim image
- [x] `HEALTHCHECK` calls `/v1/health` via `urllib.request` (no curl dependency)
- [x] Runs as non-root `dolphin` user; data volume at `/data/store`
- [x] `.dockerignore` excludes `.git`, `node_modules`, `tests/`, `__pycache__`, `.env*`, `observability/`

---

## Execution Order

```
Phase 1 (do first — correctness & safety)
  1.1  Global state locks             → kb/api/app.py
  1.2  Exception handler Phase 2      → 6 files
  1.3  @defensive decorator           → new kb/utils/defensive.py

Phase 2 (do next — quality & reliability)
  2.4  Version mismatch fix           → app.py, pyproject.toml (quick win)
  2.2  Dedup error propagation        → dedup.py, pipeline.py
  2.3  Token estimation (tiktoken)    → new kb/utils/tokens.py, app.py, async_embedder.py
  2.5  Cache invalidation logging     → app.py
  2.6  API key validation             → config.py, provider.py
  2.1  Symlink path validation        → utils.py, config.py
  2.7  File lines shared cache        → app.py
  2.8  LanceDB connection pooling     → lancedb_store.py (research first)
  2.9  Loki auth                      → observability/loki-config.yml
  2.10 sqlite_meta decomposition      → ongoing, opportunistic

Phase 3 (when convenient)
  3.1  --max-lines CLI flag           → cli.py
  3.2  Deep-merge depth limit         → config.py
  3.3  Application Dockerfile         → new Dockerfile
```

---

## Items Confirmed Done (can be closed in IMPROVEMENTS.md)

| Item | Status |
|------|--------|
| ⬜ P2/S — Watcher thread pool executor never fully awaited | ✅ Already implemented: `_shutdown_executor()` with `shutdown(wait=True, cancel_futures=True)` in `finally` block |
