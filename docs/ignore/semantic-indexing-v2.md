# Semantic Code Indexing v2 — Implementation Checklist

**Target:** Complete Phase 1 Core Enhancements + Phase 2 Graph & Hybrid Retrieval  
**Estimated Timeline:** 4-6 weeks  
**Owner:** Engineering Team

---

## PHASE 1: CORE ENHANCEMENTS (Weeks 1-2)

### Symbol Store Architecture

- [ ] **Create `symbols` table**
  - [ ] Define schema with global symbol IDs (format: `language://repo/module.Symbol`)
  - [ ] **SQL Schema:**
    ```sql
    CREATE TABLE symbols (
        symbol_id TEXT PRIMARY KEY,      -- "py://repo/pkg.mod.Class.method"
        repo_id TEXT,                    -- Repository name
        
        name TEXT,                       -- "method"
        kind TEXT,                       -- See symbol kinds reference below
        language TEXT,                   -- "python", "typescript", "markdown"
        module TEXT,                     -- "pkg.mod"
        path TEXT,                       -- Full qualified: "pkg.mod.Class.method"
        
        file_path TEXT,                  -- "src/pkg/mod.py"
        start_byte INT,
        end_byte INT,
        
        signature TEXT,                  -- "(self, arg: str) -> bool"
        docstring TEXT,
        
        exported BOOL,                   -- Is public/exported?
        commit TEXT,                     -- Commit SHA
        hash_anchor TEXT,                -- Content hash for stability
        
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        UNIQUE(repo_id, commit, module, name, kind),
        INDEX idx_by_module (repo_id, module),
        INDEX idx_by_kind (repo_id, kind),
        INDEX idx_by_file (file_path)
    );
    ```
  - [ ] **Symbol Kinds Reference:**
    - **Core kinds (all languages):**
      - `function` - Top-level function/procedure
      - `class` - Class definition
      - `method` - Class method or member function
      - `interface` - Interface/protocol/trait
      - `type` - Type alias or type definition
      - `const` - Module-level constant
      - `variable` - Module-level variable
      - `module` - File/module itself
      - `enum` - Enum definition
      - `namespace` - Namespace/package
    - **Python-specific:**
      - `decorator` - Decorator function
      - `property` - Property definition (@property)
      - `staticmethod` - Static method
      - `classmethod` - Class method
    - **TypeScript-specific:**
      - `export` - Re-exported symbol
      - `namespace` - TypeScript namespace
    - **Markdown:**
      - `section` - Markdown section (heading + content)

- [ ] **Create module computation helper**
  - [ ] Add `compute_module_from_path(file_path: str, language: str) -> str` to `chunkers/registry.py`
  - [ ] Implementation:
    ```python
    from pathlib import Path
    
    def compute_module_from_path(file_path: str, language: str) -> str:
        """Compute module name from file path and language.
        
        Converts file paths to dot-separated module identifiers.
        
        Args:
            file_path: Relative path like "src/pkg/mod.py" or "lib/utils/helpers.ts"
            language: "python", "typescript", "javascript", "markdown"
            
        Returns:
            Module identifier like "pkg.mod" or "utils.helpers"
            
        Examples:
            "src/pkg/mod.py" -> "pkg.mod"
            "lib/utils/helpers.ts" -> "utils.helpers"
            "src/utils/index.ts" -> "utils"
            "src/pkg/__init__.py" -> "pkg"
            "docs/guide/intro.md" -> "guide.intro"
        """
        path = Path(file_path)
        
        # Remove file extension
        stem = path.with_suffix('').as_posix()
        
        # Convert path separators to dots, skip conventional prefixes
        parts = stem.split('/')
        if parts[0] in ('src', 'lib', 'source', 'docs'):
            parts = parts[1:]
        
        # Special handling: convert index/__init__ -> just the directory
        if parts[-1] in ('index', '__init__'):
            parts = parts[:-1]
        
        return '.'.join(parts) if parts else 'root'
    ```
  - [ ] Add unit tests in `tests/test_chunkers_registry.py`:
    ```python
    def test_compute_module_from_path():
        assert compute_module_from_path("src/pkg/mod.py", "python") == "pkg.mod"
        assert compute_module_from_path("lib/utils/helpers.ts", "typescript") == "utils.helpers"
        assert compute_module_from_path("src/utils/index.ts", "typescript") == "utils"
        assert compute_module_from_path("src/pkg/__init__.py", "python") == "pkg"
        assert compute_module_from_path("docs/guide/intro.md", "markdown") == "guide.intro"
        assert compute_module_from_path("utils.py", "python") == "utils"
        assert compute_module_from_path("nested/deep/module.py", "python") == "nested.deep.module"
    ```

