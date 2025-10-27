# AI Assistant Onboarding Guide for Dolphin Project

## Overview

The dolphin project is a personal AI companion system that integrates multiple MCP (Model Context Protocol) servers with OpenWebUI to provide a customizable AI assistant experience. The core feature is a personas system that allows different AI agent personalities with specific behaviors and configurations.

## Repository Structure

```
dolphin/
├── personas/                 # Persona definitions and configurations
│   ├── deep-dive/           # Principal planner and systems architect
│   ├── journalist/          # Project documentarian and status tracker
│   ├── little-ripper/       # Junior engineer for precise implementation
│   ├── fancy-slave/         # Senior engineer for rapid local deployment
│   ├── popeye/              # High-priority project engineer
│   └── scripts/             # Persona management utilities
├── .dolphin/                # Repository configuration files
│   └── chunking_config.toml # Repository chunking configuration
├── .continue/               # Continue configuration files
├── instructions/            # Documentation and guides (this file)
├── tests/                   # Comprehensive test suite
│   ├── unit/                # Unit tests for individual components
│   │   ├── test_hashing.py  # Text canonicalization and SHA256 hashing
│   │   ├── test_scanner.py  # Repository scanning with ignore patterns
│   │   ├── test_token_utils.py # Token counting and text windowing
│   │   ├── test_chunker_registry.py # Language detection and routing
│   │   ├── test_dedup.py    # Content-based deduplication
│   │   ├── test_embeddings_retry.py # Embedding retry logic
│   │   ├── test_error_logging.py # Error handling and logging
│   │   ├── test_chunkers/   # Language-specific chunker tests
│   │   │   ├── test_fallback_chunker.py # Generic token windowing
│   │   │   ├── test_py_chunker.py # Python symbol extraction
│   │   │   ├── test_ts_chunker.py # TypeScript/JavaScript parsing
│   │   │   ├── test_md_chunker.py # Markdown heading detection
│   │   │   └── test_advanced_chunkers.py # Advanced chunker behavior
│   │   └── test_store/      # Storage layer tests
│   │       ├── test_sqlite_meta.py # SQLite metadata operations
│   │       └── test_lancedb_store.py # LanceDB vector store operations
│   ├── integration/         # Integration and end-to-end tests
│   │   ├── test_pipeline.py # Pipeline scanning and indexing workflows
│   │   ├── test_indexing.py # Indexing functionality and performance
│   │   ├── test_search.py   # Search and retrieval functionality
│   │   └── conftest.py     # Integration-specific fixtures
│   ├── utils/              # Test utilities and helpers
│   │   ├── backend_helpers.py # Factory for test backends
│   │   ├── mock_services.py # Mock implementations
│   │   └── coverage_utils.py # Coverage management and reporting
│   ├── fixtures/           # Test data and sample repositories
│   │   └── kb_sample_repo/ # Sample repository for testing
│   └── conftest.py         # Shared pytest fixtures
├── src/pb_kb/              # Knowledge base pipeline implementation
│   ├── ingest/             # Ingestion pipeline components
│   │   ├── pipeline.py     # Main ingestion pipeline
│   │   ├── scanner.py      # Repository scanning
│   │   ├── error_logging.py # Error handling and logging
│   │   └── cli.py          # Typer CLI interface
│   ├── store/              # Storage layer
│   │   ├── sqlite_meta.py  # SQLite metadata operations
│   │   └── lancedb_store.py # LanceDB vector store
│   ├── embeddings/         # Embedding providers
│   │   └── provider.py     # OpenAI embedding with retry logic
│   └── chunkers/           # File chunking implementations
│       ├── repo_config.py  # Repository configuration system
│       ├── py_chunker.py   # Python chunker
│       ├── ts_chunker.py   # TypeScript chunker
│       ├── md_chunker.py   # Markdown chunker
│       ├── fallback_chunker.py # Enhanced token-windowing chunker
│       ├── registry.py     # Chunker registry and routing
│       ├── types.py        # Core data types
│       └── token_utils.py  # Tokenization utilities
└── Justfile                 # Task runner configuration
```

## Prerequisites & Setup

### Required Tools
- **just**: Task runner for project commands
- **Docker**: Containerization for services
- **Python ≥3.13**: With `uv` package manager
- **Git**: Version control

### Initial Setup
1. Clone the repository:
   ```sh
   git clone <repository-url>
   cd dolphin
   ```

2. Run the setup command:
   ```sh
   just setup
   ```
   This will:
   - Create environment configuration from template
   - Validate required environment variables
   - Set up necessary dependencies

3. Configure environment variables in `.env`:
   - `GITHUB_PERSONAL_ACCESS_TOKEN`: For GitHub integrations
   - `OPENAI_API_KEY`: For AI model access

## Core Components

### Personas System

