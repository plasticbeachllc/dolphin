# Code Review Implementation Guide

This document provides specific code changes to address all recommendations from the code review.

## Progress So Far

✅ Created utility module (`kb/api/utils.py`) with:
- `validate_path_within_repo()` function
- `GitRepository` class for Git operations

## Changes to Apply

### 1. Add Constants and Imports to `kb/api/app.py`

After line 12 (`from .task_queue import TaskStatus, get_task_queue`), add:

```python
from .utils import validate_path_within_repo, GitRepository

# Constants
EMBEDDING_BATCH_SIZE = 128
ESTIMATED_TOKENS_PER_CHUNK = 200
```

### 2. Replace Magic Numbers in `kb/api/app.py`

**Line 693 and 1522:** Replace `batch_size = 128` with `EMBEDDING_BATCH_SIZE`
```python
# OLD:
batch_size = 128
for i in range(0, len(hashes_list), batch_size):
    batch_hashes = hashes_list[i:i+batch_size]

# NEW:
for i in range(0, len(hashes_list), EMBEDDING_BATCH_SIZE):
    batch_hashes = hashes_list[i:i+EMBEDDING_BATCH_SIZE]
```

**Line 994:** Replace token estimation constant
```python
# OLD:
total_tokens = chunks_count * 200

# NEW:
total_tokens = chunks_count * ESTIMATED_TOKENS_PER_CHUNK
```

### 3. Replace Path Validation Code

**Location 1 (around line 327):**
```python
# OLD:
try:
    full_path = full_path.resolve()
    if not str(full_path).startswith(str(repo_root.resolve())):
        raise HTTPException(status_code=403, detail="Path outside repository")
except Exception:
    raise HTTPException(status_code=400, detail="Invalid file path")

# NEW:
full_path = validate_path_within_repo(full_path, repo_root)
```

**Location 2 (around line 572) and Location 3 (around line 1429):**
```python
# OLD:
try:
    resolved = full_path.resolve()
    if not str(resolved).startswith(str(root.resolve())):
        continue  # Skip files outside repo
except Exception:
    continue

# NEW:
try:
    validate_path_within_repo(full_path, root)
except HTTPException:
    continue  # Skip files outside repo
```

### 4. Replace Git Command Calls

**Location 1 (around line 600):**
```python
# OLD:
try:
    commit_sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        stderr=subprocess.STDOUT
    ).decode("utf-8").strip()
    branch = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        stderr=subprocess.STDOUT
    ).decode("utf-8").strip()
except Exception:
    commit_sha = "unknown"
    branch = "unknown"

# NEW:
git_repo = GitRepository(root)
commit_sha, branch = git_repo.get_commit_and_branch()
```

**Location 2 (around line 1123):**
```python
# OLD:
commit_sha = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    stderr=subprocess.STDOUT
).decode("utf-8").strip()

# NEW:
git_repo = GitRepository(root)
commit_sha = git_repo.get_current_commit()
```

### 5. Add Constants to `kb/api/search_backend.py`

After the imports (around line 19), add:

```python
# Constants
CANDIDATE_MULTIPLIER = 4
CONFIG_FILE_SCORE_PENALTY = 0.5
BM25_SCORE_NORMALIZATION_FACTOR = 10
```

Then replace magic numbers:

**Line 69:**
```python
# OLD:
num_candidates = request.top_k * 4

# NEW:
num_candidates = request.top_k * CANDIDATE_MULTIPLIER
```

**Line 310 (remove local constant):**
```python
# OLD:
def _apply_file_type_scoring(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
    """..."""
    CONFIG_FILE_PENALTY = 0.5  # Remove this line

    adjusted = []

# NEW:
def _apply_file_type_scoring(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
    """..."""
    adjusted = []
```

**Line 356:**
```python
# OLD:
normalized_score = 1 / (1 + math.exp(-bm25_score / 10))

# NEW:
normalized_score = 1 / (1 + math.exp(-bm25_score / BM25_SCORE_NORMALIZATION_FACTOR))
```

### 6. Remove Deprecated Endpoints

