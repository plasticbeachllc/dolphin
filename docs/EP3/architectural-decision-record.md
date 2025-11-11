# ADR-003: Incremental Call Graph Extraction and Maintenance

**Status:** Accepted

**Date:** 2025-11-11

**Deciders:** Lead Architect, Core Team

---

## Context

Dolphin currently uses tree-sitter to parse code files during vector indexing, extracting semantic chunks (functions, classes, methods) for embedding and search. For EP-3 (Advanced Code Graph Intelligence), we need to extract and maintain a call graph that tracks relationships between code symbols (function calls, imports, inheritance).

### Requirements

1. **Minimal Performance Impact**: Graph extraction should not significantly slow down existing indexing pipeline
2. **Incremental Updates**: File changes should update the graph efficiently without full rebuilds
3. **Cache Validity**: Graph cache must stay synchronized with repository state
4. **Query Performance**: Sub-100ms query times for graph traversals
5. **Scalability**: Support repos with 10K-100K files

### Current State

- Tree-sitter already parses files during chunking
- File watching is implemented and triggers reindexing on changes
- Git-aware incremental indexing tracks changed files via commit SHA
- SQLite stores metadata; LanceDB stores vectors

### Constraints

- Must work with existing SQLite + NetworkX architecture (no external graph DB required for v1)
- Should integrate seamlessly with current indexing pipeline
- File watcher already implemented - must integrate with existing reindex flow

---

## Decision

We will implement **incremental call graph extraction and maintenance** in four phases, piggy-backing on existing tree-sitter parsing with minimal overhead.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Indexing Pipeline (Triggered by File Watcher)              │
│                                                             │
│  File → Tree-sitter Parse (existing)                       │
│         ├─→ Extract Chunks (existing)                      │
│         │   └─→ Embed → LanceDB                            │
│         │                                                   │
│         └─→ Extract Graph Edges (NEW)                      │
│             └─→ Incremental Update                         │
│                 ├─→ Update SQLite (persistent)             │
│                 └─→ Update NetworkX (in-memory, if loaded) │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Graph Query Path                                            │
│                                                             │
│  Query → Check Cache Validity (git SHA)                    │
│          ├─→ Valid? Use cached NetworkX graph              │
│          └─→ Stale? Rebuild from SQLite → Cache            │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

#### 1. Graph Storage (SQLite)

```sql
-- Persistent graph edge storage
CREATE TABLE graph_edges (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER NOT NULL,
    from_symbol TEXT NOT NULL,
    to_symbol TEXT NOT NULL,
    from_file TEXT NOT NULL,
    to_file TEXT,  -- NULL if external/unresolved
    edge_type TEXT NOT NULL,  -- 'calls', 'imports', 'inherits', 'uses'
    confidence REAL DEFAULT 1.0,
    line_number INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);

CREATE INDEX idx_edges_from ON graph_edges(repo_id, from_symbol);
CREATE INDEX idx_edges_to ON graph_edges(repo_id, to_symbol);
CREATE INDEX idx_edges_file ON graph_edges(from_file);

-- Cached graph metrics
CREATE TABLE graph_metrics (
    repo_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    pagerank REAL,
    betweenness REAL,
    in_degree INTEGER,
    out_degree INTEGER,
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    commit_sha TEXT,  -- Graph state when computed
    PRIMARY KEY (repo_id, symbol),
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);

-- Graph build metadata
CREATE TABLE graph_cache_state (
    repo_id INTEGER PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    last_rebuild_at TEXT DEFAULT CURRENT_TIMESTAMP,
    node_count INTEGER,
    edge_count INTEGER,
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);
```

#### 2. Cache Invalidation Strategy

**Invalidation Conditions:**

1. Repository commit SHA has changed since last rebuild
2. More than 100 edge changes since last rebuild (configurable threshold)
3. Cache age exceeds 1 hour (configurable TTL)
4. Manual invalidation via `dolphin graph rebuild`

**Implementation:**