- [ ] **Update Chunk dataclass**
  - [ ] Add `symbol_module: str | None = None` field to `chunkers/types.py`
  - [ ] Full updated class:
    ```python
    from dataclasses import dataclass
    
    @dataclass(slots=True)
    class Chunk:
        """A chunk of text with provenance and metadata.
        
        Attributes:
            text: The chunk text (canonicalized for embedding)
            start_line: 1-based inclusive starting line number
            end_line: 1-based inclusive ending line number
            token_count: Number of tokens in the chunk (computed by tiktoken)
            text_hash: SHA256 hash of canonicalized text for deduplication
            
            symbol_kind: Symbol kind (function|class|method|module|etc)
            symbol_name: Symbol name (e.g., "foo")
            symbol_path: Full qualified path (e.g., "pkg.mod.Class.method")
            symbol_module: Just the module part (e.g., "pkg.mod")
            
            h1/h2/h3: Optional heading levels (Markdown only)
        """
        
        text: str
        start_line: int
        end_line: int
        token_count: int
        text_hash: str | None = None
        
        # Symbol metadata
        symbol_kind: str | None = None
        symbol_name: str | None = None
        symbol_path: str | None = None
        symbol_module: str | None = None
        
        # Markdown metadata
        h1: str | None = None
        h2: str | None = None
        h3: str | None = None
    ```

- [ ] **Update chunking pipeline to emit module data**
  - [ ] In `py_chunker.py`:
    ```python
    def chunk_source(source: str, file_path: str, *, model: str = "small", ...) -> list[Chunk]:
        # ... existing chunking logic ...
        module = compute_module_from_path(file_path, "python")
        
        for sym in symbols:
            # Build full qualified path
            symbol_path = f"{module}.{sym.name}"
            
            # Create chunks with both module and path
            chunk = Chunk(
                text=...,
                start_line=...,
                symbol_kind=sym.kind,
                symbol_name=sym.name,
                symbol_path=symbol_path,
                symbol_module=module,
            )
    ```
  - [ ] In `ts_chunker.py`: Apply same pattern
  - [ ] In `md_chunker.py`:
    ```python
    def chunk_markdown(text: str, file_path: str, *, model: str = "small") -> list[Chunk]:
        module = compute_module_from_path(file_path, "markdown")
        current_h1 = current_h2 = None
        
        for section in parse_sections(text):
            if section.heading_level == 1:
                current_h1 = section.title
            elif section.heading_level == 2:
                current_h2 = section.title
            
            # For Markdown, symbol_name is the section title
            symbol_name = f"{current_h1}/{current_h2}" if current_h2 else current_h1
            symbol_path = f"{module}#{symbol_name}"
            
            chunk = Chunk(
                text=section.content,
                start_line=...,
                symbol_kind="section",
                symbol_name=symbol_name,
                symbol_path=symbol_path,
                symbol_module=module,
                h1=current_h1,
                h2=current_h2,
            )
    ```

- [ ] **Update chunk_file_with_config() router**
  - [ ] In `chunkers/registry.py`, ensure file_path and language passed through:
    ```python
    def chunk_file_with_config(
        abs_path: Path,
        rel_path: str,
        language: str,
        text: str,
        repo_config: dict,
    ) -> list[Chunk]:
        """Route to appropriate chunker with module computation."""
        if language == "python":
            chunks = chunk_source(text, file_path=rel_path, model="small")
        elif language == "typescript":
            chunks = chunk_typescript_source(text, file_path=rel_path, model="small")
        elif language == "markdown":
            chunks = chunk_markdown(text, file_path=rel_path, model="small")
        else:
            chunks = chunk_fallback(text, file_path=rel_path, model="small")
        return chunks
    ```

