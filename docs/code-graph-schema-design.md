# Code Graph Database Schema Design

**Version**: 1.0.0  
**Date**: 2025-11-08  
**Status**: Design Phase  
**Priority**: Navigation queries (callsites, implementations, dependency tracing)

---

## Executive Summary

This document defines a comprehensive code graph database schema designed from first principles to enrich Dolphin's semantic retrieval engine with rich code relationship data. The schema prioritizes **navigation queries** (finding callsites, implementations, and tracing dependencies) while maintaining scalability and performance.

### Design Goals

1. **Fast navigation queries**: Find "who calls this?", "what implements this?", "what depends on this?" in <50ms
2. **Cross-language support**: Unified schema for Python, TypeScript, SQL, Svelte, and future languages
3. **Cross-repo analysis**: Track relationships that span multiple repositories
4. **Incremental updates**: Support efficient updates when code changes
5. **Semantic integration**: Enrich search results with graph context without performance degradation
6. **Scalability**: Handle 1M+ nodes and 10M+ edges on a MacBook Pro M4

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Database Technology Choice](#database-technology-choice)
- [Core Schema Design](#core-schema-design)
- [Indexing Strategy](#indexing-strategy)
- [Query Patterns](#query-patterns)
- [Integration with Semantic Search](#integration-with-semantic-search)
- [Storage Estimates](#storage-estimates)
- [Implementation Plan](#implementation-plan)

---

## Architecture Overview

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Indexing Pipeline                         │
└─────────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
    ▼                         ▼                         ▼
┌─────────┐            ┌──────────┐            ┌──────────────┐
│ SQLite  │            │ LanceDB  │            │ Graph Store  │
│Metadata │            │ Vectors  │            │ (SQLite)     │
└─────────┘            └──────────┘            └──────────────┘
    │                         │                         │
    └─────────────────────────┼─────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Search Results  │
                    │  + Graph Context │
                    └──────────────────┘
```

### Graph Database Choice: SQLite

**Rationale for SQLite over dedicated graph DBs:**

1. **Simplicity**: Already using SQLite for metadata - no new dependencies
2. **Performance**: With proper indexing, SQLite can handle navigation queries efficiently
3. **Transactions**: ACID guarantees for graph consistency
4. **Size**: Proven to scale to 1M+ nodes on embedded systems
5. **Portability**: Same data directory, single file, no network overhead
6. **SQL Power**: Recursive CTEs for graph traversal, window functions for ranking

**Trade-offs:**
- ❌ No native graph query language (Cypher, Gremlin)
- ❌ Manual optimization of graph traversals
- ✅ Familiar query patterns, mature optimizer
- ✅ Zero operational overhead
- ✅ Easy integration with existing codebase

**Future migration path**: If we need dedicated graph DB (Neo4j, TigerGraph), schema can be translated directly.

---

## Core Schema Design

### Entity-Relationship Model

```
┌──────────────┐
│   Repos      │
└──────┬───────┘
       │
       │ 1:N
       ▼
┌──────────────┐       ┌──────────────────┐
│   Files      │◄──────│  Code Nodes      │
└──────┬───────┘  N:1  └──────┬───────────┘
       │                       │
       │ 1:N                   │ N:M
       ▼                       ▼
┌──────────────┐       ┌──────────────────┐
│   Chunks     │       │   Code Edges     │
└──────────────┘       └──────────────────┘
```

### Table: `code_nodes`

Stores all code entities (functions, classes, tables, components, etc.)

```sql
CREATE TABLE code_nodes (
  -- Identity
  id TEXT PRIMARY KEY,  -- UUID for stable references
  node_type TEXT NOT NULL,  -- 'function', 'class', 'method', 'table', 'view', 'component', 'interface', 'type', 'enum'
  
  -- Naming
  name TEXT NOT NULL,  -- Simple name (e.g., "calculate_total")
  qualified_name TEXT NOT NULL,  -- Full path (e.g., "myapp.utils.math.calculate_total")
  
  -- Location
  repo_id INTEGER NOT NULL,
  file_id INTEGER NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  
  -- Language context
  language TEXT NOT NULL,  -- 'python', 'typescript', 'sql', 'svelte'
  
  -- Optional metadata (language-specific)
  signature TEXT,  -- Function signature or type definition
  docstring TEXT,  -- Documentation/comments
  visibility TEXT,  -- 'public', 'private', 'protected', 'exported'
  is_async BOOLEAN DEFAULT 0,
  is_generator BOOLEAN DEFAULT 0,
  
  -- Lifecycle tracking
  commit_sha TEXT NOT NULL,
  branch TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  
  -- Foreign keys
  FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Indexes for fast lookups
CREATE INDEX idx_nodes_qualified_name ON code_nodes(qualified_name);
CREATE INDEX idx_nodes_name ON code_nodes(name);
CREATE INDEX idx_nodes_type ON code_nodes(node_type);
CREATE INDEX idx_nodes_file ON code_nodes(file_id);
CREATE INDEX idx_nodes_repo ON code_nodes(repo_id);
CREATE INDEX idx_nodes_location ON code_nodes(repo_id, file_id, start_line);

-- Full-text search on names and signatures
CREATE VIRTUAL TABLE code_nodes_fts USING fts5(
  node_id UNINDEXED,
  qualified_name,
  name,
  signature,
  docstring,
  tokenize='porter unicode61'
);
```

### Table: `code_edges`

Stores relationships between code entities

```sql
CREATE TABLE code_edges (
  -- Identity
  id TEXT PRIMARY KEY,  -- UUID
  
  -- Relationship
  source_node_id TEXT NOT NULL,
  target_node_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,  -- See edge types below
  
  -- Context
  line_number INTEGER,  -- Where this relationship occurs in source
  is_direct BOOLEAN DEFAULT 1,  -- Direct vs. transitive relationship
  
  -- Optional metadata
  relationship_metadata TEXT,  -- JSON for language-specific details
  
  -- Lifecycle
  commit_sha TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  
  -- Foreign keys
  FOREIGN KEY (source_node_id) REFERENCES code_nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (target_node_id) REFERENCES code_nodes(id) ON DELETE CASCADE
);

-- Indexes for traversal queries
CREATE INDEX idx_edges_source ON code_edges(source_node_id, edge_type);
CREATE INDEX idx_edges_target ON code_edges(target_node_id, edge_type);
CREATE INDEX idx_edges_type ON code_edges(edge_type);
CREATE INDEX idx_edges_bidirectional ON code_edges(source_node_id, target_node_id);

-- Composite index for "find all X that Y does Z"
CREATE INDEX idx_edges_source_type_target ON code_edges(source_node_id, edge_type, target_node_id);
CREATE INDEX idx_edges_target_type_source ON code_edges(target_node_id, edge_type, source_node_id);
```

### Edge Types Taxonomy

**Universal Edge Types** (all languages):
- `calls` - Function/method invocation
- `imports` - Module/file import
- `references` - Generic reference to another entity

**Object-Oriented** (Python, TypeScript):
- `inherits` - Class inheritance
- `implements` - Interface implementation
- `decorates` - Decorator/annotation application
- `overrides` - Method override

**Type System** (TypeScript, SQL):
- `type_depends_on` - Type dependency
- `extends_type` - Type extension
- `satisfies` - Type constraint satisfaction

**Data/SQL**:
- `depends_on_table` - Table dependency
- `depends_on_view` - View dependency
- `calls_function` - Stored procedure call
- `references_column` - Column reference

**Component/UI** (Svelte):
- `uses_component` - Component usage
- `subscribes_to_store` - Store subscription
- `emits_event` - Event emission
- `listens_to_event` - Event listener

### Table: `node_aliases`

Tracks multiple names for the same entity (imports, renames, etc.)

```sql
CREATE TABLE node_aliases (
  id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  alias_name TEXT NOT NULL,  -- Imported/aliased name
  alias_qualified_name TEXT NOT NULL,  -- Full alias path
  file_id INTEGER NOT NULL,  -- Where this alias exists
  line_number INTEGER,
  
  FOREIGN KEY (node_id) REFERENCES code_nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX idx_aliases_name ON node_aliases(alias_name);
CREATE INDEX idx_aliases_qualified ON node_aliases(alias_qualified_name);
CREATE INDEX idx_aliases_node ON node_aliases(node_id);
```

### Table: `cross_repo_references`

Tracks relationships across repository boundaries

```sql
CREATE TABLE cross_repo_references (
  id TEXT PRIMARY KEY,
  
  -- Source (current repo)
  source_node_id TEXT NOT NULL,
  source_repo_id INTEGER NOT NULL,
  
  -- Target (external reference)
  target_package TEXT NOT NULL,  -- npm package, pip package, etc.
  target_module TEXT,
  target_symbol TEXT,
  reference_type TEXT NOT NULL,  -- 'import', 'call', 'type_reference'
  
  -- Location
  file_id INTEGER NOT NULL,
  line_number INTEGER,
  
  -- Lifecycle
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  
  FOREIGN KEY (source_node_id) REFERENCES code_nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (source_repo_id) REFERENCES repos(id) ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX idx_cross_repo_source ON cross_repo_references(source_node_id);
CREATE INDEX idx_cross_repo_package ON cross_repo_references(target_package, target_module);
```

---

## Indexing Strategy

### Query Performance Targets

| Query Type | Target Latency | Index Strategy |
|------------|---------------|----------------|
| Find callsites | <50ms | `idx_edges_target` + type filter |
| Find implementations | <50ms | `idx_edges_target` + type='implements' |
| Trace dependencies (depth 3) | <200ms | Recursive CTE + `idx_edges_source` |
| Full-text symbol search | <100ms | FTS5 index |
| Cross-repo lookups | <100ms | `idx_cross_repo_package` |

### Index Size Estimates

For a medium-sized codebase (10K files, 500K nodes, 2M edges):

| Index | Size | Rationale |
|-------|------|-----------|
| Primary keys | ~50 MB | UUID strings |
| `idx_nodes_qualified_name` | ~80 MB | B-tree on qualified names |
| `idx_edges_source` | ~120 MB | Most frequently used for navigation |
| `idx_edges_target` | ~120 MB | Critical for "who calls this?" queries |
| `idx_edges_type` | ~40 MB | Small cardinality (20-30 edge types) |
| FTS5 index | ~200 MB | Full-text search on symbols |
| **Total** | **~600 MB** | Fits comfortably in memory |

### Optimization Techniques

1. **Covering Indexes**: Include frequently queried columns in index
2. **Partial Indexes**: For common edge types (e.g., only `calls` edges)
3. **Materialized Views**: Pre-compute transitive closures for critical paths
4. **Query Result Caching**: Cache results for popular symbols (LRU)
5. **Batch Updates**: Group graph updates into transactions for efficiency

---

## Query Patterns

### Pattern 1: Find All Callsites (Who calls this function?)

**Use Case**: User searches for a function and wants to see all places it's called.

```sql
-- Find all direct callsites for a function
SELECT 
  cn.qualified_name AS caller,
  cn.node_type AS caller_type,
  f.path AS file_path,
  ce.line_number,
  ce.edge_type
FROM code_edges ce
JOIN code_nodes cn ON ce.source_node_id = cn.id
JOIN files f ON cn.file_id = f.id
WHERE ce.target_node_id = :target_function_id
  AND ce.edge_type = 'calls'
ORDER BY f.path, ce.line_number;
```

**Performance**: Single index seek on `idx_edges_target`, then lookups. ~10-20ms for 100 callsites.

### Pattern 2: Find Implementations (What implements this interface?)

**Use Case**: Given an interface/base class, find all implementations.

```sql
-- Find all implementations of an interface
SELECT 
  cn.qualified_name AS implementation,
  cn.node_type,
  f.path,
  cn.start_line,
  cn.visibility
FROM code_edges ce
JOIN code_nodes cn ON ce.source_node_id = cn.id
JOIN files f ON cn.file_id = f.id
WHERE ce.target_node_id = :interface_id
  AND ce.edge_type IN ('implements', 'inherits')
ORDER BY cn.qualified_name;
```

### Pattern 3: Trace Dependency Chain (Transitive Dependencies)

**Use Case**: Understand what a module depends on transitively.

```sql
-- Recursive CTE for dependency traversal (up to depth 3)
WITH RECURSIVE deps(node_id, depth, path) AS (
  -- Base case: direct dependencies
  SELECT 
    ce.target_node_id,
    1,
    cn.qualified_name || ' → ' || target.qualified_name
  FROM code_edges ce
  JOIN code_nodes cn ON ce.source_node_id = cn.id
  JOIN code_nodes target ON ce.target_node_id = target.id
  WHERE ce.source_node_id = :start_node_id
    AND ce.edge_type IN ('imports', 'depends_on_table', 'depends_on_view')
  
  UNION ALL
  
  -- Recursive case: transitive dependencies
  SELECT 
    ce.target_node_id,
    d.depth + 1,
    d.path || ' → ' || target.qualified_name
  FROM deps d
  JOIN code_edges ce ON d.node_id = ce.source_node_id
  JOIN code_nodes target ON ce.target_node_id = target.id
  WHERE d.depth < 3  -- Limit depth
    AND ce.edge_type IN ('imports', 'depends_on_table', 'depends_on_view')
)
SELECT DISTINCT 
  cn.qualified_name,
  d.depth,
  d.path
FROM deps d
JOIN code_nodes cn ON d.node_id = cn.id
ORDER BY d.depth, cn.qualified_name;
```

**Performance**: With proper indexing and depth limit, ~100-200ms for typical cases.

### Pattern 4: Symbol Search with Graph Context

**Use Case**: Search for a symbol by name and include callers/callees.

```sql
-- Full-text search with graph enrichment
SELECT 
  cn.id,
  cn.qualified_name,
  cn.node_type,
  f.path,
  cn.start_line,
  -- Count incoming edges (how many things call/use this)
  (SELECT COUNT(*) FROM code_edges WHERE target_node_id = cn.id) AS incoming_refs,
  -- Count outgoing edges (how many things this calls/uses)
  (SELECT COUNT(*) FROM code_edges WHERE source_node_id = cn.id) AS outgoing_refs
FROM code_nodes_fts fts
JOIN code_nodes cn ON fts.node_id = cn.id
JOIN files f ON cn.file_id = f.id
WHERE code_nodes_fts MATCH :search_query
ORDER BY incoming_refs DESC  -- Popular symbols first
LIMIT 20;
```

### Pattern 5: Cross-Repo Analysis

**Use Case**: Find external dependencies used across multiple repos.

```sql
-- Most commonly used external packages
SELECT 
  crr.target_package,
  COUNT(DISTINCT crr.source_repo_id) AS repo_count,
  COUNT(DISTINCT crr.source_node_id) AS usage_count,
  GROUP_CONCAT(DISTINCT r.name) AS repos
FROM cross_repo_references crr
JOIN repos r ON crr.source_repo_id = r.id
GROUP BY crr.target_package
HAVING repo_count > 1  -- Used in multiple repos
ORDER BY usage_count DESC
LIMIT 50;
```

---

## Integration with Semantic Search

### Enrichment Strategy

When a user performs a semantic search and gets results, we enrich each result with graph context:

```python
# Pseudo-code for enrichment
def enrich_search_result(hit: SearchHit) -> EnrichedSearchHit:
    """Add graph context to a search result."""
    
    # Find the code node for this chunk
    node = find_node_for_chunk(hit.chunk_id, hit.start_line, hit.end_line)
    
    if not node:
        return hit  # No graph data available
    
    # Add graph context
    graph_context = {
        "node_id": node.id,
        "node_type": node.node_type,
        "qualified_name": node.qualified_name,
        
        # Callers (limited to top 5 by importance)
        "callers": find_callers(node.id, limit=5),
        
        # Callees (limited to top 5)
        "callees": find_callees(node.id, limit=5),
        
        # Implementations (if interface/base class)
        "implementations": find_implementations(node.id, limit=5),
        
        # Dependencies
        "depends_on": find_dependencies(node.id, limit=5),
        
        # Popularity metrics
        "incoming_reference_count": count_incoming_edges(node.id),
        "outgoing_reference_count": count_outgoing_edges(node.id),
    }
    
    return {**hit, "graph": graph_context}
```

### API Response Format

**Enhanced Search Response** (backward compatible):

```json
{
  "hits": [
    {
      "chunk_id": "abc-123",
      "repo": "myapp",
      "path": "src/utils/math.py",
      "start_line": 45,
      "end_line": 60,
      "score": 0.89,
      "symbol_name": "calculate_total",
      
      // NEW: Graph context
      "graph": {
        "node_id": "node-uuid-123",
        "node_type": "function",
        "qualified_name": "myapp.utils.math.calculate_total",
        
        "callers": [
          {
            "qualified_name": "myapp.controllers.order.OrderController.create_order",
            "file": "src/controllers/order.py",
            "line": 89,
            "edge_type": "calls"
          },
          {
            "qualified_name": "myapp.services.billing.calculate_invoice",
            "file": "src/services/billing.py",
            "line": 234,
            "edge_type": "calls"
          }
        ],
        
        "callees": [
          {
            "qualified_name": "myapp.utils.math.apply_tax",
            "file": "src/utils/math.py",
            "line": 52,
            "edge_type": "calls"
          }
        ],
        
        "incoming_reference_count": 12,
        "outgoing_reference_count": 3
      }
    }
  ],
  "meta": {
    "top_k": 20,
    "graph_enrichment_enabled": true
  }
}
```

### Performance Considerations

**Graph enrichment overhead:**
- Single-node lookup: ~5ms (indexed)
- Find callers (top 5): ~10ms (indexed)
- Find callees (top 5): ~10ms (indexed)
- **Total per result**: ~25ms overhead

**For 20 results**: ~500ms total graph enrichment time

**Mitigation strategies:**
1. **Parallel enrichment**: Enrich all results concurrently
2. **Batch queries**: Use `WHERE node_id IN (...)` for all results at once
3. **Caching**: Cache graph context for popular symbols
4. **Opt-in**: Make graph enrichment optional (`include_graph=true` parameter)

---

## Storage Estimates

### Node Count Estimates

| Repo Size | Files | Nodes/File | Total Nodes |
|-----------|-------|------------|-------------|
| Small | 1K | 50 | 50K |
| Medium | 10K | 50 | 500K |
| Large | 100K | 50 | 5M |

### Edge Count Estimates

Typical ratios:
- **Calls**: 5 edges per function (average)
- **Imports**: 10 edges per file
- **Inherits/Implements**: 0.1 edges per class (sparse)
- **Type dependencies**: 3 edges per type

**Edge-to-node ratio**: ~4:1 (conservative estimate)

### Disk Space Requirements

| Component | Small Repo | Medium Repo | Large Repo |
|-----------|------------|-------------|------------|
| `code_nodes` | ~10 MB | ~100 MB | ~1 GB |
| `code_edges` | ~40 MB | ~400 MB | ~4 GB |
| `node_aliases` | ~2 MB | ~20 MB | ~200 MB |
| Indexes | ~60 MB | ~600 MB | ~6 GB |
| **Total** | **~112 MB** | **~1.1 GB** | **~11 GB** |

**Memory requirements** (if loading indexes):
- Small: <100 MB
- Medium: ~600 MB (fits in M4 MacBook memory)
- Large: ~6 GB (still manageable)

---

## Implementation Plan

### Phase 1: Schema Creation (Week 1)

**Tasks:**
1. Create SQLModel classes for graph tables
2. Add migration logic to `sqlite_meta.py`
3. Create indexes
4. Add FTS5 table for symbol search
5. Write basic CRUD operations

**Deliverables:**
- `kb/store/graph_store.py` - Graph database interface
- `kb/store/sql_models.py` - SQLModel classes for graph tables
- Unit tests for graph storage

### Phase 2: Graph Extraction Integration (Week 1-2)

**Tasks:**
1. Update ingestion pipeline to call graph extractors
2. Store extracted nodes and edges during indexing
3. Handle incremental updates (detect changed files)
4. Implement cleanup for deleted nodes/edges

**Deliverables:**
- Modified `kb/ingest/pipeline.py` to store graph data
- Integration tests for graph extraction → storage

### Phase 3: Query API (Week 2)

**Tasks:**
1. Implement navigation query functions:
   - `find_callers(node_id, limit)`
   - `find_callees(node_id, limit)`
   - `find_implementations(node_id, limit)`
   - `trace_dependencies(node_id, depth, limit)`
2. Add graph search API:
   - `search_symbols(query, filters)`
3. Optimize with query result caching

**Deliverables:**
- `kb/graph/queries.py` - Graph query functions
- Unit tests for all query patterns
- Performance benchmarks

### Phase 4: Search Integration (Week 2-3)

**Tasks:**
1. Add graph enrichment to search backend
2. Update REST API response format (backward compatible)
3. Update MCP tool to include graph context
4. Add `include_graph` parameter to search endpoint

**Deliverables:**
- Modified `kb/api/search_backend.py`
- Updated `mcp-bridge/src/mcp/tools/search_knowledge.ts`
- API documentation updates

### Phase 5: Optimization & Testing (Week 3)

**Tasks:**
1. Benchmark query performance on real codebases
2. Optimize slow queries with better indexes
3. Add query result caching (LRU cache)
4. Implement partial index strategies
5. Test on large codebases (1M+ nodes)

**Deliverables:**
- Performance benchmarks document
- Optimization guide
- Production-ready graph system

---

## Alternative Designs Considered

### Option 1: Dedicated Graph Database (Neo4j)

**Pros:**
- Native graph query language (Cypher)
- Optimized graph traversal algorithms
- Built-in graph analytics

**Cons:**
- ❌ Additional dependency and operational overhead
- ❌ Network latency for queries
- ❌ Complex deployment (Java runtime, separate process)
- ❌ Larger memory footprint

**Verdict**: Overkill for initial version. SQLite sufficient for target scale.

### Option 2: In-Memory Graph (NetworkX)

**Pros:**
- Fast traversals (pure Python/NumPy)
- Rich graph algorithms library

**Cons:**
- ❌ No persistence (must rebuild on startup)
- ❌ Memory constraints (5M nodes = several GB)
- ❌ No concurrent access control

**Verdict**: Not suitable for production system requiring persistence.

### Option 3: Embedded Graph DB (DuckDB with graph extension)

**Pros:**
- Analytical query performance
- Columnar storage efficiency

**Cons:**
- ❌ Newer technology, less mature
- ❌ Graph extension still experimental
- ❌ Another database to manage

**Verdict**: Interesting for future, but SQLite more proven for now.

---

## Future Enhancements

### v2.0 Features

1. **Temporal Graph**: Track how code evolves over time (git history)
2. **Call Graph Analysis**: Detect dead code, circular dependencies
3. **Impact Analysis**: "If I change this, what breaks?"
4. **Code Similarity**: Find similar functions based on call patterns
5. **Architectural Queries**: "Show me all boundary violations"
6. **Cross-Repo Intelligence**: Link related code across repositories

### Scalability Improvements

1. **Graph Partitioning**: Shard graph by repository or module
2. **Distributed Graph**: Use TigerGraph for multi-machine setup
3. **Incremental Indexing**: Only update changed subgraphs
4. **Approximate Queries**: Use sampling for very large graphs

---

## References

- SQLite Recursive CTEs: https://www.sqlite.org/lang_with.html
- Graph Algorithms in SQL: https://www.slideshare.net/MarkusWinand/modern-sql
- LanceDB Integration: `kb/store/lancedb_store.py`
- Current Schema: `kb/store/sql_models.py`
- Graph Extraction: `kb/chunkers/graph_types.py`

---

**Next Steps:**
1. Review this design with stakeholders
2. Approve schema and query patterns
3. Begin Phase 1 implementation
4. Create detailed task breakdown in project tracker

---

**Status**: ✅ Design Complete  
**Ready for**: Implementation  
**Estimated Effort**: 3 weeks (full-time)