```python
class GraphCacheValidator:
    def is_cache_valid(self, repo_id: int) -> bool:
        """Check if cached NetworkX graph is still valid."""

        # Get current repo state
        current_commit = self._get_current_commit_sha(repo_id)

        # Get cache state
        cache_state = self.db.query_one("""
            SELECT commit_sha, last_rebuild_at, edge_count
            FROM graph_cache_state
            WHERE repo_id = ?
        """, (repo_id,))

        if not cache_state:
            return False

        # Check 1: Commit SHA match
        if cache_state.commit_sha != current_commit:
            logger.info(f"Cache invalid: commit changed "
                       f"{cache_state.commit_sha[:7]} → {current_commit[:7]}")
            return False

        # Check 2: Edge change threshold
        if self.edge_changes_since_rebuild > 100:
            logger.info(f"Cache invalid: {self.edge_changes_since_rebuild} "
                       f"edge changes exceed threshold")
            return False

        # Check 3: Time-based invalidation
        cache_age = datetime.now() - datetime.fromisoformat(cache_state.last_rebuild_at)
        if cache_age > timedelta(hours=1):
            logger.info(f"Cache invalid: age {cache_age} exceeds 1 hour")
            return False

        return True
```

---

## Implementation Phases

### Phase 1: Graph Extraction Integration (Week 1-2)

**Goal:** Extract call graph edges during existing indexing pipeline with <10% overhead.

**Changes to `kb/ingest/pipeline.py`:**

```python
from kb.graph.extractor import CallGraphExtractor
from kb.graph.store import GraphStore

class IndexingPipeline:
    def __init__(self, ...):
        # Existing
        self.chunker = get_chunker(language)

        # New
        self.graph_extractor = CallGraphExtractor()
        self.graph_store = GraphStore(self.db)

    def process_file(self, file_path: str, content: str):
        """Process file: chunking + embeddings + graph extraction."""

        # Parse once with tree-sitter (existing)
        tree = self.parser.parse(bytes(content, 'utf8'))

        # 1. Extract chunks (existing - no change)
        chunks = self.chunker.chunk_from_tree(file_path, tree, content)

        # 2. Extract graph edges (NEW - parallel operation)
        graph_edges = self.graph_extractor.extract_from_tree(
            file_path=file_path,
            tree=tree,
            repo_id=self.repo_id
        )

        # 3. Store chunks (existing)
        self.store_chunks(chunks)

        # 4. Store graph edges (NEW)
        self.graph_store.update_file_edges(file_path, graph_edges)
```

**New file: `kb/graph/extractor.py`:**

```python
from tree_sitter import Tree, Node
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class GraphEdge:
    from_symbol: str
    to_symbol: str
    from_file: str
    to_file: Optional[str]
    edge_type: str  # 'calls', 'imports', 'inherits', 'uses'
    confidence: float
    line_number: int

class CallGraphExtractor:
    """Extract call graph edges from tree-sitter AST."""

    def extract_from_tree(
        self,
        file_path: str,
        tree: Tree,
        repo_id: int
    ) -> List[GraphEdge]:
        """Extract all graph edges from parsed file."""
        edges = []

        # Extract different edge types
        edges.extend(self._extract_call_edges(file_path, tree))
        edges.extend(self._extract_import_edges(file_path, tree))
        edges.extend(self._extract_inheritance_edges(file_path, tree))

        return edges

    def _extract_call_edges(self, file_path: str, tree: Tree) -> List[GraphEdge]:
        """Extract function/method call relationships."""
        edges = []

        # Walk AST looking for call expressions
        for node in self._walk_tree(tree.root_node):
            if node.type in ('call', 'call_expression'):
                edge = self._extract_single_call(node, file_path)
                if edge:
                    edges.append(edge)

        return edges

    def _extract_single_call(
        self,
        call_node: Node,
        file_path: str
    ) -> Optional[GraphEdge]:
        """Extract a single call edge from AST node."""

        # Find enclosing function (caller)
        caller = self._get_enclosing_function(call_node)
        if not caller:
            return None

        # Find called function (callee)
        callee = self._get_called_function(call_node)
        if not callee:
            return None

        # Compute confidence based on resolution certainty
        confidence = self._compute_confidence(call_node)

        return GraphEdge(
            from_symbol=caller,
            to_symbol=callee,
            from_file=file_path,
            to_file=None,  # Resolved in post-processing
            edge_type='calls',
            confidence=confidence,
            line_number=call_node.start_point[0]
        )

    def _get_enclosing_function(self, node: Node) -> Optional[str]:
        """Find the function/method that contains this node."""
        current = node.parent

        while current:
            if current.type in ('function_definition', 'method_definition'):
                name_node = current.child_by_field_name('name')
                if name_node:
                    # Build fully qualified name: Class.method
                    return self._build_qualified_name(current)
            current = current.parent

        return None

    def _get_called_function(self, call_node: Node) -> Optional[str]:
        """Extract the name of the function being called."""
        function_node = call_node.child_by_field_name('function')

        if not function_node:
            return None

        # Handle different call patterns:
        # - Simple: foo()
        # - Method: obj.foo()
        # - Chained: obj.bar().foo()

        if function_node.type == 'identifier':
            return function_node.text.decode('utf8')

        elif function_node.type == 'attribute':
            # obj.method() -> extract 'method'
            attr_node = function_node.child_by_field_name('attribute')
            if attr_node:
                return attr_node.text.decode('utf8')

        return None

    def _compute_confidence(self, call_node: Node) -> float:
        """Compute confidence score for edge (0.0-1.0)."""
        # High confidence: Direct call to known function
        # Medium confidence: Method call on typed object
        # Low confidence: Dynamic call, unclear resolution

        # Simple heuristic for now
        function_node = call_node.child_by_field_name('function')

        if function_node.type == 'identifier':
            return 0.9  # Direct function call
        elif function_node.type == 'attribute':
            return 0.7  # Method call
        else:
            return 0.5  # Dynamic/unclear
```