- [ ] **Update ingest/pipeline.py to handle symbols**
  - [ ] When upserting chunks, also upsert to symbols table:
    ```python
    # In IngestionPipeline.index()
    for chunk in chunks:
        if chunk.symbol_kind:
            symbol_id = f"{language}://{repo_name}/{chunk.symbol_path}"
            self.metadata.upsert_symbol(
                symbol_id=symbol_id,
                repo_id=repo_id,
                name=chunk.symbol_name,
                kind=chunk.symbol_kind,
                language=language,
                module=chunk.symbol_module,
                path=chunk.symbol_path,
                file_path=str(file_path),
                start_byte=chunk.start_line,  # TODO: convert to actual byte offset
                end_byte=chunk.end_line,
                commit_sha=commit_sha,
            )
    ```

- [ ] **Add symbol upsert method to SQLiteMetadataStore**
  - [ ] In `store/sqlite_meta.py`:
    ```python
    def upsert_symbol(
        self,
        symbol_id: str,
        repo_id: int,
        name: str,
        kind: str,
        language: str,
        module: str,
        path: str,
        file_path: str,
        start_byte: int,
        end_byte: int,
        commit_sha: str,
        signature: str | None = None,
        docstring: str | None = None,
        exported: bool = True,
    ) -> str:
        """Insert or update a symbol record."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO symbols (
                    symbol_id, repo_id, name, kind, language, module, path,
                    file_path, start_byte, end_byte, signature, docstring,
                    exported, commit, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(symbol_id) DO UPDATE SET
                    start_byte=excluded.start_byte,
                    end_byte=excluded.end_byte,
                    signature=excluded.signature,
                    docstring=excluded.docstring
                RETURNING symbol_id
                """,
                (symbol_id, repo_id, name, kind, language, module, path,
                 file_path, start_byte, end_byte, signature, docstring, exported, commit_sha),
            )
            row = cur.fetchone()
            conn.commit()
            return str(row[0]) if row else symbol_id
    ```

- [ ] **Test symbol extraction and module computation**
  - [ ] Integration test: index a Python file with class and methods
    - Verify symbols table contains class, method, and function symbols
    - Verify symbol_path includes module prefix
    - Verify symbol_module extracted correctly
  - [ ] Integration test: index a TypeScript file with exports
    - Verify export symbols created with correct kinds
  - [ ] Integration test: index a Markdown file with headings
    - Verify section symbols created
    - Verify h1/h2/h3 metadata tracked
  - [ ] Unit test: Module computation on diverse paths (see above)

- [ ] **Migration from chunk_locations** (if upgrading existing installation)
  - [ ] Create migration script that:
    - [ ] Iterates through existing chunk_locations with symbol metadata
    - [ ] Computes module from file_path
    - [ ] Generates symbol_id in format `language://repo_id/module.name`
    - [ ] Inserts into symbols table
    - [ ] Validates no duplicate symbol_ids
  - [ ] Backfill symbol_module field on existing chunks
  - [ ] Add FK constraint: chunk_locations.symbol_id → symbols.symbol_id

- [ ] **Add unique constraints and indices**
  - [ ] UNIQUE(repo_id, commit, module, name, kind) for symbol identity
  - [ ] INDEX on (repo_id, module) for module lookups
  - [ ] INDEX on (repo_id, kind) for kind-based searches
  - [ ] INDEX on file_path for file browsing


### Symbol Store Architecture

- [ ] **Create `symbols` table**
  - [ ] Define schema with global symbol IDs (`language://repo/module.Symbol`)
  - [ ] Fields: symbol_id, name, kind, language, file_path, start_byte, end_byte
  - [ ] Fields: signature, docstring, exported, repo_id, commit, hash_anchor
  - [ ] Add unique constraints on (repo_id, commit, file_path, name, kind)
  - [ ] Create indices on symbol_id, repo_id, file_path, kind

- [ ] **Migration from chunk_locations**
  - [ ] There is no current data to migrate, so migration can be safely ignored.

- [ ] **Update chunking pipeline**
  - [ ] Modify chunkers to emit symbol_id alongside symbol_kind/name/path
  - [ ] Update chunk_locations to store foreign key to symbols table
  - [ ] Add FK constraint on chunk_locations.symbol_id → symbols.symbol_id

### Multi-Chunk Sequencing

