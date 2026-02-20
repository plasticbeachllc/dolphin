# Changelog - pb-dolphin Python Package

All notable changes to the pb-dolphin Python package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Note**: This changelog covers only the Python package. For component-specific changes:

- **MCP Bridge**: See [mcp-bridge/CHANGELOG.md](mcp-bridge/CHANGELOG.md)

---

---

## [Unreleased]

## [0.2.2] - 2026-02-20

### Added

- **Schema Version Tracking + Startup Auto-Migration**: Metadata startup now tracks `schema_version` and automatically applies pending migrations to canonical schema `v1`.
- **CLI Query UX Upgrade**: `dolphin search` now supports compact default output, `--verbose` expanded output, stable `--json` mode, language filtering (`--lang`), exclusion filters, and snippet/context controls.
- **Terminal UX Refresh**: `dolphin serve` and related CLI status output now use consistent rich-formatted status lines with clearer startup/shutdown/watcher context and actionable hints.
- **Application Output Beautification**: Standardized user-facing CLI/server/indexing output with clearer status levels, compact progress lines, and actionable terminal hints.
- **Logging Controls**: Added configurable log level (`DOLPHIN_LOG_LEVEL`) and opt-in traceback payloads (`DOLPHIN_LOG_TRACEBACK=1`) while keeping structured JSON log output stable.
- **Cleaner Indexing Progress Output**: Removed duplicate `Indexing file:` lines and moved per-file chunker diagnostics to debug-level so default indexing output stays high-signal.

### Fixed

- **Foreign Key Deletion Ordering**: Reordered deleted-file processing to clean graph dependencies before deleting file records, preventing `FOREIGN KEY constraint failed` errors during incremental deletion handling in the ingestion pipeline.
- **Canonical Schema Baseline (`v1`)**: Startup now auto-migrates metadata DBs to canonical schema `v1` and records `schema_version`, establishing `v1` as the only supported runtime schema for this release.
- **Deleted-File Reliability**: Unified sync/parallel deletion cleanup flow, fixed `dry_run` deletion mutations, and added actionable FK failure diagnostics with dependent-row context.
- **Graceful Server Shutdown**: Watcher shutdown now requests stop and explicitly closes watcher executors, preventing post-shutdown Ctrl-C hangs/noisy thread-exit traces.
- **Default Ignore Coverage**: Added `*.log` and `*.log.*` to built-in ignore patterns and default config so log files are skipped by default.
- **FK Deletion Diagnostics**: Corrected `graph_metrics` dependency diagnostics to join via `code_nodes` (no direct `file_id` lookup), preventing masked errors on FK failures.
- **Migration Rebuild Stability**: Canonical schema table rebuilds now drop renamed legacy backup tables before index recreation to avoid SQLite index-name collisions during startup migration.

## [0.2.1] - 2026-01-26

### Added

- **Cursor-based Pagination**: Implemented cursor-based pagination for search results (`next_cursor`), enabling efficient and stateless deep pagination.
- **Atomic Indexing**: Indexing sessions are now atomic; changes are only committed upon successful completion, preventing partial index states.
- **Structured Snippets**: Search results now return structured snippet objects with distinct `text`, `context_before`, and `context_after` fields instead of flat strings.

### Fixed

- **IPC Memory Leak**: Resolved a critical memory leak in the IPC layer.
- **Cache Invalidation**: Fixed issues with cache invalidation to ensure stale data is properly cleared.

### Changed

- **Search Backend**: Refactored the search backend signature to return a tuple of `(results, next_cursor)`, standardizing pagination handling across backends.

## [0.2.0] - 2026-01-25

### Added

- `pb-dolphin==0.2.0`
- `watchfiles` dependency (used for repository watching).
- `dolphin serve` repo watching defaults:
  - Watches all registered repos unless `--no-watch` is set
  - Supports `--watch <repo>` to limit watching to specific repos
