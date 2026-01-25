# Changelog - pb-dolphin Python Package

All notable changes to the pb-dolphin Python package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Note**: This changelog covers only the Python package. For component-specific changes:

- **MCP Bridge**: See [mcp-bridge/CHANGELOG.md](mcp-bridge/CHANGELOG.md)
- **VSCode Extension (Experimental)**: See [vscode-extension/CHANGELOG.md](vscode-extension/CHANGELOG.md)

---

## [0.2.0] - 2026-01-25

This release focuses the release-targeted surface on the Knowledge Bank (Python) and the versioned KB REST API.

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

### Changed

- Ignore pattern handling standardized to `.gitignore` semantics.
- **Breaking**: KB REST API is now `/v1/*` only (legacy unversioned routes removed).

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