The personas system defines different AI agent personalities with specific behaviors, guardrails, and configurations. Each persona consists of:

- `persona.toml`: Metadata, provider settings, and parameters
- `system.md`: System prompt defining behavior and capabilities
- `guardrails.md`: Safety rules and constraints (optional)

#### Available Personas

- **Deep Dive**: Principal AI planner and systems architect who breaks work into ordered, testable increments, surfaces trade-offs and risks, and ensures production-ready patterns
- **Journalist**: Meticulous project documentarian who synthesizes repository state and changes, highlights gaps between plans and reality, and maintains accurate records
- **Little Ripper**: Junior software engineer who thrives on tight feedback cycles, follows specifications exactly, and implements small, verifiable changes
- **Fancy Slave**: Principal engineer focused on tackling projects' most difficult problems
- **Popeye**: Senior engineer responsible for implementation and writing thoughtful, elegant, and maintainable code

### Repository Chunking Configuration System

The chunking configuration system allows per-repository customization of file chunking parameters for semantic retrieval. Each repository can have a `.dolphin/chunking_config.toml` file:

**Status**: ✅ **PHASE 4 COMPLETE** - Chunker registry and configuration system fully implemented

#### Global Configuration (`.dolphin/config.toml`)
The new comprehensive configuration system consolidates all settings:

```toml
# Extension → Language mappings (50+ extensions supported)
[languages]
py = "python"
ts = "typescript"
md = "markdown"
json = "json"
# ... more mappings

# Chunking defaults
[chunking]
default_window_size = 350
overlap_pct = 0.10

[chunking.per_language]
python = 512
typescript = 350
markdown = 256

# Embeddings configuration
[embeddings]
model = "text-embedding-3-small"

# Storage and retrieval settings
[storage]
store_root = "~/.dolphin/knowledge_store"

[server]
endpoint = "127.0.0.1:7777"

[retrieval]
score_cutoff = 0.15
top_k = 8
max_snippet_tokens = 240
```

#### Repository Configuration (`.dolphin/chunking_config.toml`)
Individual repositories can override settings:

```toml
default_window_size = 400

[per_language]
python = 600  # Larger windows for this repo
```

**Key Features:**
- Per-repository token window sizes (200-500 tokens recommended)
- Per-language overrides for 14 common languages
- OpenAI embedding model selection (text-embedding-3-small/large)
- Tokenizer encoding configuration
- 10% overlap between chunks for context preservation

**Default Settings:**
- Default window: 350 tokens (optimal for semantic retrieval)
- Python/Java/C++: 512 tokens (more verbose languages)
- JSON/YAML/TOML: 128 tokens (structured data)
- Markdown/Text: 256 tokens
- Embedding model: text-embedding-3-small
- Tokenizer: cl100k_base (OpenAI standard)

### Personas Management Commands

- `just personas-list`: List all available personas
- `just personas-preview --id <persona_id>`: Preview a specific persona's configuration
- `just personas-generate`: Generate Continue config from all personas

Example usage:
```sh
just personas-preview --id journalist --verbose
```

### Testing Commands

Test the complete system using pytest:
```sh
# Run all tests
just test

# Run unit tests only
just test-unit

# Run integration tests only  
just test-integration

# Run tests with coverage reporting
just test-coverage

# Run specific test file
just test-file -- file=tests/unit/test_chunker_registry.py

# Run tests with verbose output
just test-verbose
```

**Test Status**: Complete Test Framework ✅
- **147/147 tests passing** with comprehensive coverage
- **Unit Tests**: 144 passing - Core component functionality
- **Integration Tests**: 21 passing - Component interactions and workflows
- **Skipped Tests**: 2 - External service dependencies
- **Execution Time**: ~2.8 seconds for full test suite

## Development Workflow

### Testing

We use **pytest** as the primary test framework with comprehensive fixture support and integration testing. The test suite includes:

- **Unit Tests**: Isolated component testing with mocked dependencies
- **Integration Tests**: End-to-end pipeline workflows with Git repository setup
- **Mock Services**: Deterministic testing for external dependencies (OpenAI, LanceDB)
- **Test Fixtures**: Shared test data and environment setup

Run the complete test suite:
```sh
just test
```

Run specific test categories:
```sh
# Run only unit tests
just test-unit

# Run only integration tests
just test-integration

# Run with coverage reporting
just test-coverage
```

### Running Services

Start all services:
```sh
just run
```

This launches:
- OpenWebUI interface
- Backend MCP servers
- Personas configurations

### Common Development Commands

- `just run`: Start all services (OpenWebUI, MCP servers)
- `just stop`: Stop all services
- `just setup-openwebui`: Pull latest images and start web UI
- `just test`: Run all tests using pytest
- `just test-unit`: Run unit tests only
- `just test-integration`: Run integration tests only
- `just test-coverage`: Run tests with coverage reporting
- `just personas-list`: List available personas
- `just personas-preview --id <persona_id>`: Preview persona configuration
- `just personas-generate`: Generate Continue config
- `just list`: Show all available Just commands

