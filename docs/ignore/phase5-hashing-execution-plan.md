# Phase 5: Hashing and Idempotency Execution Plan (Revised)

## Purpose
Implement deterministic content hashing and idempotency so we index only what changed. Combine file-level Git diff gating with chunk-level hash-based deduplication to skip re-embedding identical content and keep metadata consistent when chunks move.

## Goals
1. Content canonicalization for stable fingerprints across platforms/editors
2. SHA256 hashing of canonicalized chunks
3. Idempotent chunk processing via text-hash deduplication (ignore locations for dedup)
4. Centralized, maintainable SQLite schema (SQLModel-only; no raw DDL)
5. File-level gating using Git diff since the last successful session
6. Metadata hygiene: prune invalidated chunks and synchronize locations
7. Cost savings: embed only new content

## Guiding Principles
- Canonicalize before hashing: LF newlines, strip trailing whitespace, remove leading/trailing blank lines, ensure one trailing newline, preserve indentation
- Deduplicate by content text_hash + embed_model rather than by line numbers
- Centralize schema in `src/pb_kb/store/sql_models.py` using SQLModel
- For changed files only: embed new content hashes, update metadata for unchanged, prune content not present anymore, and sync locations
- Track session counters including chunks_skipped

## Data Model (SQLModel; centralized)
Always modify `src/pb_kb/store/sql_models.py`. Never use raw SQL DDL.

We normalize chunk storage into two tables separating content identity from occurrences/locations.

1) chunk_content
- id: str (PK) — UUID for content row (per repo/file/hash/model)
- repo_id: int (FK repos.id)
- file_id: int (FK files.id)
- text_hash: str (SHA256 hex, 64 chars)
- embed_model: str (e.g., "small", "large")
- first_indexed_at: TEXT (ISO timestamp)
- last_indexed_at: TEXT (ISO timestamp)
- UNIQUE(repo_id, file_id, text_hash, embed_model)
- Index on (repo_id, file_id)

2) chunk_locations
- id: str (PK) — UUID for occurrence row
- content_id: str (FK chunk_content.id)
- start_line: int
- end_line: int
- symbol_kind: TEXT | NULL
- symbol_name: TEXT | NULL
- symbol_path: TEXT | NULL
- last_seen_at: TEXT (ISO timestamp)
- UNIQUE(content_id, start_line, end_line)
- Index on (content_id)

Existing tables (repos, sessions, files) remain as-is, with sessions extended to include chunks_skipped.

## Content Canonicalization Rules
1. Line endings: normalize CRLF/CR to `\n`
2. Trailing whitespace: strip per line
3. Leading/trailing blank lines: remove
4. Final newline: ensure exactly one trailing `\n`
5. Preserve indentation (significant for Python/YAML/Makefiles)

Implementation lives in `src/pb_kb/hashing.py` as:
- canonicalize_text(text: str) -> str
- hash_text(text: str) -> str

## Hash Format
- Algorithm: SHA256
- Output: 64-char lowercase hex

## Core Algorithms

1) File-level gating (Phase 6 integration)
- Let last_success = commit_sha from the last successful session for the repo
- Use: `git diff --name-only last_success..HEAD` to list changed files
- Only process those files; skip all others entirely

2) Per-file processing (changed files only)
- Chunk file into Chunk objects (with start/end and text)
- Compute chunk.text_hash = hash_text(chunk.text)
- Build desired map: desired[hash] -> list of occurrences [(start, end, symbol_meta)...]
- Query existing content for the file+embed_model: existing_hashes = {hash -> content_id}
- New content = desired.keys() - existing_hashes.keys()
- Unchanged content = intersection(desired.keys(), existing_hashes.keys())
- For new content:
  - Insert chunk_content rows (one per new hash)
  - Embed these new chunks (and write vectors in Phase 6)
- For unchanged content:
  - Update chunk_content.last_indexed_at = now
- Sync locations for all desired hashes (insert/update/delete to match current occurrences; set last_seen_at = now)
- Prune invalidated content for this file (content whose hashes are not present anymore), which also deletes orphaned locations

3) Location synchronization per content_id
- Fetch existing occurrences for content_ids
- Compute to_insert, to_update (symbol meta changed), to_delete by set difference
- Apply INSERT/UPDATE/DELETE; set last_seen_at = now for seen rows

4) Pruning invalidated file content
- current_hashes = set(desired.keys())
- Delete locations and content where text_hash NOT IN current_hashes for that (repo_id, file_id, embed_model)

## Store API Surface (SQLiteMetadataStore)
All implemented with sqlite3 on top of SQLModel-managed tables.

- begin_session(repo_id, commit_sha, branch, embed_model) -> int
- set_session_status(session_id, status, notes=None) -> None
- bump_session_counters(session_id, *, files_indexed=None, chunks_indexed=None, vectors_written=None, chunks_skipped=None) -> None
- upsert_file(repo_id, *, path, ext, language, is_binary, size_bytes) -> int
- set_file_latest_commit(repo_id, path, commit_sha) -> None

