# Changelog

## [Unreleased]

### Added
- **Missing Dependencies**
  - Added `networkx>=3.0` for graph intelligence features
  - Added `scipy>=1.11.0` for PageRank computation in network analysis

### Fixed
- **Code Quality Issues**
  - Fixed `_coerce_optional` method calls missing `cls.` prefix in `kb/config.py:266, 270`
  - Fixed incorrect type hints in `kb/ingest/graph_helpers.py` (GraphNode and GraphEdge imports)
  - Fixed incorrect variable name in error logging in `kb/api/app.py:382` (file_path → path)
  - Fixed incorrect method call signature in `kb/ingest/cli.py:286` for `get_chunks_for_file()`
- **Test Infrastructure**
  - Removed problematic manual test script that was interfering with pytest collection

## [1.0.0] - 2025-11-12

This is the first major release of Dolphin, marking a significant milestone in AI-powered development tooling. Version 1.0.0 represents a complete, production-ready platform with comprehensive testing, accessibility compliance, and a beautiful VSCode extension.

### Added

#### 🎨 VSCode Extension with Claude CLI Support

- **Dual Authentication System**
  - Claude CLI integration for subscription-based usage (no API costs)
  - Direct Anthropic API key support as fallback
  - Automatic authentication detection and status display
  - OAuth workflow integration for Claude Code

- **Modern Webview Interface**
  - Beautiful SvelteKit-based UI with shadcn/ui component library
  - Real-time token-by-token streaming from Claude
  - VSCode theme integration with dark/light mode support
  - Multiple routes: Chat, Settings, Gallery, Profile, Tools, Functions
  - Component gallery for development and testing
  - Interactive plan timeline visualization with animated status indicators

- **Rich Editor Integration**
  - Context menu commands: "Ask About Selection", "Refactor Selection", "Ask About File", "Ask About Folder"
  - Keyboard shortcuts (Cmd+L/Ctrl+L to focus chat input)
  - Diff viewer with syntax highlighting and side-by-side/unified modes
  - Copy functionality for code blocks and diffs
  - File and folder context injection

- **Conversation Management**
  - Persistent conversation history in TOML format
  - Conversation branching support
  - Message metadata tracking with hybrid token counting
  - Session restoration across VSCode restarts
  - Comprehensive test suite (52+ TypeScript tests)

#### 🧠 Architect Mode & Intelligent Planning

- **Personas System**
  - Nine specialized AI personas for different development scenarios:
    - **Smartest Guy** - Senior engineer for architectural excellence
    - **Chief of Staff** - Project coordination and strategic planning
    - **Deep Dive** - Detailed technical analysis and research
    - **Big Balls** - Bold decision-making and risk assessment
    - **Journalist** - Documentation and clear communication
    - **Little Ripper** - Fast iteration and prototyping
    - **Popeye** - Strength-focused, robust solutions
    - **Quiet Kid** - Thoughtful, methodical approach
    - **Fancy Slave** - Polished, production-ready implementation
  - TOML-based persona configuration
  - System prompt customization per persona

- **Structured Planning Process**
  - Task planning with semantic search integration
  - Adaptive planner architecture
  - Event-driven progress tracking system
  - Step-by-step execution with status tracking (pending, running, completed, error)
  - Plan timeline visualization component with interactive draggable UI
  - Tool call visualization cards with real-time status updates

#### ♿ Accessibility Standards (WCAG 2.1 AA Compliance)

- **Comprehensive Keyboard Navigation**
  - Full keyboard accessibility for all extension features
  - Logical tab order throughout the interface
  - Focus indicators with 3:1 minimum contrast ratio
  - Standard keyboard shortcuts (Escape to close, Enter to submit)
  - No keyboard traps in any UI components

- **Screen Reader Support**
  - ARIA labels and landmarks for all interactive elements
  - Semantic HTML structure with proper heading hierarchy
  - Live regions for dynamic content announcements
  - Context announcements for tool calls and status changes
  - Tested with NVDA, JAWS, VoiceOver, and Orca screen readers

