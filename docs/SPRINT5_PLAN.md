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

## Phase 2 — Medium Priority (P2)

### 2.1 ⬜ Path validation allows symlinks by default
**File**: `kb/api/utils.py:52`
**Effort**: S

**Steps**:
- [ ] Change default from `allow_symlinks=True` to `allow_symlinks=False` in `PathValidator` instantiation
- [ ] Add a config knob `security.allow_symlinks` (default `false`) in `kb/config_template.toml` and `kb/config.py`
- [ ] Wire config value into `PathValidator` construction
- [ ] Add test: symlink pointing outside repo root should be rejected when `allow_symlinks=False`

### 2.2 ⬜ Deduplicator returns empty set on error
**File**: `kb/ingest/dedup.py:27–43`
**Effort**: S

**Steps**:
- [ ] Remove the `except Exception: return set()` fallback
- [ ] Let the exception propagate to the caller (`pipeline.py`)
- [ ] In `pipeline.py`, catch `sqlite3.OperationalError` at the file-processing level and skip the file with an error log + increment `files_error` counter
- [ ] Add unit test: dedup raises on DB error → pipeline skips file and reports error

### 2.3 ⬜ Token estimation is inaccurate
**Files**: `kb/api/app.py:234` and `kb/ingest/async_embedder.py:67`
**Effort**: S

Two inconsistent heuristics: `total_chars / 4.0` (app.py) vs `len(t.split()) * 1.3` (async_embedder.py). tiktoken is already a dependency.

**Steps**:
- [ ] Create a shared utility `kb/utils/tokens.py` with `estimate_tokens(text: str) -> int` using tiktoken (`cl100k_base` encoding)
- [ ] Add a fast-path fallback (`len(text) // 4`) if tiktoken import fails, with a logged warning
- [ ] Replace the heuristic in `app.py:234` with `estimate_tokens()`
- [ ] Replace the heuristic in `async_embedder.py:67` with `estimate_tokens()`
- [ ] Add unit test comparing heuristic vs tiktoken on code samples

### 2.4 ⬜ CHANGELOG version mismatch
**Files**: `pyproject.toml:7` (`0.2.2`) vs `kb/api/app.py:33` (`0.2.1`)
**Effort**: S

**Steps**:
- [ ] In `app.py`, read version dynamically: `from importlib.metadata import version; __version__ = version("pb-dolphin")`
- [ ] Use `__version__` in `FastAPI(version=__version__)`
- [ ] Remove hardcoded version string from `app.py`
- [ ] Verify with `python -c "from kb.api.app import app; print(app.version)"`

### 2.5 ⬜ Cache invalidation failures are swallowed
**File**: `kb/api/app.py:339–347`
**Effort**: S

**Steps**:
- [ ] Change `_log.warning(...)` to `_log.error(..., exc_info=True)` in the cache invalidation except block
- [ ] Add a module-level flag `_cache_invalidation_healthy = True` that flips to `False` on failure
- [ ] Surface this flag in the `/v1/health?check=deep` response (add `"cache_invalidation": "ok" | "degraded"`)
- [ ] Add test: simulate cache invalidation failure → deep health check reports degraded

### 2.6 ⬜ OpenAI API key validation is existence-only
**Files**: `kb/config.py` and `kb/embeddings/provider.py`
**Effort**: S

**Steps**:
- [ ] In `kb/config.py`, add format validation: key must start with `sk-` and be non-empty after strip
- [ ] Log a clear error message if the key is empty string or malformed
- [ ] In `provider.py`, add optional startup validation: a lightweight test embed call with a 1-token string (gated behind a `validate_on_init` flag, default `True`)
- [ ] Catch `openai.AuthenticationError` specifically and surface a clear message
- [ ] Add test: empty string key → config validation fails with descriptive error

### 2.7 ⬜ File lines cached per-request, not shared
**File**: `kb/api/app.py:158`
**Effort**: S

**Steps**:
- [ ] Replace the local `file_lines_cache` dict with a module-level `functools.lru_cache(maxsize=128)` or `cachetools.TTLCache(maxsize=128, ttl=30)`
- [ ] Key on `(file_path, mtime)` to auto-invalidate when the file changes
- [ ] Ensure thread safety (TTLCache is not thread-safe; wrap with `threading.Lock` or use `@lru_cache`)
- [ ] Add a cache-clear hook when reindexing completes

### 2.8 ⬜ LanceDB connection not pooled
**File**: `kb/store/lancedb_store.py:35–50`
**Effort**: S

**Steps**:
- [ ] Research: check LanceDB docs for thread safety of a single connection object (if concurrent reads are safe, this may be a non-issue)
- [ ] If not safe: implement a simple connection pool (similar to `SQLiteConnectionPool`) with configurable `max_connections` (default 4)
- [ ] If safe: document the finding in a code comment and close this item
- [ ] Add a test: concurrent vector lookups don't produce errors or corruption

### 2.9 ⬜ Loki auth disabled
**File**: `observability/loki/loki-config.yml`
**Effort**: S

**Steps**:
- [ ] Add `auth_enabled: true` with env-var override in loki config
- [ ] Add Loki auth credentials to `observability/.env.example`
- [ ] Document the auth setup in `docs/DEPLOYMENT.md` under the observability section
- [ ] Note: for local-only development, auth can remain disabled; gate via environment

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

## Phase 3 — Nice-to-Have (P3)

### 3.1 ⬜ `dolphin search` truncates at 8 lines with no override
**File**: `kb/ingest/cli.py`
**Effort**: S

**Steps**:
- [ ] Add `--max-lines` option to the `search` command (default: current hardcoded value)
- [ ] Pass through to snippet display logic
- [ ] Update `--help` text

### 3.2 ⬜ Config deep-merge has no depth limit
**File**: `kb/config.py` (`_deep_merge`)
**Effort**: S

**Steps**:
- [ ] Add a `_depth` parameter (default 0) and `max_depth` constant (10) to `_deep_merge`
- [ ] Raise `ValueError("Config nesting exceeds max depth")` if exceeded
- [ ] Add test: deeply nested config (11 levels) raises ValueError

### 3.3 ⬜ No application Dockerfile
**Effort**: S

**Steps**:
- [ ] Create `Dockerfile` at repo root with multi-stage build:
  - Stage 1: `python:3.12-slim` + uv + bun for building
  - Stage 2: slim runtime with only production deps
- [ ] Add `HEALTHCHECK` instruction hitting `/v1/health`
- [ ] Run as non-root user (`dolphin`)
- [ ] Add `.dockerignore` (exclude `.git`, `node_modules`, `__pycache__`, `.env`)
- [ ] Document in `docs/DEPLOYMENT.md`

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