- Standalone `dolphin watch <repo>` command.
- Expanded versioned `/v1/*` REST API surface:
  - `/v1/health`, `/v1/search`, `/v1/repos`, `/v1/chunks/{chunk_id}`, `/v1/file`
  - Indexing tasks: `/v1/index`, `/v1/index/status/{task_id}`, `/v1/index/tasks`
  - Repo operations: `/v1/repos/{repo_name}/stats`, `/v1/repos/{repo_name}/reindex`, `/v1/repos/{repo_name}/index`
  - Change tracking: `/v1/repos/{repo_name}/changes`, `/v1/repos/{repo_name}/pending-changes`, `/v1/repos/{repo_name}/changes/mark-processed`, `/v1/repos/{repo_name}/drift`
  - Admin: `/v1/admin/reload`, `/v1/admin/rebuild-fts5`
- Major ingestion/indexing improvements for performance and correctness (async/parallel pipeline, dynamic pooling, branch tracking, and file-watching workflows).

#### 📘 Documentation and Process

- Standardized all testing guidance into the canonical `docs/TESTING.md`, consolidating backend/extension/MCP/observability instructions and adding a post-merge verification checklist to keep releases linted, tested, and reflected in the changelog.

#### 📚 Enhanced Knowledge Base Core

- **Advanced Language-Aware Chunking**
  - **Python** (`py_chunker.py`): Tree-sitter AST parsing for classes, functions, methods, docstrings
  - **TypeScript/JavaScript** (`ts_chunker.py`): Exports, functions, classes, interfaces, type definitions
  - **Markdown** (`md_chunker.py`): Heading-based hierarchical sectioning (H1-H6)
  - **SQL** (`sql_chunker.py`): Table definitions, queries, stored procedures, views
  - **Svelte** (`svelte_chunker.py`): Component parsing with script/template/style separation
  - **Fallback** (`fallback_chunker.py`): Token-windowing with configurable overlap for unsupported languages

- **Hybrid Semantic Search**
  - OpenAI embeddings (text-embedding-3-small: 1536-dim, text-embedding-3-large: 3072-dim)
  - LanceDB vector storage with IVF (Inverted File) indexing
  - **Hybrid Search**: BM25 full-text + Vector search with Reciprocal Rank Fusion
    - 40% better precision on identifier searches vs. vector-only
    - Configurable BM25 k1 and b parameters
    - Configurable fusion k parameter (default: 60)
  - **Cross-Encoder Reranking** (optional, install with `pip install pb-dolphin[reranking]`):
    - ms-marco-MiniLM-L-6-v2 model
    - 20-30% MRR improvement over baseline
    - Batch processing with configurable batch size
    - Score threshold filtering
    - Device selection (CPU/CUDA)
    - Trade-off: 2-3x slower, ~2GB additional install size

- **Result Ranking**
  - **Maximal Marginal Relevance (MMR)**: Balances relevance and diversity
    - Prevents redundant/similar results
    - Configurable lambda parameter (default: 0.7)
    - Improves result variety for exploratory searches
  - **Reciprocal Rank Fusion (RRF)**: Combines multiple ranking sources
    - Merges BM25 and vector search results
    - No score normalization required
    - Robust to outliers and score scale differences

- **Code Graph Store**
  - SQLite-based graph database for code entities and relationships
  - Node types: functions, classes, methods, modules
  - Edge types: calls, imports, inheritance, references
  - Cross-repository relationship tracking
  - Entity metadata: signatures, docstrings, visibility modifiers
  - Graph pruning on file deletions to prevent orphaned data
  - Query optimization for large codebases

- **Multi-Backend Storage**
  - **SQLite**: Metadata, provenance, graph, FTS5 full-text search
  - **LanceDB**: Vector embeddings with ANN search
  - Content deduplication via SHA256 hashing
  - Separate LanceDB collections per embedding model
  - Foreign key constraints for referential integrity

#### ⚡ Parallelized Knowledge Base

- **Batch Processing**
  - Configurable batch size for embedding API calls (default: 100)
  - Parallel embedding requests with concurrency control
  - Rate limit handling with exponential backoff retry logic
  - Batch processing for cross-encoder reranking (batch size: 32)

