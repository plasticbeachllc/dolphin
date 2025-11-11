**Version**: 1.0  
**Date**: November 11, 2025  
**Timeline**: 10-14 weeks  
**Status**: Ready for Development Handoff

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack & Dependencies](#technology-stack--dependencies)
4. [Phase 1: Graph Extraction Enhancement](#phase-1-graph-extraction-enhancement)
5. [Phase 2: Graph-Powered Search](#phase-2-graph-powered-search)
6. [Phase 3: Impact Analysis Engine](#phase-3-impact-analysis-engine)
7. [Phase 4: Architectural Insights & Reports](#phase-5-architectural-insights--reports)
8. [Testing Strategy](#testing-strategy)
9. [Observability & Monitoring](#observability--monitoring)
10. [Reference Implementations](#reference-implementations)
11. [Risk Mitigation](#risk-mitigation)
12. [Success Metrics & KPIs](#success-metrics--kpis)

---

## Executive Summary

### Current State

Dolphin has a **production-ready foundation** with:

- ✅ Tree-sitter parsing for Python/TypeScript (191+ passing tests)
- ✅ SQLite metadata storage with well-defined schemas
- ✅ LanceDB vector storage with hybrid search
- ✅ Basic AST extraction (functions, classes, methods)
- ⚠️ **Underutilized**: Graph edges exist but no advanced analysis, visualization, or impact analysis

### Objectives

Transform the existing code graph infrastructure into a **comprehensive code intelligence system** that provides:

1. **Deep Code Understanding**: Call graphs, data flow, type relationships, cross-language edges
2. **Intelligent Search**: Graph-aware ranking using PageRank and structural patterns
3. **Impact Analysis**: "What breaks if I change this?" with risk scoring
4. **Automated Insights**: Anti-pattern detection, architectural metrics, quality reports

### Key Architectural Decisions

| Decision           | Chosen Approach                                           | Rationale                                            |
| ------------------ | --------------------------------------------------------- | ---------------------------------------------------- |
| **Graph Storage**  | SQLite adjacency lists + NetworkX for algorithms          | Maintains current stack, proven at scale (1M+ nodes) |
| **Graph Updates**  | Incremental edge addition/removal with conflict detection | Balances performance with correctness                |
| **PageRank**       | Pre-computed with incremental updates                     | <100ms search latency requirement                    |
| **Cross-Language** | Pattern matching on RPC/REST annotations                  | Pragmatic, works without full type inference         |
| **API Exposure**   | MCP tools + FastAPI REST endpoints                        | Agent use + web UI flexibility                       |

### Implementation Approach

- **5 sequential phases** with clear deliverables and acceptance criteria
- **Day-by-day schedules** with realistic estimates and buffer time
- **Incremental delivery**: Each phase produces usable features
- **Research-driven**: Leverage Aider's graph ranking, Kilocode's patterns
- **Test-driven**: 80%+ coverage target, comprehensive E2E tests
- **Observable**: Prometheus metrics, distributed tracing, Grafana dashboards

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     VSCode Extension (TypeScript)               │
│  • Impact analysis UI                                           │
│  • Architecture insights panel                                  │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP + JSON-RPC
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Core (Bun/TypeScript)                  │
│  • Graph query orchestration                                    │
│  • Impact analysis requests                                     │
│  • MCP tool exposure                                            │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                Knowledge Bank REST API (FastAPI)                │
│  ┌─────────────────────────────────────────────────────────-─┐  │
│  │              Graph Intelligence Layer (NEW)               │  │
│  │  • Call graph extraction                                  │  │
│  │  • Data flow tracking                                     │  │
│  │  • PageRank computation                                   │  │
│  │  • Impact analysis algorithms                             │  │
│  │  • Anti-pattern detection                                 │  │
│  └───────────────┬──────────────────────────────────────────-┘  │
│                  │                                              │
│  ┌───────────────▼──────────────────────────────────────────┐   │
│  │           Enhanced Graph Store (SQLite)                  │   │
│  │  Tables:                                                 │   │
│  │  • graph_nodes (id, type, name, file, line, metadata)    │   │
│  │  • graph_edges (source_id, target_id, edge_type, attrs)  │   │
│  │  • graph_metrics (node_id, pagerank, centrality, ...)    │   │
│  │  • graph_snapshots (commit_sha, timestamp, graph_data)   │   │
│  └────────────────────────────────────────────────────────────--│
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

**Indexing Pipeline Enhancement:**

```
Code Files → Tree-sitter Parse → AST Extraction
    ↓
Enhanced Graph Extraction (NEW)
    ├─ Function calls → Call edges
    ├─ Variable usage → Data flow edges
    ├─ Imports → Dependency edges
    ├─ Type inheritance → Type edges
    └─ Cross-language patterns → RPC edges
    ↓
Graph Store (SQLite)
    ├─ Nodes: Functions, classes, files
    ├─ Edges: Typed relationships
    └─ Metrics: PageRank, centrality
    ↓
NetworkX In-Memory (for algorithms)
    ├─ PageRank computation
    ├─ Community detection
    └─ Path finding
```

**Search Enhancement:**

```
User Query → Vector Search (existing)
    ↓
Graph-Aware Ranking (NEW)
    ├─ Load relevant subgraph
    ├─ Apply PageRank scores
    ├─ Compute path-based relevance
    └─ Re-rank results
    ↓
Enhanced Results + Graph Context
```

---

## Technology Stack & Dependencies

### Python Dependencies (Knowledge Bank)

```toml
# pyproject.toml additions
[project]
dependencies = [
    # Existing dependencies...

    # Graph processing
    "networkx>=3.2",           # Graph algorithms
    "python-louvain>=0.16",    # Community detection
    "scipy>=1.11.0",           # Scientific computing for metrics

    # Cross-language parsing
    "tree-sitter>=0.20.4",     # Already present, ensure latest
    "tree-sitter-python>=0.20.4",
    "tree-sitter-typescript>=0.20.3",
    "tree-sitter-javascript>=0.20.1",
]

[project.optional-dependencies]
neo4j = [
    "neo4j>=5.14.0",           # Optional Neo4j support
]
```

### Database Schema Extensions

```sql
-- kb/store/migrations/007_graph_tables.sql

-- Nodes table (enhanced)
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    repo_id INTEGER NOT NULL,
    node_type TEXT NOT NULL,  -- function, class, method, file, module
    name TEXT NOT NULL,
    qualified_name TEXT,       -- Full path: module.Class.method
    file_path TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    language TEXT,
    signature TEXT,            -- Function signature or class definition
    docstring TEXT,
    metadata JSON,             -- Additional language-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);

CREATE INDEX idx_graph_nodes_repo ON graph_nodes(repo_id);
CREATE INDEX idx_graph_nodes_type ON graph_nodes(node_type);
CREATE INDEX idx_graph_nodes_name ON graph_nodes(name);
CREATE INDEX idx_graph_nodes_file ON graph_nodes(file_path);

-- Edges table (enhanced)
CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,  -- calls, imports, inherits, implements, uses, contains
    weight REAL DEFAULT 1.0,
    attributes JSON,           -- Call context, import alias, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
    UNIQUE(source_id, target_id, edge_type)
);

CREATE INDEX idx_graph_edges_source ON graph_edges(source_id);
CREATE INDEX idx_graph_edges_target ON graph_edges(target_id);
CREATE INDEX idx_graph_edges_type ON graph_edges(edge_type);
CREATE INDEX idx_graph_edges_repo ON graph_edges(repo_id);

-- Metrics table (for PageRank, centrality, etc.)
CREATE TABLE IF NOT EXISTS graph_metrics (
    node_id TEXT PRIMARY KEY,
    pagerank REAL,
    betweenness_centrality REAL,
    in_degree INTEGER,
    out_degree INTEGER,
    cyclomatic_complexity INTEGER,  -- For functions
    community_id INTEGER,            -- From community detection
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES graph_nodes(id) ON DELETE CASCADE
);

CREATE INDEX idx_graph_metrics_pagerank ON graph_metrics(pagerank DESC);
CREATE INDEX idx_graph_metrics_community ON graph_metrics(community_id);

-- Snapshots table (for time-travel)
CREATE TABLE IF NOT EXISTS graph_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    commit_sha TEXT NOT NULL,
    commit_message TEXT,
    commit_timestamp TIMESTAMP,
    node_count INTEGER,
    edge_count INTEGER,
    snapshot_data BLOB,  -- Compressed NetworkX graph pickle
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
);

CREATE INDEX idx_graph_snapshots_repo_commit ON graph_snapshots(repo_id, commit_sha);
```

---

## Phase 1: Graph Extraction Enhancement (4 weeks)

### Overview

**Goal**: Extract comprehensive graph structures from Python and TypeScript codebases using tree-sitter, storing call graphs, data flow, import dependencies, and type relationships.

**Timeline**: Weeks 1-4 (20 working days)

**Team**: 2 engineers (primary + reviewer)

### Detailed Schedule

#### Week 1: Foundation & Call Graph Extraction

**Days 1-2: Setup & Architecture**

_Deliverables:_

- New module structure created
- Database migrations applied
- Unit test scaffolding complete

_Tasks:_

```bash
# Create module structure
mkdir -p kb/graph_intelligence/
touch kb/graph_intelligence/__init__.py
touch kb/graph_intelligence/extractors.py
touch kb/graph_intelligence/call_graph.py
touch kb/graph_intelligence/data_flow.py
touch kb/graph_intelligence/type_graph.py
touch kb/graph_intelligence/graph_store.py
touch kb/graph_intelligence/algorithms.py

# Create tests
mkdir -p tests/unit/graph_intelligence/
touch tests/unit/graph_intelligence/test_call_graph.py
touch tests/unit/graph_intelligence/test_data_flow.py
touch tests/unit/graph_intelligence/test_extractors.py

# Migration
cp kb/store/migrations/007_graph_tables.sql kb/store/migrations/
```

_Code: Base Graph Node/Edge Models_

```python
# kb/graph_intelligence/models.py
"""Domain models for graph intelligence."""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of nodes in the code graph."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    FILE = "file"
    VARIABLE = "variable"


class EdgeType(str, Enum):
    """Types of edges in the code graph."""
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    USES = "uses"  # Variable/data usage
    CONTAINS = "contains"  # Module contains class, class contains method
    DEFINES = "defines"  # Function defines variable
    MODIFIES = "modifies"  # Function modifies variable


class GraphNode(BaseModel):
    """Represents a node in the code graph."""
    id: str
    repo_id: int
    node_type: NodeType
    name: str
    qualified_name: Optional[str] = None
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    language: str
    signature: Optional[str] = None
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Represents an edge in the code graph."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    attributes: Dict[str, Any] = Field(default_factory=dict)


class GraphMetrics(BaseModel):
    """Computed metrics for a graph node."""
    node_id: str
    pagerank: Optional[float] = None
    betweenness_centrality: Optional[float] = None
    in_degree: int = 0
    out_degree: int = 0
    cyclomatic_complexity: Optional[int] = None
    community_id: Optional[int] = None
```

**Days 3-5: Python Call Graph Extraction**

_Deliverable: Python call graph extractor with 80%+ accuracy_

_Code: Python Call Graph Extractor_

```python
# kb/graph_intelligence/extractors/python_call_graph.py
"""Extract call graph from Python code using tree-sitter."""

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node
from typing import List, Set, Tuple
from ..models import GraphNode, GraphEdge, NodeType, EdgeType


class PythonCallGraphExtractor:
    """Extracts call graph from Python code."""

    def __init__(self):
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)

        # Query for function/method definitions
        self.definition_query = self.language.query("""
            (function_definition
                name: (identifier) @func_name
                parameters: (parameters) @params
                body: (block) @body) @function

            (class_definition
                name: (identifier) @class_name
                body: (block) @class_body) @class
        """)

        # Query for function calls
        self.call_query = self.language.query("""
            (call
                function: [
                    (identifier) @simple_call
                    (attribute
                        object: (_)
                        attribute: (identifier) @method_call)
                ]) @call
        """)

    def extract(self, file_path: str, content: str, repo_id: int) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """Extract call graph from Python file.

        Returns:
            Tuple of (nodes, edges)
        """
        tree = self.parser.parse(bytes(content, "utf8"))
        nodes = []
        edges = []

        # Extract function/class definitions
        definitions = self._extract_definitions(tree.root_node, file_path, repo_id)
        nodes.extend(definitions)

        # Extract call edges
        call_edges = self._extract_calls(tree.root_node, definitions, repo_id)
        edges.extend(call_edges)

        return nodes, edges

    def _extract_definitions(self, root: Node, file_path: str, repo_id: int) -> List[GraphNode]:
        """Extract function and class definitions."""
        nodes = []
        captures = self.definition_query.captures(root)

        current_class = None

        for node, capture_name in captures:
            if capture_name == "class":
                class_node = self._extract_class_node(node, file_path, repo_id)
                nodes.append(class_node)
                current_class = class_node

            elif capture_name == "function":
                func_node = self._extract_function_node(
                    node, file_path, repo_id, current_class
                )
                nodes.append(func_node)

        return nodes

    def _extract_class_node(self, node: Node, file_path: str, repo_id: int) -> GraphNode:
        """Extract class definition node."""
        name_node = node.child_by_field_name("name")
        class_name = name_node.text.decode('utf8') if name_node else "Unknown"

        return GraphNode(
            id=f"{file_path}::{class_name}::{node.start_point[0]}",
            repo_id=repo_id,
            node_type=NodeType.CLASS,
            name=class_name,
            qualified_name=f"{file_path.replace('/', '.')}.{class_name}",
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="python",
            signature=node.text.decode('utf8')[:200],  # First 200 chars
            metadata={"ast_type": "class_definition"}
        )

    def _extract_function_node(self, node: Node, file_path: str, repo_id: int,
                              parent_class: Optional[GraphNode] = None) -> GraphNode:
        """Extract function/method definition node."""
        name_node = node.child_by_field_name("name")
        func_name = name_node.text.decode('utf8') if name_node else "Unknown"

        if parent_class:
            node_type = NodeType.METHOD
            qualified_name = f"{parent_class.qualified_name}.{func_name}"
        else:
            node_type = NodeType.FUNCTION
            qualified_name = f"{file_path.replace('/', '.')}.{func_name}"

        # Extract parameters for signature
        params_node = node.child_by_field_name("parameters")
        signature = f"def {func_name}{params_node.text.decode('utf8') if params_node else '()'}"

        # Extract docstring if present
        docstring = self._extract_docstring(node)

        return GraphNode(
            id=f"{file_path}::{qualified_name}::{node.start_point[0]}",
            repo_id=repo_id,
            node_type=node_type,
            name=func_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            language="python",
            signature=signature,
            docstring=docstring,
            metadata={
                "ast_type": "function_definition",
                "parent_class": parent_class.id if parent_class else None
            }
        )

    def _extract_calls(self, root: Node, definitions: List[GraphNode],
                      repo_id: int) -> List[GraphEdge]:
        """Extract call edges from function bodies."""
        edges = []
        captures = self.call_query.captures(root)

        # Create a map of function nodes by their AST positions
        def_map = {
            (node.start_line, node.end_line): node
            for node in definitions if node.node_type in (NodeType.FUNCTION, NodeType.METHOD)
        }

        for node, capture_name in captures:
            if capture_name == "call":
                # Find the containing function
                caller = self._find_containing_function(node, def_map)
                if not caller:
                    continue

                # Extract callee name
                function_node = node.child_by_field_name("function")
                if not function_node:
                    continue

                callee_name = self._extract_call_target(function_node)

                # Try to resolve callee to a definition
                callee = self._resolve_callee(callee_name, definitions)
                if callee:
                    edges.append(GraphEdge(
                        source_id=caller.id,
                        target_id=callee.id,
                        edge_type=EdgeType.CALLS,
                        attributes={
                            "call_line": node.start_point[0],
                            "call_type": "direct" if capture_name == "simple_call" else "method"
                        }
                    ))

        return edges

    def _find_containing_function(self, node: Node, def_map: dict) -> Optional[GraphNode]:
        """Find the function/method that contains this node."""
        current = node.parent
        while current:
            line_range = (current.start_point[0], current.end_point[0])
            if line_range in def_map:
                return def_map[line_range]
            current = current.parent
        return None

    def _extract_call_target(self, node: Node) -> str:
        """Extract the name of the called function/method."""
        if node.type == "identifier":
            return node.text.decode('utf8')
        elif node.type == "attribute":
            # For method calls like obj.method()
            attr_node = node.child_by_field_name("attribute")
            return attr_node.text.decode('utf8') if attr_node else "Unknown"
        return "Unknown"

    def _resolve_callee(self, name: str, definitions: List[GraphNode]) -> Optional[GraphNode]:
        """Resolve a call target name to a definition node."""
        # Simple name matching - can be enhanced with scope analysis
        for node in definitions:
            if node.name == name:
                return node
        return None

    def _extract_docstring(self, func_node: Node) -> Optional[str]:
        """Extract docstring from function definition."""
        body = func_node.child_by_field_name("body")
        if body and body.child_count > 0:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.children[0]
                if expr.type == "string":
                    return expr.text.decode('utf8').strip('"\'')
        return None
```

_Tests:_

```python
# tests/unit/graph_intelligence/test_python_call_graph.py
"""Tests for Python call graph extraction."""

import pytest
from kb.graph_intelligence.extractors.python_call_graph import PythonCallGraphExtractor
from kb.graph_intelligence.models import NodeType, EdgeType


def test_extract_simple_function():
    """Test extraction of simple function definition."""
    code = '''
def hello():
    """Say hello."""
    print("Hello")
'''
    extractor = PythonCallGraphExtractor()
    nodes, edges = extractor.extract("test.py", code, repo_id=1)

    assert len(nodes) == 1
    assert nodes[0].name == "hello"
    assert nodes[0].node_type == NodeType.FUNCTION
    assert nodes[0].docstring == "Say hello."


def test_extract_function_call():
    """Test extraction of function call edge."""
    code = '''
def caller():
    callee()

def callee():
    pass
'''
    extractor = PythonCallGraphExtractor()
    nodes, edges = extractor.extract("test.py", code, repo_id=1)

    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0].edge_type == EdgeType.CALLS
    assert edges[0].attributes["call_type"] == "direct"


def test_extract_class_and_methods():
    """Test extraction of class with methods."""
    code = '''
class Calculator:
    """A simple calculator."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers."""
        return self.add(a, 0) * b
'''
    extractor = PythonCallGraphExtractor()
    nodes, edges = extractor.extract("test.py", code, repo_id=1)

    # Should have: Calculator class, add method, multiply method
    assert len(nodes) == 3

    class_node = next(n for n in nodes if n.node_type == NodeType.CLASS)
    assert class_node.name == "Calculator"

    method_nodes = [n for n in nodes if n.node_type == NodeType.METHOD]
    assert len(method_nodes) == 2
    assert set(n.name for n in method_nodes) == {"add", "multiply"}

    # multiply calls add
    call_edges = [e for e in edges if e.edge_type == EdgeType.CALLS]
    assert len(call_edges) >= 1


def test_async_function_detection():
    """Test detection of async functions."""
    code = '''
async def fetch_data():
    """Async function."""
    await some_api_call()

async def some_api_call():
    pass
'''
    extractor = PythonCallGraphExtractor()
    nodes, edges = extractor.extract("test.py", code, repo_id=1)

    assert len(nodes) == 2
    fetch_node = next(n for n in nodes if n.name == "fetch_data")
    assert "async" in fetch_node.signature


def test_nested_function_calls():
    """Test extraction of nested function calls."""
    code = '''
def outer():
    def inner():
        helper()
    inner()

def helper():
    pass
'''
    extractor = PythonCallGraphExtractor()
    nodes, edges = extractor.extract("test.py", code, repo_id=1)

    # Should detect: outer, inner, helper
    assert len(nodes) == 3

    # Should have edges: outer->inner, inner->helper
    assert len(edges) >= 2
```

**Day 5: Integration with Indexing Pipeline**

_Deliverable: Graph extraction integrated into KB indexing_

```python
# kb/ingest/pipeline.py (modifications)

from kb.graph_intelligence.extractors.python_call_graph import PythonCallGraphExtractor
from kb.graph_intelligence.graph_store import GraphStore

class IndexingPipeline:
    def __init__(self, ...):
        # Existing initialization...
        self.graph_store = GraphStore(self.sqlite_store)
        self.py_graph_extractor = PythonCallGraphExtractor()

    async def process_file(self, file: FileCandidate) -> IndexingResult:
        """Process a single file with graph extraction."""
        # Existing chunking and embedding...

        # NEW: Graph extraction
        if file.language == "python":
            nodes, edges = self.py_graph_extractor.extract(
                file.path,
                content,
                self.repo.id
            )
            await self.graph_store.upsert_nodes(nodes)
            await self.graph_store.upsert_edges(edges)

        # Continue with existing flow...
```

#### Week 2: TypeScript Call Graph + Data Flow

**Days 6-8: TypeScript Call Graph Extraction**

_Deliverable: TypeScript call graph extractor_

```python
# kb/graph_intelligence/extractors/typescript_call_graph.py
"""Extract call graph from TypeScript code using tree-sitter."""

import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Node
# Similar structure to Python extractor...

class TypeScriptCallGraphExtractor:
    """Extracts call graph from TypeScript code."""

    def __init__(self):
        self.language = Language(tsts.language_typescript())
        self.parser = Parser(self.language)

        # Queries for TS function declarations, arrow functions, classes, etc.
        self.definition_query = self.language.query("""
            (function_declaration
                name: (identifier) @func_name) @function

            (method_definition
                name: (property_identifier) @method_name) @method

            (class_declaration
                name: (type_identifier) @class_name) @class

            (arrow_function) @arrow_func
        """)

    # Similar methods to Python extractor...
```

**Days 9-10: Data Flow Tracking**

_Deliverable: Variable dependency tracking_

```python
# kb/graph_intelligence/data_flow.py
"""Data flow analysis for tracking variable dependencies."""

from typing import List, Set, Dict
from .models import GraphNode, GraphEdge, EdgeType


class DataFlowAnalyzer:
    """Analyzes data flow and variable dependencies."""

    def extract_data_flow(self, tree_root: Node, definitions: List[GraphNode]) -> List[GraphEdge]:
        """Extract data flow edges (variable usage, mutations)."""
        edges = []

        # Track variable definitions and uses
        var_defs = self._find_variable_definitions(tree_root)
        var_uses = self._find_variable_uses(tree_root)

        # Create edges for each use pointing back to definition
        for use in var_uses:
            for definition in var_defs:
                if use.var_name == definition.var_name:
                    # Check scope overlap
                    if self._in_scope(use, definition):
                        edges.append(GraphEdge(
                            source_id=use.func_id,
                            target_id=definition.func_id,
                            edge_type=EdgeType.USES,
                            attributes={
                                "variable": use.var_name,
                                "use_line": use.line
                            }
                        ))

        return edges

    def _find_variable_definitions(self, node: Node) -> List[Dict]:
        """Find all variable definitions in the tree."""
        # Implementation using tree-sitter queries...
        pass

    def _find_variable_uses(self, node: Node) -> List[Dict]:
        """Find all variable uses in the tree."""
        # Implementation...
        pass
```

#### Week 3: Import Graph + Type Relationships

**Days 11-13: Import/Dependency Graph**

_Deliverable: Module dependency tracking with circular detection_

```python
# kb/graph_intelligence/import_graph.py
"""Import and dependency graph extraction."""

from typing import List, Set
from .models import GraphEdge, EdgeType
import re


class ImportGraphExtractor:
    """Extracts import dependencies between modules."""

    def extract_imports_python(self, tree_root: Node, source_file: str,
                               all_nodes: List[GraphNode]) -> List[GraphEdge]:
        """Extract Python import statements."""
        edges = []

        # Query for imports
        import_query = """
            (import_statement
                name: (dotted_name) @import_path)

            (import_from_statement
                module_name: (dotted_name) @from_module)
        """

        captures = self.parser.query(import_query).captures(tree_root)

        for node, capture_name in captures:
            imported_module = node.text.decode('utf8')

            # Try to resolve to actual file in the repository
            target_node = self._resolve_import(imported_module, all_nodes)

            if target_node:
                edges.append(GraphEdge(
                    source_id=f"{source_file}::module",
                    target_id=target_node.id,
                    edge_type=EdgeType.IMPORTS,
                    attributes={
                        "import_statement": imported_module,
                        "import_type": capture_name
                    }
                ))

        return edges

    def detect_circular_dependencies(self, edges: List[GraphEdge]) -> List[List[str]]:
        """Detect circular import dependencies."""
        import networkx as nx

        # Build directed graph
        G = nx.DiGraph()
        for edge in edges:
            if edge.edge_type == EdgeType.IMPORTS:
                G.add_edge(edge.source_id, edge.target_id)

        # Find cycles
        try:
            cycles = list(nx.simple_cycles(G))
            return cycles
        except:
            return []
```

**Days 14-15: Type Relationships (Inheritance, Implementations)**

_Deliverable: Type hierarchy extraction_

```python
# kb/graph_intelligence/type_graph.py
"""Type relationship extraction (inheritance, implementations)."""

class TypeGraphExtractor:
    """Extracts type hierarchies and relationships."""

    def extract_inheritance_python(self, tree_root: Node,
                                   class_nodes: List[GraphNode]) -> List[GraphEdge]:
        """Extract class inheritance relationships."""
        edges = []

        # Query for class definitions with base classes
        query = """
            (class_definition
                name: (identifier) @class_name
                superclasses: (argument_list) @bases)
        """

        captures = self.parser.query(query).captures(tree_root)

        for class_node, bases_node in zip(captures[::2], captures[1::2]):
            class_name = class_node[0].text.decode('utf8')

            # Parse base classes
            bases_text = bases_node[0].text.decode('utf8')
            base_names = [b.strip() for b in bases_text.strip('()').split(',')]

            # Create edges
            for base_name in base_names:
                base_node = self._find_class_by_name(base_name, class_nodes)
                if base_node:
                    child_node = self._find_class_by_name(class_name, class_nodes)
                    if child_node:
                        edges.append(GraphEdge(
                            source_id=child_node.id,
                            target_id=base_node.id,
                            edge_type=EdgeType.INHERITS,
                            attributes={"base_class": base_name}
                        ))

        return edges
```

#### Week 4: Cross-Language Edges + Testing

**Days 16-18: Cross-Language Pattern Matching**

_Deliverable: RPC/REST call detection across Python ↔ TypeScript_

```python
# kb/graph_intelligence/cross_language.py
"""Cross-language edge detection (RPC, REST, etc.)."""

import re
from typing import List, Pattern


class CrossLanguageEdgeDetector:
    """Detects edges between Python and TypeScript code."""

    def __init__(self):
        # Patterns for FastAPI route definitions
        self.fastapi_route_pattern = re.compile(
            r'@(?:router|app)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']\)'
        )

        # Patterns for TypeScript fetch/axios calls
        self.fetch_pattern = re.compile(
            r'(?:fetch|axios\.(?:get|post|put|delete))\(["\']([^"\']+)["\']\)'
        )

    def extract_rest_endpoints(self, python_nodes: List[GraphNode]) -> Dict[str, GraphNode]:
        """Extract REST API endpoints from Python FastAPI code."""
        endpoints = {}

        for node in python_nodes:
            if node.node_type == NodeType.FUNCTION:
                # Check if function has route decorator
                matches = self.fastapi_route_pattern.findall(node.signature)
                for method, path in matches:
                    endpoint_key = f"{method.upper()} {path}"
                    endpoints[endpoint_key] = node

        return endpoints

    def detect_rest_calls(self, ts_nodes: List[GraphNode],
                         py_endpoints: Dict[str, GraphNode]) -> List[GraphEdge]:
        """Detect TypeScript code calling Python REST endpoints."""
        edges = []

        for node in ts_nodes:
            if node.node_type in (NodeType.FUNCTION, NodeType.METHOD):
                # Search for fetch/axios calls in function body
                # (In real implementation, parse the TS AST)
                matches = self.fetch_pattern.findall(node.signature)

                for url in matches:
                    # Try to match URL to known endpoint
                    for endpoint_key, endpoint_node in py_endpoints.items():
                        if endpoint_key.split()[1] in url:  # Match path
                            edges.append(GraphEdge(
                                source_id=node.id,
                                target_id=endpoint_node.id,
                                edge_type=EdgeType.CALLS,
                                attributes={
                                    "cross_language": True,
                                    "protocol": "REST",
                                    "url": url
                                }
                            ))

        return edges
```

**Days 19-20: Comprehensive Testing + Documentation**

_Deliverables:_

- 80%+ test coverage for all extractors
- Integration tests with real repositories
- Performance benchmarks
- Documentation

```python
# tests/integration/test_graph_extraction_e2e.py
"""End-to-end tests for graph extraction."""

import pytest
from pathlib import Path


@pytest.mark.integration
async def test_full_repository_graph_extraction(tmp_path: Path):
    """Test graph extraction on a complete repository."""
    # Create a mini repository with Python + TypeScript
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Python file
    (repo_path / "backend.py").write_text('''
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/users")
def get_users():
    return fetch_from_db()

def fetch_from_db():
    return []
''')

    # TypeScript file
    (repo_path / "frontend.ts").write_text('''
async function loadUsers() {
    const response = await fetch("/api/users");
    return response.json();
}
''')

    # Run full extraction pipeline
    pipeline = IndexingPipeline(...)
    await pipeline.index_repository(str(repo_path))

    # Verify graph structure
    graph_store = GraphStore(...)

    # Check nodes
    nodes = await graph_store.get_all_nodes(repo_id=1)
    assert len(nodes) >= 3  # get_users, fetch_from_db, loadUsers

    # Check cross-language edge
    edges = await graph_store.get_edges_by_type(EdgeType.CALLS)
    rest_call_edges = [e for e in edges if e.attributes.get("cross_language")]
    assert len(rest_call_edges) >= 1
```

### Phase 1 Success Criteria

- [ ] Python call graph extraction: 95%+ accuracy (verified on 50+ test files)
- [ ] TypeScript call graph extraction: 90%+ accuracy
- [ ] Data flow tracking: Basic variable usage tracked
- [ ] Import graph: Circular dependencies detected
- [ ] Type relationships: Inheritance hierarchies extracted
- [ ] Cross-language: REST API calls detected between Python/TS
- [ ] Test coverage: 80%+
- [ ] Performance: <5s for 1000-file repository
- [ ] Documentation: API docs + usage examples complete

---

## Phase 2: Graph-Powered Search (3 weeks)

### Overview

**Goal**: Enhance search ranking using graph features (PageRank, structural patterns, path-based relevance) to improve search quality by 15%+ MRR.

**Timeline**: Weeks 5-7 (15 working days)

### Detailed Schedule

#### Week 5: PageRank Implementation

**Days 21-22: PageRank Computation**

_Deliverable: PageRank algorithm with incremental updates_

```python
# kb/graph_intelligence/algorithms.py
"""Graph algorithms for code intelligence."""

import networkx as nx
from typing import Dict, List
import numpy as np


class GraphAlgorithms:
    """Implements graph algorithms for code intelligence."""

    def __init__(self, graph_store):
        self.graph_store = graph_store

    def compute_pagerank(self, repo_id: int, alpha: float = 0.85,
                        max_iter: int = 100) -> Dict[str, float]:
        """Compute PageRank scores for all nodes in a repository.

        Args:
            repo_id: Repository ID
            alpha: Damping parameter (default 0.85)
            max_iter: Maximum iterations

        Returns:
            Dictionary mapping node_id to PageRank score
        """
        # Load graph from database
        G = self._load_graph(repo_id)

        # Compute PageRank
        pagerank_scores = nx.pagerank(
            G,
            alpha=alpha,
            max_iter=max_iter,
            tol=1e-6
        )

        # Store results in database
        self.graph_store.update_pagerank_scores(pagerank_scores)

        return pagerank_scores

    def _load_graph(self, repo_id: int) -> nx.DiGraph:
        """Load repository graph into NetworkX."""
        nodes = self.graph_store.get_nodes(repo_id)
        edges = self.graph_store.get_edges(repo_id)

        G = nx.DiGraph()

        # Add nodes
        for node in nodes:
            G.add_node(node.id, **node.dict())

        # Add edges (only structural edges for PageRank)
        for edge in edges:
            if edge.edge_type in (EdgeType.CALLS, EdgeType.IMPORTS, EdgeType.CONTAINS):
                G.add_edge(edge.source_id, edge.target_id, weight=edge.weight)

        return G

    def incremental_pagerank_update(self, repo_id: int,
                                   added_edges: List[GraphEdge],
                                   removed_edges: List[GraphEdge]) -> Dict[str, float]:
        """Incrementally update PageRank after graph changes.

        This is more efficient than full recomputation for small changes.
        """
        # Load current scores
        current_scores = self.graph_store.get_pagerank_scores(repo_id)

        # If changes are large (>10% of edges), do full recomputation
        total_edges = len(self.graph_store.get_edges(repo_id))
        change_ratio = (len(added_edges) + len(removed_edges)) / total_edges

        if change_ratio > 0.1:
            return self.compute_pagerank(repo_id)

        # Otherwise, use power iteration starting from current scores
        G = self._load_graph(repo_id)

        # Apply edge changes
        for edge in removed_edges:
            if G.has_edge(edge.source_id, edge.target_id):
                G.remove_edge(edge.source_id, edge.target_id)

        for edge in added_edges:
            G.add_edge(edge.source_id, edge.target_id, weight=edge.weight)

        # Run PageRank with current scores as initial guess
        pagerank_scores = nx.pagerank(
            G,
            alpha=0.85,
            max_iter=20,  # Fewer iterations since we have good initial guess
            nstart=current_scores
        )

        self.graph_store.update_pagerank_scores(pagerank_scores)
        return pagerank_scores
```

**Days 23-25: Personalized PageRank for Query-Specific Ranking**

_Deliverable: Query-aware PageRank computation_

```python
def personalized_pagerank(self, repo_id: int, seed_nodes: List[str],
                         alpha: float = 0.85) -> Dict[str, float]:
    """Compute Personalized PageRank from seed nodes.

    This ranks nodes by relevance to a specific set of seed nodes,
    useful for query-specific ranking.

    Args:
        repo_id: Repository ID
        seed_nodes: List of node IDs to start random walk from
        alpha: Damping parameter

    Returns:
        Dictionary mapping node_id to relevance score
    """
    G = self._load_graph(repo_id)

    # Create personalization vector (uniform over seed nodes)
    personalization = {node: 0.0 for node in G.nodes()}
    for seed in seed_nodes:
        if seed in personalization:
            personalization[seed] = 1.0 / len(seed_nodes)

    # Compute PPR
    ppr_scores = nx.pagerank(
        G,
        alpha=alpha,
        personalization=personalization,
        max_iter=100
    )

    return ppr_scores


def path_based_relevance(self, start_node: str, candidate_nodes: List[str]) -> Dict[str, float]:
    """Compute relevance scores based on shortest path distances.

    Nodes closer to the start node in the call graph are ranked higher.
    """
    G = self._load_graph(repo_id=start_node.split("::")[0])  # Extract repo_id

    relevance_scores = {}

    for candidate in candidate_nodes:
        try:
            # Compute shortest path length
            path_length = nx.shortest_path_length(G, start_node, candidate)
            # Convert to relevance score (inverse distance)
            relevance_scores[candidate] = 1.0 / (1.0 + path_length)
        except nx.NetworkXNoPath:
            # No path exists
            relevance_scores[candidate] = 0.0

    return relevance_scores
```

#### Week 6: Search Integration

**Days 26-27: Graph Features in Search**

_Deliverable: Graph-aware ranking integrated into search API_

```python
# kb/api/search.py (modifications)

from kb.graph_intelligence.algorithms import GraphAlgorithms


class SearchBackend:
    def __init__(self, ...):
        # Existing initialization...
        self.graph_algorithms = GraphAlgorithms(self.graph_store)

    async def graph_aware_search(
        self,
        query: str,
        repo_ids: List[int],
        use_pagerank: bool = True,
        use_personalized_pr: bool = False,
        top_k: int = 20
    ) -> List[SearchResult]:
        """Enhanced search with graph-aware ranking."""

        # Step 1: Regular vector/hybrid search
        initial_results = await self.hybrid_search(query, repo_ids, top_k=top_k*2)

        if not use_pagerank:
            return initial_results[:top_k]

        # Step 2: Load PageRank scores
        pagerank_scores = {}
        for repo_id in repo_ids:
            scores = self.graph_store.get_pagerank_scores(repo_id)
            pagerank_scores.update(scores)

        # Step 3: Re-rank using graph features
        for result in initial_results:
            # Extract node ID from result metadata
            node_id = result.metadata.get("node_id")

            if node_id and node_id in pagerank_scores:
                # Combine semantic relevance with PageRank
                semantic_score = result.score
                graph_score = pagerank_scores[node_id]

                # Weighted combination (tunable)
                result.score = 0.7 * semantic_score + 0.3 * graph_score

        # Step 4: Re-sort and return top_k
        initial_results.sort(key=lambda x: x.score, reverse=True)
        return initial_results[:top_k]
```

**Days 28-29: A/B Testing Infrastructure**

_Deliverable: A/B test framework to measure ranking improvements_

```python
# kb/evaluation/ab_testing.py
"""A/B testing framework for search ranking experiments."""

from enum import Enum
from typing import List, Dict
import hashlib


class ExperimentVariant(str, Enum):
    CONTROL = "control"  # Baseline search
    TREATMENT = "treatment"  # Graph-aware search


class ABTestingFramework:
    """Manages A/B tests for search ranking experiments."""

    def __init__(self):
        self.active_experiments: Dict[str, Experiment] = {}

    def assign_variant(self, user_id: str, experiment_id: str) -> ExperimentVariant:
        """Assign user to experiment variant (deterministic based on user_id)."""
        # Hash user_id to get consistent assignment
        hash_value = int(hashlib.md5(f"{user_id}{experiment_id}".encode()).hexdigest(), 16)

        # 50/50 split
        if hash_value % 2 == 0:
            return ExperimentVariant.CONTROL
        else:
            return ExperimentVariant.TREATMENT

    async def execute_search(
        self,
        user_id: str,
        query: str,
        repo_ids: List[int],
        experiment_id: str = "graph_ranking_v1"
    ) -> List[SearchResult]:
        """Execute search based on A/B test assignment."""
        variant = self.assign_variant(user_id, experiment_id)

        if variant == ExperimentVariant.CONTROL:
            results = await self.search_backend.hybrid_search(query, repo_ids)
        else:
            results = await self.search_backend.graph_aware_search(query, repo_ids)

        # Log for analysis
        await self.log_search_event(user_id, query, variant, results)

        return results

    async def log_search_event(self, user_id: str, query: str,
                               variant: ExperimentVariant,
                               results: List[SearchResult]):
        """Log search event for later analysis."""
        # Store in SQLite or send to analytics pipeline
        pass
```

**Day 30: Performance Optimization**

_Deliverable: Optimized graph queries, cached PageRank scores_

```python
# kb/graph_intelligence/graph_store.py
"""Graph storage layer with caching."""

from functools import lru_cache
import pickle


class GraphStore:
    """Manages graph storage and retrieval with caching."""

    def __init__(self, sqlite_store):
        self.db = sqlite_store
        self._pagerank_cache = {}

    @lru_cache(maxsize=100)
    def get_pagerank_scores(self, repo_id: int) -> Dict[str, float]:
        """Get PageRank scores with caching."""
        if repo_id in self._pagerank_cache:
            return self._pagerank_cache[repo_id]

        # Load from database
        query = "SELECT node_id, pagerank FROM graph_metrics WHERE node_id LIKE ?"
        rows = self.db.execute(query, (f"%{repo_id}%",)).fetchall()

        scores = {row[0]: row[1] for row in rows}
        self._pagerank_cache[repo_id] = scores
        return scores

    def invalidate_pagerank_cache(self, repo_id: int):
        """Invalidate cache after graph updates."""
        if repo_id in self._pagerank_cache:
            del self._pagerank_cache[repo_id]

        # Clear LRU cache
        self.get_pagerank_scores.cache_clear()
```

#### Week 7: Evaluation & Refinement

**Days 31-33: Evaluation on Benchmark Dataset**

_Deliverable: MRR improvement measured, results documented_

```python
# tests/evaluation/test_graph_search_quality.py
"""Evaluate graph-aware search quality."""

import pytest
from kb.evaluation.metrics import mean_reciprocal_rank


@pytest.fixture
def benchmark_queries():
    """Benchmark query set with ground truth."""
    return [
        {
            "query": "authentication handler",
            "relevant_results": ["src/auth.py::authenticate", "src/auth.py::verify_token"],
            "repo_id": 1
        },
        {
            "query": "database connection pool",
            "relevant_results": ["src/db.py::ConnectionPool", "src/db.py::get_connection"],
            "repo_id": 1
        },
        # 50+ more queries...
    ]


@pytest.mark.evaluation
async def test_graph_search_vs_baseline(benchmark_queries):
    """Compare graph-aware search to baseline."""
    baseline_mrr = []
    graph_mrr = []

    for query_data in benchmark_queries:
        # Baseline search
        baseline_results = await search_backend.hybrid_search(
            query_data["query"],
            [query_data["repo_id"]]
        )
        baseline_mrr.append(
            mean_reciprocal_rank([baseline_results], [query_data["relevant_results"]])
        )

        # Graph-aware search
        graph_results = await search_backend.graph_aware_search(
            query_data["query"],
            [query_data["repo_id"]]
        )
        graph_mrr.append(
            mean_reciprocal_rank([graph_results], [query_data["relevant_results"]])
        )

    avg_baseline_mrr = sum(baseline_mrr) / len(baseline_mrr)
    avg_graph_mrr = sum(graph_mrr) / len(graph_mrr)

    improvement = (avg_graph_mrr - avg_baseline_mrr) / avg_baseline_mrr * 100

    print(f"Baseline MRR: {avg_baseline_mrr:.3f}")
    print(f"Graph MRR: {avg_graph_mrr:.3f}")
    print(f"Improvement: {improvement:.1f}%")

    # Target: 15%+ improvement
    assert improvement >= 15.0
```

**Days 34-35: Documentation & Refinement**

_Deliverables:_

- API documentation for graph-aware search
- Tuning guide (PageRank weight, combining factors)
- Performance profiling report

### Phase 2 Success Criteria

- [ ] PageRank pre-computed for all repositories
- [ ] Incremental PageRank updates working correctly
- [ ] Graph-aware search integrated into REST API
- [ ] MRR improvement of 15%+ on dependency-related queries
- [ ] Search latency <100ms (p95)
- [ ] A/B testing framework operational
- [ ] Documentation complete

---

## Phase 3: Impact Analysis Engine (3 weeks)

### Overview

**Goal**: Build forward/backward graph traversal to answer "what breaks if I change this?" with 90%+ accuracy.

**Timeline**: Weeks 8-10 (15 working days)

### Detailed Schedule

#### Week 8: Traversal Algorithms

**Days 36-38: Forward/Backward Traversal**

_Deliverable: BFS/DFS traversal with depth limits_

```python
# kb/graph_intelligence/impact_analysis.py
"""Impact analysis algorithms."""

from typing import List, Set, Dict
from enum import Enum
import networkx as nx


class ImpactDirection(str, Enum):
    FORWARD = "forward"  # What depends on this?
    BACKWARD = "backward"  # What does this depend on?
    BOTH = "both"


class ImpactResult:
    """Result of impact analysis."""

    def __init__(self):
        self.affected_nodes: List[GraphNode] = []
        self.impact_paths: List[List[str]] = []
        self.risk_score: float = 0.0
        self.depth_distribution: Dict[int, int] = {}


class ImpactAnalyzer:
    """Analyzes code change impact using graph traversal."""

    def __init__(self, graph_store, graph_algorithms):
        self.graph_store = graph_store
        self.algorithms = graph_algorithms

    def analyze_impact(
        self,
        node_id: str,
        direction: ImpactDirection = ImpactDirection.FORWARD,
        max_depth: int = 5,
        include_tests: bool = True
    ) -> ImpactResult:
        """Analyze impact of changing a code node.

        Args:
            node_id: ID of the node being changed
            direction: Direction of impact (forward/backward/both)
            max_depth: Maximum traversal depth
            include_tests: Whether to include test files in results

        Returns:
            ImpactResult with affected nodes and risk score
        """
        result = ImpactResult()

        # Load graph
        node = self.graph_store.get_node(node_id)
        G = self.algorithms._load_graph(node.repo_id)

        # Traverse graph
        if direction == ImpactDirection.FORWARD:
            affected = self._forward_traversal(G, node_id, max_depth)
        elif direction == ImpactDirection.BACKWARD:
            affected = self._backward_traversal(G, node_id, max_depth)
        else:  # BOTH
            forward = self._forward_traversal(G, node_id, max_depth)
            backward = self._backward_traversal(G, node_id, max_depth)
            affected = forward | backward

        # Filter out test files if requested
        if not include_tests:
            affected = {n for n in affected if "/test" not in n and "_test" not in n}

        # Load node details
        result.affected_nodes = [self.graph_store.get_node(n) for n in affected]

        # Compute risk score
        result.risk_score = self._compute_risk_score(result.affected_nodes, G)

        # Find representative paths
        result.impact_paths = self._find_impact_paths(G, node_id, list(affected)[:10])

        # Depth distribution
        result.depth_distribution = self._compute_depth_distribution(G, node_id, affected)

        return result

    def _forward_traversal(self, G: nx.DiGraph, start_node: str,
                          max_depth: int) -> Set[str]:
        """Traverse forward (downstream) from start node."""
        visited = set()
        queue = [(start_node, 0)]  # (node, depth)

        while queue:
            node, depth = queue.pop(0)

            if depth > max_depth or node in visited:
                continue

            visited.add(node)

            # Add successors (nodes that depend on this node)
            for successor in G.successors(node):
                if successor not in visited:
                    queue.append((successor, depth + 1))

        visited.discard(start_node)  # Don't include start node
        return visited

    def _backward_traversal(self, G: nx.DiGraph, start_node: str,
                           max_depth: int) -> Set[str]:
        """Traverse backward (upstream) from start node."""
        visited = set()
        queue = [(start_node, 0)]

        while queue:
            node, depth = queue.pop(0)

            if depth > max_depth or node in visited:
                continue

            visited.add(node)

            # Add predecessors (nodes this node depends on)
            for predecessor in G.predecessors(node):
                if predecessor not in visited:
                    queue.append((predecessor, depth + 1))

        visited.discard(start_node)
        return visited

    def _compute_risk_score(self, affected_nodes: List[GraphNode],
                           G: nx.DiGraph) -> float:
        """Compute risk score based on impact scope.

        Risk factors:
        - Number of affected nodes
        - PageRank of affected nodes (high centrality = high risk)
        - Presence of critical nodes (main, __init__, etc.)
        - Test coverage (more tests = lower risk)
        """
        if not affected_nodes:
            return 0.0

        # Factor 1: Count (normalized)
        count_score = min(len(affected_nodes) / 100.0, 1.0)

        # Factor 2: PageRank sum
        pagerank_scores = self.graph_store.get_pagerank_scores(affected_nodes[0].repo_id)
        pagerank_sum = sum(pagerank_scores.get(n.id, 0.0) for n in affected_nodes)
        pagerank_score = min(pagerank_sum / 1.0, 1.0)  # Normalize

        # Factor 3: Critical nodes
        critical_count = sum(
            1 for n in affected_nodes
            if any(keyword in n.name for keyword in ["main", "__init__", "config", "app"])
        )
        critical_score = min(critical_count / 5.0, 1.0)

        # Factor 4: Test nodes (inverse - more tests = lower risk)
        test_count = sum(1 for n in affected_nodes if "test" in n.file_path)
        test_ratio = test_count / max(len(affected_nodes), 1)
        test_score = 1.0 - min(test_ratio, 0.5)  # Max 50% reduction

        # Weighted combination
        risk_score = (
            0.3 * count_score +
            0.3 * pagerank_score +
            0.2 * critical_score +
            0.2 * test_score
        )

        return risk_score

    def _find_impact_paths(self, G: nx.DiGraph, start_node: str,
                          target_nodes: List[str]) -> List[List[str]]:
        """Find representative paths from start to target nodes."""
        paths = []

        for target in target_nodes[:10]:  # Limit to 10 paths
            try:
                path = nx.shortest_path(G, start_node, target)
                paths.append(path)
            except nx.NetworkXNoPath:
                continue

        return paths
```

**Days 39-40: Diff-Aware Impact Analysis**

_Deliverable: Compare graph before/after changes_

```python
def diff_aware_impact(
    self,
    before_commit: str,
    after_commit: str,
    changed_files: List[str]
) -> Dict[str, ImpactResult]:
    """Analyze impact of actual code changes between commits.

    Args:
        before_commit: SHA of commit before changes
        after_commit: SHA of commit after changes
        changed_files: List of files that changed

    Returns:
        Dictionary mapping changed node IDs to impact results
    """
    results = {}

    # Load graph snapshots
    before_graph = self._load_snapshot(before_commit)
    after_graph = self._load_snapshot(after_commit)

    # Find changed nodes
    changed_nodes = self._detect_changed_nodes(
        before_graph, after_graph, changed_files
    )

    # Analyze impact for each changed node
    for node_id in changed_nodes:
        result = self.analyze_impact(
            node_id,
            direction=ImpactDirection.FORWARD,
            max_depth=5
        )
        results[node_id] = result

    return results
```

#### Week 9: CLI & VSCode Integration

**Days 41-43: CLI Command**

_Deliverable: `dolphin impact <symbol>` command_

```python
# kb/cli/impact.py
"""CLI commands for impact analysis."""

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

app = typer.Typer()
console = Console()


@app.command()
def analyze(
    symbol: str = typer.Argument(..., help="Symbol to analyze (function, class, file)"),
    repo: str = typer.Option(None, help="Repository path or ID"),
    direction: str = typer.Option("forward", help="Direction: forward, backward, both"),
    max_depth: int = typer.Option(5, help="Maximum traversal depth"),
    output_format: str = typer.Option("table", help="Output format: table, json, graph")
):
    """Analyze the impact of changing a code symbol."""

    # Resolve symbol to node_id
    node_id = resolve_symbol(symbol, repo)

    if not node_id:
        console.print(f"[red]Error:[/red] Symbol '{symbol}' not found")
        return

    # Run analysis
    analyzer = ImpactAnalyzer(...)
    result = analyzer.analyze_impact(node_id, direction, max_depth)

    # Display results
    if output_format == "table":
        display_impact_table(result)
    elif output_format == "graph":
        display_impact_graph(result)
    else:
        display_impact_json(result)


def display_impact_table(result: ImpactResult):
    """Display impact analysis results as a table."""
    console.print(f"\n[bold]Impact Analysis Results[/bold]")
    console.print(f"Risk Score: [{'red' if result.risk_score > 0.7 else 'yellow' if result.risk_score > 0.4 else 'green'}]{result.risk_score:.2f}[/]\n")

    table = Table(title="Affected Nodes")
    table.add_column("Node", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("File", style="green")
    table.add_column("PageRank", style="yellow")

    for node in result.affected_nodes[:20]:  # Top 20
        pagerank = f"{node.metadata.get('pagerank', 0.0):.4f}"
        table.add_row(node.name, node.node_type.value, node.file_path, pagerank)

    console.print(table)

    # Display representative paths
    if result.impact_paths:
        console.print("\n[bold]Sample Impact Paths:[/bold]")
        for i, path in enumerate(result.impact_paths[:5], 1):
            tree = Tree(f"Path {i}")
            current = tree
            for node_id in path:
                node = GraphStore().get_node(node_id)
                current = current.add(f"{node.name} ({node.file_path})")
            console.print(tree)
```

**Days 44-45: VSCode Extension Integration**

_Deliverable: Impact analysis panel in VSCode_

```typescript
// vscode-extension/src/features/impactAnalysis.ts
/**
 * Impact analysis feature for VSCode extension.
 */

import * as vscode from "vscode";

export class ImpactAnalysisProvider {
  private panel: vscode.WebviewPanel | undefined;

  async showImpact(symbol: string) {
    // Create or reveal panel
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        "dolphinImpact",
        "Impact Analysis",
        vscode.ViewColumn.Two,
        { enableScripts: true }
      );
    }

    // Fetch impact data from KB
    const result = await this.fetchImpactData(symbol);

    // Render in webview
    this.panel.webview.html = this.getHtmlContent(result);
  }

  private async fetchImpactData(symbol: string): Promise<ImpactResult> {
    const response = await fetch("http://localhost:8000/v1/graph/impact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, direction: "forward" }),
    });

    return await response.json();
  }

  private getHtmlContent(result: ImpactResult): string {
    const riskColor =
      result.risk_score > 0.7
        ? "red"
        : result.risk_score > 0.4
        ? "orange"
        : "green";

    return `
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body { font-family: var(--vscode-font-family); padding: 20px; }
                    .risk-score { font-size: 24px; color: ${riskColor}; }
                    .node-list { margin-top: 20px; }
                    .node-item { padding: 8px; border-bottom: 1px solid #ccc; }
                </style>
            </head>
            <body>
                <h2>Impact Analysis</h2>
                <div class="risk-score">
                    Risk Score: ${result.risk_score.toFixed(2)}
                </div>
                <div class="node-list">
                    <h3>Affected Nodes (${result.affected_nodes.length})</h3>
                    ${result.affected_nodes
                      .map(
                        (node) => `
                        <div class="node-item">
                            <strong>${node.name}</strong> - ${node.file_path}
                        </div>
                    `
                      )
                      .join("")}
                </div>
            </body>
            </html>
        `;
  }
}

// Register command
export function activate(context: vscode.ExtensionContext) {
  const provider = new ImpactAnalysisProvider();

  const command = vscode.commands.registerCommand(
    "dolphin.analyzeImpact",
    async () => {
      // Get symbol at cursor
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;

      const position = editor.selection.active;
      const wordRange = editor.document.getWordRangeAtPosition(position);
      const symbol = editor.document.getText(wordRange);

      await provider.showImpact(symbol);
    }
  );

  context.subscriptions.push(command);
}
```

#### Week 10: Testing & Refinement

**Days 46-50: Comprehensive Testing**

_Deliverables:_

- Unit tests for traversal algorithms
- Integration tests with real repositories
- Accuracy validation (90%+ target)
- Performance benchmarks
- Documentation

### Phase 3 Success Criteria

- [ ] Forward/backward traversal algorithms implemented
- [ ] Risk scoring with 4+ factors
- [ ] CLI command functional
- [ ] VSCode extension integration complete
- [ ] Impact analysis accurate for 90%+ of symbol changes
- [ ] Performance: <2s for analysis up to depth 5
- [ ] Test coverage: 85%+

## Phase 4: Architectural Insights & Reports (2 weeks)

### Overview

**Goal**: Implement anti-pattern detectors and automated architectural quality reports.

**Timeline**: Weeks 15-16 (10 working days)

### Detailed Schedule

**(Days 71-75: Anti-Pattern Detection)**

```python
# kb/graph_intelligence/anti_patterns.py
"""Detect architectural anti-patterns."""

from typing import List, Dict
from enum import Enum


class AntiPatternType(str, Enum):
    GOD_CLASS = "god_class"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    DEAD_CODE = "dead_code"
    TIGHT_COUPLING = "tight_coupling"
    LOW_COHESION = "low_cohesion"


class AntiPatternDetector:
    """Detect architectural anti-patterns in code graph."""

    def detect_god_classes(self, repo_id: int) -> List[Dict]:
        """Detect classes with too many responsibilities."""
        god_classes = []

        class_nodes = self.graph_store.get_nodes_by_type(repo_id, NodeType.CLASS)

        for class_node in class_nodes:
            # Count methods
            methods = self.graph_store.get_children(class_node.id, NodeType.METHOD)

            # Count dependencies
            deps = len(list(self.graph.successors(class_node.id)))

            # Heuristic: >20 methods OR >30 dependencies
            if len(methods) > 20 or deps > 30:
                god_classes.append({
                    "node_id": class_node.id,
                    "name": class_node.name,
                    "file": class_node.file_path,
                    "method_count": len(methods),
                    "dependency_count": deps,
                    "severity": "high" if len(methods) > 30 else "medium"
                })

        return god_classes

    def detect_circular_dependencies(self, repo_id: int) -> List[List[str]]:
        """Detect circular import dependencies."""
        G = self.algorithms._load_graph(repo_id)

        # Get import edges only
        import_graph = nx.DiGraph()
        for u, v, data in G.edges(data=True):
            if data.get('edge_type') == EdgeType.IMPORTS:
                import_graph.add_edge(u, v)

        # Find cycles
        cycles = list(nx.simple_cycles(import_graph))

        return cycles

    def detect_dead_code(self, repo_id: int, entry_points: List[str]) -> List[Dict]:
        """Detect code unreachable from entry points."""
        G = self.algorithms._load_graph(repo_id)

        # Find reachable nodes from entry points
        reachable = set()
        for entry in entry_points:
            if entry in G:
                reachable.update(nx.descendants(G, entry))
                reachable.add(entry)

        # Find unreachable nodes
        all_nodes = set(G.nodes())
        unreachable = all_nodes - reachable

        dead_code = []
        for node_id in unreachable:
            node = self.graph_store.get_node(node_id)
            if node.node_type in (NodeType.FUNCTION, NodeType.CLASS):
                dead_code.append({
                    "node_id": node_id,
                    "name": node.name,
                    "file": node.file_path,
                    "type": node.node_type.value
                })

        return dead_code
```

**(Days 76-80: Report Generation + CI Integration)**

```python
# kb/graph_intelligence/reports.py
"""Generate architectural quality reports."""

from jinja2 import Template


class ReportGenerator:
    """Generate architectural quality reports."""

    def generate_markdown_report(self, repo_id: int) -> str:
        """Generate comprehensive markdown report."""
        detector = AntiPatternDetector(...)

        # Detect all anti-patterns
        god_classes = detector.detect_god_classes(repo_id)
        circular_deps = detector.detect_circular_dependencies(repo_id)
        dead_code = detector.detect_dead_code(repo_id, entry_points=["main"])

        # Compute metrics
        metrics = self.graph_store.get_aggregate_metrics(repo_id)

        # Render template
        template = Template("""
# Architectural Quality Report

**Repository ID**: {{ repo_id }}
**Generated**: {{ timestamp }}

## Executive Summary

- **Total Nodes**: {{ metrics.node_count }}
- **Total Edges**: {{ metrics.edge_count }}
- **Average Degree**: {{ metrics.avg_degree | round(2) }}
- **Anti-Patterns Detected**: {{ anti_pattern_count }}

## Anti-Patterns

### God Classes ({{ god_classes | length }})
{% for cls in god_classes %}
- **{{ cls.name }}** ({{ cls.file }})
  - Methods: {{ cls.method_count }}
  - Dependencies: {{ cls.dependency_count }}
  - Severity: {{ cls.severity }}
{% endfor %}

### Circular Dependencies ({{ circular_deps | length }})
{% for cycle in circular_deps %}
- {{ cycle | join(' → ') }}
{% endfor %}

### Dead Code ({{ dead_code | length }})
{% for item in dead_code %}
- {{ item.name }} ({{ item.file }})
{% endfor %}

## Recommendations

1. Refactor god classes into smaller, focused classes
2. Break circular dependencies by introducing abstractions
3. Remove or document dead code
4. Improve test coverage for high-centrality nodes
""")

        return template.render(
            repo_id=repo_id,
            timestamp=datetime.now().isoformat(),
            metrics=metrics,
            god_classes=god_classes,
            circular_deps=circular_deps,
            dead_code=dead_code,
            anti_pattern_count=len(god_classes) + len(circular_deps) + len(dead_code)
        )
```

### Phase 4 Success Criteria

- [ ] 10+ architectural insights detected automatically
- [ ] Markdown/HTML report generation working
- [ ] CI integration examples provided
- [ ] Documentation complete

---

## Testing Strategy

### Unit Testing

**Target Coverage**: 85%+

```bash
# Run all graph intelligence tests
uv run pytest tests/unit/graph_intelligence/ -v --cov=kb.graph_intelligence

# Specific test suites
uv run pytest tests/unit/graph_intelligence/test_call_graph.py
uv run pytest tests/unit/graph_intelligence/test_impact_analysis.py
uv run pytest tests/unit/graph_intelligence/test_algorithms.py
```

### Integration Testing

```python
# tests/integration/test_graph_end_to_end.py

@pytest.mark.integration
async def test_full_graph_pipeline():
    """Test complete graph extraction → analysis → visualization pipeline."""
    # 1. Index repository
    # 2. Extract graph
    # 3. Compute PageRank
    # 4. Run impact analysis
    # 5. Generate report
    pass
```

### Performance Benchmarks

```python
# tests/performance/test_graph_performance.py

def test_pagerank_computation_time():
    """PageRank should complete in <30s for 10K nodes."""
    # Test on large graph
    pass

def test_impact_analysis_latency():
    """Impact analysis should complete in <2s for depth 5."""
    pass

def test_graph_query_api_throughput():
    """Graph query API should handle 100 req/s."""
    pass
```

---

## Observability & Monitoring

### Prometheus Metrics

```python
# kb/graph_intelligence/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Extraction metrics
graph_extraction_duration = Histogram(
    'dolphin_graph_extraction_seconds',
    'Time to extract graph from file',
    ['language', 'file_size_kb']
)

graph_nodes_extracted = Counter(
    'dolphin_graph_nodes_extracted_total',
    'Total nodes extracted',
    ['node_type', 'language']
)

# PageRank metrics
pagerank_computation_duration = Histogram(
    'dolphin_pagerank_computation_seconds',
    'Time to compute PageRank',
    ['repo_id', 'node_count']
)

# Impact analysis metrics
impact_analysis_duration = Histogram(
    'dolphin_impact_analysis_seconds',
    'Time to perform impact analysis',
    ['direction', 'depth']
)

# Graph size metrics
graph_size_nodes = Gauge(
    'dolphin_graph_nodes_total',
    'Total nodes in graph',
    ['repo_id']
)

graph_size_edges = Gauge(
    'dolphin_graph_edges_total',
    'Total edges in graph',
    ['repo_id', 'edge_type']
)
```

### Distributed Tracing

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("extract_call_graph")
def extract_call_graph(file_path: str):
    span = trace.get_current_span()
    span.set_attribute("file_path", file_path)
    span.set_attribute("language", "python")

    # Extraction logic...

    span.set_attribute("nodes_extracted", len(nodes))
    span.set_attribute("edges_extracted", len(edges))
```

---

## Reference Implementations

### Aider's Repository Maps

**Location**: https://github.com/Aider-AI/aider

**Key Files to Study**:

- `aider/repo_map.py`: Tree-sitter repo map implementation
- `aider/repomap.py`: Graph ranking logic
- `aider/coder.py`: Integration with agent workflows

**What to Learn**:

- Tree-sitter query patterns for Python/TypeScript
- Graph-based ranking (PageRank-like algorithm)
- Dynamic context optimization for token budgets
- Integration with LLM context management

### Kilocode's Pattern Matching

**Location**: https://github.com/Kilo-Org/kilocode

**Key Areas**:

- Cross-language call detection patterns
- REST API endpoint extraction
- Symbol resolution across files

### Cline's File Operations

**Location**: https://github.com/cline/cline

**Key Areas**:

- VSCode integration patterns
- Webview communication
- File system watching for incremental updates

---

## Risk Mitigation

### Risk 1: Poor Call Graph Accuracy

**Impact**: High - Affects all downstream features

**Mitigation**:

- Extensive testing on diverse codebases (50+ test files per language)
- Incremental rollout: Python first, TypeScript second
- Fallback to basic graph if extraction fails
- User feedback mechanism to report missed calls

### Risk 2: PageRank Performance

**Impact**: Medium - Could slow down search

**Mitigation**:

- Pre-compute and cache PageRank scores
- Incremental updates for small changes
- Async background computation
- Monitoring: Alert if computation >30s

### Risk 3: Cross-Language Detection Accuracy

**Impact**: Low - Nice-to-have feature

**Mitigation**:

- Start with simple pattern matching (REST, RPC)
- Iterate based on user feedback
- Document limitations clearly
- Provide manual edge annotation if needed

---

## Success Metrics & KPIs

### Phase 1: Graph Extraction

- **Accuracy**: 95%+ for Python call graphs (manual verification on 50 files)
- **Coverage**: 90%+ of function calls detected
- **Performance**: <5s for 1000-file repository
- **Test Coverage**: 80%+

### Phase 2: Graph-Powered Search

- **MRR Improvement**: 15%+ on dependency-related queries
- **Latency**: <100ms p95 for graph-aware search
- **Adoption**: 50%+ of search queries use graph features

### Phase 3: Impact Analysis

- **Accuracy**: 90%+ for symbol change impact (verified on 100 examples)
- **Performance**: <2s for depth-5 analysis
- **Usage**: 100+ CLI commands per day

### Phase 4: Insights

- **Detection**: 10+ anti-patterns automatically detected
- **Accuracy**: 85%+ precision (verified manually on 50 repos)
- **Adoption**: 20+ teams using reports in CI

---

## Questions for Clarification

1. **Priority**: Should we prioritize Python or TypeScript first in Phase 1?

   - **Recommendation**: Python (Knowledge Bank is Python, more mature tree-sitter support)

2. **Deployment**: Should graph visualization be in VSCode or standalone web?

   - **Recommendation**: Both - VSCode panel for quick access, standalone for deep exploration

3. **Staffing**: 2 engineers sufficient or need 3?

   - **Recommendation**: 2 primary + 1 reviewer/advisor is optimal

4. **OSS Reference**: Which codebase should we prioritize studying?
   - **Recommendation**: Aider (graph ranking) > Kilocode (patterns) > Cline (VSCode integration)

---

## Next Steps

1. **Review & Approve** this implementation plan
2. **Assign Team**: 2 primary engineers + 1 reviewer
3. **Setup Development Environment**:
   - Clone reference repositories (Aider, Kilocode, Cline)
   - Setup local Knowledge Bank instance
   - Create feature branch: `feature/ep3-code-graph`
4. **Week 1 Kickoff**:
   - Day 1: Team orientation + architecture walkthrough
   - Day 2-5: Begin Phase 1 implementation
5. **Weekly Sync**: Every Friday to review progress, adjust timeline

---

## Appendix: Additional Resources

### Documentation to Create

- API documentation for graph endpoints
- Developer guide for adding new extractors
- User guide for impact analysis CLI
- Visualization user manual

### Tools to Install

```bash
# Python dependencies
uv pip install networkx python-louvain scipy
```

### Testing Datasets

- **Dolphin itself**: ~1K files, Python + TypeScript
- **FastAPI**: ~500 files, Python only
- **React**: ~2K files, JavaScript/TypeScript
- **Django**: ~3K files, Python only