**Performance Target:**

- Graph extraction: <10ms per file
- Total indexing overhead: <10%

---

### Phase 2: Lazy Graph Loading (Week 2)

**Goal:** Build NetworkX graph on-demand, not on every query.

**New file: `kb/graph/manager.py`:**

```python
import networkx as nx
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class GraphManager:
    """Manage NetworkX graph with lazy loading and cache validation."""

    def __init__(self, db, repo_id: int):
        self.db = db
        self.repo_id = repo_id

        # In-memory cache
        self._graph: Optional[nx.DiGraph] = None
        self._last_rebuild: Optional[datetime] = None
        self._edge_changes_since_rebuild: int = 0

        # Validator
        self.validator = GraphCacheValidator(db, repo_id)

    def get_graph(self, force_rebuild: bool = False) -> nx.DiGraph:
        """Get NetworkX graph, rebuilding if necessary."""

        # Check if rebuild needed
        if (force_rebuild or
            self._graph is None or
            not self.validator.is_cache_valid(self.repo_id)):

            logger.info(f"Rebuilding graph for repo {self.repo_id}")
            self._rebuild_graph()

        return self._graph

    def _rebuild_graph(self):
        """Rebuild NetworkX graph from SQLite edges."""
        start_time = datetime.now()

        # Get current repo state
        current_commit = self._get_current_commit_sha()

        # Fetch all edges from SQLite
        edges = self.db.query("""
            SELECT from_symbol, to_symbol, from_file, to_file,
                   edge_type, confidence, line_number
            FROM graph_edges
            WHERE repo_id = ?
        """, (self.repo_id,))

        # Build graph
        G = nx.DiGraph()

        for edge in edges:
            G.add_edge(
                edge.from_symbol,
                edge.to_symbol,
                file=edge.from_file,
                to_file=edge.to_file,
                type=edge.edge_type,
                confidence=edge.confidence,
                line=edge.line_number
            )

        # Update cache
        self._graph = G
        self._last_rebuild = datetime.now()
        self._edge_changes_since_rebuild = 0

        # Update cache state in DB
        self.db.execute("""
            INSERT OR REPLACE INTO graph_cache_state
            (repo_id, commit_sha, last_rebuild_at, node_count, edge_count)
            VALUES (?, ?, ?, ?, ?)
        """, (
            self.repo_id,
            current_commit,
            self._last_rebuild.isoformat(),
            G.number_of_nodes(),
            G.number_of_edges()
        ))

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"Graph rebuilt: {G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges in {elapsed:.2f}s"
        )

    def _get_current_commit_sha(self) -> str:
        """Get current HEAD commit SHA for repo."""
        repo = self.db.query_one(
            "SELECT root_path FROM repos WHERE id = ?",
            (self.repo_id,)
        )

        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.root_path,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    def on_edges_changed(self, count: int):
        """Track edge changes for cache invalidation."""
        self._edge_changes_since_rebuild += count
```

---

### Phase 3: Graph Store with Update Logic (Week 3)

**Goal:** Efficiently update SQLite when files change.

**New file: `kb/graph/store.py`:**

