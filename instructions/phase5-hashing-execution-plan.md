# Phase 5: Hashing and Idempotency Execution Plan

## Purpose
Implement content hashing and idempotency checks to enable efficient, incremental indexing by skipping unchanged chunks and avoiding redundant embeddings.

## Goals
1. **Content Canonicalization**: Normalize chunk text before hashing for stable fingerprints
2. **SHA256 Hashing**: Generate deterministic content hashes for deduplication
3. **Idempotent Processing**: Skip chunks that haven't changed since last indexing
4. **Database Integration**: Extend SQLite metadata store to track chunk hashes
5. **Cost Savings**: Avoid re-embedding unchanged content

## Guiding Principles
- Canonicalize before hashing: normalize line endings, strip trailing whitespace
- Use SHA256 for cryptographic-strength fingerprints
- Store text_hash in chunks_meta table alongside chunk metadata
- Upsert strategy: compare hashes to detect changes
- Preserve provenance: track when chunks were last indexed

## Data Contracts

### Chunk Hash Record (SQLite chunks_meta table)
```sql
CREATE TABLE IF NOT EXISTS chunks_meta (
    id TEXT PRIMARY KEY,              -- UUID for chunk
    repo_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    text_hash TEXT NOT NULL,          -- SHA256 hex digest (64 chars)
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    symbol_kind TEXT,                 -- function|class|method|module|null
    symbol_name TEXT,
    symbol_path TEXT,                 -- "path/to/file.py:Class.method"
    embed_model TEXT NOT NULL,        -- "small"|"large"
    indexed_at TEXT NOT NULL,         -- ISO timestamp
    FOREIGN KEY (repo_id) REFERENCES repos(id),
    FOREIGN KEY (file_id) REFERENCES files(id),
    UNIQUE(repo_id, file_id, start_line, end_line, text_hash)
);
```

### Content Canonicalization Rules
1. **Line Endings**: Normalize all line endings to `\n` (Unix-style)
2. **Trailing Whitespace**: Strip trailing spaces/tabs from each line
3. **Final Newline**: Ensure content ends with exactly one `\n`
4. **No Leading/Trailing Blank Lines**: Strip empty lines at start and end
5. **Preserve Indentation**: Keep leading whitespace (significant in Python/YAML)

### Hash Format
- Algorithm: SHA256
- Output: Lowercase hexadecimal string (64 characters)
- Example: `"a3c5f8d9e1b2c4d6f7e8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0"`

## Implementation Components

### 1. Content Canonicalizer (`src/pb_kb/hashing.py`)
```python
def canonicalize_content(text: str) -> str:
    """Normalize chunk text for stable hashing.
    
    Transformations:
    - Normalize line endings to \n
    - Strip trailing whitespace from each line
    - Remove leading/trailing blank lines
    - Ensure single trailing newline
    
    Args:
        text: Raw chunk text
        
    Returns:
        Canonicalized text ready for hashing
    """
```

### 2. Hash Generator (`src/pb_kb/hashing.py`)
```python
def hash_chunk(text: str) -> str:
    """Generate SHA256 hash of canonicalized chunk text.
    
    Args:
        text: Chunk text (will be canonicalized first)
        
    Returns:
        64-character lowercase hex digest
    """
```

### 3. Chunk Deduplicator (`src/pb_kb/ingest/dedup.py`)
```python
class ChunkDeduplicator:
    """Manages chunk deduplication via content hashing."""
    
    def __init__(self, store: SQLiteMetadataStore):
        self.store = store
    
    def get_existing_hashes(
        self, 
        repo_id: int, 
        file_id: int
    ) -> Dict[Tuple[int, int], str]:
        """Get existing chunk hashes for a file.
        
        Returns:
            Dict mapping (start_line, end_line) to text_hash
        """
    
    def filter_unchanged_chunks(
        self,
        chunks: List[Chunk],
        repo_id: int,
        file_id: int
    ) -> Tuple[List[Chunk], List[Chunk]]:
        """Separate changed from unchanged chunks.
        
        Returns:
            (changed_chunks, unchanged_chunks)
        """
```

