# Dolphin Vision & Implementation Roadmap
**Making LLMs Smarter with Better Context**

**Status**: Living Document - Collaborative Planning Phase
**Created**: 2025-10-30
**Last Updated**: 2025-10-30
**Owner**: Product & Engineering Teams

---

## Executive Summary

Dolphin has achieved technical completeness as a semantic code search platform (243/243 tests passing). This document outlines our **vision for dramatically increasing the value Dolphin provides to LLMs** by improving search quality, context relevance, performance, usability, and cost-efficiency.

### Core Value Proposition

**Dolphin exists to make LLMs more effective by providing them with the *right* code context, *faster*, and *cheaper*.**

---

## Table of Contents

- [1. Current State Analysis](#1-current-state-analysis)
- [2. Vision: High-Impact Improvements](#2-vision-high-impact-improvements)
- [3. Search Quality Enhancements](#3-search-quality-enhancements)
- [4. Context Building Improvements](#4-context-building-improvements)
- [5. Performance & Speed Optimizations](#5-performance--speed-optimizations)
- [6. LLM Usability & Integration](#6-llm-usability--integration)
- [7. Cost & Efficiency Gains](#7-cost--efficiency-gains)
- [8. Evaluation & Measurement](#8-evaluation--measurement)
- [9. Implementation Roadmap](#9-implementation-roadmap)
- [10. Success Metrics](#10-success-metrics)

---

## 1. Current State Analysis

### 1.1 What Works Well ✅

**Technical Foundation**
- **Semantic search**: OpenAI embeddings + LanceDB vector search working end-to-end
- **Language-aware chunking**: Tree-sitter AST-based chunking for Python, TypeScript, Markdown
- **Metadata richness**: Symbol paths, line numbers, commit SHAs, language tags
- **Git-aware indexing**: Incremental indexing based on git history
- **Multi-interface access**: MCP, REST API, CLI
- **Comprehensive testing**: 243/243 tests passing

**Architecture Strengths**
- Modular design with clear separation of concerns
- Fixed-size vectors per model (1536 small, 3072 large)
- Content deduplication via SHA256 hashing
- Retry logic with exponential backoff for API calls
- Session spend caps to prevent cost overruns

### 1.2 Areas for Material Improvement 🎯

**Search Quality Issues**
1. **Pure vector search limitations**: No keyword matching → misses exact identifier searches
2. **No reranking**: Initial KNN results may not be optimally ordered for the query
3. **Limited result diversity**: May return similar/duplicate code snippets
4. **No query understanding**: Treats all queries the same way
5. **No negative filtering**: Can't exclude irrelevant patterns (e.g., "not tests")

**Context Building Gaps**
1. **Missing contextual expansion**: Doesn't automatically include related code (imports, callers, callees)
2. **No code graph awareness**: Doesn't understand dependencies between chunks
3. **Limited snippet sizing**: Fixed token windows don't adapt to query needs
4. **No chunk ranking within files**: Returns chunks independently without file-level context
5. **Missing cross-repository linking**: Can't connect related code across repos

**Performance Bottlenecks**
1. **Query latency**: ~300ms p50 is good but could be <100ms for simple queries
2. **No caching**: Every query hits OpenAI API + LanceDB
3. **Sequential processing**: Embedding and search happen sequentially
4. **No pre-computation**: Could pre-compute common query patterns
5. **No result streaming**: Returns full result set at once

**Usability for LLMs**
1. **Flat result structure**: No hierarchical organization of results
2. **Limited metadata in MCP**: Could provide more structured info
3. **No confidence scores**: Just distance → similarity conversion
4. **No explanations**: Why were these results returned?
5. **No suggested follow-ups**: What else should the LLM ask for?

**Cost & Efficiency**
1. **Every query embeds**: Even cached queries pay embedding cost
2. **No model selection guidance**: LLM doesn't know which embed model to use
3. **Over-fetching**: Returns full chunks even when snippets would suffice
4. **No incremental updates**: Forces full reindex on configuration changes

---

## 2. Vision: High-Impact Improvements

### 2.1 North Star Metrics

**Primary Goal**: **Double the value Dolphin provides to LLMs in 6 months**

Measured by:
- **Search quality**: 2x improvement in relevance (measured by human eval & LLM task success)
- **Context quality**: 2x reduction in "I need more context" from LLMs
- **Speed**: 3x faster for common queries (<100ms p50)
- **Cost efficiency**: 50% reduction in embedding costs per search
- **LLM success rate**: 2x improvement in task completion without additional searches

### 2.2 Design Principles

1. **Relevance First**: Always prioritize returning the *right* code over more code
2. **LLM-Native**: Design for machine consumers, not just humans
3. **Progressive Disclosure**: Start with best results, allow LLM to drill deeper
4. **Cost-Conscious**: Every API call should provide maximum value
5. **Fast by Default**: Speed enables interactive exploration
6. **Explainable**: LLMs should understand *why* results were returned

---

## 3. Search Quality Enhancements

### 3.1 Hybrid Search (BM25 + Vector)

**Problem**: Pure vector search fails for:
- Exact identifier searches (`findUserById`)
- Rare technical terms (`SIGKILL`, `OAuth2`)
- Version-specific queries (`Python 3.11 match statement`)

**Solution**: Combine BM25 keyword search with vector semantic search

**Implementation**:
```python
# 1. Add BM25 index to SQLite
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  chunk_id, content, tokenize='porter'
);

# 2. Parallel search
vector_results = lance_store.query(query_vec, top_k=20)
keyword_results = fts_search(query_text, top_k=20)

# 3. Reciprocal Rank Fusion
final_results = fuse_results(
  vector_results, keyword_results,
  alpha=0.6  # Weight toward vector
)
```

**Impact**:
- **+30% precision** on identifier searches
- **+20% recall** on technical term queries
- **No latency increase** (parallel execution)

**Effort**: 2 weeks (1 backend, 1 testing/tuning)

---

### 3.2 Cross-Encoder Reranking

**Problem**: Initial KNN may return relevant chunks but in suboptimal order

**Solution**: Use a cross-encoder model to rerank top-K results

**Implementation**:
```python
# After initial retrieval
top_k_results = hybrid_search(query, top_k=20)

# Rerank with cross-encoder
reranked = reranker.rerank(
  query=query,
  documents=[r.text for r in top_k_results],
  top_k=5
)
```

**Options**:
- **ms-marco-MiniLM-L-6-v2**: Fast, local inference (~20ms)
- **bge-reranker-large**: Higher quality (~50ms)
- **Cohere Rerank API**: Highest quality, external cost

**Impact**:
- **+15-25% MRR** (Mean Reciprocal Rank)
- **Better first result**: Critical for LLM single-shot queries
- **Latency**: +20-50ms per query

**Effort**: 1 week (implementation + model selection)

---

### 3.3 Query Understanding & Routing

**Problem**: All queries treated the same way, regardless of intent

**Solution**: Classify query intent and route to specialized retrieval strategies

**Query Types**:
1. **Identifier search**: "find UserController class" → Exact match + fuzzy
2. **Concept search**: "authentication flow" → Broad vector search
3. **Example search**: "how to parse JSON" → Syntactic pattern matching
4. **Bug hunting**: "race condition in login" → Search + static analysis hints
5. **API usage**: "FastAPI dependency injection" → Docs + usage examples

**Implementation**:
```python
intent = classify_query(query)  # Light LLM call or rule-based

if intent == "identifier":
    # Exact match first, then fuzzy
    results = exact_search(query) or fuzzy_search(query)
elif intent == "concept":
    # Broad vector search with expansion
    results = vector_search(expand_query(query))
elif intent == "example":
    # Pattern-based search
    results = pattern_search(query)
```

**Impact**:
- **+20% precision** on identifier queries
- **+10% recall** on broad concept queries
- **Better UX**: Right strategy for the right query

**Effort**: 2-3 weeks (classifier + routing logic)

---

### 3.4 Result Diversity & Deduplication

**Problem**: Top-K may contain near-duplicate code snippets

**Solution**: Maximal Marginal Relevance (MMR) for diverse results

**Implementation**:
```python
def mmr_rerank(query_vec, candidates, lambda_param=0.7):
    """
    MMR = λ * Similarity(query, doc) - (1-λ) * max(Similarity(doc, selected))
    """
    selected = []
    while len(selected) < top_k:
        mmr_scores = []
        for cand in candidates:
            relevance = cosine_sim(query_vec, cand.vector)
            if selected:
                max_sim = max(cosine_sim(cand.vector, s.vector)
                              for s in selected)
                diversity = 1 - max_sim
            else:
                diversity = 1.0
            mmr = lambda_param * relevance + (1-lambda_param) * diversity
            mmr_scores.append((mmr, cand))

        # Pick best MMR candidate
        best = max(mmr_scores, key=lambda x: x[0])[1]
        selected.append(best)
        candidates.remove(best)

    return selected
```

**Impact**:
- **Better coverage**: Show diverse code patterns
- **+15% user satisfaction**: Less redundancy
- **Marginal latency**: +10-20ms for MMR calculation

**Effort**: 1 week (implementation + parameter tuning)

---

### 3.5 Negative Filtering & Boolean Queries

**Problem**: Can't exclude patterns (e.g., "authentication but not tests")

**Solution**: Support boolean operators and negative filters

**Syntax**:
```
"authentication AND login NOT test"
"FastAPI routes" -test -example
repo:api-server path:src/auth/* "token validation"
```

**Implementation**:
```python
# Parse query into components
parsed = parse_query(
  "authentication AND login NOT test"
)
# → {
#   "must_include": ["authentication", "login"],
#   "must_exclude": ["test"],
#   "filters": {}
# }

# Apply in hybrid search
vector_results = vector_search(parsed.must_include)
keyword_results = bm25_search(parsed.must_include)

# Post-filter exclusions
results = [r for r in fused_results
           if not any(term in r.text.lower()
                     for term in parsed.must_exclude)]
```

**Impact**:
- **+25% precision** on complex queries
- **Power user enablement**: Advanced query construction
- **LLM tooling**: Better programmatic search

**Effort**: 2 weeks (parser + query engine integration)

---

## 4. Context Building Improvements

### 4.1 Automatic Context Expansion

**Problem**: LLM receives isolated chunks without related code (imports, callees, callers)

**Solution**: Automatically expand chunks with relevant context

**Expansion Strategies**:

1. **Import Resolution**
   ```python
   # If chunk contains:
   from src.auth import validate_token

   # Automatically include:
   - Definition of validate_token
   - validate_token's docstring
   - validate_token's dependencies
   ```

2. **Call Graph Expansion**
   ```python
   # If chunk defines function foo():
   # Include:
   - Functions that call foo() (callers)
   - Functions that foo() calls (callees)
   - Shared utilities used by foo()
   ```

3. **Class Hierarchy**
   ```python
   # If chunk is a class method:
   # Include:
   - Parent class definitions
   - Overridden methods
   - Abstract method signatures
   ```

**Implementation**:
```python
def expand_chunk_context(chunk: Chunk) -> ExpandedChunk:
    context = {
        "primary": chunk,
        "imports": resolve_imports(chunk),
        "callers": find_callers(chunk),
        "callees": find_callees(chunk),
        "hierarchy": get_class_hierarchy(chunk),
    }

    # Budget: Add context until token limit
    expanded_text = build_context(
        context,
        max_tokens=2000,
        priority=["primary", "imports", "callees", "callers"]
    )

    return ExpandedChunk(
        text=expanded_text,
        metadata=context,
        token_count=count_tokens(expanded_text)
    )
```

**Impact**:
- **-50% "need more context" queries**: LLM gets complete picture
- **+30% task success rate**: LLM has everything it needs
- **+200 tokens/result**: Manageable cost increase

**Effort**: 3-4 weeks (call graph analysis + import resolution)

---

### 4.2 Code Graph & Dependency Awareness

**Problem**: Chunks returned independently without understanding relationships

**Solution**: Build and leverage a code knowledge graph

**Graph Schema**:
```
Nodes:
- File
- Function
- Class
- Method
- Module

Edges:
- imports
- calls
- inherits
- defines
- references
```

**Use Cases**:
1. **Dependency-aware search**: "Show me authentication and its dependencies"
2. **Impact analysis**: "What would break if I change this function?"
3. **Path finding**: "How does UserController connect to database?"
4. **Ranking boost**: Related code gets higher scores

**Implementation** (using SQLite Graph):
```sql
-- Nodes
CREATE TABLE code_nodes (
  id TEXT PRIMARY KEY,
  type TEXT,  -- 'function', 'class', 'module'
  name TEXT,
  file_path TEXT,
  start_line INT,
  repo TEXT
);

-- Edges
CREATE TABLE code_edges (
  from_id TEXT,
  to_id TEXT,
  edge_type TEXT,  -- 'calls', 'imports', 'inherits'
  PRIMARY KEY (from_id, to_id, edge_type)
);

-- Query: Find all callees
WITH RECURSIVE callees AS (
  SELECT to_id FROM code_edges
  WHERE from_id = ? AND edge_type = 'calls'
  UNION
  SELECT e.to_id FROM code_edges e
  JOIN callees ON e.from_id = callees.to_id
  WHERE e.edge_type = 'calls'
)
SELECT * FROM code_nodes WHERE id IN (SELECT to_id FROM callees);
```

**Impact**:
- **Contextual ranking**: Related code appears together
- **Better navigation**: LLM can explore relationships
- **Advanced queries**: "Show me the call path from A to B"

**Effort**: 4-5 weeks (AST analysis + graph building + query engine)

---

### 4.3 Adaptive Snippet Sizing

**Problem**: Fixed token windows (256-512) don't adapt to query needs

**Solution**: Dynamically size snippets based on query complexity and chunk type

**Sizing Strategy**:
```python
def adaptive_snippet_size(query: str, chunk: Chunk) -> int:
    # Base size
    base_size = 300

    # Query complexity
    if is_complex_query(query):  # Multiple concepts
        base_size += 200

    # Chunk type
    if chunk.symbol_kind == "class":
        # Classes need more context
        base_size += 300
    elif chunk.symbol_kind == "function":
        # Functions can be concise
        base_size += 100

    # Chunk importance (from reranker)
    if chunk.score > 0.9:  # Top result
        base_size += 200

    # Relationship density
    if chunk.num_references > 10:  # Heavily interconnected
        base_size += 150

    return min(base_size, 1500)  # Cap at 1500 tokens
```

**Impact**:
- **Better context**: Right amount for each result
- **Token efficiency**: Don't over-send simple results
- **Improved comprehension**: LLM gets complete logical units

**Effort**: 1-2 weeks (heuristics + testing)

---

### 4.4 Multi-File Context Assembly

**Problem**: LLM often needs multiple related files, receives them piecemeal

**Solution**: Assemble multi-file contexts based on relationships

**Assembly Strategies**:

1. **Feature-Based Assembly**
   ```python
   # Query: "authentication flow"
   # Return:
   - src/auth/routes.py (entry point)
   - src/auth/middleware.py (validation)
   - src/auth/models.py (data structures)
   - src/auth/utils.py (helpers)
   # Ordered by dependency flow
   ```

2. **Module-Based Assembly**
   ```python
   # Query: "User management"
   # Return entire module with:
   - __init__.py (exports)
   - models.py (User class)
   - services.py (business logic)
   - repository.py (data access)
   ```

**Implementation**:
```python
def assemble_multi_file_context(
    query: str,
    initial_chunks: List[Chunk],
    max_files: int = 5
) -> MultiFileContext:
    # Group chunks by file
    by_file = group_by(initial_chunks, key="path")

    # Analyze relationships
    graph = build_file_dependency_graph(by_file.keys())

    # Select related files
    selected_files = []
    for file in by_file.keys():
        related = graph.get_related_files(file, max_depth=2)
        selected_files.extend(related[:max_files])

    # Assemble in dependency order
    ordered = topological_sort(selected_files, graph)

    return MultiFileContext(
        files=ordered,
        primary_file=initial_chunks[0].path,
        dependency_graph=graph.subgraph(ordered)
    )
```

**Impact**:
- **-40% multi-turn queries**: LLM gets full picture upfront
- **Better understanding**: LLM sees module structure
- **Faster task completion**: Less back-and-forth

**Effort**: 3 weeks (file relationship analysis + assembly logic)

---

### 4.5 Hierarchical Result Organization

**Problem**: Flat list of chunks doesn't show structure

**Solution**: Return hierarchically organized results

**Structure**:
```json
{
  "results": [
    {
      "repo": "api-server",
      "relevance_score": 0.92,
      "modules": [
        {
          "path": "src/auth/",
          "files": [
            {
              "path": "src/auth/routes.py",
              "chunks": [
                {
                  "symbol": "login_handler",
                  "score": 0.95,
                  "text": "...",
                  "related": [
                    {"symbol": "validate_credentials", "path": "auth/utils.py"}
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**Impact**:
- **Better navigation**: LLM understands code organization
- **Contextual ranking**: Related code grouped together
- **Improved UX**: More structured, less overwhelming

**Effort**: 2 weeks (result transformer + MCP integration)

---

## 5. Performance & Speed Optimizations

### 5.1 Query Result Caching

**Problem**: Identical queries hit OpenAI + LanceDB every time

**Solution**: Multi-level caching with smart invalidation

**Cache Levels**:

1. **Embedding Cache** (L1)
   ```python
   # Cache query embeddings (1 hour TTL)
   embedding_cache = {
     "authentication": [0.1, 0.2, ...],  # 1536-d vector
     "login flow": [0.3, 0.1, ...],
   }

   # Hit rate: ~40% (common queries repeated)
   # Savings: ~$0.0001 per cached query
   ```

2. **Result Cache** (L2)
   ```python
   # Cache full search results (15 min TTL)
   result_cache = {
     "query:authentication|repo:api-server|top_k:5": [
       {chunk_id: "...", score: 0.92},
       ...
     ]
   }

   # Hit rate: ~25% (exact query repetition)
   # Latency: <10ms for cache hit
   ```

3. **Warm Cache** (L3)
   ```python
   # Pre-compute common queries
   COMMON_QUERIES = [
     "authentication", "error handling",
     "database connection", "API routes"
   ]

   # Refresh every 1 hour
   # Hit rate: ~10% (popular queries)
   ```

**Cache Invalidation**:
```python
# Invalidate on:
- Repository reindex
- File modification (via git hook)
- Manual flush via API
- TTL expiration
```

**Implementation**:
```python
import redis
from functools import lru_cache

class QueryCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.embedding_ttl = 3600  # 1 hour
        self.result_ttl = 900      # 15 min

    def get_embedding(self, query: str, model: str) -> Optional[List[float]]:
        key = f"embed:{model}:{hash(query)}"
        cached = self.redis.get(key)
        if cached:
            return json.loads(cached)
        return None

    def set_embedding(self, query: str, model: str, embedding: List[float]):
        key = f"embed:{model}:{hash(query)}"
        self.redis.setex(key, self.embedding_ttl, json.dumps(embedding))

    def get_results(self, query_hash: str) -> Optional[List[dict]]:
        key = f"results:{query_hash}"
        cached = self.redis.get(key)
        if cached:
            return json.loads(cached)
        return None
```

**Impact**:
- **3x faster**: Cached queries <100ms vs 300ms
- **50% cost reduction**: Skip OpenAI calls
- **Better UX**: Near-instant results for common queries

**Effort**: 1 week (Redis integration + cache logic)

---

### 5.2 Async & Parallel Query Processing

**Problem**: Sequential execution (embed → search → rerank)

**Solution**: Parallelize independent operations

**Current Flow** (Sequential, ~300ms):
```
Query → Embed (150ms) → Vector Search (50ms) → BM25 Search (waiting) → Fuse (20ms) → Rerank (50ms)
Total: 270ms
```

**Optimized Flow** (Parallel, ~180ms):
```
                  ┌→ Vector Search (50ms) ─┐
Query → Embed ────┤                         ├→ Fuse (20ms) → Rerank (50ms)
      (150ms)     └→ BM25 Search (40ms) ───┘
Total: 150ms + max(50ms, 40ms) + 20ms + 50ms = 220ms
```

**Implementation**:
```python
async def hybrid_search(query: str, top_k: int):
    # Embed query first (required for vector search)
    embedding = await embed_async(query)

    # Parallel searches
    vector_task = asyncio.create_task(
        vector_search_async(embedding, top_k=20)
    )
    bm25_task = asyncio.create_task(
        bm25_search_async(query, top_k=20)
    )

    # Wait for both
    vector_results, bm25_results = await asyncio.gather(
        vector_task, bm25_task
    )

    # Fuse and rerank
    fused = fuse_results(vector_results, bm25_results)
    reranked = await rerank_async(query, fused, top_k=top_k)

    return reranked
```

**Impact**:
- **-30% latency**: 300ms → 200ms p50
- **Better resource utilization**: CPU + I/O parallelism
- **Scalability**: Handle more concurrent queries

**Effort**: 2 weeks (async refactor + testing)

---

### 5.3 Approximate Nearest Neighbor Tuning

**Problem**: LanceDB default settings may not be optimal

**Solution**: Tune ANN parameters for speed/accuracy tradeoff

**LanceDB Parameters**:
```python
# Current (default)
lance_store.query(
    query_vec,
    metric="L2",
    # Default: nprobes=20, refine_factor=10
)

# Optimized for speed (95% recall, 2x faster)
lance_store.query(
    query_vec,
    metric="cosine",      # Slightly faster than L2
    nprobes=10,           # Fewer probes = faster
    refine_factor=5,      # Less refinement = faster
)

# Optimized for accuracy (99% recall, same speed)
lance_store.query(
    query_vec,
    metric="cosine",
    nprobes=30,
    refine_factor=20,
)
```

**Dynamic Tuning**:
```python
def adaptive_ann_params(query_type: str, top_k: int):
    if query_type == "identifier":
        # Need high precision
        return {"nprobes": 30, "refine_factor": 20}
    elif top_k <= 5:
        # Small result set, can afford accuracy
        return {"nprobes": 20, "refine_factor": 10}
    else:
        # Large result set, prioritize speed
        return {"nprobes": 10, "refine_factor": 5}
```

**Impact**:
- **-40% vector search time**: 50ms → 30ms
- **Configurable tradeoff**: Speed vs accuracy
- **Per-query optimization**: Right params for each query

**Effort**: 1 week (benchmarking + tuning)

---

### 5.4 Result Streaming

**Problem**: All results returned at once, even for large result sets

**Solution**: Stream results as they become available

**Streaming Flow**:
```python
async def search_stream(query: str, top_k: int = 20):
    # Emit initial results quickly
    embedding = await embed_async(query)

    # Stream vector results first (fastest)
    async for result in vector_search_stream(embedding, top_k):
        yield {
            "type": "partial",
            "result": result,
            "confidence": "medium"
        }

    # Then stream reranked results
    async for result in rerank_stream(query, all_results):
        yield {
            "type": "final",
            "result": result,
            "confidence": "high"
        }
```

**MCP Integration**:
```typescript
// MCP supports streaming via progress notifications
async function* searchKnowledge(query: string) {
  for await (const result of searchStream(query)) {
    yield {
      progress: {
        current: result.index,
        total: result.total
      },
      data: result
    };
  }
}
```

**Impact**:
- **Perceived latency**: Results appear in <100ms
- **Better UX**: LLM can start processing immediately
- **Interruptible**: Cancel if first results satisfy query

**Effort**: 2 weeks (streaming infrastructure + MCP integration)

---

### 5.5 Pre-computation & Materialized Views

**Problem**: Expensive computations repeated on every query

**Solution**: Pre-compute common aggregations and views

**Pre-computed Data**:

1. **Popular Symbols Index**
   ```python
   # Daily job: Find most-referenced symbols
   popular_symbols = compute_popular_symbols()
   # → ["UserController", "authenticate", "DatabaseConnection"]

   # Boost these in search results
   if chunk.symbol_name in popular_symbols:
       chunk.score *= 1.2
   ```

2. **Materialized Similarity Clusters**
   ```python
   # Offline: Cluster similar chunks
   clusters = kmeans_clustering(all_chunks, k=1000)

   # Online: Search within relevant clusters only
   relevant_clusters = find_clusters_for_query(query_vec)
   results = search_within_clusters(query_vec, relevant_clusters)
   # → 5x faster for large codebases
   ```

3. **Precomputed Call Graphs**
   ```python
   # Build call graph during indexing (not query time)
   call_graph = build_call_graph(repo)

   # Store in SQLite
   INSERT INTO call_edges (caller, callee) VALUES (?, ?)

   # Query: O(1) graph lookup vs O(n) AST parsing
   ```

**Impact**:
- **10x faster** graph queries
- **Reduced query load**: Shift work to indexing time
- **Better ranking**: Leverage global statistics

**Effort**: 2 weeks (materialization logic + maintenance)

---

## 6. LLM Usability & Integration

### 6.1 Structured Result Metadata

**Problem**: LLM receives unstructured text, hard to parse programmatically

**Solution**: Rich, structured metadata with every result

**Enhanced Result Schema**:
```typescript
interface EnhancedSearchResult {
  // Core
  chunk_id: string;
  score: number;

  // Content
  text: string;
  snippet: string;  // Highlighted excerpt
  token_count: number;

  // Location
  repo: string;
  path: string;
  start_line: number;
  end_line: number;
  url: string;  // vscode://file/... or GitHub URL

  // Semantics
  language: string;
  symbol_kind: "function" | "class" | "method" | "module";
  symbol_name: string;
  symbol_path: string;  // Full qualified name
  signature?: string;   // Function signature
  docstring?: string;   // Extracted docs

  // Relationships
  imports: string[];
  callees: string[];
  callers: string[];
  related_chunks: string[];  // chunk_ids

  // Quality Signals
  confidence: "high" | "medium" | "low";
  popularity: number;  // How often referenced
  recency: number;     // Days since last modified
  test_coverage?: number;

  // Provenance
  commit: string;
  branch: string;
  last_modified: string;
  author?: string;

  // Explanation
  match_reason: string;  // "Semantic match to 'authentication'"
  matched_terms: string[];  // ["auth", "login", "token"]

  // Actions
  suggested_followups: string[];  // Next queries to try
}
```

**Impact**:
- **Better LLM decision-making**: Rich signals inform choices
- **Programmatic filtering**: LLM can filter by metadata
- **Improved tracing**: Understand why results were returned

**Effort**: 1 week (schema + population)

---

### 6.2 Confidence Scores & Explanations

**Problem**: LLM doesn't know how much to trust each result

**Solution**: Multi-factor confidence scoring with explanations

**Confidence Calculation**:
```python
def calculate_confidence(chunk: Chunk, query: str) -> dict:
    factors = {}

    # Similarity score
    factors["similarity"] = chunk.score

    # Keyword overlap
    query_terms = set(tokenize(query))
    chunk_terms = set(tokenize(chunk.text))
    factors["keyword_overlap"] = len(query_terms & chunk_terms) / len(query_terms)

    # Recency
    days_old = (now() - chunk.last_modified).days
    factors["recency"] = 1.0 / (1 + days_old / 30)  # Decay over months

    # Popularity (how often referenced)
    factors["popularity"] = min(chunk.reference_count / 100, 1.0)

    # Code quality signals
    factors["has_tests"] = 1.0 if chunk.has_tests else 0.5
    factors["has_docs"] = 1.0 if chunk.docstring else 0.7

    # Weighted confidence
    confidence = (
        0.40 * factors["similarity"] +
        0.20 * factors["keyword_overlap"] +
        0.15 * factors["popularity"] +
        0.15 * factors["recency"] +
        0.10 * factors["has_tests"]
    )

    # Categorical confidence
    if confidence > 0.8:
        level = "high"
        explanation = "Strong semantic match with high code quality"
    elif confidence > 0.6:
        level = "medium"
        explanation = "Good semantic match, verify relevance"
    else:
        level = "low"
        explanation = "Weak match, consider refining query"

    return {
        "confidence": level,
        "score": confidence,
        "factors": factors,
        "explanation": explanation
    }
```

**Impact**:
- **Better LLM filtering**: Ignore low-confidence results
- **Transparency**: LLM understands ranking
- **Debugging**: Users can see why results were ranked

**Effort**: 1 week (factor collection + scoring)

---

### 6.3 Suggested Follow-up Queries

**Problem**: LLM doesn't know what else to search for

**Solution**: Suggest related queries based on initial results

**Suggestion Strategies**:

1. **Related Symbols**
   ```python
   # Query: "UserController"
   # Suggestions:
   - "UserService" (called by UserController)
   - "User model" (used by UserController)
   - "UserRepository" (database layer)
   ```

2. **Broader/Narrower Concepts**
   ```python
   # Query: "JWT validation"
   # Suggestions (broader):
   - "authentication flow"
   - "security middleware"

   # Suggestions (narrower):
   - "JWT expiration check"
   - "JWT signature verification"
   ```

3. **Related Files**
   ```python
   # Query returned: src/auth/routes.py
   # Suggestions:
   - "show me auth middleware"
   - "show me auth models"
   - "show me auth tests"
   ```

**Implementation**:
```python
def generate_followup_suggestions(
    query: str,
    results: List[Chunk]
) -> List[str]:
    suggestions = []

    # Extract symbols from results
    symbols = [r.symbol_name for r in results if r.symbol_name]

    # Find related symbols via call graph
    for symbol in symbols[:3]:
        related = graph.get_related_symbols(symbol, depth=1)
        suggestions.extend([f"show me {s}" for s in related[:2]])

    # Broaden query
    query_embedding = embed(query)
    broader_queries = find_similar_queries(
        query_embedding,
        filter=lambda q: len(q.split()) < len(query.split())
    )
    suggestions.extend(broader_queries[:2])

    # Related files
    files = list(set([r.path for r in results]))
    for file in files[:2]:
        module = extract_module(file)
        suggestions.append(f"show me {module}")

    return deduplicate(suggestions)[:5]
```

**Impact**:
- **Reduced query iterations**: LLM knows what to ask next
- **Better exploration**: Discover related code
- **Improved task success**: LLM follows breadcrumb trail

**Effort**: 2 weeks (suggestion engine + testing)

---

### 6.4 Query Templates & Shortcuts

**Problem**: LLM constructs queries from scratch every time

**Solution**: Pre-defined query templates for common patterns

**Template Examples**:
```python
QUERY_TEMPLATES = {
    "find_usage": "show me where {symbol} is used",
    "find_definition": "show me the definition of {symbol}",
    "find_tests": "show me tests for {symbol}",
    "find_similar": "find code similar to {symbol}",
    "trace_calls": "show me the call chain from {start} to {end}",
    "find_module": "show me all code in {module}",
    "find_pattern": "show me examples of {pattern}",
}

# MCP Tool
def search_from_template(
    template: str,
    **kwargs
) -> List[Chunk]:
    query = QUERY_TEMPLATES[template].format(**kwargs)
    return search(query)
```

**MCP Integration**:
```typescript
// Specialized tools for common patterns
{
  "name": "find_symbol_usage",
  "description": "Find where a symbol is used",
  "parameters": {
    "symbol": "string"
  }
}

{
  "name": "find_call_chain",
  "description": "Trace call path between two symbols",
  "parameters": {
    "from_symbol": "string",
    "to_symbol": "string"
  }
}
```

**Impact**:
- **Faster queries**: Templates optimize common cases
- **Better results**: Templates tuned for specific intent
- **Easier integration**: Higher-level abstractions for LLMs

**Effort**: 1 week (templates + MCP tools)

---

### 6.5 Context Budget Management

**Problem**: LLM context windows are limited, need smart allocation

**Solution**: Budget-aware result selection

**Budget Strategies**:

1. **Tiered Results**
   ```python
   def budget_aware_results(
       results: List[Chunk],
       budget: int = 8000  # tokens
   ) -> dict:
       """
       Tier 1 (30% budget): Top 2 results, full context
       Tier 2 (40% budget): Next 5 results, medium context
       Tier 3 (30% budget): Next 10 results, summaries only
       """
       allocated = {
           "tier1": {"budget": budget * 0.3, "results": []},
           "tier2": {"budget": budget * 0.4, "results": []},
           "tier3": {"budget": budget * 0.3, "results": []},
       }

       # Allocate tier 1 (full chunks + expansion)
       for chunk in results[:2]:
           expanded = expand_context(chunk, max_tokens=1200)
           if expanded.token_count <= allocated["tier1"]["budget"]:
               allocated["tier1"]["results"].append(expanded)
               allocated["tier1"]["budget"] -= expanded.token_count

       # Allocate tier 2 (chunks only, no expansion)
       for chunk in results[2:7]:
           if chunk.token_count <= allocated["tier2"]["budget"]:
               allocated["tier2"]["results"].append(chunk)
               allocated["tier2"]["budget"] -= chunk.token_count

       # Allocate tier 3 (summaries)
       for chunk in results[7:17]:
           summary = summarize(chunk, max_tokens=100)
           if summary.token_count <= allocated["tier3"]["budget"]:
               allocated["tier3"]["results"].append(summary)
               allocated["tier3"]["budget"] -= summary.token_count

       return allocated
   ```

2. **Progressive Disclosure**
   ```python
   # Initial query: Return summaries
   initial_results = [
       {"chunk_id": "abc", "summary": "Login handler...", "score": 0.95}
   ]

   # LLM requests details for specific chunks
   detailed_chunk = fetch_chunk_with_context("abc", max_tokens=2000)
   ```

**Impact**:
- **Optimized context usage**: Fit more results in same budget
- **Better prioritization**: Best results get most space
- **Reduced costs**: Less token usage overall

**Effort**: 1 week (budget allocation logic)

---

## 7. Cost & Efficiency Gains

### 7.1 Embedding Cost Reduction

**Problem**: Every query pays embedding cost (~$0.0001 per query)

**Solutions**:

1. **Query Embedding Cache** (covered in 5.1)
   - **Savings**: 50% reduction for cached queries
   - **ROI**: $500/month for 5M queries

2. **Batch Query Processing**
   ```python
   # Instead of: 10 sequential queries = 10 API calls
   # Do: Batch 10 queries = 1 API call

   async def batch_embed(queries: List[str]) -> List[List[float]]:
       # Single API call for up to 100 queries
       response = await openai_client.embeddings.create(
           input=queries,
           model="text-embedding-3-small"
       )
       return [item.embedding for item in response.data]
   ```
   - **Savings**: 10x fewer API calls
   - **Latency**: Amortized cost

3. **Smaller Model for Simple Queries**
   ```python
   def select_embedding_model(query: str) -> str:
       # Simple identifier queries → small model
       if is_identifier_query(query):
           return "text-embedding-3-small"  # 1536-d, $0.00002/1K tokens

       # Complex semantic queries → large model
       else:
           return "text-embedding-3-large"  # 3072-d, $0.00013/1K tokens
   ```
   - **Savings**: 84% cost reduction on simple queries
   - **Quality**: Minimal impact on identifier searches

**Total Impact**:
- **70% cost reduction**: $1000 → $300 per 10M queries
- **Maintained quality**: Smart model selection
- **Better margins**: More affordable at scale

**Effort**: 1 week (batching + model selection)

---

### 7.2 Incremental Indexing Improvements

**Problem**: Configuration changes force full reindex

**Solution**: Smarter incremental updates

**Selective Reindexing**:
```python
def incremental_reindex(
    repo: Repository,
    changes: List[ConfigChange]
) -> None:
    """
    Only reindex what changed:
    - New files → index them
    - Modified files → reindex them
    - Deleted files → prune them
    - Config changes → selective reindex
    """

    if "chunk_size" in changes:
        # Only reindex if chunk boundaries would change
        affected_files = find_files_with_changed_chunks(repo, changes)
        reindex_files(affected_files)

    elif "embedding_model" in changes:
        # Full reindex needed (different vector dimensions)
        full_reindex(repo)

    elif "ignore_patterns" in changes:
        # Remove newly-ignored files, index newly-included
        removed = find_newly_ignored(repo, changes)
        added = find_newly_included(repo, changes)
        prune_files(removed)
        index_files(added)
```

**Impact**:
- **10x faster updates**: Minutes instead of hours
- **Cost savings**: Only pay for changed embeddings
- **Better UX**: Config changes are instant

**Effort**: 2 weeks (change detection + selective reindex)

---

### 7.3 Deduplication Enhancements

**Problem**: Current dedup only catches exact matches

**Solution**: Near-duplicate detection

**Near-Duplicate Detection**:
```python
from sklearn.feature_extraction.text import MinHashLSH

def detect_near_duplicates(chunks: List[Chunk], threshold=0.9) -> List[Set[str]]:
    """
    Find chunks that are >90% similar using MinHash LSH.
    Returns groups of near-duplicate chunk IDs.
    """
    lsh = MinHashLSH(threshold=threshold)

    # Add all chunks to LSH index
    for chunk in chunks:
        minhash = compute_minhash(chunk.text)
        lsh.insert(chunk.id, minhash)

    # Find duplicates
    duplicate_groups = []
    seen = set()

    for chunk in chunks:
        if chunk.id in seen:
            continue

        # Find near-duplicates
        minhash = compute_minhash(chunk.text)
        candidates = lsh.query(minhash)

        if len(candidates) > 1:
            duplicate_groups.append(set(candidates))
            seen.update(candidates)

    return duplicate_groups
```

**Dedup Strategies**:
```python
# For near-duplicates, keep only:
# 1. Most recent version
# 2. Version with best docstring
# 3. Version with most references

def select_canonical_chunk(group: Set[str]) -> str:
    chunks = [get_chunk(id) for id in group]

    # Score each chunk
    scores = []
    for chunk in chunks:
        score = (
            0.4 * recency_score(chunk) +
            0.3 * documentation_score(chunk) +
            0.3 * reference_score(chunk)
        )
        scores.append((score, chunk.id))

    # Return best
    return max(scores)[1]
```

**Impact**:
- **-20% storage**: Fewer redundant chunks
- **-20% embedding cost**: Don't embed duplicates
- **Better results**: No duplicate results

**Effort**: 2 weeks (LSH implementation + testing)

---

### 7.4 Smart Chunking Strategies

**Problem**: Fixed chunking misses logical boundaries, creates partial contexts

**Solution**: Semantic-aware chunking

**Improvements**:

1. **Respect Function Boundaries**
   ```python
   # Current: May split functions mid-way
   def long_function():
       # 500 lines
       ...

   # New: Keep functions intact, split only at major sections
   def smart_chunk_function(func_node):
       if func.line_count < max_chunk_size:
           # Keep entire function
           return [Chunk(func.text, ...)]
       else:
           # Split at logical sections (control flow, comments)
           sections = detect_logical_sections(func)
           return [Chunk(section, ...) for section in sections]
   ```

2. **Include Critical Context**
   ```python
   # Always include in chunks:
   # - Function signature
   # - Docstring
   # - Import statements (at top)
   # - Class definition (if method)

   def build_chunk_with_context(node):
       chunk_text = (
           get_imports(node) + "\n\n" +
           get_class_definition(node) + "\n\n" +
           get_signature(node) + "\n" +
           get_docstring(node) + "\n" +
           get_body(node)
       )
       return chunk_text
   ```

3. **Overlap at Semantic Boundaries**
   ```python
   # Current: Fixed token overlap (64 tokens)
   # New: Overlap at logical boundaries

   def semantic_overlap(chunks: List[Chunk]) -> List[Chunk]:
       """Ensure overlap includes complete statements."""
       for i in range(len(chunks) - 1):
           # Find last complete statement in chunk[i]
           last_stmt = find_last_complete_statement(chunks[i])

           # Start chunk[i+1] from this statement
           chunks[i+1].prepend(last_stmt)

       return chunks
   ```

**Impact**:
- **+15% chunk quality**: More self-contained chunks
- **+10% search precision**: Better semantic boundaries
- **-5% chunks**: Fewer, higher-quality chunks

**Effort**: 3 weeks (AST analysis + chunking logic)

---

### 7.5 Vector Storage Optimization

**Problem**: LanceDB storage grows large for big codebases

**Solution**: Optimize vector storage and indexing

**Optimizations**:

1. **Quantization**
   ```python
   # Reduce vector precision: float32 → float16
   # Savings: 50% storage, minimal quality loss

   lance_store.create_table(
       "chunks_small_quantized",
       schema=pa.schema([
           ("id", pa.string()),
           ("vector", pa.list_(pa.float16(), 1536)),  # Half precision
           ...
       ])
   )
   ```

2. **Dimension Reduction**
   ```python
   # For large repos, reduce dimensions via PCA
   from sklearn.decomposition import PCA

   # Reduce 1536 → 768 dimensions (50% storage)
   pca = PCA(n_components=768)
   reduced_vectors = pca.fit_transform(original_vectors)

   # Trade-off: ~5% recall loss, 2x storage savings
   ```

3. **Tiered Storage**
   ```python
   # Hot: Recent/popular chunks (full precision)
   # Warm: Older chunks (quantized)
   # Cold: Rarely accessed (compressed, off-index)

   def tier_chunk(chunk: Chunk) -> str:
       if chunk.last_accessed > 7_days_ago:
           return "hot"
       elif chunk.last_accessed > 90_days_ago:
           return "warm"
       else:
           return "cold"
   ```

**Impact**:
- **-50% storage costs**: Quantization + tiering
- **Minimal quality loss**: <5% recall reduction
- **Faster queries**: Smaller index = faster search

**Effort**: 2 weeks (quantization + tiering logic)

---

## 8. Evaluation & Measurement

### 8.1 Retrieval Quality Metrics

**Problem**: No systematic way to measure search quality

**Solution**: Automated evaluation framework

**Metrics to Track**:

1. **Precision@K**
   ```python
   # What % of top-K results are relevant?
   def precision_at_k(results: List[Chunk], k: int, ground_truth: Set[str]) -> float:
       top_k = results[:k]
       relevant = [r for r in top_k if r.chunk_id in ground_truth]
       return len(relevant) / k
   ```

2. **Recall@K**
   ```python
   # What % of relevant docs are in top-K?
   def recall_at_k(results: List[Chunk], k: int, ground_truth: Set[str]) -> float:
       top_k = results[:k]
       relevant = [r for r in top_k if r.chunk_id in ground_truth]
       return len(relevant) / len(ground_truth)
   ```

3. **Mean Reciprocal Rank (MRR)**
   ```python
   # Average position of first relevant result
   def mrr(results: List[Chunk], ground_truth: Set[str]) -> float:
       for i, result in enumerate(results):
           if result.chunk_id in ground_truth:
               return 1.0 / (i + 1)
       return 0.0
   ```

4. **Normalized Discounted Cumulative Gain (NDCG)**
   ```python
   # Weighted metric considering result position
   def ndcg(results: List[Chunk], relevance_scores: dict) -> float:
       dcg = sum(
           relevance_scores.get(r.chunk_id, 0) / math.log2(i + 2)
           for i, r in enumerate(results)
       )
       ideal_dcg = sum(
           score / math.log2(i + 2)
           for i, score in enumerate(sorted(relevance_scores.values(), reverse=True))
       )
       return dcg / ideal_dcg if ideal_dcg > 0 else 0.0
   ```

**Evaluation Dataset**:
```python
# Create test queries with ground truth
TEST_QUERIES = [
    {
        "query": "JWT token validation",
        "ground_truth": ["chunk_123", "chunk_456"],
        "relevance": {"chunk_123": 3, "chunk_456": 2, "chunk_789": 1}
    },
    {
        "query": "database connection pooling",
        "ground_truth": ["chunk_abc", "chunk_def"],
        "relevance": {"chunk_abc": 3, "chunk_def": 2}
    },
    # ... 100+ queries
]

# Run evaluation
for test in TEST_QUERIES:
    results = search(test["query"])
    metrics = {
        "p@5": precision_at_k(results, 5, test["ground_truth"]),
        "r@10": recall_at_k(results, 10, test["ground_truth"]),
        "mrr": mrr(results, test["ground_truth"]),
        "ndcg": ndcg(results, test["relevance"])
    }
    log_metrics(test["query"], metrics)
```

**Impact**:
- **Data-driven optimization**: Measure improvement
- **Regression detection**: Catch quality degradation
- **A/B testing**: Compare retrieval strategies

**Effort**: 2 weeks (test set creation + evaluation framework)

---

### 8.2 LLM Task Success Metrics

**Problem**: Don't know if search results actually help LLMs complete tasks

**Solution**: End-to-end task evaluation

**Task Benchmarks**:
```python
LLM_TASKS = [
    {
        "name": "explain_function",
        "setup": "Given a function name, explain what it does",
        "query": "explain UserController.login",
        "success_criteria": "Explanation includes: auth flow, token generation, error handling"
    },
    {
        "name": "find_bug",
        "setup": "Find the bug in authentication logic",
        "query": "why does login fail with expired tokens",
        "success_criteria": "Identifies missing expiration check"
    },
    {
        "name": "generate_test",
        "setup": "Generate a test for a function",
        "query": "write a test for UserService.createUser",
        "success_criteria": "Test covers happy path + error cases"
    },
]

# Evaluation
def evaluate_llm_task(task: dict) -> bool:
    # 1. LLM searches with Dolphin
    search_results = search(task["query"])

    # 2. LLM completes task using results
    llm_output = llm.complete_task(task["setup"], search_results)

    # 3. Check if success criteria met
    success = evaluate_criteria(llm_output, task["success_criteria"])

    # 4. Track metrics
    return {
        "task": task["name"],
        "success": success,
        "num_queries": llm.num_queries,
        "total_latency": llm.total_time,
        "tokens_used": count_tokens(search_results)
    }
```

**Metrics**:
- **Task Success Rate**: % of tasks completed successfully
- **Queries per Task**: How many searches needed
- **Time to Success**: Total time from query to completion
- **Context Efficiency**: Tokens used / task complexity

**Impact**:
- **Real-world validation**: Measure actual LLM performance
- **Holistic improvement**: Optimize for task success, not just search metrics
- **User-aligned**: Metrics match user goals

**Effort**: 3 weeks (task creation + LLM integration + evaluation)

---

### 8.3 Performance Benchmarking

**Problem**: No systematic performance tracking

**Solution**: Continuous performance monitoring

**Benchmarks**:
```python
PERFORMANCE_BENCHMARKS = [
    {"name": "simple_query", "query": "authentication", "expected_p50": 100},
    {"name": "complex_query", "query": "trace JWT validation flow", "expected_p50": 300},
    {"name": "cold_cache", "query": "new_query_" + random_string(), "expected_p50": 400},
    {"name": "hot_cache", "query": "authentication", "repeat": 10, "expected_p50": 50},
]

def run_performance_suite():
    for benchmark in PERFORMANCE_BENCHMARKS:
        latencies = []
        for _ in range(100):
            start = time.time()
            results = search(benchmark["query"])
            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)

        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        p99 = percentile(latencies, 99)

        # Alert if regression
        if p50 > benchmark["expected_p50"] * 1.2:
            alert(f"Performance regression: {benchmark['name']} p50={p50}ms")

        log_metrics({
            "benchmark": benchmark["name"],
            "p50": p50,
            "p95": p95,
            "p99": p99
        })
```

**Tracked Metrics**:
- **Latency** (p50, p95, p99)
- **Throughput** (queries/second)
- **Resource usage** (CPU, memory, disk I/O)
- **Cache hit rate**
- **API cost** (embedding calls)

**Impact**:
- **Prevent regressions**: Catch performance degradation
- **Capacity planning**: Know when to scale
- **Optimization targets**: Identify bottlenecks

**Effort**: 1 week (benchmark suite + monitoring)

---

### 8.4 Cost Tracking & Optimization

**Problem**: Don't track costs per query/user/repo

**Solution**: Comprehensive cost analytics

**Cost Breakdown**:
```python
class CostTracker:
    def __init__(self):
        self.embedding_costs = defaultdict(float)
        self.storage_costs = defaultdict(float)
        self.compute_costs = defaultdict(float)

    def track_query(self, query: str, user: str, repo: str):
        # Embedding cost
        if not in_cache(query):
            tokens = count_tokens(query)
            cost = tokens * EMBEDDING_COST_PER_TOKEN
            self.embedding_costs[user] += cost
            self.embedding_costs[repo] += cost

        # Compute cost (infrastructure)
        compute = estimate_compute_cost(query_complexity)
        self.compute_costs[user] += compute

    def track_index(self, repo: str, chunks: int):
        # Embedding cost
        total_tokens = sum(chunk.token_count for chunk in chunks)
        cost = total_tokens * EMBEDDING_COST_PER_TOKEN
        self.embedding_costs[repo] += cost

        # Storage cost
        storage_mb = estimate_storage(chunks)
        monthly_cost = storage_mb * STORAGE_COST_PER_MB
        self.storage_costs[repo] += monthly_cost

    def generate_report(self, period="month"):
        return {
            "total_cost": sum(self.embedding_costs.values()) +
                         sum(self.storage_costs.values()) +
                         sum(self.compute_costs.values()),
            "by_user": self.get_costs_by_user(),
            "by_repo": self.get_costs_by_repo(),
            "breakdown": {
                "embedding": sum(self.embedding_costs.values()),
                "storage": sum(self.storage_costs.values()),
                "compute": sum(self.compute_costs.values())
            }
        }
```

**Optimization Recommendations**:
```python
def recommend_optimizations(costs: dict) -> List[str]:
    recommendations = []

    # High embedding costs
    if costs["embedding"] > costs["total"] * 0.7:
        recommendations.append(
            "Enable query caching to reduce embedding API calls"
        )

    # Large storage costs
    if costs["storage"] > costs["total"] * 0.5:
        recommendations.append(
            "Consider vector quantization to reduce storage by 50%"
        )

    # Expensive repos
    expensive_repos = [
        repo for repo, cost in costs["by_repo"].items()
        if cost > threshold
    ]
    if expensive_repos:
        recommendations.append(
            f"Review chunking config for: {expensive_repos}"
        )

    return recommendations
```

**Impact**:
- **Cost visibility**: Know where money goes
- **Budget management**: Set limits per user/repo
- **Optimization guidance**: Data-driven decisions

**Effort**: 1 week (tracking + reporting)

---

## 9. Implementation Roadmap

### 9.1 Phased Rollout (6 Months)

#### Phase 1: Search Quality (Months 1-2)

**Priority 1: High-Impact, Low-Effort**
- [ ] **Hybrid Search (BM25 + Vector)** - 2 weeks
  - Impact: +30% precision on identifier queries
  - Implementation: SQLite FTS5 + parallel search

- [ ] **Result Diversity (MMR)** - 1 week
  - Impact: +15% user satisfaction, less redundancy
  - Implementation: Post-processing rerank

- [ ] **Query Caching** - 1 week
  - Impact: 3x faster, 50% cost reduction
  - Implementation: Redis cache layer

**Priority 2: Medium-Impact, Medium-Effort**
- [ ] **Cross-Encoder Reranking** - 1 week
  - Impact: +20% MRR
  - Implementation: Local model inference

- [ ] **Negative Filtering** - 2 weeks
  - Impact: +25% precision on complex queries
  - Implementation: Query parser + filter logic

**Deliverable**:
- 50% improvement in search quality metrics (P@5, MRR)
- 50% reduction in embedding costs
- <200ms p50 latency for cached queries

---

#### Phase 2: Context Building (Months 2-3)

**Priority 1: High-Impact, Medium-Effort**
- [ ] **Automatic Context Expansion** - 3 weeks
  - Impact: -50% "need more context" queries
  - Implementation: Import resolution + call graph

- [ ] **Adaptive Snippet Sizing** - 1 week
  - Impact: Better token efficiency
  - Implementation: Dynamic sizing heuristics

- [ ] **Structured Result Metadata** - 1 week
  - Impact: Better LLM decision-making
  - Implementation: Enhanced schema + population

**Priority 2: Advanced Features**
- [ ] **Code Graph & Dependencies** - 4 weeks
  - Impact: Contextual ranking, advanced queries
  - Implementation: AST analysis + graph database

- [ ] **Multi-File Context Assembly** - 3 weeks
  - Impact: -40% multi-turn queries
  - Implementation: File relationship analysis

**Deliverable**:
- 2x improvement in LLM task success rate
- 40% reduction in multi-turn queries
- Hierarchical result organization

---

#### Phase 3: Performance & Speed (Month 4)

**Priority 1: Latency Reduction**
- [ ] **Async & Parallel Processing** - 2 weeks
  - Impact: -30% latency (300ms → 200ms)
  - Implementation: Async refactor

- [ ] **ANN Tuning** - 1 week
  - Impact: -40% vector search time
  - Implementation: LanceDB parameter optimization

- [ ] **Result Streaming** - 2 weeks
  - Impact: Perceived latency <100ms
  - Implementation: Streaming infrastructure

**Priority 2: Scalability**
- [ ] **Pre-computation & Materialized Views** - 2 weeks
  - Impact: 10x faster graph queries
  - Implementation: Offline computation

**Deliverable**:
- <100ms p50 latency for common queries
- 2x throughput (queries/second)
- Streaming results for better UX

---

#### Phase 4: LLM Integration (Month 5)

**Priority 1: Usability**
- [ ] **Confidence Scores & Explanations** - 1 week
  - Impact: Better LLM filtering
  - Implementation: Multi-factor confidence

- [ ] **Suggested Follow-ups** - 2 weeks
  - Impact: Reduced query iterations
  - Implementation: Suggestion engine

- [ ] **Query Templates** - 1 week
  - Impact: Faster, more accurate queries
  - Implementation: Template library + MCP tools

- [ ] **Context Budget Management** - 1 week
  - Impact: Optimized token usage
  - Implementation: Tiered results

**Deliverable**:
- 5 new specialized MCP tools
- 30% reduction in query iterations
- Smart context budget allocation

---

#### Phase 5: Cost Optimization (Month 5-6)

**Priority 1: Cost Reduction**
- [ ] **Batch Query Processing** - 1 week
  - Impact: 10x fewer API calls
  - Implementation: Batching logic

- [ ] **Model Selection** - 1 week
  - Impact: 84% cost on simple queries
  - Implementation: Query classification

- [ ] **Near-Duplicate Detection** - 2 weeks
  - Impact: -20% storage, -20% embedding cost
  - Implementation: MinHash LSH

- [ ] **Vector Quantization** - 2 weeks
  - Impact: -50% storage
  - Implementation: Float16 quantization

**Priority 2: Indexing Efficiency**
- [ ] **Incremental Reindexing** - 2 weeks
  - Impact: 10x faster updates
  - Implementation: Change detection

- [ ] **Smart Chunking** - 3 weeks
  - Impact: +15% chunk quality, -5% volume
  - Implementation: Semantic boundaries

**Deliverable**:
- 70% reduction in total costs
- 50% storage savings
- 10x faster configuration updates

---

#### Phase 6: Evaluation & Polish (Month 6)

**Priority 1: Measurement**
- [ ] **Retrieval Quality Metrics** - 2 weeks
  - Implementation: Evaluation framework + test set

- [ ] **LLM Task Success Metrics** - 3 weeks
  - Implementation: Task benchmarks + LLM integration

- [ ] **Performance Benchmarking** - 1 week
  - Implementation: Continuous monitoring

- [ ] **Cost Tracking** - 1 week
  - Implementation: Analytics dashboard

**Priority 2: Advanced Features**
- [ ] **Query Understanding** - 3 weeks
  - Impact: +20% precision via routing
  - Implementation: Classifier + routing

**Deliverable**:
- Comprehensive evaluation framework
- Automated regression detection
- Cost optimization dashboard
- Query intent routing

---

### 9.2 Quick Wins (First 2 Weeks)

**Week 1:**
1. Query caching (embedding + results)
2. Result diversity (MMR)
3. Adaptive snippet sizing

**Week 2:**
1. Hybrid search (BM25 + vector)
2. Structured metadata enrichment
3. Performance benchmarking

**Impact**:
- 2x faster queries (caching)
- +30% search precision (hybrid)
- Better LLM integration (metadata)

---

### 9.3 Resource Requirements

**Engineering**:
- **Backend Engineer (Full-time)**: Months 1-6
  - Search quality, context building, performance

- **ML Engineer (50%)**: Months 1-3, 5-6
  - Reranking, embeddings, evaluation

- **Infrastructure Engineer (25%)**: Months 3-4, 6
  - Caching, async processing, monitoring

**Infrastructure**:
- **Redis**: Query caching (~$50/month)
- **Additional LanceDB storage**: Quantized vectors (~$20/month)
- **Monitoring**: Prometheus + Grafana (self-hosted)
- **Reranking model**: Local inference (no cost) or Cohere API (~$100/month)

**Total Investment**: ~$80K (6 months, 1.75 FTE engineers)

---

### 9.4 Risk Mitigation

**Technical Risks**:
1. **Hybrid search integration complexity**
   - Mitigation: Start with simple BM25, iterate
   - Fallback: Pure vector search still works

2. **Performance regression from new features**
   - Mitigation: Continuous benchmarking, feature flags
   - Rollback: Easy to disable new features

3. **Cost overruns from context expansion**
   - Mitigation: Token budgets, tiered results
   - Monitoring: Cost tracking per query

**Product Risks**:
1. **Features don't improve LLM task success**
   - Mitigation: End-to-end task evaluation
   - Pivot: Focus on metrics that matter

2. **Complexity overwhelms users**
   - Mitigation: Smart defaults, progressive disclosure
   - Simplify: Hide advanced features behind flags

**Operational Risks**:
1. **Team capacity constraints**
   - Mitigation: Phased rollout, prioritize quick wins
   - Adjust: Extend timeline if needed

---

## 10. Success Metrics

### 10.1 Primary Metrics (North Star)

**Goal**: Double the value Dolphin provides to LLMs in 6 months

| Metric | Baseline | 3-Month Target | 6-Month Target |
|--------|----------|----------------|----------------|
| **Search Precision@5** | 60% | 75% | 85% |
| **LLM Task Success Rate** | 40% | 60% | 80% |
| **Query Latency (p50)** | 300ms | 200ms | 100ms |
| **Cost per Query** | $0.0002 | $0.0001 | $0.00006 |
| **Context Efficiency** | 1000 tokens/task | 700 tokens/task | 500 tokens/task |

---

### 10.2 Secondary Metrics

**Search Quality**:
- Mean Reciprocal Rank (MRR): 0.65 → 0.85
- Recall@10: 70% → 90%
- Result diversity: 50% unique → 80% unique
- Query understanding accuracy: N/A → 85%

**Performance**:
- Queries/second: 10 → 30
- Cache hit rate: 0% → 40%
- Latency p95: 800ms → 300ms
- Latency p99: 2s → 600ms

**Cost**:
- Embedding cost per 1000 queries: $0.20 → $0.06
- Storage cost per 1M chunks: $50 → $25
- Total cost per user/month: $5 → $2

**User Experience**:
- Queries per task: 3 → 1.5
- "Need more context" rate: 50% → 20%
- Follow-up query suggestions used: N/A → 30%
- Confidence in results: N/A → 4.2/5

---

### 10.3 Leading Indicators

**Weekly Tracking**:
- Search query volume
- Cache hit rate
- Average results per query
- LLM follow-up query rate

**Monthly Tracking**:
- Embedding API costs
- Storage growth rate
- User-reported issues
- Feature adoption rate

---

## 11. Long-Term Vision (12-24 Months)

### Beyond the 6-Month Roadmap

**Advanced Capabilities**:
1. **Multi-modal code search**: Search by natural language, code examples, diagrams
2. **Proactive suggestions**: "You might also need..." based on context
3. **Cross-repository intelligence**: Connect related code across codebases
4. **Learning from usage**: Improve based on LLM query patterns
5. **Natural language code generation**: Generate code from search results

**Platform Evolution**:
1. **Team collaboration**: Shared search history, curated results
2. **Custom ranking models**: Fine-tune retrievers per organization
3. **Integration ecosystem**: Plugins for GitHub, GitLab, Jira, etc.
4. **Enterprise features**: SSO, audit logs, compliance

**Research Directions**:
1. **Better code representations**: Graph neural networks, learned embeddings
2. **Query reformulation**: Automatically improve ambiguous queries
3. **Result explanation**: Why was this returned? What makes it relevant?
4. **Personalization**: Adapt to individual user or team preferences

---

## 12. Conclusion

This roadmap represents a comprehensive plan to **double the value Dolphin provides to LLMs** through systematic improvements in search quality, context building, performance, usability, and cost efficiency.

**Key Takeaways**:

1. **Search Quality**: Hybrid search, reranking, and query understanding will dramatically improve relevance
2. **Context Building**: Automatic expansion and code graph awareness will reduce "need more context" queries by 50%
3. **Performance**: Caching, async processing, and streaming will achieve <100ms p50 latency
4. **LLM Integration**: Structured metadata, confidence scores, and follow-up suggestions will make Dolphin easier to use
5. **Cost Efficiency**: Smart caching, batching, and quantization will reduce costs by 70%

**Next Steps**:

1. **Review & refine**: Team discussion on priorities and trade-offs
2. **Quick wins**: Implement caching, MMR, hybrid search in first 2 weeks
3. **Establish baselines**: Run evaluation framework to measure current state
4. **Iterative development**: Ship incrementally, measure, adjust
5. **User feedback**: Engage with LLM developers to validate improvements

**Success Criteria**:

By the end of 6 months, Dolphin should:
- Return the *right* code 85% of the time (Precision@5)
- Enable LLMs to complete tasks 80% of the time (Task Success Rate)
- Respond in <100ms for common queries (p50 latency)
- Cost 70% less per query ($0.0002 → $0.00006)
- Require 50% fewer follow-up queries (better context)

**The opportunity is clear: By making Dolphin smarter, faster, and more cost-effective, we can fundamentally improve how LLMs interact with code, unlocking new levels of developer productivity.**

---

**Document Metadata**:
- **Last Updated**: 2025-10-30
- **Version**: 1.0
- **Status**: Draft for Review
- **Feedback**: Please add comments, suggestions, and alternative approaches
- **Related Docs**: [ARCHITECTURE.md](ARCHITECTURE.md), [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md), [UX_POLISH.md](UX_POLISH.md)