- **Concurrent Search Capabilities**
  - 8 parallel search queries supported (for LLM multi-tool calls)
  - ~300ms p50 search latency for medium-sized repos (~500K chunks)
  - ~800ms p95 search latency ""
  - 10-20 sustained queries per second for single-user workloads

- **Adaptive ANN (Approximate Nearest Neighbor) Tuning**
  - Automatic query-type detection (identifier vs. concept vs. example-based)
  - Dynamic nprobes adjustment based on dataset size and query patterns
  - Three preset optimization strategies: speed, accuracy, development
  - Custom parameter support for fine-tuning
  - ~40% faster searches with adaptive tuning vs. static parameters
  - Profiling and benchmarking scripts (`scripts/benchmark_ann.py`)

- **Multi-Level Caching System**
  - Redis support for distributed caching (optional)
  - In-memory LRU caching for hot queries
  - 512 MB LanceDB cache (configurable via `LANCE_DB_CACHE_SIZE`)
  - Embedding deduplication via SHA256 content hashing
  - Query result caching with TTL

- **Resource Management**
  - Baseline memory footprint: ~200 MB
  - Under load (8 concurrent queries): ~500 MB
  - Per-session spend caps (default: $10 USD)
  - Token usage tracking and reporting
  - Graceful handling of rate limits

#### 🌐 REST API

- **Production FastAPI REST API**
  - **5 Core Endpoints**:
    1. `GET /health` - Health checks (shallow: API availability, deep: DB + vector store)
    2. `GET /v1/repos` - List indexed repositories with file counts and statistics
    3. `POST /v1/search` - Semantic search with configurable parameters (top_k, score_threshold, etc.)
    4. `GET /v1/chunks/{id}` - Retrieve specific chunk by ID with metadata
    5. `GET /v1/file` - Fetch file slices by line range with path traversal protection
  - CORS middleware for local development clients
  - Structured error responses with remediation hints
  - Request validation with Pydantic models
  - JSONL logging with automatic rotation
  - `/v1` aliases added for core read endpoints (search, repos, chunks, file); `/health` remains unauthenticated

#### 🔧 Configuration & CLI Management

- **Multi-Level Configuration System**
  - Repository-specific: `.dolphin/config.toml`
  - User-global: `~/.dolphin/config.toml`
  - Automatic config creation with sensible defaults
  - TOML format with schema validation
  - Config hierarchy: repo-specific overrides user-global

- **Unified CLI (`dolphin` command)**
  - `dolphin init` - Initialize configuration files
  - `dolphin add-repo` - Register a repository for indexing
  - `dolphin index` - Index or reindex repository
  - `dolphin search` - Interactive semantic code search
  - `dolphin serve` - Start REST API server
  - `dolphin config --show` - Display active configuration
  - Rich terminal output with progress bars and status indicators
  - Legacy `kb` CLI maintained for backward compatibility

- **Repository Management Commands**
  - `rm-repo` - Remove repository with cleanup validation and confirmation (use `--force` to skip)
  - `reset-repo` - Reset repository state with automatic session abort
  - `validate-repo` - Check repository integrity and index health
  - `repair-repo` - Repair corrupted repositories with `--dry-run` support
  - Foreign key validation during operations
  - Comprehensive cleanup with warnings for non-critical issues

#### 🧪 Comprehensive Testing Framework

- **Extensive Test Suite (191+ Python Tests)**
  - **Unit tests**: `tests/unit/` - Test individual components
    - Chunkers (Python, TypeScript, Markdown, SQL, Svelte, fallback): 45+ tests
    - Embeddings (OpenAI provider, retry logic, stub implementations): 15 tests
    - Storage layers (SQLite, LanceDB, graph store): 29 tests
    - Hashing and content deduplication: 12 tests
    - Scanner and `.gitignore` handling: 18 tests
    - Token counting utilities: 8 tests
    - ANN tuning and optimization: Multiple tests
  - **Integration tests**: `tests/integration/` - Test API endpoints and workflows
    - Search API integration: 11 tests
    - Search backend unit tests: 10 tests
    - MCP endpoints: 12 tests
    - Rank fusion algorithms: 19 tests
    - End-to-end pipeline tests: 12 tests
    - Hybrid search: Multiple tests
    - KB auto-sync system: Multiple tests
  - **Run**: `uv run pytest tests/unit/ -v` or `uv run pytest tests/integration/ -v`
  - **Coverage**: `uv run pytest --cov=kb/src`