### 4. SQLite Schema Extension (`src/pb_kb/store/sqlite_meta.py`)
```python
class SQLiteMetadataStore:
    # Existing methods...
    
    def create_chunks_meta_table(self):
        """Create chunks_meta table if not exists."""
    
    def upsert_chunk_metadata(
        self,
        chunk_id: str,
        repo_id: int,
        file_id: int,
        text_hash: str,
        start_line: int,
        end_line: int,
        symbol_kind: str | None,
        symbol_name: str | None,
        symbol_path: str | None,
        embed_model: str,
    ) -> None:
        """Insert or update chunk metadata."""
    
    def get_chunk_hashes_for_file(
        self,
        repo_id: int,
        file_id: int
    ) -> List[Dict]:
        """Retrieve existing chunk hashes for a file.
        
        Returns list of dicts with:
        - start_line
        - end_line
        - text_hash
        - chunk_id
        """
    
    def mark_chunks_outdated(
        self,
        repo_id: int,
        file_id: int,
        commit_sha: str
    ) -> int:
        """Mark chunks as outdated if file changed.
        
        Returns number of chunks marked outdated.
        """
```

## Integration with Ingestion Pipeline

### Updated Ingestion Flow
```
1. Scan files (existing - Phase 3)
2. Chunk files (existing - Phase 4)
3. **NEW: Canonicalize and hash chunks**
4. **NEW: Query existing hashes from chunks_meta**
5. **NEW: Filter unchanged chunks**
6. Embed changed chunks only (Phase 6)
7. **NEW: Upsert chunk metadata with hashes**
8. Write embeddings to LanceDB (Phase 6)
```

### Pipeline Integration Points
```python
# In ingestion pipeline after chunking:
from pb_kb.hashing import hash_chunk
from pb_kb.ingest.dedup import ChunkDeduplicator

# After chunking each file:
chunks = chunk_file(...)

# Add hashes to chunks
for chunk in chunks:
    chunk.text_hash = hash_chunk(chunk.text)

# Deduplicate
deduplicator = ChunkDeduplicator(metadata_store)
changed_chunks, unchanged_chunks = deduplicator.filter_unchanged_chunks(
    chunks, repo_id, file_id
)

# Only embed changed chunks
embeddings = embed_chunks(changed_chunks)

# Update metadata for all chunks (mark unchanged as still valid)
for chunk in changed_chunks:
    metadata_store.upsert_chunk_metadata(chunk, ...)
```

## Testing Strategy

### Unit Tests (`tests/test_hashing.py`)
1. **Canonicalization Tests**
   - Normalize various line ending formats (CRLF, CR, LF)
   - Strip trailing whitespace consistently
   - Handle edge cases (empty strings, whitespace-only)
   - Preserve indentation

2. **Hashing Tests**
   - Deterministic output for same input
   - Different hashes for different inputs
   - Stable across multiple calls
   - Expected hash format (64 hex chars)

3. **Deduplication Tests**
   - Correctly identify unchanged chunks
   - Detect changed chunks
   - Handle new files (no existing hashes)
   - Handle deleted chunks

### Integration Tests (`tests/test_dedup_integration.py`)
1. **End-to-End Deduplication**
   - Index file twice, second pass skips all chunks
   - Modify file, only changed chunks re-indexed
   - Add new chunks, only new ones embedded

2. **Database Integration**
   - Chunk metadata persisted correctly
   - Hashes queryable by file
   - Outdated chunks marked properly

## Success Criteria

Phase 5 complete when:
- [ ] Content canonicalization is deterministic and well-tested
- [ ] SHA256 hashing produces stable fingerprints
- [ ] chunks_meta table created and integrated
- [ ] Deduplication logic correctly identifies unchanged chunks
- [ ] Integration with ingestion pipeline is seamless
- [ ] Unit tests pass (canonicalization, hashing, deduplication)
- [ ] Integration tests demonstrate idempotent indexing
- [ ] Cost savings verified (skipped embeddings logged)

## Implementation Sequence