- [ ] **Add sequence tracking to schema**
  - [ ] Add `chunk_sequence` INT (nullable) to chunk_content
  - [ ] Add `total_chunks` INT (nullable) to chunk_content
  - [ ] Add unique constraint on (content_id, chunk_sequence) for ordered retrieval
  - [ ] Update LanceDB schema to include sequence fields

- [ ] **Implement token-based slicing**
  - [ ] Create `chunk_long_symbol()` function in py_chunker.py
  - [ ] Create `chunk_long_symbol()` function in ts_chunker.py
  - [ ] Parameters: max_tokens=500, overlap=100 (configurable)
  - [ ] Return list of (Chunk, sequence, total) tuples
  - [ ] Track start_line/end_line per chunk correctly through windowing

- [ ] **Test multi-chunking**
  - [ ] Unit test: long Python function (>1000 tokens) → 3+ chunks
  - [ ] Unit test: long TypeScript class (>800 tokens) → 2+ chunks
  - [ ] Verify chunk_sequence ordering is correct
  - [ ] Verify overlap regions contain consistent content

### Context Windows (Prefix/Suffix)

- [ ] **Add context fields to schema**
  - [ ] Add `prefix_context` TEXT to chunk_locations
  - [ ] Add `suffix_context` TEXT to chunk_locations
  - [ ] Add to LanceDB schema (optional; nullable)

- [ ] **Capture surrounding lines during chunking**
  - [ ] Extract 3-5 lines before chunk start (up to 100 tokens)
  - [ ] Extract 3-5 lines after chunk end (up to 100 tokens)
  - [ ] Store in chunk_locations or embed separately

- [ ] **Update embedding input**
  - [ ] Labeled concatenation: prefix + [CODE] + code + [SUFFIX] + suffix
  - [ ] Modify `build_embed_input()` to include context
  - [ ] Test with actual embeddings (stub returns zero vectors)

### Query Embedding Preparation

- [ ] **Implement query embedding function**
  - [ ] Create `embed_query()` in embeddings/provider.py
  - [ ] Takes query string + model → vector
  - [ ] Consistent with chunk embedding model

- [ ] **Add query preprocessing**
  - [ ] Lowercase, normalize whitespace
  - [ ] Optional: spell check or synonym expansion
  - [ ] Cache frequent queries (opt-in)

---

## PHASE 2: GRAPH & HYBRID RETRIEVAL (Weeks 3-5)

### Graph Edge Inference (Static Analysis)

- [ ] **Create `graph_edges` table**
  - [ ] Schema: id, source_symbol_id, target_symbol_id, edge_type, confidence, repo_id, commit
  - [ ] edge_type: CALLS, IMPORTS, IMPLEMENTS, TESTS, DOCUMENTS, COCHANGED_WITH
  - [ ] confidence: REAL (0.0-1.0)
  - [ ] Create indices on (source_symbol_id, edge_type), (target_symbol_id)

- [ ] **Implement CALLS edge inference**
  - [ ] Python: Extract function calls via AST traversal
  - [ ] TypeScript: Extract function calls via AST traversal
  - [ ] Resolve call target to target_symbol_id (simple heuristics initially)
  - [ ] Set initial confidence: 0.80 for direct calls, 0.60 for dynamic calls
  - [ ] Store in graph_edges

- [ ] **Implement IMPORTS edge inference**
  - [ ] Python: Extract import statements (`import x`, `from x import y`)
  - [ ] TypeScript: Extract import statements (`import`, `require`)
  - [ ] Resolve imports to module symbols
  - [ ] Set confidence: 0.95 (explicit imports are reliable)

- [ ] **Implement IMPLEMENTS edge inference**
  - [ ] Python: Extract class inheritance via `class Foo(Base)`
  - [ ] TypeScript: Extract class extension via `extends` and `implements`
  - [ ] Resolve to target class symbols
  - [ ] Set confidence: 0.98 (inheritance is explicit)

- [ ] **Implement TESTS edge inference** (heuristic-based initially)
  - [ ] Detect test files by naming pattern (test_*.py, *.test.ts, *.spec.ts)
  - [ ] Extract test function names and extract function calls within them
  - [ ] Create TESTS edge from test_symbol to tested_symbol
  - [ ] Set confidence: 0.70 (heuristic; will improve with coverage data)