- **Profiling and Benchmarking Tools**
  - `scripts/benchmark_ann.py` - ANN parameter profiling across datasets
  - `scripts/test_hybrid_search_performance.py` - Hybrid search quality metrics:
    - Precision@5, Precision@10 measurements
    - Mean Reciprocal Rank (MRR) calculations
    - Latency profiling (mean, median, p95, p99)
    - Baseline vs. hybrid vs. reranked comparisons
  - Performance regression detection
  - Memory profiling utilities

- **Evaluation Framework**
  - Search quality metrics (Precision, Recall, MRR, NDCG)
  - Latency and throughput tracking
  - HTML and XML coverage reports
  - JUnit XML output for CI/CD integration
  - Parallel test execution with `pytest-xdist`
  - Cache testing guide for embedding providers

#### 🚀 Production-Ready Features

- **Security Hardening**
  - Path traversal protection in file serving endpoints
  - Parameterized SQL queries to prevent injection attacks
  - Secure environment variable handling for API keys
  - Secret file exclusion (`.env`, `.pem`, `.aws/`, etc.)
  - Input validation and sanitization
  - CORS configuration for local development clients

- **Robust Error Handling**
  - Comprehensive error messages with actionable guidance
  - Graceful degradation on service failures
  - Exponential backoff retry logic for transient errors
  - Automatic session cleanup on fatal errors
  - Transaction rollback for database operations
  - Non-blocking warnings for non-critical issues

- **Monitoring and Observability**
  - Health check endpoints (shallow and deep)
  - Real-time progress tracking with file-level granularity
  - Latency metrics (p50, p95, p99)
  - Token usage tracking and reporting
  - Spend cap enforcement per session
  - JSONL structured logging for analysis
  - Warning detection and reporting

#### 📚 Enhanced Knowledge Base Core

- **Advanced Language-Aware Chunking**
  - **Python** (`py_chunker.py`): Tree-sitter AST parsing for classes, functions, methods, docstrings
  - **TypeScript/JavaScript** (`ts_chunker.py`): Exports, functions, classes, interfaces, type definitions
  - **Markdown** (`md_chunker.py`): Heading-based hierarchical sectioning (H1-H6)
  - **SQL** (`sql_chunker.py`): Table definitions, queries, stored procedures, views
  - **Svelte** (`svelte_chunker.py`): Component parsing with script/template/style separation
  - **Fallback** (`fallback_chunker.py`): Token-windowing with configurable overlap for unsupported languages

- **Hybrid Semantic Search**
  - OpenAI embeddings (text-embedding-3-small: 1536-dim, text-embedding-3-large: 3072-dim)
  - LanceDB vector storage with IVF (Inverted File) indexing
  - **Hybrid Search**: BM25 full-text + Vector search with Reciprocal Rank Fusion
    - 40% better precision on identifier searches vs. vector-only
    - Configurable BM25 k1 and b parameters
    - Configurable fusion k parameter (default: 60)
  - **Cross-Encoder Reranking** (optional, install with `pip install pb-dolphin[reranking]`):
    - ms-marco-MiniLM-L-6-v2 model
    - 20-30% MRR improvement over baseline
    - Batch processing with configurable batch size
    - Score threshold filtering
    - Device selection (CPU/CUDA)
    - Trade-off: 2-3x slower, ~2GB additional install size

- **Result Ranking**
  - **Maximal Marginal Relevance (MMR)**: Balances relevance and diversity
    - Prevents redundant/similar results
    - Configurable lambda parameter (default: 0.7)
    - Improves result variety for exploratory searches
  - **Reciprocal Rank Fusion (RRF)**: Combines multiple ranking sources
    - Merges BM25 and vector search results
    - No score normalization required
    - Robust to outliers and score scale differences