### Step 1: Content Canonicalization and Hashing
**Files to create:**
- `src/pb_kb/hashing.py` - Core hashing utilities
- `tests/test_hashing.py` - Unit tests

**Implementation:**
1. Implement `canonicalize_content()` with all normalization rules
2. Implement `hash_chunk()` using hashlib.sha256
3. Add comprehensive unit tests
4. Verify deterministic behavior

### Step 2: SQLite Schema Extension
**Files to modify:**
- `src/pb_kb/store/sqlite_meta.py` - Add chunks_meta table and methods

**Implementation:**
1. Add `CREATE TABLE chunks_meta` to schema
2. Implement `upsert_chunk_metadata()`
3. Implement `get_chunk_hashes_for_file()`
4. Implement `mark_chunks_outdated()`
5. Add database migration if needed
6. Add unit tests for new methods

### Step 3: Deduplication Logic
**Files to create:**
- `src/pb_kb/ingest/dedup.py` - Chunk deduplication
- `tests/test_dedup.py` - Deduplication tests

**Implementation:**
1. Implement `ChunkDeduplicator` class
2. Add `get_existing_hashes()` method
3. Add `filter_unchanged_chunks()` method
4. Unit tests for deduplication logic

### Step 4: Pipeline Integration
**Files to modify:**
- `src/pb_kb/ingest/pipeline.py` - Add deduplication step
- `src/pb_kb/chunkers/types.py` - Add text_hash field to Chunk

**Implementation:**
1. Extend Chunk dataclass with `text_hash: str | None = None`
2. Add hashing step after chunking
3. Add deduplication before embedding
4. Update chunk counters (changed vs unchanged)
5. Add logging for skipped chunks

### Step 5: Integration Testing
**Files to create:**
- `tests/test_dedup_integration.py` - End-to-end tests

**Implementation:**
1. Test full pipeline with unchanged files
2. Test incremental updates
3. Verify cost savings (no redundant embeddings)
4. Verify database consistency

## Cost Savings Analysis

### Expected Improvements
- **Initial Index**: 100% of chunks embedded (baseline)
- **Re-index (no changes)**: 0% of chunks embedded (100% savings)
- **Incremental Update**: Only modified chunks embedded
- **Typical Workflow**: 80-95% cost savings on subsequent indexes

### Metrics to Track
- Total chunks processed
- Chunks skipped (unchanged)
- Chunks embedded (changed or new)
- Embedding API calls saved
- Estimated cost savings per session

## Error Handling

### Hash Collision (extremely unlikely with SHA256)
- Log warning if detected
- Treat as changed chunk (safe fallback)
- Continue processing

### Database Errors
- Retry transient failures
- Fall back to re-embedding if hash lookup fails
- Log errors for debugging

### Canonicalization Edge Cases
- Handle empty chunks gracefully
- Handle binary/malformed content
- Log warnings for unexpected input

## Performance Considerations

### Hash Computation
- SHA256 is fast (~500 MB/s on modern CPUs)
- Minimal overhead compared to embedding API latency
- Batch canonicalization for efficiency

### Database Queries
- Index on (repo_id, file_id) for fast lookups
- Batch hash queries by file
- Use prepared statements for upserts

### Memory Usage
- Store hashes in memory during session (reasonable for small repos)
- Stream processing for large repositories
- Clear hash cache between files

## Future Enhancements (Post-Phase 5)

1. **Chunk Evolution Tracking**: Store hash history to detect oscillating changes
2. **Similarity Hashing**: Use simhash/minhash for near-duplicate detection
3. **Delta Indexing**: Only re-embed changed symbols, preserve metadata for moved code
4. **Hash-Based Garbage Collection**: Remove orphaned chunk metadata

## Documentation Updates Needed

- Update README.md with idempotent indexing behavior
- Document canonicalization rules in API docs
- Add examples of incremental indexing workflows
- Update cost estimation guidance

---

**Status**: Ready to implement
**Dependencies**: Phase 4 (Chunking) complete ✅
**Estimated Effort**: 2-3 days
**Priority**: High (enables cost-effective incremental indexing)