```python
from typing import List
from kb.graph.extractor import GraphEdge

class GraphStore:
    """Manage graph edge persistence in SQLite."""

    def __init__(self, db):
        self.db = db

    def update_file_edges(self, file_path: str, new_edges: List[GraphEdge]):
        """Replace all edges for a file with new edges."""

        with self.db.transaction():
            # Delete old edges originating from this file
            self.db.execute("""
                DELETE FROM graph_edges
                WHERE from_file = ?
            """, (file_path,))

            # Insert new edges
            if new_edges:
                self.db.executemany("""
                    INSERT INTO graph_edges
                    (repo_id, from_symbol, to_symbol, from_file, to_file,
                     edge_type, confidence, line_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (e.repo_id, e.from_symbol, e.to_symbol, e.from_file,
                     e.to_file, e.edge_type, e.confidence, e.line_number)
                    for e in new_edges
                ])

        # Notify manager of changes
        if hasattr(self, '_manager'):
            self._manager.on_edges_changed(len(new_edges))
```

---

### Phase 4: Incremental In-Memory Updates (Week 4)

**Goal:** Update NetworkX graph in-place without full rebuild when possible.

**Enhancement to `GraphManager`:**

```python
class GraphManager:
    # ... (existing methods) ...

    def update_file_edges_incremental(
        self,
        file_path: str,
        new_edges: List[GraphEdge]
    ):
        """Incrementally update graph when file changes."""

        # Only update if graph is loaded
        if self._graph is None:
            # Graph not loaded - just update SQLite
            self.store.update_file_edges(file_path, new_edges)
            return

        # Get old edges for this file
        old_edges = self.db.query("""
            SELECT from_symbol, to_symbol, edge_type
            FROM graph_edges
            WHERE from_file = ?
        """, (file_path,))

        # Compute diff
        old_edge_set = {(e.from_symbol, e.to_symbol, e.edge_type)
                        for e in old_edges}
        new_edge_set = {(e.from_symbol, e.to_symbol, e.edge_type)
                        for e in new_edges}

        removed = old_edge_set - new_edge_set
        added = new_edge_set - old_edge_set

        # Update NetworkX graph in-place
        for from_sym, to_sym, _ in removed:
            if self._graph.has_edge(from_sym, to_sym):
                self._graph.remove_edge(from_sym, to_sym)

        for edge in new_edges:
            if (edge.from_symbol, edge.to_symbol, edge.edge_type) in added:
                self._graph.add_edge(
                    edge.from_symbol,
                    edge.to_symbol,
                    file=edge.from_file,
                    to_file=edge.to_file,
                    type=edge.edge_type,
                    confidence=edge.confidence,
                    line=edge.line_number
                )

        # Update SQLite
        self.store.update_file_edges(file_path, new_edges)

        # Track changes
        self.on_edges_changed(len(added) + len(removed))

        logger.debug(
            f"Incremental update for {file_path}: "
            f"+{len(added)} -{len(removed)} edges"
        )
```

**Integration with pipeline:**

```python
# kb/ingest/pipeline.py
def process_file(self, file_path: str, content: str):
    # ... (existing chunking + embedding) ...

    # Extract graph edges
    graph_edges = self.graph_extractor.extract_from_tree(
        file_path, tree, self.repo_id
    )

    # Incremental update (Phase 4)
    self.graph_manager.update_file_edges_incremental(
        file_path,
        graph_edges
    )
```

---

## Consequences

### Positive

1. **Minimal Performance Impact**

   - Graph extraction adds only 5-10ms per file (tree-sitter already parsing)
   - Total indexing overhead: <10%
   - No impact on query performance when graph is cached

2. **Efficient Updates**

   - File changes update graph in 40-60ms (incremental)
   - No full rebuilds needed for single file changes
   - Graph stays synchronized with file system

3. **Smart Cache Management**

   - Git commit SHA ensures cache stays in sync with repository state
   - Automatic invalidation prevents stale graph queries
   - Configurable thresholds balance freshness vs. rebuild cost

4. **Scalability**

   - Supports 10K-100K file repositories
   - NetworkX rebuild: 1s for 10K files, 5s for 50K files
   - Rebuilds are rare (only when cache invalid)

5. **Query Performance**
   - <10ms for graph traversals when cached
   - PageRank and centrality metrics computed once, reused
   - Supports complex multi-hop queries efficiently

### Negative