- **Code Graph Store**
  - SQLite-based graph database for code entities and relationships
  - Node types: functions, classes, methods, modules
  - Edge types: calls, imports, inheritance, references
  - Cross-repository relationship tracking
  - Entity metadata: signatures, docstrings, visibility modifiers
  - Graph pruning on file deletions to prevent orphaned data
  - Query optimization for large codebases

- **Multi-Backend Storage**
  - **SQLite**: Metadata, provenance, graph, FTS5 full-text search
  - **LanceDB**: Vector embeddings with ANN search
  - Content deduplication via SHA256 hashing
  - Separate LanceDB collections per embedding model
  - Foreign key constraints for referential integrity

#### ⚡ Parallelized Knowledge Base

- **Batch Processing**
  - Configurable batch size for embedding API calls (default: 100)
  - Parallel embedding requests with concurrency control
  - Rate limit handling with exponential backoff retry logic
  - Batch processing for cross-encoder reranking (batch size: 32)

- **Concurrent Search Capabilities**
  - 8 parallel search queries supported (for LLM multi-tool calls)
  - ~300ms p50 search latency for medium-sized repos (~500K chunks)
  - ~800ms p95 search latency ""
  - 10-20 sustained queries per second for single-user workloads

- **Adaptive ANN (Approximate Nearest Neighbor) Tuning**
  - Automatic query-type detection (identifier vs. concept vs. example-based)
  - Dynamic nprobes adjustment based on dataset size and query patterns
  - Three preset optimization strategies: speed, accuracy, development
  - Custom parameter support for fine-tuning
  - ~40% faster searches with adaptive tuning vs. static parameters
  - Profiling and benchmarking scripts (`scripts/benchmark_ann.py`)

- **Multi-Level Caching System**
  - Redis support for distributed caching (optional)
  - In-memory LRU caching for hot queries
  - 512 MB LanceDB cache (configurable via `LANCE_DB_CACHE_SIZE`)
  - Embedding deduplication via SHA256 content hashing
  - Query result caching with TTL

- **Resource Management**
  - Baseline memory footprint: ~200 MB
  - Under load (8 concurrent queries): ~500 MB
  - Per-session spend caps (default: $10 USD)
  - Token usage tracking and reporting
  - Graceful handling of rate limits

#### 🌐 REST API

- **Production FastAPI REST API**
  - **5 Core Endpoints**:
    1. `GET /health` - Health checks (shallow: API availability, deep: DB + vector store)
    2. `GET /v1/repos` - List indexed repositories with file counts and statistics
    3. `POST /v1/search` - Semantic search with configurable parameters (top_k, score_threshold, etc.)
    4. `GET /v1/chunks/{id}` - Retrieve specific chunk by ID with metadata
    5. `GET /v1/file` - Fetch file slices by line range with path traversal protection
  - CORS middleware for local development clients
  - Structured error responses with remediation hints
  - Request validation with Pydantic models
  - JSONL logging with automatic rotation
  - `/v1` aliases added for core read endpoints (search, repos, chunks, file); `/health` remains unauthenticated

#### 🔧 Configuration & CLI Management

- **Multi-Level Configuration System**
  - Repository-specific: `.dolphin/config.toml`
  - User-global: `~/.dolphin/config.toml`
  - Automatic config creation with sensible defaults
  - TOML format with schema validation
  - Config hierarchy: repo-specific overrides user-global

- **Unified CLI (`dolphin` command)**
  - `dolphin init` - Initialize configuration files
  - `dolphin add-repo` - Register a repository for indexing
  - `dolphin index` - Index or reindex repository
  - `dolphin search` - Interactive semantic code search
  - `dolphin serve` - Start REST API server
  - `dolphin config --show` - Display active configuration
  - Rich terminal output with progress bars and status indicators
  - Legacy `kb` CLI maintained for backward compatibility

- **Repository Management Commands**
  - `rm-repo` - Remove repository with cleanup validation and confirmation (use `--force` to skip)
  - `reset-repo` - Reset repository state with automatic session abort
  - `validate-repo` - Check repository integrity and index health
  - `repair-repo` - Repair corrupted repositories with `--dry-run` support
  - Foreign key validation during operations
  - Comprehensive cleanup with warnings for non-critical issues