- **Visual Accessibility**
  - 4.5:1 minimum contrast ratio for normal text
  - 3:1 minimum contrast ratio for UI components and focus indicators
  - VSCode theme token integration for consistent, accessible colors
  - High contrast mode support
  - Color-independent information display (no meaning by color alone)
  - Reduced motion support (`prefers-reduced-motion` media query)

- **Accessibility Testing Infrastructure**
  - axe-core integration for automated accessibility testing
  - ARIA validation in component tests
  - Manual testing checklist for keyboard and screen reader workflows
  - Comprehensive accessibility guide in `/docs/accessibility-guide.md`

#### 🔄 Dual-Path Indexing (File Watch + Git Diff)

- **Real-Time File Watch System**
  - Live file change detection via VSCode file system API
  - Crash-proof pending changes queue stored in SQLite
  - Four auto-sync modes:
    - **Off** - Manual indexing only
    - **Manual** - User confirmation required for each sync
    - **Smart** (default) - Auto-sync during idle periods (30+ seconds)
    - **Aggressive** - Immediate incremental indexing on every change
  - Mid-index change detection and automatic re-queuing
  - Progress tracking with current file display
  - Configurable debounce timing

- **Git-Aware Incremental Indexing**
  - `git diff` integration for efficient change detection
  - Commit SHA and branch tracking with each indexed chunk
  - Drift detection for offline/background changes
  - Post-commit hook support for automatic indexing
  - Only reindexes changed files for maximum efficiency
  - Graph pruning on file deletions to maintain data integrity

- **Robust Architecture**
  - TypeScript (VSCode) handles detection and triggers indexing
  - Python (FastAPI) handles processing and persistence
  - JSON-RPC communication over stdio with proper framing
  - Automatic status updates on completion
  - Path normalization before API sync
  - Comprehensive test coverage for all sync phases

#### ⚡ Parallelized Knowledge Base

- **High-Performance Batch Processing**
  - Configurable batch size for embedding API calls (default: 100)
  - Parallel embedding requests with concurrency control
  - Rate limit handling with exponential backoff retry logic
  - Batch processing for cross-encoder reranking (batch size: 32)

- **Concurrent Search Capabilities**
  - 8 parallel search queries supported (for LLM multi-tool calls)
  - ~300ms p50 search latency (60% faster than target)
  - ~800ms p95 search latency (60% faster than target)
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

#### 🧪 Comprehensive Testing, Profiling, and Evaluation Frameworks

- **Extensive Test Suite (243+ Tests)**
  - **Python Tests (191+ passing tests)**:
    - Chunkers (Python, TypeScript, Markdown, SQL, Svelte, fallback): 45+ tests
    - Embeddings (OpenAI provider, retry logic, stub implementations): 15 tests
    - Storage layers (SQLite, LanceDB, graph store): 29 tests
    - Hashing and content deduplication: 12 tests
    - Scanner and `.gitignore` handling: 18 tests
    - Token counting utilities: 8 tests
    - ANN tuning and optimization: Multiple tests
    - Search API integration: 11 tests
    - Search backend unit tests: 10 tests
    - MCP endpoints: 12 tests
    - Rank fusion algorithms: 19 tests
    - End-to-end pipeline tests: 12 tests
    - Hybrid search: Multiple tests
    - KB auto-sync system: Multiple tests
  - **TypeScript Tests (52+ passing tests)**:
    - MCP Bridge: 36 tool implementation tests
    - REST client: 8 tests
    - Agent Core: Conversation persistence, IPC, KB lifecycle
    - VSCode Extension: E2E and webview integration tests
  - Unified test runner: `tests/run_tests.py`
  - Separate directories for unit/integration/e2e tests
  - Mock backends for fast unit testing
  - Real backends for integration validation

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

#### 📊 Plan Visualization and Comprehensive UI Styling

- **Plan Timeline Visualization**
  - Interactive draggable timeline component (`PlanTimeline.svelte`)
  - Visual step indicators with dynamic status colors
  - Animated pulsing for currently running steps
  - Connected step visualization with progress lines
  - Status tracking: pending, running, completed, error
  - Expandable/collapsible step details

- **Advanced Diff Viewer**
  - Side-by-side and unified diff display modes (`DiffViewer.svelte`)
  - Syntax highlighting for all supported languages
  - Line-by-line change visualization with add/delete markers
  - Copy functionality for code selections
  - Binary file and size guards

