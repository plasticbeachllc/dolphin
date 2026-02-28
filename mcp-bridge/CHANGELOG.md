# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.4] - 2026-02-27

### Changed

- **Server Dependency Injection**: `createServer()` now accepts an optional `CreateServerDeps` parameter for config, logger, transport, and tools, enabling clean unit testing without `mock.module()`.
- **Malformed Tool Guard**: Tool registration skips entries with missing `name` or non-function `handler` and logs a warning instead of crashing.
- **Logger Error Surfacing**: Log-write and log-rotation failures now emit to stderr instead of being silently swallowed.
- **Test Rewrite**: Rewrote server integration tests to use DI instead of fragile `mock.module()` mocks.
- **Tool Handler Type Safety**: Replaced `any` handler types across all tool registrations with a shared `ToolHandler` type, eliminating 8 eslint-disable directives.
- **Config Cross-Validation**: Added `floor_exceeds_cap` and `cap_below_shrunk` diagnostics for inconsistent snippet size configurations.

### Fixed

- **Dependency Security Hardening**: Added root-workspace transitive overrides for MCP runtime dependency paths so SDK-adjacent advisories resolve to patched versions (`ajv@8.18.0`, `body-parser@2.2.2`, `qs@6.15.0`, `hono@4.12.0`).
- **ReDoS Surface Reduction**: Forced `minimatch@10.2.2` via workspace override to remove known vulnerable minimatch ranges from the resolved graph.
- **Audit Delta**: Reduced Bun audit findings from 11 advisories to 1 remaining advisory.
- **Debug Comment Cleanup**: Removed stale `// DEBUG:` prefixes from snippet fetcher log calls.

### Removed

- **`open_in_editor` Tool**: Deleted unregistered dead-code tool with path traversal vulnerability; functionality already covered by `buildVscodeFileUri()` in search result transforms.

### Known Issues

- **Remaining Advisory (Tooling)**: `bun audit` still reports `ajv <8.18.0` because current ESLint (`eslint@9.x`) depends on `ajv@6.x`, which is incompatible with a hard `ajv@8` override. Lint and tests remain green; full removal requires lint-stack migration or upstream ESLint dependency changes.

## [0.2.3] - 2026-01-26

### Added

- **New Tool**: Introduced `open_ref` tool to unify resolution of `kb://` URIs and chunk IDs, streamlining navigation/references.

### Fixed

- **Version Bump**: Release preparation for 0.2.3.

## [0.2.2] - 2026-01-25

### Fixed

- Fixed OpenTelemetry missing dependency declaration.

## [0.2.1] - 2026-01-25

### Fixed

- Bun entry point fixed to enable tool call via `bunx`.

## [0.2.0] - 2026-01-25

This release focuses the release-targeted surface on the MCP bridge and its contract with the KB `/v1/*` API.

### Added

- `KBClient` REST wrapper to enable dependency injection and more reliable unit/integration testing.
- Search output improvements (formatting + payload trimming) and request options:
  - Optional snippets, with configurable `context_lines_before` / `context_lines_after`
  - Support for filters like `exclude_paths`, `exclude_patterns`, `score_cutoff`, and `max_snippets`
- Standardized MCP tool set:
  - `search`
  - `chunk_get`
  - `file_lines`
  - `store_info`
  - `metadata_get`
  - `repos_list`
  - `health`
  - `open_in_editor`
- Graph-based code intelligence integration:
  - Support for `include_graph_context` parameter in search queries
  - Entity relationship enrichment (calls, imports, inheritance)
  - Cross-file dependency context
  - Enhanced search results with structural understanding
- Context line expansion via `context_lines_before` / `context_lines_after`.
- JSON-RPC protocol support (in addition to MCP stdio).
- Advanced search parameters: `exclude_paths`, `exclude_patterns`, `mmr_enabled`, `mmr_lambda`, `score_cutoff`.
- Enhanced logging and debugging with structured JSONL and correlation IDs.

### Changed

- **Breaking**: Minimum required KB API version is now 0.2.0.
- REST client targets KB `/v1` endpoints for search, repos, chunks, and file slices.
- **Breaking**: Cursor-based pagination and `deadline_ms` are not supported in v0.2.0 (clients must not send them).
- **Breaking**: Removed legacy `include_snippets` from KB search requests; use `max_snippets`.
- **Breaking**: Removed `embed_model` filter from the `search` tool; use repository/default embed model configuration instead.
- Tool response format now includes graph context when available.
- Search results enriched with entity relationships.
- Error messages provide actionable remediation guidance.

### Improved

- **Performance optimizations** for batch operations
- **Memory efficiency** in file reading operations
- **Concurrent request handling** for multiple tool calls
- **Type safety** with enhanced Zod schemas

### Documentation

- Updated tool schemas with new parameters
- Added examples for file system operations
- Documented graph context integration
- Enhanced error handling guide

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
  - `chunk.get` - Fetch code chunks by ID
  - `file.lines` - Fetch file slices by line range
  - `store.info` - Repository metadata
  - `metadata.get` - Chunk metadata
  - `open_in_editor` - Generate VS Code URIs
- Support for Continue.dev and Claude Desktop
- JSONL logging to `logs/mcp.log`
- 50KB payload cap with intelligent truncation
- Environment variable configuration
- Comprehensive test suite