#### 🧪 Comprehensive Testing Framework

- **Extensive Test Suite (191+ Python Tests)**
  - **Unit tests**: `tests/unit/` - Test individual components
    - Chunkers (Python, TypeScript, Markdown, SQL, Svelte, fallback): 45+ tests
    - Embeddings (OpenAI provider, retry logic, stub implementations): 15 tests
    - Storage layers (SQLite, LanceDB, graph store): 29 tests
    - Hashing and content deduplication: 12 tests
    - Scanner and `.gitignore` handling: 18 tests
    - Token counting utilities: 8 tests
    - ANN tuning and optimization: Multiple tests
  - **Integration tests**: `tests/integration/` - Test API endpoints and workflows
    - Search API integration: 11 tests
    - Search backend unit tests: 10 tests
    - MCP endpoints: 12 tests
    - Rank fusion algorithms: 19 tests
    - End-to-end pipeline tests: 12 tests
    - Hybrid search: Multiple tests
    - KB auto-sync system: Multiple tests
  - **Run**: `uv run pytest tests/unit/ -v` or `uv run pytest tests/integration/ -v`
  - **Coverage**: `uv run pytest --cov=kb/src`

- **Profiling and Benchmarking Tools**
  - `scripts/benchmark_ann.py` - ANN parameter profiling across datasets
  - `scripts/test_hybrid_search_performance.py` - Hybrid search quality metrics:
    - Precision@5, Precision@10 measurements
    - Mean Reciprocal Rank (MRR) calculations
    - Latency profiling (mean, median, p95, p99)
    - Baseline vs. hybrid vs. reranked comparisons
  - Performance regression detection
  - Memory profiling utilities

- **Evaluation Framework**
  - Search quality metrics (Precision, Recall, MRR, NDCG)
  - Latency and throughput tracking
  - HTML and XML coverage reports
  - JUnit XML output for CI/CD integration
  - Parallel test execution with `pytest-xdist`
  - Cache testing guide for embedding providers

#### 🚀 Production-Ready Features

- **Security Hardening**
  - Path traversal protection in file serving endpoints
  - Parameterized SQL queries to prevent injection attacks
  - Secure environment variable handling for API keys
  - Secret file exclusion (`.env`, `.pem`, `.aws/`, etc.)
  - Input validation and sanitization
  - CORS configuration for local development clients

- **Robust Error Handling**
  - Comprehensive error messages with actionable guidance
  - Graceful degradation on service failures
  - Exponential backoff retry logic for transient errors
  - Automatic session cleanup on fatal errors
  - Transaction rollback for database operations
  - Non-blocking warnings for non-critical issues

- **Monitoring and Observability**
  - Health check endpoints (shallow and deep)
  - Real-time progress tracking with file-level granularity
  - Latency metrics (p50, p95, p99)
  - Token usage tracking and reporting
  - Spend cap enforcement per session
  - JSONL structured logging for analysis
  - Warning detection and reporting

### Changed

- **Dependency Optimization**
  - Core install reduced from ~2GB to ~200MB
  - Heavy ML dependencies moved to optional extras
  - Reranking: `pip install pb-dolphin[reranking]` (~2GB)
  - Orchestrator: `pip install pb-dolphin[orchestrator]`
  - Faster installation and reduced storage footprint

- **Configuration System Improvements**
  - Fixed config template field names to match parser expectations
  - Added missing configuration fields (cache settings, batch_size, concurrency)
  - Removed non-functional config sections to reduce confusion
  - Default embedding provider now "openai" (was "stub")
  - Config hierarchy properly loads user config before system defaults

### Fixed

- `chunk_id` followups: `/v1/chunks/{chunk_id}` supports both Row IDs and deterministic FTS IDs (unblocks MCP followups).
- Incremental indexing preserves vectors for unchanged chunks when Row IDs change (e.g., code moves).
- `/v1/file` validates line ranges (rejects invalid `start > end`).
- Search responses omit raw embedding vectors to reduce payload size.
- LanceDB table enumeration uses `list_tables()` to avoid deprecation warnings.

