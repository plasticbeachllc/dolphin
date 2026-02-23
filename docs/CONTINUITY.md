# Plan: Graceful Ctrl-C Shutdown + Resume-on-Restart for Indexing

## Context

When a user presses Ctrl-C during `dolphin index`, the pipeline catches `KeyboardInterrupt`, marks the session "aborted", and re-raises — producing a traceback. On re-run, the pipeline starts over from scratch because it only looks at the last **succeeded** session. Files already indexed in the aborted run are re-processed unnecessarily.

**Goal**: Ctrl-C finishes the current file, saves progress, exits cleanly (no traceback). Re-running resumes from where it left off.

## Approach

Two mechanisms:

1. **Cooperative cancellation via SIGINT handler** — A signal handler sets a `threading.Event` flag instead of raising `KeyboardInterrupt`. The file-processing loop checks the flag between files and breaks cleanly. A second Ctrl-C force-quits.

2. **Per-file checkpoint via `files.latest_commit_sha`** — After each file completes, stamp it with the session's commit SHA using the existing `set_file_latest_commit()` method (sqlite_meta.py:1057). On resume, skip files already stamped with the current HEAD. No schema changes needed.

Session stays `status='aborted'` (terminal state, so `begin_session()` won't block). The `notes` field distinguishes resumable interrupts from crashes.

## Files to Modify

### 1. `kb/ingest/pipeline.py` (primary changes)

**A. Add cancellation infrastructure to `IngestionPipeline`**

In `__post_init__` (line 62), initialize:
```python
self._cancel_requested = threading.Event()
self._original_sigint = None
```

Add two methods:
- `_install_sigint_handler()` — saves current handler, installs one that sets `_cancel_requested` on first Ctrl-C and raises `KeyboardInterrupt` on second
- `_restore_sigint_handler()` — restores original handler

**B. Modify `process_files()` (line 474)**

- Check `self._cancel_requested.is_set()` at the top of `for path in files:` loop — break if set
- After each file completes successfully (after line 691), call `self.metadata.set_file_latest_commit(repo_id, path, commit_sha)` when not dry_run

**C. Modify `index()` (lines 850-1012)**

- Install/restore SIGINT handler around the try block
- After `process_files()` returns (line 884), check `_cancel_requested`:
  - If set: bump session counters with partial progress, set status to `"aborted"` with `notes="interrupted:resumable"`, print clean summary with "run again to resume" message, return result dict with `"interrupted": True`
  - Skip deletions, pruning, and success path
- After computing `changed_files` (line 864), add resume filtering:
  ```python
  already_done = self.metadata.get_files_with_commit_sha(repo_id, commit_sha)
  changed_files = [f for f in changed_files if f not in already_done]
  ```
  Print count of skipped files if resuming
- Replace the existing `except KeyboardInterrupt` (line 1007) — this now only fires on force-quit (second Ctrl-C)

**D. Modify `_setup_parallel_session()` (lines 1101-1118)**

- Same resume filtering after computing `changed_files`: filter out files already stamped with `commit_sha`

**E. Modify `index_parallel()` (lines 1134-1568)**

- Install/restore SIGINT handler
- Check `_cancel_requested` at top of batch loop (line 1203, `for i in range(...)`)
- After each file fully persists (after line 1486), call `set_file_latest_commit`
- After batch loop, check `_cancel_requested` and handle partial-progress save (same as sync)
- Move session counter update + success status inside the try block (currently at lines 1509-1520, outside `except`), so interrupted path can save partial counters before the `finally` stops the embedding queue

### 2. `kb/store/sqlite_meta.py`

**Add one method** near `set_file_latest_commit` (line 1057):

```python
def get_files_with_commit_sha(self, repo_id: int, commit_sha: str) -> set[str]:
    """Return file paths already stamped with this commit SHA (for resume)."""
    # SELECT path FROM files WHERE repo_id=? AND latest_commit_sha=?
```

### 3. `kb/ingest/cli.py` (lines 204-243)

- Catch `KeyboardInterrupt` separately from `Exception` — exit with code 130, no traceback
- Check `result.get("interrupted")` — skip summary/server-reload, exit cleanly with code 0

### 4. Tests

Add to existing test files:
- `tests/unit/store/test_sqlite_meta.py` — test `get_files_with_commit_sha`
- `tests/unit/ingest/test_pipeline_core.py` — test cancel flag stops processing, test per-file checkpoint, test resume filtering

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| HEAD moves between runs | New commit SHA doesn't match old stamps → all files reprocessed (correct) |
| `--full` reindex | `_drop_repo_index` deletes file rows → stamps gone → full reprocess |
| Second Ctrl-C | Handler raises `KeyboardInterrupt` immediately → forced abort |
| Watcher compatibility | Watcher's `abort_stale_sessions()` is fine — interrupted sessions are already "aborted" |
| Content dedup safety | `ensure_content_rows_for_file()` uses ON CONFLICT → re-indexing stamped files is harmless |

## Verification

```bash
# 1. Index a repo, Ctrl-C partway through
uv run dolphin index <repo> --no-parallel
# Expect: "Finishing current file..." message, clean exit, no traceback

# 2. Re-run same command
uv run dolphin index <repo> --no-parallel
# Expect: "Resuming: skipping N files already indexed" message

# 3. Same for parallel path
uv run dolphin index <repo>
# Ctrl-C, then re-run — same resume behavior

# 4. Unit tests
uv run pytest tests/unit/store/test_sqlite_meta.py -v -k "commit_sha"
uv run pytest tests/unit/ingest/test_pipeline_core.py -v -k "cancel or resume or checkpoint"
```