1. **Initial Query Latency**

   - First query after startup incurs rebuild cost (~1s for 10K repo)
   - Mitigated by background warming on KB server start

2. **Memory Usage**

   - NetworkX graph adds ~10-20 bytes per edge in memory
   - 50K edges = ~1-2 MB additional memory
   - Acceptable for target workloads

3. **Edge Resolution Complexity**

   - Resolving function calls to actual definitions is heuristic-based
   - Confidence scores reflect uncertainty
   - Will improve over time with better static analysis

4. **Git Dependency**
   - Cache invalidation relies on git repository
   - Non-git projects need alternative state tracking
   - Can fallback to file modification time

### Risks and Mitigations

| Risk                                      | Impact | Mitigation                                                    |
| ----------------------------------------- | ------ | ------------------------------------------------------------- |
| Graph extraction slows indexing           | Medium | Profile and optimize AST walking; parallelize with embeddings |
| Cache invalidation too aggressive         | Low    | Make thresholds configurable; monitor cache hit rates         |
| NetworkX rebuild too slow for large repos | Medium | Pre-warm on server start; consider optional MemGraph backend  |
| False positive call edges                 | Low    | Use confidence scores; allow manual edge curation             |

---

## Alternatives Considered

### Alternative 1: Real-time Graph Updates Without Cache

**Approach:** Rebuild NetworkX graph from SQLite on every query.

**Rejected because:**

- 1s rebuild latency unacceptable for interactive queries
- Wastes CPU rebuilding identical graphs

### Alternative 2: MemGraph for Real-Time Updates

**Approach:** Use MemGraph in-memory graph database instead of NetworkX.

**Rejected for Phase 1 because:**

- Adds deployment complexity (separate process)
- SQLite + NetworkX sufficient for target scale
- Can revisit as optional backend in Phase 2

### Alternative 3: Event-Driven Graph Updates

**Approach:** Use event bus to propagate edge changes to graph.

**Rejected because:**

- Over-engineered for current scale
- Adds architectural complexity
- Git SHA validation is simpler and sufficient

---

## Implementation Checklist

### Phase 1: Extraction (Week 1-2)

- [ ] Create `graph_edges` table schema
- [ ] Implement `CallGraphExtractor` class
- [ ] Integrate with existing `IndexingPipeline`
- [ ] Add unit tests for edge extraction
- [ ] Profile indexing overhead (<10% target)

### Phase 2: Lazy Loading (Week 2)

- [ ] Create `graph_cache_state` table schema
- [ ] Implement `GraphCacheValidator` class
- [ ] Implement `GraphManager.get_graph()` with lazy loading
- [ ] Add git commit SHA tracking
- [ ] Add cache hit/miss metrics

### Phase 3: Store Logic (Week 3)

- [ ] Implement `GraphStore.update_file_edges()`
- [ ] Add transaction support for atomic updates
- [ ] Integrate with file change events
- [ ] Add edge change tracking

### Phase 4: Incremental Updates (Week 4)

- [ ] Implement `update_file_edges_incremental()`
- [ ] Add edge diff computation
- [ ] Integrate with pipeline
- [ ] Add performance monitoring
- [ ] Document cache invalidation behavior

### Testing & Validation

- [ ] End-to-end test: file change → graph update
- [ ] Performance test: 10K file repository indexing
- [ ] Cache invalidation test: commit SHA changes
- [ ] Stress test: 100 rapid file changes
- [ ] Integration test with existing KB search

---

## Success Metrics

**Performance Targets:**

- Graph extraction overhead: <10% of total indexing time
- File change to graph update: <60ms (p95)
- Graph rebuild time: <1s for 10K files, <5s for 50K files
- Query latency: <10ms when graph cached
- Cache hit rate: >95% during normal development

**Validation:**

- Extract 95%+ of function call relationships
- Handle file changes within 100ms (including vector reindex)
- No queries blocked by graph rebuilds (lazy loading works)

---

## References

- EP-3: Advanced Code Graph Intelligence
- ARCHITECTURE.md: Current system architecture
- Aider research: Tree-sitter repository maps
- NetworkX documentation: Graph algorithms

---

## Notes

- This ADR assumes tree-sitter parsing is already optimized
- Graph metrics (PageRank, centrality) are out of scope for this ADR
- Will be covered in separate ADR for graph-powered search
- Future: Consider cross-file symbol resolution improvements