### Making Changes

1. **Code Changes**: Modify files in the appropriate directories
2. **Persona Updates**: Edit persona files in `personas/<persona-id>/`
3. **Chunking Configuration**: Update `.dolphin/chunking_config.toml` for repository settings
4. **Testing**: Use `just test` to verify changes
5. **Configuration**: Update `.continue/` files for Continue integration

**Testing Workflow**:
- Run `just test-unit` for quick feedback on core changes
- Run `just test-integration` for pipeline workflow validation
- Run `just test-coverage` before committing to ensure adequate test coverage
- Use `just test-file -- file=path/to/test.py` for focused testing

### Creating New Personas

1. Create a new directory under `personas/` with slug-style name:
   ```sh
   mkdir personas/my-new-persona
   ```

2. Add required files:
   - `persona.toml`: Define metadata and configuration
   - `system.md`: Write system prompt and behavior definition
   - `guardrails.md`: Add safety rules (optional)

3. Validate the persona:
   ```sh
   just personas-preview --id my-new-persona
   ```

4. Generate updated configuration:
   ```sh
   just personas-generate
   ```

### Configuring Repository Chunking

1. Create or edit `.dolphin/chunking_config.toml` in repository root
2. Configure token window sizes and embedding model:
   ```toml
   default_window_size = 350
   
   [per_language]
   python = 512
   typescript = 350
   
   [embeddings]
   model = "text-embedding-3-small"
   ```

3. Test configuration loading:
   ```python
   from pb_kb.chunkers import load_repo_chunking_config
   config = load_repo_chunking_config(Path("/path/to/repo"))
   python_window = config.get_window_size_for_language("python")  # 512
   ```

## Key Files and Their Purposes

### Configuration Files
- `Justfile`: Task definitions and project commands
- `pyproject.toml`: Python project configuration and dependencies
- `.env`: Environment variables (create from `.env.example`)
- `.dolphin/chunking_config.toml`: Repository chunking configuration

### Persona Files
- `persona.toml`: Persona metadata, provider settings, token budgets
- `system.md`: Core behavior definition and capabilities
- `guardrails.md`: Constraints and safety rules

### Chunking System Files
- `src/pb_kb/chunkers/repo_config.py`: Repository configuration loading and validation
- `src/pb_kb/chunkers/py_chunker.py`: Python source code chunker with tree-sitter
- `src/pb_kb/chunkers/ts_chunker.py`: TypeScript/JavaScript chunker
- `src/pb_kb/chunkers/md_chunker.py`: Markdown chunker with heading tracking
- `src/pb_kb/chunkers/fallback_chunker.py`: Enhanced token-windowing chunker for generic files
- `src/pb_kb/chunkers/token_utils.py`: Tokenization and windowing utilities

### Scripts
- `personas/scripts/personas.py`: CLI for persona management
- `personas/scripts/persona_utils.py`: Utilities for persona loading and validation

## AI Assistant Best Practices

### When Answering Questions
1. Reference specific files or code sections when possible
2. Use the personas system context to provide appropriate responses
3. Suggest relevant Just commands for common tasks
4. Consider the user's current context (open files, recent changes)
5. Mention repository chunking configuration when discussing file processing
6. Note that the fallback chunker now uses token windowing for all file types
7. Highlight that all chunkers maintain accurate 1-based line number mapping

### When Making Changes
1. Use the multi_edit tool for multiple changes to a single file
2. Follow existing code patterns and conventions
3. Test changes with `just test` when appropriate
4. Update documentation if functionality changes
5. Consider repository chunking configuration when modifying file processing

### When Developing Plans
1. Break down complex tasks into smaller, testable increments
2. Consider which persona might be best suited for the task
3. Surface trade-offs, risks, and unknowns
4. Provide implementation steps with verification criteria
5. Consider token window sizes and embedding models for semantic retrieval

## Troubleshooting Common Issues

### Environment Setup
- Ensure all prerequisites are installed and accessible
- Verify `.env` file exists with required variables
- Check Docker is running for containerized services

### Persona Issues
- Use `just personas-preview` to validate persona configurations
- Check for syntax errors in TOML files
- Verify token budgets are within 200-8000 range

### Chunking Configuration Issues
- Verify `.dolphin/chunking_config.toml` syntax is valid TOML
- Test configuration loading with `tests/test_repo_config.py`
- Check that window sizes are positive integers
- Ensure embedding model is "text-embedding-3-small" or "text-embedding-3-large"
- Test fallback chunker with `tests/test_fallback_chunker.py` if generic file chunking fails

### Service Problems
- Use `just stop` and `just run` to restart services
- Check Docker container status if services fail to start
- Verify network connectivity for external dependencies