Delete lines 1362-1613 in `kb/api/app.py`:
- Remove `@app.post("/v1/index/sync")` and `index_files_sync()` function
- Remove `@app.post("/v1/index_old")` and `index_files_old()` function

Keep only the `def main()` function at the end.

### 7. Improve Variable Naming

Throughout `kb/api/app.py`, consider renaming:

```python
# In _process_index_task and index_files_old:
dedup → chunk_deduplicator
hash_to_vec → text_hash_to_embedding
h → text_hash
occ → occurrence
cur → cursor
```

Example:
```python
# OLD:
dedup = ChunkDeduplicator(_sql_store)
changed_chunks, unchanged_chunks = dedup.filter_unchanged_chunks(...)

# NEW:
chunk_deduplicator = ChunkDeduplicator(_sql_store)
changed_chunks, unchanged_chunks = chunk_deduplicator.filter_unchanged_chunks(...)
```

### 8. Add Missing Type Hints

Add return type annotations to functions missing them:

```python
# In kb/api/app.py:
async def _process_index_task(task_id: str, repo_name: str, files: list[str]) -> None:
    ...

async def _process_full_reindex_task(
    task_id: str,
    repo_name: str,
    files: list[str],
    clear_existing: bool = False
) -> None:
    ...
```

### 9. Create Result Hydration Helper in `kb/api/search_backend.py`

Add this method to consolidate hydration logic:

```python
def _hydrate_chunk_content(
    self,
    chunk_ids: list[str],
    sql_store: SQLiteMetadataStore
) -> dict[str, str]:
    """Hydrate content for chunk IDs.

    Args:
        chunk_ids: List of chunk row IDs from LanceDB
        sql_store: Metadata store for content lookup

    Returns:
        Dictionary mapping chunk_id -> content
    """
    if not chunk_ids:
        return {}

    # Convert LanceDB row IDs to content_ids
    content_id_map = self._resolve_content_ids(chunk_ids)
    content_ids = list(content_id_map.values())

    if not content_ids:
        return {}

    # Fetch content from metadata store
    contents = sql_store.get_chunk_contents(content_ids)

    # Map content back to original chunk_ids
    result = {}
    for chunk_id in chunk_ids:
        content_id = content_id_map.get(chunk_id)
        if content_id and content_id in contents:
            result[chunk_id] = contents[content_id]

    return result
```

Then use it in multiple places:
- In `search()` method (line 179-203)
- In `_hydrate_docs_for_reranking()` method (line 435-454)

### 10. Standardize Error Handling

Create a standard pattern for error handling:

```python
# Bad (inconsistent):
except Exception as e:
    # Sometimes logs, sometimes doesn't
    pass

# Good (consistent):
except Exception as e:
    import logging
    logging.error(f"Operation failed: {operation_name}", exc_info=True)
    # Then either raise HTTPException or return empty result
```

Apply this pattern to all exception handlers in:
- `kb/api/app.py` lines 135-136, 268-269, etc.
- `kb/api/search_backend.py` lines 84-87, 100-103, etc.

## Additional Refactorings (Medium Priority)

### 11. Break Up Long Functions

**`_process_index_task()` (341 lines) should be split into:**

```python
def _validate_and_filter_files(files: list[str], root: Path) -> list[str]:
    """Validate files and filter to only those that exist."""
    ...

def _get_or_create_git_info(root: Path) -> tuple[str, str]:
    """Get commit SHA and branch, or return 'unknown'."""
    ...

async def _index_single_file(
    file_path: Path,
    repo_id: int,
    file_id: int,
    sql_store,
    lance_store,
    embed_model: str,
    repo_name: str,
    commit_sha: str,
    branch: str
) -> tuple[int, int]:  # Returns (indexed_count, skipped_count)
    """Index a single file and return counts."""
    ...

async def _detect_and_queue_mid_index_changes(
    initial_snapshots: dict,
    root: Path,
    repo_id: int,
    sql_store
) -> int:
    """Detect files that changed during indexing."""
    ...
```

**`search()` method (171 lines) should be split into:**