- [ ] **Implement DOCUMENTS edge inference**
  - [ ] Markdown files: extract code block references (```python, ```ts)
  - [ ] Create DOCUMENTS edges from doc_symbol to code_symbol
  - [ ] Extract heading references to symbols (e.g., "## Using `foo()`")
  - [ ] Set confidence: 0.60 (heuristic; may be false positives)

### Edge Confidence Calibration

- [ ] **Build confidence calibration harness**
  - [ ] Function `calibrate_edge_confidence(edge_type, language, sample_size=200)`
  - [ ] Randomly sample N edges per (edge_type, language) pair
  - [ ] Heuristic validation: check if target symbol exists + semantic match
  - [ ] Compute precision = validated / sample_size
  - [ ] Store as confidence prior in config

- [ ] **Define validation rules per edge type**
  - [ ] CALLS: target symbol exists and is callable
  - [ ] IMPORTS: target module exists
  - [ ] IMPLEMENTS: target is base class or interface
  - [ ] TESTS: target is non-test and called in test body
  - [ ] DOCUMENTS: target symbol mentioned in markdown text

- [ ] **Run calibration on sample repos**
  - [ ] Test on 2-3 diverse repos (Python + TS)
  - [ ] Report precision per (edge_type, language)
  - [ ] Update confidence defaults

- [ ] **Store calibration results**
  - [ ] Create `edge_confidence_priors` table: edge_type, language, confidence
  - [ ] Update pipeline to use priors when creating edges

### Deduplication Infrastructure