- **Tool Call Visualization**
  - Real-time tool execution cards (`ToolCallCard.svelte`)
  - Knowledge base search visualization with result counts
  - Success/error/loading state indicators
  - Expandable/collapsible tool result displays
  - Metadata display (latency, result count, status)

- **Rich Message Components**
  - Markdown rendering with code syntax highlighting
  - Code blocks with one-click copy buttons
  - User/assistant/system message styling
  - Error alerts with contextual information
  - Confirmation dialogs with accessible keyboard controls
  - Loading states with spinners and skeleton screens

- **Component Library (shadcn/ui)**
  - 20+ accessible, reusable UI components:
    - Alert, Alert Dialog, Avatar, Badge
    - Button, Card, Checkbox, Collapsible
    - Dialog, Input, Label, Navigation Menu
    - Progress, Radio Group, Scroll Area
    - Separator, Skeleton, Tabs, Textarea
  - Tailwind CSS utility-first styling
  - Consistent design tokens across all components
  - Typography system with semantic hierarchy
  - Responsive layout utilities

- **Theme System**
  - VSCode theme token integration for native look and feel
  - Seamless dark/light theme switching
  - High contrast mode support
  - Custom color palette with WCAG-compliant contrast ratios
  - CSS custom properties for theming

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

- **Advanced Result Ranking**
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
  - **File System**: Repository files and snapshots
  - Content deduplication via SHA256 hashing
  - Separate LanceDB collections per embedding model
  - Foreign key constraints for referential integrity

#### 🌐 REST API & MCP Bridge

- **Production FastAPI REST API**
  - **5 Core Endpoints**:
    1. `GET /health` - Health checks (shallow: API availability, deep: DB + vector store)
    2. `GET /v1/repos` - List indexed repositories with file counts and statistics
    3. `POST /v1/search` - Semantic search with configurable parameters (top_k, score_threshold, etc.)
    4. `GET /v1/chunks/{id}` - Retrieve specific chunk by ID with metadata
    5. `GET /v1/file` - Fetch file slices by line range with path traversal protection
  - CORS middleware for VSCode webview integration
  - Structured error responses with remediation hints
  - Request validation with Pydantic models
  - JSONL logging with automatic rotation

- **MCP Bridge (Published as `dolphin-mcp` v0.1.2)**
  - **6 MCP Protocol Tools**:
    1. `search_knowledge` - Semantic code search with inline citations
    2. `fetch_chunk` - Retrieve specific code chunks by ID
    3. `fetch_lines` - File slice retrieval by line range
    4. `get_vector_store_info` - Vector store statistics and health
    5. `get_metadata` - Chunk metadata without full content
    6. `open_in_editor` - VS Code URI generation for deep linking
  - MCP Protocol 2025-06-18 compliance
  - 50KB content budget with multi-stage trimming and truncation
  - TypeScript implementation with Zod schema validation
  - AbortSignal support for request cancellation
  - Works with Claude Desktop, Continue.dev, and other MCP clients
  - Dynamic `KB_REST_BASE_URL` reading for flexible deployment

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

#### 🚀 Production-Ready Features

- **Security Hardening**
  - Path traversal protection in file serving endpoints
  - Parameterized SQL queries to prevent injection attacks
  - Secure environment variable handling for API keys
  - Secret file exclusion (`.env`, `.pem`, `.aws/`, etc.)
  - Input validation and sanitization
  - CORS configuration for webview security

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

- **Comprehensive Documentation**
  - Architecture documentation (`/docs`)
  - Testing guide with examples
  - Accessibility compliance guide
  - Claude CLI integration specification
  - API endpoint documentation
  - MCP bridge usage guide
  - Git diff vs. file sync comparison document
  - Phase-by-phase implementation documentation

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

- **IPC Architecture Improvements**
  - JSON-RPC framing alignment in AgentCore stdio communication
  - Improved error propagation between TypeScript and Python layers
  - Event-driven status updates for better responsiveness
  - Robust handling of process lifecycle and crashes

- **File Sync Architecture**
  - Python backend now auto-marks changes as processed (Phase 2)
  - Path normalization before API synchronization
  - Improved crash recovery with persistent queues
  - Better handling of rapid file changes