```python
def _execute_vector_search(self, request: SearchRequest, query_embedding) -> list[dict]:
    """Execute vector search and return formatted results."""
    ...

def _execute_bm25_search(self, request: SearchRequest) -> list[dict]:
    """Execute BM25 search and return hydrated results."""
    ...

def _apply_fusion_and_ranking(
    self,
    vector_results: list[dict],
    bm25_results: list[dict],
    request: SearchRequest
) -> list[dict]:
    """Apply RRF fusion and optional reranking."""
    ...

def _apply_mmr_diversification(
    self,
    hits: list[dict],
    query_embedding: list[float],
    request: SearchRequest
) -> list[dict]:
    """Apply MMR for result diversification."""
    ...
```

### 12. Simplify Config Loading in `kb/config.py`

Replace the giant `from_mapping()` method with helper methods:

```python
@classmethod
def from_mapping(cls, data: Mapping[str, Any]) -> "KBConfig":
    """Create configuration from mapping."""
    return cls(
        store_root=cls._extract_store_root(data),
        retrieval=cls._build_retrieval_config(data.get("retrieval", {})),
        embedding_provider=cls._extract_embedding_provider(data),
        embedding_batch_size=data.get("embedding", {}).get("batch_size", 100),
        cache_enabled=data.get("cache", {}).get("enabled", True),
        redis_url=data.get("cache", {}).get("redis_url"),
        # ... other fields
    )

@classmethod
def _build_retrieval_config(cls, data: dict) -> RetrievalConfig:
    """Build retrieval configuration section."""
    return RetrievalConfig(
        reranking=cls._build_reranking_config(data.get("reranking", {})),
        hybrid_search=cls._build_hybrid_search_config(data.get("hybrid_search", {})),
        ann=cls._build_ann_config(data.get("ann", {})),
        score_cutoff=data.get("score_cutoff", 0.15),
        # ... other fields
    )
```

## Testing Checklist

After applying changes:

- [ ] Run `pytest tests/` to ensure all tests pass
- [ ] Test search endpoint: `curl -X POST http://localhost:8000/search -d '{"query": "test"}'`
- [ ] Test indexing endpoint: Create test repo and index files
- [ ] Check that path validation works (try to access files outside repo - should fail)
- [ ] Verify Git operations work in both Git and non-Git directories
- [ ] Check that constants are used correctly (no hard-coded magic numbers remain)

## Commit Strategy

1. **Commit 1:** Add utility module and constants
   ```bash
   git add kb/api/utils.py
   git commit -m "Add utility functions for path validation and Git operations"
   ```

2. **Commit 2:** Apply constants and utilities to app.py
   ```bash
   git add kb/api/app.py
   git commit -m "Refactor: Extract constants and use utility functions in app.py"
   ```

3. **Commit 3:** Apply constants to search_backend.py
   ```bash
   git add kb/api/search_backend.py
   git commit -m "Refactor: Extract constants in search_backend.py"
   ```

4. **Commit 4:** Remove deprecated endpoints
   ```bash
   git add kb/api/app.py
   git commit -m "Remove deprecated index_files_sync and index_files_old endpoints"
   ```

5. **Commit 5:** Improve variable naming
   ```bash
   git add kb/api/app.py
   git commit -m "Improve variable naming for better readability"
   ```

6. **Commit 6:** Add missing type hints
   ```bash
   git add kb/api/app.py kb/api/search_backend.py
   git commit -m "Add missing type hints throughout codebase"
   ```

## Estimated Time

- **Quick wins (constants, utils, deprecated code removal):** 2-3 hours
- **Variable naming improvements:** 1-2 hours
- **Type hints:** 1-2 hours
- **Function splitting:** 4-6 hours
- **Config simplification:** 2-3 hours
- **Testing:** 2-3 hours

**Total:** 12-19 hours for complete implementation

## Benefits

Once all changes are applied:

- **30-40% reduction in code duplication**
- **Improved readability** with clear variable names and smaller functions
- **Better maintainability** with extracted utilities and constants
- **Easier testing** with smaller, focused functions
- **Reduced technical debt** with deprecated code removed