- [ ] **Location-based deduplication**
  - [ ] Function `dedupe_by_location(items)` in retrieval module
  - [ ] Group items by coarse file span (e.g., start_byte // 16)
  - [ ] Keep first occurrence per group
  - [ ] O(K) complexity

- [ ] **Semantic deduplication**
  - [ ] Function `dedupe_by_semantics(items, max_k=50, similarity_thresh=0.95)`
  - [ ] Compute pairwise cosine similarity on embeddings
  - [ ] Greedy selection: keep items with minimal redundancy
  - [ ] O(K²) for small K; document LSH migration path for future

- [ ] **Test deduplication**
  - [ ] Unit test: identical code in multiple files → deduplicated
  - [ ] Unit test: similar-but-different code → not deduplicated
  - [ ] Integration test: top-50 results deduplicated correctly

### BM25 Keyword Index

- [ ] **Choose indexing backend**
  - [ ] Option A: SQLite FTS5 (built-in, no dependency)
  - [ ] Option B: Tantivy (Rust-based, external)
  - [ ] Recommendation: Start with SQLite FTS5 for simplicity

- [ ] **Create FTS5 virtual table**
  - [ ] Table: `chunks_fts(chunk_id, content, file_path, symbol_name)`
  - [ ] Enable BM25 ranking (FTS5 default)
  - [ ] Create triggers to keep FTS5 in sync with chunk_content table

- [ ] **Implement BM25 search**
  - [ ] Function `search_bm25(query, top_k=20, repo_filter=None)`
  - [ ] Query FTS5 with BM25 ranking
  - [ ] Return list of (chunk_id, bm25_score, rank)

- [ ] **Integrate BM25 into pipeline**
  - [ ] Update `ingest/pipeline.py` to populate FTS5 on chunk insert
  - [ ] Handle deletions (delete from FTS5 when chunk pruned)

- [ ] **Test BM25 search**
  - [ ] Unit test: query for common identifier → returns relevant chunks
  - [ ] Unit test: typos don't crash search
  - [ ] Integration test: BM25 recall on hand-curated test set

### Rank Fusion (Vector + BM25)

- [ ] **Implement reciprocal rank fusion**
  - [ ] Function `reciprocal_rank_fusion(vector_results, bm25_results, k=60, weights=(0.6, 0.4))`
  - [ ] Normalize ranks from 1 to K for each result set
  - [ ] Compute fused score: (weight_v * (K+1 - rank_v)) + (weight_bm25 * (K+1 - rank_bm25))
  - [ ] Re-rank by fused score
  - [ ] Return top K deduplicated results

- [ ] **Add weighting configuration**
  - [ ] Store fusion weights in config (default 0.6 vector, 0.4 BM25)
  - [ ] Allow per-query override via SearchRequest parameter
  - [ ] Document tuning guidance

- [ ] **Test fusion**
  - [ ] Unit test: exact same results → same rank order
  - [ ] Unit test: complementary results → merged correctly
  - [ ] Integration test: fusion improves recall vs. vector-only

### Graph Expansion (1-Hop Neighbors)

- [ ] **Implement neighbor retrieval**
  - [ ] Function `get_neighbors(symbol_id, edge_types=None, min_conf=0.85, limit=10)`
  - [ ] Query graph_edges for target_symbol_id = symbol_id
  - [ ] Filter by confidence >= min_conf
  - [ ] Limit to N results per node
  - [ ] Prefetch symbol and chunk metadata

- [ ] **Implement graph expansion in retrieval**
  - [ ] Function `expand_with_neighbors(primary_hits, max_neighbors_per=5, conf_thresh=0.85, token_budget=2000)`
  - [ ] For each primary hit, fetch neighbors
  - [ ] Down-weight neighbor scores (×0.6)
  - [ ] Combine and deduplicate with primary hits
  - [ ] Truncate to token_budget

- [ ] **Add to search response**
  - [ ] Include `graph` field in hit response: `{"calls": [...], "imports": [...], "tests": [...]}`
  - [ ] Each neighbor includes rank, score, and role ("primary" or "neighbor")

- [ ] **Test graph expansion**
  - [ ] Unit test: function A → neighbors include B (if CALLS A→B)
  - [ ] Unit test: confidence filtering works (skip low-confidence edges)
  - [ ] Unit test: token budget enforced

### BM25 + Vector Integration in `/v1/search`

- [ ] **Update SearchRequest model**
  - [ ] Add optional `search_strategy`: "hybrid" (default), "vector-only", "bm25-only"
  - [ ] Add optional `fusion_weights`: [vector_weight, bm25_weight]
  - [ ] Add optional `include_graph`: boolean (default true)
  - [ ] Add optional `graph_confidence_threshold`: float (default 0.85)

- [ ] **Implement hybrid search backend**
  - [ ] Function `hybrid_search(request: SearchRequest) -> List[Dict]`
  - [ ] Embed query if strategy in ["hybrid", "vector-only"]
  - [ ] Search LanceDB for top_k*2 vector hits
  - [ ] Search BM25 for top_k*2 keyword hits
  - [ ] Fuse results using reciprocal rank fusion
  - [ ] Expand with graph neighbors if include_graph=True
  - [ ] Return top_k deduplicated results

- [ ] **Update API endpoint**
  - [ ] Modify POST `/v1/search` to use hybrid_search backend
  - [ ] Ensure response format matches spec (hits, meta, latency)
  - [ ] Log search metrics (strategy used, hits count, latency breakdown)

- [ ] **Test `/v1/search` integration**
  - [ ] Integration test: vector-only search works (backward compatible)
  - [ ] Integration test: hybrid search returns plausible results
  - [ ] Integration test: graph expansion included in results
  - [ ] Integration test: latency < 300ms p95 on 10k chunks

---

## PHASE 2 ADVANCED: OPTIONAL ENHANCEMENTS (Week 5+)

### Query Rewriting (Optional, High ROI)

- [ ] **Implement query expansion**
  - [ ] Detect synonyms in query using word embeddings or ontology
  - [ ] Generate alternative queries (e.g., "JSON serialization" → "JSON marshal, JSON encode")
  - [ ] Execute multiple searches and combine results

- [ ] **Implement semantic query clustering**
  - [ ] Cluster similar queries by embedding
  - [ ] Return cached results for previously seen queries

### Caching Layer (Optional)

- [ ] **Implement query result cache**
  - [ ] LRU cache: most frequent queries cached in memory
  - [ ] TTL: invalidate cache on index update
  - [ ] Config: max_cache_size, ttl_seconds

- [ ] **Implement neighborhood cache**
  - [ ] Pre-compute 1-hop neighborhoods for high-degree nodes
  - [ ] Store in memory or Redis
  - [ ] Refresh on graph update

### LSH for Large-K Deduplication (Optional)

- [ ] **Implement MinHash + LSH bands**
  - [ ] For top-K > 100, use LSH for semantic dedup (O(K log K) vs. O(K²))
  - [ ] Tune band parameters for 95% recall at 90% FPR threshold
  - [ ] Benchmark: compare LSH vs. naive dedup on large result sets

---

## TESTING & VALIDATION (Throughout, Weeks 1-6)

### Unit Tests (Per Feature)

- [ ] Symbol store migration: 95%+ data preserved
- [ ] Multi-chunking: long functions split correctly
- [ ] Context windows: prefix/suffix captured accurately
- [ ] Graph inference: CALLS/IMPORTS/TESTS edges created correctly
- [ ] Confidence calibration: precision computed accurately
- [ ] BM25 search: queries return relevant results
- [ ] Deduplication: O(K) location dedup + O(K²) semantic dedup work
- [ ] Rank fusion: combined results ranked sensibly
- [ ] Graph expansion: neighbors retrieved with correct confidence filtering

### Integration Tests

- [ ] End-to-end: index repo → search → get results with graph
- [ ] Hybrid search: vector + BM25 fusion produces better recall than vector-only
- [ ] Latency: search completes < 300ms p95 on 10k chunks
- [ ] Deduplication: top-50 results have no exact duplicates
- [ ] Graph expansion: neighbors included in results as expected

### Manual Quality Tests

- [ ] Hand-curated 20-query test set:
  - [ ] 5 queries for function lookup
  - [ ] 5 queries for module/class lookup
  - [ ] 5 queries for documentation/concepts
  - [ ] 5 queries for error handling patterns
- [ ] Compute Precision@5, Recall@10, MRR
- [ ] Target: P@5 ≥ 0.70, R@10 ≥ 0.65, MRR ≥ 0.65

### Performance Benchmarking

- [ ] Indexing throughput: chunks/min with new features
- [ ] Search latency: p50/p95 breakdown by phase (embedding, search, fusion, expansion)
- [ ] Memory usage: graph size, cache size
- [ ] False positive rates: confidence calibration accuracy

---

## DEPLOYMENT & ROLLOUT (Week 6)

### Backward Compatibility

- [ ] Existing `/v1/search` queries still work (default to hybrid)
- [ ] Old schema data migrated to new schema (dual-write phase)
- [ ] Rollback plan documented

### Migration Checklist

- [ ] Dual-write to symbols + chunk_locations during transition
- [ ] Validate data consistency (spot checks)
- [ ] Run parallel searches on old/new backends for comparison
- [ ] Gradual traffic shift to new backend (10% → 50% → 100%)
- [ ] Monitor error rates and latency
- [ ] Cleanup old schema after 1 week stable

### Documentation

- [ ] Update architecture docs (mcp_indexing_architecture_detailed.md)
- [ ] Update implementation guide for future contributors
- [ ] Add troubleshooting guide for common issues
- [ ] Document calibration procedures

---

## SUCCESS CRITERIA

### Functional

- ✅ Symbol store operational with ≥98% of symbols migrated
- ✅ Multi-chunking working for functions >500 tokens
- ✅ Graph edges inferred with ≥75% precision per type
- ✅ Hybrid search returns ≥70% precision@5
- ✅ Graph expansion adds contextually relevant neighbors
- ✅ Zero data loss during migration

### Performance

- ✅ Search latency <300ms p95 (10k chunks)
- ✅ Indexing throughput ≥10k chunks/min
- ✅ Deduplication reduces results by ≥20% (typically)
- ✅ Memory usage <2GB for 100k chunks on 24GB system

### Quality

- ✅ Manual eval: P@5 ≥ 0.70, R@10 ≥ 0.65, MRR ≥ 0.65
- ✅ Confidence calibration: edge precision ≥75% across types
- ✅ Graph coverage: ≥80% of symbols have ≥1 edge

---

## BLOCKERS & DEPENDENCIES

- [ ] OpenAI API key provisioning (for real embeddings in Phase 2 testing)
- [ ] Test coverage data source (pytest/coverage.py integration)
- [ ] Git blame tooling (git blame output parsing)
- [ ] Performance baseline (latency targets validated against hardware)

---

## COMMUNICATION PLAN

- **Weekly:** Engineering sync on blocker resolution
- **Bi-weekly:** Demo session showing progress (indexed data, search results)
- **End of Phase 2:** Full architecture review + handoff docs

---

**Status:** Ready to begin Phase 1 Core Enhancements  
**Next Step:** Create symbol store schema + migration script