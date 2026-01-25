# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-01-25

This release focuses the release-targeted surface on the MCP bridge and its contract with the KB `/v1/*` API.

### Added

- `KBClient` REST wrapper to enable dependency injection and more reliable unit/integration testing.
- Search output improvements (formatting + payload trimming) and request options:
  - Optional snippets, with configurable `context_lines_before` / `context_lines_after`
  - Support for filters like `exclude_paths`, `exclude_patterns`, `score_cutoff`, `deadline_ms`, and `embed_model`
- Standardized MCP tool set:
  - `search`
  - `chunk_get`
  - `file_lines`
  - `store_info`
  - `metadata_get`
  - `repos_list`
  - `health`
  - `open_in_editor`

### Changed

- **Breaking**: Minimum required KB API version is now 0.2.0.
- REST client targets KB `/v1` endpoints for search, repos, chunks, and file slices.

### Removed

- Filesystem read/write tools removed for safety (`read_files`, `file_write`).

### Fixed

- Search/snippet handling and trimming behavior for more stable MCP payload sizes.
- Prevent cache pollution in `getReposByName` when a client is provided.

### Breaking / Migration Notes

- MCP tool names/availability changed; downstream MCP clients may need updates (e.g., legacy `search_knowledge` / `fetch_chunk` / `fetch_lines` / `get_vector_store_info` are replaced by the tool set above).

---

## [0.1.3] - 2025-11-08

### Fixed

- **Snippet visibility**: Removed pre-filtering logic that excluded snippets longer than 500 characters from resource blocks
- Snippets are now always included in search results, with intelligent trimming only applied when payload cap is exceeded

### Changed

- **Payload capacity increased** from 50KB to 70KB for richer search result context
- **Snippet size limits doubled**:
  - Initial cap: 500 → 1000 characters
  - Shrunk cap: 300 → 600 characters
  - Minimum floor: 200 → 300 characters
- Improved snippet context preservation while maintaining graceful degradation under payload constraints

## [0.1.2] - 2025-11-08

### Fixed

- Fixed bugs related to snippet fetching

### Changed

- **REST client configuration** now reads `KB_REST_BASE_URL` dynamically to support test mocking while maintaining production behavior

## [0.1.1] - 2025-11-04

### Added

- **Parallel snippet fetching** with configurable concurrency for `search` tool
- Configuration options for concurrency control:
  - `MAX_CONCURRENT_SNIPPET_FETCH` (default: 8, range: 1-12)
  - `SNIPPET_FETCH_TIMEOUT_MS` (default: 2000ms, range: 500-10000ms)
  - `SNIPPET_FETCH_RETRY_ATTEMPTS` (default: 1, range: 0-3)

### Improved

- Test coverage for concurrency features (400+ lines of tests)
- Error handling in parallel snippet fetching with graceful degradation
- Memory leak prevention with proper cleanup of event listeners and timeouts
- Configuration validation with bounds checking

## [0.1.0] - 2025-11-03

### Added

- Initial release of dolphin-mcp
- MCP server implementation for Dolphin semantic code search
- Tools:
  - `search` - Semantic search across indexed repositories
  - `chunk_get` - Fetch code chunks by ID
  - `file_lines` - Fetch file slices by line range
  - `store_info` - Repository metadata
  - `metadata_get` - Chunk metadata
  - `open_in_editor` - Generate VS Code URIs
- Support for Continue.dev and Claude Desktop
- JSONL logging to `logs/mcp.log`
- 50KB payload cap with intelligent truncation
- Environment variable configuration
- Comprehensive test suite