New/updated for Phase 5:
- get_distinct_hashes_for_file(repo_id: int, file_id: int, embed_model: str) -> set[str]
  - SELECT DISTINCT text_hash FROM chunk_content WHERE repo_id=? AND file_id=? AND embed_model=?
- upsert_chunk_content(repo_id: int, file_id: int, text_hash: str, embed_model: str) -> str
  - Inserts if missing; updates last_indexed_at if exists; returns content_id
- get_locations_for_content_ids(content_ids: list[str]) -> dict[str, list[dict]]
  - For syncing locations
- sync_locations_for_file(repo_id: int, file_id: int, embed_model: str, desired: dict[str, list[Occurrence]]) -> None
  - Inserts/updates/deletes rows in chunk_locations to match desired state; updates last_seen_at
- prune_invalidated_content_for_file(repo_id: int, file_id: int, embed_model: str, current_hashes: set[str]) -> int
  - Deletes content (and cascading locations) whose text_hash NOT IN current_hashes; returns count deleted

Note: we continue using SQLModel to materialize schema; we do not use raw DDL for table creation.

## Deduplication Component (`src/pb_kb/ingest/dedup.py`)
Keep a simple class that assists per-file decisions using the store. Hash-only dedup (ignore locations).

- get_existing_hashes(repo_id, file_id, embed_model) -> set[str]
- split_by_novelty(chunks, existing_hashes) -> (new_chunks, unchanged_chunks)
- Safety: on any store error, log warning and treat affected chunks as changed

## Integration with Ingestion Pipeline (Phase 6)
High-level flow per repo:
1. Determine changed files via Git diff (last successful session -> HEAD)
2. For each changed file:
   - Chunk -> hash -> dedup by text_hash
   - Embed only new content
   - Upsert chunk_content for all content (new/unchanged)
   - Sync chunk_locations (insert/update/delete)
   - Prune invalidated content for this file
   - Update counters: chunks_indexed (new unique hashes), chunks_skipped (occurrences of unchanged content)
3. Unchanged files: skipped entirely

## Error Handling
- Hash computation or lookup failures: log warning, treat chunk as changed (conservative)
- DB errors: retry where appropriate; log and continue with conservative behavior
- Hash collisions: log warning and treat as changed (extremely unlikely)

## Performance Considerations
- File-level gating avoids touching unchanged files
- Hashing is fast vs embedding latency; cost is dominated by embeddings
- Queries indexed by (repo_id, file_id) and (content_id) for locations
- Memory: in-memory sets/maps per file are OK for small/medium repos (our current target)

## Testing Strategy
Unit tests
- hashing: canonicalization rules, determinism, hash format
- store: upsert_chunk_content, get_distinct_hashes_for_file, location sync, prune logic
- dedup: correct splitting for new vs unchanged; robustness to store failures

Integration tests
- Index file twice (no changes) → 0 embeddings, counters reflect skips
- Modify file: only new hashes embedded; moved chunks update locations only; removed chunks are pruned
- Duplicate chunks in a file: single embedding, multiple locations recorded

## Success Criteria
- Canonicalization deterministic and tested
- Hashing stable and correct
- Schema materialized via SQLModel; no raw DDL
- File-level gating applied (Phase 6 integration)
- Dedup logic skips unchanged content; moved chunks do not trigger embeddings
- Locations are kept in sync; removed content is pruned
- Counters reflect savings; logs show skipped chunks

## Implementation Sequence

Step 1: Content Canonicalization and Hashing (DONE)
- `src/pb_kb/hashing.py` provides canonicalize_text and hash_text

Step 2: Schema and Store API
- Update `src/pb_kb/store/sql_models.py` to add chunk_content and chunk_locations models
- Extend `src/pb_kb/store/sqlite_meta.py` with the new store APIs listed above
- Ensure sessions includes chunks_skipped; initialize() creates/validates tables

Step 3: Deduplication Logic
- Implement/adjust `src/pb_kb/ingest/dedup.py` to use text-hash-only dedup and the store’s distinct-hash query

Step 4: Pipeline Integration (Phase 6)
- Add Git diff gating and per-file processing flow
- Hook embedding of new content only; upsert content; sync locations; prune invalidated content
- Update session counters and logging

Step 5: Tests
- Add unit tests for hashing, store, dedup
- Add integration tests that exercise unchanged, changed, moved, and duplicate chunk scenarios

## Documentation Updates
- README: explain idempotent indexing and incremental updates
- API docs: canonicalization rules and dedup behavior
- Examples: show before/after indexing runs and cost savings

---

Status: Ready to implement
Dependencies: Phase 4 (Chunking) complete ✅
Estimated Effort: 2–3 days
Priority: High (enables cost-effective incremental indexing)
