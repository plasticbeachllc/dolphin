# Dolphin Architecture

Technical architecture and implementation status for the Dolphin AI enablement platform.

**Version**: 1.0.0
**Status**: Production Ready
**Last Updated**: 2025-10-30

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Components](#components)
- [Data Model](#data-model)
- [Pipeline Flow](#pipeline-flow)
- [Implementation Status](#implementation-status)
- [Test Coverage](#test-coverage)
- [Performance Metrics](#performance-metrics)
- [Technology Stack](#technology-stack)

---

## Overview

Dolphin is a full-stack AI enablement platform that combines semantic code retrieval with multiple AI interfaces. The system decomposes repositories into language-aware chunks, embeds them using OpenAI, stores them in LanceDB, and provides semantic search via REST API and MCP protocol.

### Design Goals

1. **Semantic Precision**: Retrieve relevant code for natural-language queries
2. **Structural Awareness**: Preserve AST structure, symbols, and file anchors
3. **Git Integration**: Incremental indexing based on git history
4. **Multiple Interfaces**: Support CLI, REST API, MCP, and Continue IDE
5. **Cost Control**: Deduplication and session spend caps
6. **Local-First**: Run on MacBook Pro M4 (24GB RAM)

---

## System Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     User Interfaces                       │
├──────────────┬──────────────┬──────────────┬─────────────┤
│ Claude Desktop│  CLI (kb)   │  REST API    │ TypeScript  │
│   (MCP)      │  (bash)      │  (curl)      │  (bun)      │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬──────┘
       │              │              │              │
       │ MCP Protocol │              │              │
       │ (stdio)      │              │ HTTP         │
       ▼              ▼              ▼              ▼
┌──────────────────────────────────────────────────────────┐
│              MCP Bridge (TypeScript/Bun)                  │
│  • 6 MCP Tools                                            │
│  • REST Client                                            │
│  • Content Truncation (50KB)                              │
│  • Type-safe interfaces                                   │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP
                           ▼
┌──────────────────────────────────────────────────────────┐
│              REST API (Python/FastAPI)                    │
│  • 5 Endpoints                                            │
│  • Search Backend                                         │
│  • Embedding Pipeline                                     │
│  • Rank Fusion                                            │
└──────────────────────────┬───────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌──────────────┐
│ SQLite        │  │ LanceDB       │  │ Disk         │
│ (metadata)    │  │ (vectors)     │  │ (files)      │
└───────────────┘  └───────────────┘  └──────────────┘
```

### Data Flow

#### Indexing (Write Path)

```
Repository → Scanner → Chunker → Deduplicator → Embedder → Storage
                 │         │           │            │          │
              .gitignore  AST      SHA256      OpenAI    LanceDB+SQLite
                         parser    hash        API
```

#### Retrieval (Read Path)

```
Query → Embed → Vector Search → Re-rank → Snippet → Response
         │          │              │          │         │
     OpenAI    LanceDB KNN    Fusion     Truncate   JSON/MCP
```

---

## Components

### 1. REST API Backend (Python/FastAPI)

**Location**: `kb/api/`

**Endpoints**:

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/v1/health` | GET | Health check (shallow/deep) | ✅ |
| `/v1/repos` | GET | List indexed repositories | ✅ |
| `/v1/search` | POST | Semantic code search with MMR | ✅ |
| `/v1/chunks/{id}` | GET | Fetch chunk by ID | ✅ |
| `/v1/file` | GET | Fetch file slice by line range | ✅ |

**Key Features**:
- Automatic backend initialization on startup
- OpenAI + Stub embedding providers
- LanceDB vector search with fixed-size vectors
- **Maximal Marginal Relevance (MMR)** for result diversity
- Multi-level caching (Redis + in-memory) for performance
- Path traversal security protection
- Comprehensive error handling
- Session spend cap enforcement

**Files**:
- `kb/api/app.py` - FastAPI endpoints
- `kb/api/server.py` - Server initialization
- `kb/api/search_backend.py` - Search pipeline with MMR integration

### 2. MCP Bridge (TypeScript/Bun)

**Location**: `mcp-bridge/`

**Tools Implemented**:

| Tool | Purpose | Status |
|------|---------|--------|
| `search_knowledge` | Semantic code search with citations | ✅ |
| `fetch_chunk` | Retrieve chunk by ID | ✅ |
| `fetch_lines` | Retrieve file slice by line range | ✅ |
| `get_vector_store_info` | Get store metadata and stats | ✅ |
| `get_metadata` | Get chunk metadata without content | ✅ |
| `open_in_editor` | Open file in user's editor | ✅ |

**Key Features**:
- MCP Protocol 2025-06-18 compliance
- 50KB content budget with multi-stage trimming
- Structured error responses with remediation hints
- JSONL logging to `mcp-bridge/logs/mcp.log`
- Full TypeScript types with Zod validation
- AbortSignal support for cancellation

**Files**:
- `mcp-bridge/src/index.ts` - MCP server entry point
- `mcp-bridge/src/mcp/tools/` - Tool implementations
- `mcp-bridge/src/rest/client.ts` - REST API client
- `mcp-bridge/kb-cli.ts` - CLI wrapper

### 3. Knowledge Base Pipeline (Python)

**Location**: `kb/`

**Components**:

#### Scanner (`ingest/scanner.py`)
- Discovers files respecting `.gitignore`
- Security patterns (`.env`, `.pem`, `.aws/`, etc.)
- Language detection via file extension
- Returns `FileCandidate` objects

#### Chunkers (`chunkers/`)
- **Python** (`py_chunker.py`): Tree-sitter AST extraction (classes, functions, methods)
- **TypeScript** (`ts_chunker.py`): Tree-sitter AST extraction
- **Markdown** (`md_chunker.py`): Heading-based chunking
- **Fallback** (`fallback_chunker.py`): Token-windowing for unknown languages
- Registry (`registry.py`): Language detection and routing
- Token utils (`token_utils.py`): tiktoken integration

#### Embeddings (`embeddings/provider.py`)
- OpenAI `text-embedding-3-small` (1536 dims) - default
- OpenAI `text-embedding-3-large` (3072 dims) - per-repo override
- Stub provider for testing (zero vectors)
- Exponential backoff retry on 429/5xx
- Batch processing with concurrency control
- Per-session spend cap

#### Storage (`store/`)
- **SQLite** (`sqlite_meta.py`): Metadata store
  - Tables: `repos`, `sessions`, `files`, `chunk_content`, `chunk_locations`
  - SQLModel-based schema with migrations
- **LanceDB** (`lancedb_store.py`): Vector store
  - Collections: `chunks_small` (1536-dim), `chunks_large` (3072-dim)
  - Fixed-size vectors for compatibility
  - Upsert via delete-then-append

#### Ingestion Pipeline (`ingest/pipeline.py`)
- Orchestrates scanning → chunking → embedding → storage
- Git-aware incremental indexing
- Content deduplication via SHA256 hashing
- Idempotent re-runs
- Error logging per session
- Dry-run mode for cost estimation

#### CLI (`ingest/cli.py`)
- `kb init` - Initialize knowledge store
- `kb add-repo` - Register repository
- `kb index` - Index/reindex repository
- `kb status` - Show repository status
- `kb prune` - Remove deleted files
- Typer-based with rich output

### 4. CLI Tools

**kb-search** (`bin/kb-search`):
- Bash wrapper for MCP tools
- High-level commands (search, repos, chunk, lines, info, health)
- curl-based commands (no Bun required)
- Environment variable support (KB_TOP_K, KB_REPOS)

---

## Data Model

### SQLite Schema

#### repos
```sql
CREATE TABLE repos (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE,
  root_path TEXT,
  default_embed_model TEXT,  -- "small" or "large"
  created_at TEXT,
  updated_at TEXT
);
```

#### sessions
```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER,
  started_at TEXT,
  ended_at TEXT,
  commit_sha TEXT,
  branch TEXT,
  embed_model TEXT,
  status TEXT,  -- "running", "success", "failed"
  chunks_indexed INTEGER,
  chunks_skipped INTEGER,
  vectors_written INTEGER,
  tokens_used INTEGER,
  estimated_cost_usd REAL
);
```

#### files
```sql
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER,
  path TEXT,
  ext TEXT,
  language TEXT,
  is_binary BOOLEAN,
  last_commit_sha TEXT,
  last_indexed_at TEXT,
  UNIQUE(repo_id, path)
);
```

#### chunk_content
```sql
CREATE TABLE chunk_content (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER,
  file_id INTEGER,
  text_hash TEXT,  -- SHA256 for deduplication
  embed_model TEXT,
  content TEXT,
  token_count INTEGER,
  created_at TEXT,
  UNIQUE(repo_id, file_id, text_hash, embed_model)
);
```

#### chunk_locations
```sql
CREATE TABLE chunk_locations (
  id INTEGER PRIMARY KEY,
  content_id INTEGER,  -- FK to chunk_content
  start_line INTEGER,
  end_line INTEGER,
  symbol_kind TEXT,    -- "function", "class", "method", etc.
  symbol_name TEXT,
  symbol_path TEXT,    -- Full path like "pkg.mod.Class.method"
  commit_sha TEXT,
  indexed_at TEXT
);
```

### LanceDB Schema

Collections per embedding model:
- `chunks_small` - 1536 dimensions (text-embedding-3-small)
- `chunks_large` - 3072 dimensions (text-embedding-3-large)

Columns:
```python
{
  "id": str,              # Unique chunk location ID
  "vector": float32[],    # Embedding vector (fixed size)
  "repo": str,
  "path": str,
  "start_line": int,
  "end_line": int,
  "text_hash": str,
  "commit": str,
  "branch": str,
  "embed_model": str,
  "language": str,
  "symbol_kind": str,
  "symbol_name": str,
  "symbol_path": str,
  "heading_h1": str,      # Markdown only
  "heading_h2": str,      # Markdown only
  "heading_h3": str,      # Markdown only
  "token_count": int
}
```

---

## Pipeline Flow

### Indexing Flow

```
1. Scan Repository
   ├─ Read .gitignore
   ├─ Apply security patterns
   ├─ Discover files
   └─ Detect languages

2. Chunk Files
   ├─ Load repo config (.dolphin/config.toml)
   ├─ Route to language-specific chunker
   │  ├─ Python: Tree-sitter AST → functions/classes
   │  ├─ TypeScript: Tree-sitter AST → exports/functions/classes
   │  ├─ Markdown: Heading-based sections
   │  └─ Fallback: Token-windowing
   └─ Emit Chunk objects with metadata

3. Deduplicate
   ├─ Canonicalize content (normalize whitespace)
   ├─ Compute SHA256 hash
   ├─ Query SQLite for existing hash
   └─ Skip unchanged chunks

4. Embed
   ├─ Build embed input (code + docstring + signature)
   ├─ Batch texts (default 100)
   ├─ Call OpenAI API with retry/backoff
   ├─ Track token usage and cost
   └─ Enforce session spend cap

5. Persist
   ├─ Write to LanceDB (vectors + metadata)
   ├─ Write to SQLite (chunk_content, chunk_locations)
   ├─ Update file last_indexed_at
   └─ Record session stats
```

### Search Flow

```
1. Receive Query
   ├─ Parse request (query, repos, path_prefix, top_k, etc.)
   └─ Validate parameters

2. Embed Query
   ├─ Use same model as collection (small/large)
   ├─ Call OpenAI API
   └─ Get query vector

3. Vector Search
   ├─ Query LanceDB collection
   ├─ Apply filters (repo, path_prefix)
   ├─ KNN search for top_k results
   └─ Get initial hits with scores

4. Re-rank (if enabled)
   ├─ Reciprocal Rank Fusion
   ├─ Weighted score fusion
   ├─ **Maximal Marginal Relevance (MMR)** for result diversity
   └─ Sort by final score

5. Post-process
   ├─ Apply score_cutoff filter
   ├─ Apply MMR reranking (if enabled)
   ├─ Truncate snippets to max_snippet_tokens
   ├─ Fetch metadata from SQLite
   └─ Build response

6. Return Results
   ├─ Hits array with provenance
   ├─ Meta (latency, model, top_k)
   └─ JSON or MCP protocol response
```

---

## Implementation Status

### ✅ Phase 1-6 Complete: Knowledge Base Pipeline

- ✅ Full KB pipeline operational (147/147 tests passing)
- ✅ OpenAI embedding integration with retry logic
- ✅ SQLite + LanceDB storage layer
- ✅ Git-aware incremental indexing
- ✅ Language-specific chunking (Python, TypeScript, Markdown, fallback)
- ✅ Per-repository configuration system
- ✅ Content-based deduplication
- ✅ Idempotent ingestion (safe re-runs)

### ✅ Phase 7 Complete: REST API

- ✅ All 5 endpoints implemented and tested
- ✅ Automatic backend initialization
- ✅ Path traversal security
- ✅ Comprehensive error handling
- ✅ Health checks (shallow + deep)
- ✅ Repository listing with stats
- ✅ Semantic search with filtering
- ✅ Chunk and file retrieval

### ✅ Phase 5b Complete: MCP Bridge

- ✅ Specification and design
- ✅ TypeScript project scaffolding
- ✅ All 6 MCP tools implemented
- ✅ Unit test framework with mock REST server
- ✅ JSONL logging with rotation
- ✅ Content truncation (50KB budget)
- ✅ Error handling with remediation hints

### 🔜 Future Enhancements

- 🔜 Hybrid search (BM25 + vector)
- 🔜 Reranking models
- 🔜 Watch mode for auto-indexing
- 🔜 Query understanding and routing
- 🔜 Cross-repo code intelligence
- 🔜 Evaluation framework (P@5, R@10, MRR)

---

## Test Coverage

### Python Tests: 191/191 Passing ✅

**Unit Tests**:
- Chunkers (Python, TypeScript, Markdown, fallback): 45 tests
- Embeddings (OpenAI provider, retry, stub): 15 tests
- Storage (SQLite, LanceDB): 29 tests
- Hashing and deduplication: 12 tests
- Scanner and ignore handling: 18 tests
- Token utilities: 8 tests

**Integration Tests**:
- Search API: 11 tests
- Search backend: 10 tests
- MCP endpoints: 12 tests
- Rank fusion: 19 tests
- Pipeline end-to-end: 12 tests

### TypeScript Tests: 52/52 Passing ✅

**MCP Bridge Tests**:
- Tool implementations: 36 tests
- REST client: 8 tests
- Logging and concurrency: 4 tests
- Security and connectivity: 4 tests

### Total: 243/243 Tests Passing ✅

**Test Commands**:
```bash
# Python tests
pytest tests/unit/ -v                    # Unit tests
pytest tests/integration/ -v             # Integration tests
pytest --cov=kb/src                    # With coverage

# TypeScript tests
cd mcp-bridge && bun test                # All MCP tests

# Integration test (requires kb-api running)
cd mcp-bridge && bun run test-integration.ts
```

---

## Performance Metrics

### Latency Targets

| Metric | Target | Current |
|--------|--------|---------|
| Search p50 | ≤ 600ms | ~300ms |
| Search p95 | ≤ 2s | ~800ms |
| Search p99 | ≤ 5s | ~2s |
| Embedding | - | ~150ms |
| Vector search | - | ~50ms |

### Throughput

- Single-user: 10-20 QPS sustained
- Concurrent: 8 parallel queries (for LLM multi-tool calls)

### Index Size

| Repo Size | Files | Chunks | LanceDB | SQLite |
|-----------|-------|--------|---------|--------|
| Small | 1K | 50K | ~100 MB | ~5 MB |
| Medium | 10K | 500K | ~1 GB | ~50 MB |
| Large | 100K | 5M | ~10 GB | ~500 MB |

### Memory Usage

- Baseline (idle): ~200 MB
- Under load (8 concurrent): ~500 MB
- LanceDB cache: 512 MB (configurable)

---

## Technology Stack

### Backend (Python)

- **FastAPI** - REST API framework
- **SQLModel** - ORM for SQLite
- **LanceDB** - Vector database
- **OpenAI** - Embeddings API
- **Tree-sitter** - Code parsing (Python, TypeScript)
- **tiktoken** - Token counting
- **pathspec** - .gitignore parsing
- **Typer** - CLI framework

### MCP Bridge (TypeScript)

- **Bun** - Runtime
- **Zod** - Schema validation
- **@modelcontextprotocol/sdk** - MCP protocol
- **TypeScript** - Type safety

### Storage

- **SQLite** - Metadata and provenance
- **LanceDB** - Vector search (ANN)
- **File system** - Repository files

### Development

- **pytest** - Python testing
- **Bun test** - TypeScript testing
- **uv** - Python package manager
- **Justfile** - Task automation
- **Git** - Version control and indexing

---

## Key Design Decisions

### 1. Fixed-Size Vectors

**Problem**: LanceDB requires fixed-size vector columns.

**Solution**: Changed from `pa.list_(pa.float32())` to `pa.list_(pa.float32(), dim)` with explicit dimensions (1536 for small, 3072 for large).

### 2. Separate Collections per Model

**Problem**: Can't mix 1536-dim and 3072-dim vectors in one table.

**Solution**: Maintain separate LanceDB collections (`chunks_small`, `chunks_large`) per embedding model.

### 3. Content Deduplication

**Problem**: Re-embedding unchanged code wastes money and time.

**Solution**: SHA256 hash of canonicalized content; skip chunks with existing hashes in SQLite.

### 4. Chunk Location vs Content

**Problem**: Same code can appear in multiple places (copies, refactors).

**Solution**: Separate `chunk_content` (deduplicated) from `chunk_locations` (multiple occurrences).

### 5. Git-Aware Indexing

**Problem**: Full reindexing is slow and expensive.

**Solution**: Track `last_commit_sha` per file; use `git diff` to find changed files; only reindex those.

### 6. Path Traversal Protection

**Problem**: `/v1/file` endpoint could read arbitrary files.

**Solution**: Validate that resolved path is within repository root; reject requests with `..` or absolute paths outside repo.

### 7. MCP Content Budget

**Problem**: Large search results exceed MCP response limits.

**Solution**: Multi-stage trimming:
1. Trim prompt-ready text (10% iteratively)
2. Shrink snippet windows (500 → 300 → 200 chars)
3. Remove snippet text from lowest-scoring hits
4. Drop lowest-scoring citations entirely

### 8. Session Spend Cap

**Problem**: Runaway indexing could cost hundreds of dollars.

**Solution**: Per-session spend cap (default $10); abort gracefully when reached; emit cost estimates before embedding.

---

## Future Considerations

### Scalability

- **Parallel indexing**: Worker pool for multi-file embedding
- **Distributed storage**: Separate LanceDB/SQLite for multi-machine setup
- **Caching**: Query result caching with TTL

### Quality

- **Hybrid search**: Combine BM25 keyword search with vector search
- **Reranking**: Cross-encoder reranker for top-K results
- **Evaluation**: Automated P@5, R@10, MRR tracking

### Usability

- **Watch mode**: Auto-reindex on file changes
- **Post-commit hook**: Trigger indexing after git commits
- **Query understanding**: Classify intent and route appropriately

### Intelligence

- **Code graph**: Call graphs, dependency tracking
- **Cross-repo**: Link related code across repositories
- **Explanations**: Generate summaries of search results

---

## References

- [User Guide](GUIDE.md) - Complete user documentation
- [README](../README.md) - Project overview
- [Main codebase](../kb/src/) - Python implementation
- [MCP Bridge](../mcp-bridge/) - TypeScript implementation

---

**Status**: ✅ Production Ready
**Test Coverage**: 243/243 tests passing
**Version**: 1.0.0
**Date**: 2025-10-30
