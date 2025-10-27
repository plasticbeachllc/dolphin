# dolphin

Your personal AI companion.

---

## 🚀 Getting Started

### Prerequisites

*   just
*   Docker
*   Python >=3.13 (with `uv` installed)

### Installation & Setup

1.  Clone the repository:
    ```sh
    git clone <your-repo-url>
    cd dolphin
    ```
2.  Run the setup command:
    ```sh
    just setup
    ```

## 🤖 Usage

To start all services for the AI companion, run:
```sh
just run
```

This will launch OpenWebUI and the necessary backend MCP servers.

### Common Commands

*   `just run`: Starts all services.
*   `just stop`: Stops all services.
*   `just setup-openwebui`: Pulls the latest images and starts the web UI.
*   `just test`: Runs the project's test runner (tests.run_tests) which discovers test_*.py modules in the tests/ directory and executes their run_test() functions.

To see all available commands, run:
```sh
just list
```

### Testing

The project uses **pytest** as the primary test framework with comprehensive fixture support and integration testing.

Run the complete test suite:
```sh
uv run pytest -q
```

Run specific test categories:
```sh
# Run only unit tests
uv run pytest tests/unit/ -q

# Run only integration tests  
uv run pytest tests/integration/ -q

# Run with coverage reporting
uv run pytest --cov=src/pb_kb --cov-report=html
```

**Test Status**: ✅ **Complete Test Framework**
- **147/147 tests passing** with comprehensive coverage
- **Unit Tests**: 144 passing - Core component functionality
- **Integration Tests**: 21 passing - Component interactions and workflows
- **Skipped Tests**: 2 - External service dependencies
- **Execution Time**: ~2.8 seconds for full test suite

## 🎭 Personas

The dolphin project includes a personas system that allows you to define and use different AI agent personalities with specific behaviors, guardrails, and configurations.

## 🧠 Knowledge Base & Chunking System

### ✅ Phase 4 Complete: Chunker Registry & Integration

The project features a sophisticated knowledge base system with language-aware file chunking for semantic retrieval. The chunker registry system provides unified, configuration-driven routing of files to appropriate chunkers.

### Chunking Features
- **Repository Configuration**: Per-repository token window sizes via `.dolphin/chunking_config.toml`
- **Language-Aware Chunking**: Specialized chunkers for Python, TypeScript, and Markdown
- **Token-Based Windowing**: Accurate token counting using tiktoken with configurable overlap
- **Enhanced Fallback Chunker**: Robust token-windowing for generic file types (JSON, YAML, plain text, etc.)
- **Accurate Line Mapping**: Binary search-based line number tracking with 1-based indexing
- **Chunker Registry**: Automatic routing based on file extension and language
- **Global Configuration**: Consolidated settings in `.dolphin/config.toml`

### Available Chunkers
- ✅ **Python Chunker**: Tree-sitter based symbol extraction (classes, functions, methods)
- ✅ **TypeScript/TSX Chunker**: Tree-sitter based symbol extraction with token windowing
- ✅ **Markdown Chunker**: Heading-aware section chunking with YAML front matter
- ✅ **Fallback Chunker**: Token-windowing for all other file types with accurate line mapping
- ✅ **Chunker Registry**: Routes 50+ file extensions to appropriate chunkers

### Configuration Examples

**Repository Configuration** (`.dolphin/chunking_config.toml`):
```toml
default_window_size = 350

[per_language]
python = 512
typescript = 350
markdown = 256

[embeddings]
model = "text-embedding-3-small"
```

**Global Configuration** (`.dolphin/config.toml`):
```toml
# Extension → Language mappings
[languages]
py = "python"
ts = "typescript"
md = "markdown"
json = "json"
# ... 50+ mappings

[chunking]
default_window_size = 350
overlap_pct = 0.10

[chunking.per_language]
python = 512
typescript = 350
markdown = 256
```

### Available Personas

- **Deep Dive**: Principal AI planner and systems architect who breaks work into ordered, testable increments, surfaces trade-offs and risks, and ensures production-ready patterns
- **Journalist**: Meticulous project documentarian who synthesizes repository state and changes, highlights gaps between plans and reality, and maintains accurate records
- **Little Ripper**: Junior software engineer who thrives on tight feedback cycles, follows specifications exactly, and implements small, verifiable changes
- **Fancy Slave**: Pragmatic cheap labor focused on conversation, efficiency, and adaptability
- **Popeye**: Senior engineer at Plastic Beach responsible for implementation and engineering on high-priority projects, writing thoughtful, elegant, and maintainable code

### Personas Commands

* `just personas-list`: List all available personas
* `just personas-preview --id <persona_id>`: Preview a specific persona's configuration and system message
* `just personas-generate`: Generate Continue config from all personas (writes to `.continue/agents/personas_config.yaml`)

### Persona Structure

Each persona is defined in its own directory under `personas/` with the following structure:

```
personas/
  ├── <persona-id>/
  │   ├── persona.toml    # Persona metadata and configuration
  │   ├── system.md       # System prompt and behavior definition
  │   └── guardrails.md   # Safety rules and constraints
```

### Creating a New Persona

1. Create a new directory under `personas/` with a slug-style name (e.g., `my-new-persona`)
2. Add the required files:
   - `persona.toml`: Define persona metadata, provider settings, and parameters
   - `system.md`: Write the system prompt that defines the persona's behavior
   - `guardrails.md`: (Optional) Add safety rules and constraints
3. Use `just personas-preview --id my-new-persona` to validate your persona
4. Run `just personas-generate` to include it in the Continue configuration

### Example: Previewing a Persona

```sh
just personas-preview --id journalist --verbose
```

This will show the compiled system message, token usage, and any trimming steps applied to fit within the token budget.

## 🧪 Testing

### Test Framework

The project features a comprehensive test framework with both unit and integration tests:

**Unit Tests** (`tests/unit/`)
- Core components: hashing, scanning, token utilities, deduplication
- Chunkers: Python, TypeScript, Markdown, fallback with advanced behavior
- Storage: SQLite metadata and LanceDB vector stores
- Embeddings: Retry logic and error handling

**Integration Tests** (`tests/integration/`)
- Pipeline workflows: scanning, indexing, and search
- Performance testing with large repositories
- Error handling and recovery scenarios
- Git repository integration

Run comprehensive tests:
```sh
# Run all tests
uv run pytest -q

# Test specific components
uv run pytest tests/unit/test_chunkers/ -q
uv run pytest tests/unit/test_store/ -q
uv run pytest tests/integration/ -q

# Test with detailed output
uv run pytest -v
```

**Test Status**: ✅ **Complete Test Framework**
- **147/147 tests passing** with comprehensive coverage
- **Unit Tests**: 144 passing - Core component functionality
- **Integration Tests**: 21 passing - Component interactions and workflows
- **Skipped Tests**: 2 - External service dependencies
- **Execution Time**: ~2.8 seconds for full test suite