### Fixed

- **Configuration Template Issues**
  - Fixed `[embedding]` section name (was incorrectly `[embeddings]`)
  - Added missing `default_embed_model` field
  - Added missing `per_session_spend_cap_usd` field at top level
  - Corrected TOML syntax errors for null/default values

- **Database and Storage**
  - Foreign key validation during repository initialization
  - Proper cascade deletion order in `rm-repo` operations
  - FTS5 cleanup now uses multi-strategy approach for completeness
  - LanceDB cleanup failures now reported with warnings instead of silent failure
  - Graph pruning query optimization to avoid SQLite parameter limits

- **File Sync and Indexing**
  - Diff application on empty/new files now works correctly
  - File watcher path normalization prevents duplicate processing
  - Metadata updates now persist correctly during conversation saves
  - Indexing task async handling and TypeScript typings corrected

- **Data Integrity**
  - Active session validation prevents mid-operation deletions
  - Orphaned data detection and repair mechanisms
  - FTS5 entries validated after deletion operations
  - Graph edge cleanup handles large deletion batches correctly

### Performance

- **Search Performance**
  - Semantic search latency: ~300ms p50, ~800ms p95 (targets: 600ms/2s) ✅
  - 40% faster searches with adaptive ANN tuning vs. static parameters
  - 40% better precision with hybrid search on code identifiers
  - Optional reranking: 20-30% MRR improvement (at 2-3x latency cost)

- **Scalability Benchmarks**
  - **Small repos** (1K files, 50K chunks): ~100MB LanceDB, ~5MB SQLite
  - **Medium repos** (10K files, 500K chunks): ~1GB LanceDB, ~50MB SQLite
  - **Large repos** (100K files, 5M chunks): ~10GB LanceDB, ~500MB SQLite
  - Concurrent query support: 8 parallel queries, 10-20 QPS sustained

- **Resource Efficiency**
  - Embedding request latency: ~150ms average
  - Vector search latency: ~50ms average
  - Baseline memory: ~200 MB, under load: ~500 MB
  - Batch processing reduces API calls by 100x for large indexing jobs

### Technology Stack

**Backend (Python ≥3.12):**
- FastAPI - REST API framework
- SQLModel - Type-safe ORM for SQLite
- LanceDB - Vector database with ANN search
- OpenAI SDK - Embeddings API integration
- Tree-sitter - Language-aware code parsing
- tiktoken - Token counting for embeddings
- pathspec - `.gitignore` pattern matching
- Typer - Beautiful CLI framework
- pytest - Testing framework

**Frontend (TypeScript/JavaScript):**
- VSCode Extension API - Editor integration
- Bun - Fast JavaScript runtime for Agent Core
- Anthropic SDK - Claude API client
- SvelteKit - Full-stack web framework
- Svelte 5 - Reactive UI components
- Tailwind CSS - Utility-first styling
- shadcn/ui - Accessible component library
- Zod - Runtime type validation
- MCP SDK - Model Context Protocol implementation

**Development & Tooling:**
- uv - Fast Python package installer and resolver
- Justfile - Task automation (build, test, lint)
- Git - Version control and diff-based indexing
- Prettier - Code formatting
- ESLint - JavaScript/TypeScript linting

### Migration Notes

This is a major version release. If upgrading from 0.1.x:

1. **Configuration**: Review and update your `.dolphin/config.toml` files. Some field names have changed and new options are available.
2. **Dependencies**: If you were using reranking features, reinstall with `pip install pb-dolphin[reranking]`.
3. **VSCode Extension**: Update to the latest extension version for compatibility with the new MCP bridge and API changes.
4. **API**: REST API endpoints are backward compatible, but new parameters are available for hybrid search and MMR.
5. **Database**: Existing SQLite and LanceDB indices are compatible. Consider rebuilding for optimal performance with new features.

### Acknowledgments

This release represents months of development focused on production readiness, accessibility, and user experience. Special thanks to the open-source community and early adopters who provided valuable feedback during the beta period.

For detailed documentation, visit the `/docs` directory in the repository.

---

## [0.1.13] - 2025-11-08

### Fixed
- **MMR Relevance Selection**
  - Configured to work properly

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
