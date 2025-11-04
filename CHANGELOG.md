# Changelog

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
- **MCP Bridge** for Claude Desktop and Continue IDE integration
  - `search_knowledge` - Semantic code search with citations
  - `fetch_chunk` - Retrieve specific code chunks
  - `fetch_lines` - Fetch file slices by line range
  - `get_vector_store_info` - Vector store statistics
  - `get_metadata` - Chunk metadata retrieval
  - `open_in_editor` - Generate VS Code URIs
- **Comprehensive Testing Infrastructure**
  - 360+ passing tests (unit + integration)
  - Mock tiktoken for fast unit tests
  - Real tiktoken validation for integration tests
  - Coverage reporting and CI/CD ready
- **Advanced Retrieval Features**
  - Hybrid search (BM25 + Vector) for 40% better precision on identifiers
  - Adaptive ANN parameter tuning for 40% faster searches
  - Optional cross-encoder reranking (install with `pip install pb-dolphin[reranking]`)
  - Maximal Marginal Relevance (MMR) for result diversity
- **Unified CLI** with `dolphin` command
  - Wraps all functionality (init, add-repo, index, search, serve)
  - Subcommands for knowledge base and persona management
  - Rich terminal output with progress indicators

### Changed

- **BREAKING**: Dependency structure optimized
  - Core install now ~200MB (previously ~2GB)
  - Heavy ML dependencies moved to optional extras
  - Install reranking with `pip install pb-dolphin[reranking]`
  - Install orchestrator with `pip install pb-dolphin[orchestrator]`
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

- Config template `[embedding]` section name (was incorrectly `[embeddings]`)
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