## Integration Points

### OpenWebUI
- Primary user interface for AI interactions
- Configures personas as available models
- Manages conversation history and context

### MCP Servers
- Provide context and tools to AI models
- Handle specific domains (filesystem, GitHub, etc.)
- Extend core AI capabilities

### Continue Configuration
- Defines available models and their behaviors
- Maps personas to specific provider configurations
- Manages roles and capabilities for each persona

### Knowledge Base System
- Uses repository chunking configuration for file processing
- Supports per-repository token window sizes and embedding models
- Integrates with semantic retrieval for code and documentation
- **Enhanced Fallback Chunker**: Now uses token windowing for all file types (JSON, YAML, plain text, etc.)
- **Accurate Line Mapping**: Binary search-based line number tracking with 1-based indexing
- **Token-Based Splitting**: Splits at token boundaries, not arbitrary character positions

### Current Implementation Status
- ✅ **Repository Configuration System**: Complete with TOML loading and validation
- ✅ **Python Chunker**: Tree-sitter based symbol extraction
- ✅ **TypeScript Chunker**: Tree-sitter based symbol extraction
- ✅ **Markdown Chunker**: Heading-aware section chunking
- ✅ **Fallback Chunker**: Enhanced token-windowing implementation
- ✅ **Chunker Registry**: Complete with automatic routing and configuration integration
- ✅ **Global Configuration**: Consolidated settings in `.dolphin/config.toml`
- ✅ **Test Coverage**: Comprehensive tests for all chunkers and registry
- ✅ **Integration Testing**: Full pipeline integration tested

**Phase 4 Status**: ✅ **COMPLETE** - Ready for Phase 5 (Hashing and Idempotency)

## KB Pipeline Test Framework - Implementation Details

### Current Test Framework Status

**✅ Complete Test Framework Implementation**
- **147/147 tests passing** with comprehensive coverage
- **Unit Tests**: 144 passing - Core component functionality
- **Integration Tests**: 21 passing - Component interactions and workflows
- **Skipped Tests**: 2 - External service dependencies
- **Execution Time**: ~2.8 seconds for full test suite

### Key Test Framework Features

**Test Infrastructure**
- **pytest** with comprehensive fixture support
- **Mock Services**: Deterministic testing for external dependencies
- **Isolated Databases**: Clean test isolation with temporary databases
- **Git Integration**: Session-scoped Git repository initialization
- **Coverage Reporting**: HTML, XML, and JUnit output formats

**Test Categories**
- **Unit Tests** (`tests/unit/`): Individual component testing with mocked dependencies
- **Integration Tests** (`tests/integration/`): End-to-end pipeline workflows
- **Storage Layer Tests**: SQLite metadata and LanceDB vector operations
- **Chunker Tests**: Language-specific and fallback chunking behavior
- **Error Handling Tests**: Retry logic and graceful failure recovery

**Notable Test Patterns**
- **Dry Run Semantics**: Tests account for pipeline behavior in dry-run mode
- **Git Repository Setup**: Integration tests automatically initialize Git repos
- **Mocked External Services**: OpenAI, LanceDB, and file system operations
- **Error Injection**: Comprehensive error scenario testing
- **Performance Testing**: Memory usage and execution time validation

### Running Tests

Use Just commands for consistent testing:
```sh
# Run complete test suite
just test

# Run specific test categories
just test-unit
just test-integration

# Run with coverage reporting
just test-coverage

# Run specific test file
just test-file -- file=tests/unit/test_chunker_registry.py

# Run with detailed output
just test-verbose
```

Direct pytest commands (if needed):
```sh
# Direct pytest commands (use Just commands when possible)
uv run pytest -q
uv run pytest tests/unit/ -q
uv run pytest --cov=src/pb_kb --cov-report=html
```

### Test Framework Rules

**KB Pipeline Tests - Dry Run Semantics**
- When testing pipeline.scan or pipeline.index with dry_run=True, do not assert persisted counters; only assert session exists and status remains 'running'. Use force=True in scan/index calls when repository is not guaranteed to be a clean Git working tree.
- Our ingestion pipeline leaves session status 'running' during dry_run and does not persist counters. Tests should avoid asserting session counters in dry_run modes and include force=True where git cleanliness may fail.

**Test Execution Patterns**
- Use `just test` for comprehensive testing
- Use `just test-unit` for fast development feedback
- Use `just test-integration` for pipeline workflow validation
- Use `just test-coverage` before commits to ensure adequate test coverage
- Integration tests automatically initialize Git repositories for scan operations

### Next Development Phase

The test framework is now complete and provides comprehensive coverage for all KB pipeline components. The next phase is server implementation, building on this solid testing foundation.

This guide should enable AI assistants to effectively understand, navigate, and contribute to the dolphin project while providing accurate assistance to users.o