---

## [0.1.13] - 2025-11-08

### Fixed

- **MMR Relevance Selection** - Configured to work properly

### Changed

- **MCP Bridge Version** bumped to 0.1.2
  - REST client now reads `KB_REST_BASE_URL` dynamically during runtime
  - Maintains backward compatibility with production configurations

## [0.1.12] - 2025-11-04

### Added

- **Repository Management**
  - `rm-repo` command with cleanup and validation
  - Pre-deletion session validation
  - Fixed deletion order and cascade behavior
  - Improved DB cleanups
  - `validate-repo` command
  - `repair-repo` command with `--dry-run` support

### Changed

- **`rm-repo` CLI Command**
  - Now requires confirmation unless `--force` is used
  - Validates complete cleanup and reports warnings
- **`reset-repo` CLI Command**
  - Uses enhanced cleanup with comprehensive validation
  - Automatically aborts active sessions for clean reset
- **Database Error Handling**
  - All operations now use proper transaction rollback
  - Clear error messages with actionable guidance
  - Non-blocking warnings for non-critical issues

### Fixed

- **Repository Tracking Issues**
  - Foreign key validation during initialization
  - Proper cascade deletion order in rm-repo operations
  - Silent LanceDB cleanup failures now reported with warnings
  - Incomplete FTS5 cleanup with multi-strategy approach
- **Data Integrity Risks**
  - FTS5 entries now validated after deletion
  - Orphaned data detection and repair mechanisms
  - Active session validation prevents mid-operation deletions
  - All cleanup operations validated for completeness

## [0.1.11] - 2025-11-03

### Fixed

- **Documentation Issues**

## [0.1.10] - 2025-11-03

### Added

- **CLI Improvements**
  - Additional CLI commands for searching knowledge base

### Changed

- **Documentation Improvements**
  - Centralized docs and removed clutter
  - Updated installation instructions to be accurate

### Fixed

- **Install Process**
  - Remediated install-blocking issues

## [0.1.9] - 2025-11-02

### Added

- **Production-Ready REST API** with FastAPI
  - Health check endpoint (shallow and deep)
  - Repository listing endpoint
  - Semantic search endpoint with configurable parameters
  - Chunk retrieval endpoint
  - File slice retrieval endpoint
- **Comprehensive Testing Infrastructure**
  - 360+ passing tests (unit + integration)
  - Mock tiktoken for fast unit tests
  - Real tiktoken validation for integration tests
  - Coverage reporting and CI/CD ready
- **Advanced Retrieval Features**
  - Hybrid search (BM25 + Vector) for 40% better precision on identifiers
  - Adaptive ANN parameter tuning for 40% faster searches
  - Optional cross-encoder reranking
  - Maximal Marginal Relevance (MMR) for result diversity
- **Unified CLI** with `dolphin` command
  - Wraps all functionality (init, add-repo, index, search, serve)
  - Subcommands for knowledge base and persona management
  - Rich terminal output with progress indicators

### Changed

- **Dependencies**
  - ML dependencies moved to optional extras
- **Config system improvements**
  - Fixed config template field names to match parser
  - Removed non-functional config sections
  - Added missing fields (cache, batch_size, concurrency)
  - Default provider now "openai" (was "stub")
- **Security enhancements**
  - Path traversal protection in file endpoints
  - Parameterized SQL queries
  - Proper environment variable handling

### Fixed

- Config template `[embedding]` section name
- Missing `default_embed_model` field in config template
- Missing `per_session_spend_cap_usd` field at top level
- TOML syntax error in config template (null values)
- Config hierarchy now properly loads user config before defaults

### Performance

- Semantic search latency reduced by ~40% with adaptive ANN tuning
- Hybrid search improves precision by ~40% on code identifiers
- Optional reranking improves MRR by 20-30%

## [0.1.8] - 2025-11-01

### Added

- Initial knowledge base indexing pipeline
- Language-aware chunking (Python, TypeScript, JavaScript, Markdown)
- SQLite metadata store
- LanceDB vector store
- OpenAI embedding integration
