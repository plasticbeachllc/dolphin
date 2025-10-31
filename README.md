# 🐬 Dolphin

A full-stack AI enablement platform that integrates semantic code retrieval with multiple AI interfaces to provide intelligent assistance across development workflows.

## Overview

Dolphin is designed to power intelligent coding and documentation assistance through:

1. **OpenWebUI** — General-purpose conversational AI interface for researching code, planning, and documentation
2. **Continue (VSCode)** — IDE-integrated assistant for real-time code completion, explanation, and refactoring
3. **Custom MCP Servers** — Extensible Model Context Protocol integrations providing domain-specific tools and capabilities

At its core, Dolphin combines:
- **Personas System** — Multiple AI agent personalities with specific behaviors and guardrails (compiled for OpenWebUI and Continue)
- **Unified Knowledge Store** — Semantic retrieval system for code and documentation with intelligent chunking and embeddings
- **Metadata Management** — SQLite-backed provenance and session tracking
- **Vector Indexing** — LanceDB-powered semantic search for efficient retrieval

---

## 🎯 Current Implementation Status

### ✅ PHASES 1-5b COMPLETE: Fully Functional Platform

**Phase 6 (Embeddings & Pipeline)** — ✅ Complete
- ✅ Full KB pipeline operational and tested (191/191 tests passing)
- ✅ OpenAI embedding integration with exponential backoff retry logic
- ✅ SQLite + LanceDB storage layer working
- ✅ Git-aware incremental indexing
- ✅ Language-specific chunking (Python, TypeScript, Markdown, fallback)
- ✅ Per-repository configuration system
- ✅ Content-based deduplication
- ✅ Idempotent ingestion (safe re-runs)

**Phase 7 (REST API)** — ✅ Complete
- ✅ All 5 endpoints implemented and tested (52/52 tests passing)
- ✅ Retrieval server initialization with database connections
- ✅ Path traversal security protection
- ✅ Comprehensive error handling
- ✅ Health checks (shallow + deep)
- ✅ Repository listing with stats
- ✅ Semantic search with filtering
- ✅ Chunk and file retrieval

**Phase 5b (MCP Bridge)** — ✅ Complete
- ✅ All 6 MCP tools implemented (52/52 tests passing)
- ✅ MCP Protocol 2025-06-18 compliance
- ✅ 50KB content budget with multi-stage trimming for context windows
- ✅ Structured error responses with remediation hints
- ✅ JSONL logging with rotation
- ✅ Full TypeScript types with Zod validation
- ✅ AbortSignal support for cancellation

**Total Test Coverage**: 243/243 tests passing ✅

---

## 🚀 Quick Start

### Prerequisites

- **Python** ≥3.13 with `uv` package manager
- **Bun** (for MCP Bridge)
- **Docker** (for OpenWebUI)
- **Git** (for repository scanning)
- **OpenAI API Key** (for embeddings)

### Installation

1. **Clone and install dependencies**:

```bash
git clone https://github.com/plasticbeachllc/dolphin.git
cd dolphin

# Install Python dependencies
uv sync --group test

# Install Bun dependencies for MCP Bridge
cd mcp-bridge && bun install && cd ..
```

2. **Configure environment**:

```bash
# Copy example env file
cp env.example .env

# Add your API key
export OPENAI_API_KEY=sk-...
```

3. **Initialize the knowledge store**:

```bash
kb init
```

### Quick Commands with Justfile

```bash
# Setup
just venv            # Create venv and install Python deps
just bun-install     # Install Bun deps for mcp-bridge

# Index a repository
just init
just add-repo my-repo /path/to/repo
just reindex my-repo

# Start services
just api             # Start retrieval server
just mcp             # Start MCP bridge
just start           # Start OpenWebUI (localhost:3010)

# Search
just search "your query"
just repos           # List indexed repositories
just info            # Vector store information
just health          # Retrieval server health check
```

---

## 📖 Usage

### Indexing Repositories

Indexing commands are part of the knowledge base management:

```bash
# Initialize the knowledge base
kb init

# Add a repository
kb add-repo my-api /path/to/my-api --default-embed-model large

# Index the repository
kb index my-api

# Full re-index (force refresh)
kb index my-api --full --force

# Using Justfile
just reset my-repo /path/to/repo  # Complete setup: init + add + reindex
```

### Searching via CLI

Retrieval commands query the indexed knowledge store through the retrieval server:

```bash
# Add bin directory to PATH
export PATH="\$PWD/bin:\$PATH"

# Start the retrieval server (in one terminal)
kb-api

# Search for code (in another terminal)
kb-search search "authentication function"

# Search with more results
KB_TOP_K=10 kb-search search "error handling"

# Search in specific repositories
KB_REPOS=api-server,frontend kb-search search "login"

# List indexed repositories
kb-search repos

# Get vector store info
kb-search info

# Fetch a specific chunk
kb-search chunk abc123def456

# Fetch file lines
kb-search lines my-repo src/main.py 1 50
```

### Searching via REST API

```bash
# Start the retrieval server
kb-api

# Search for code
curl -X POST http://127.0.0.1:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "JWT token validation",
    "top_k": 5,
    "repos": ["my-api"],
    "score_cutoff": 0.15
  }'

# List repositories
curl http://127.0.0.1:7777/v1/repos

# Get chunk by ID
curl http://127.0.0.1:7777/v1/chunks/abc123def456

# Fetch file lines
curl "http://127.0.0.1:7777/v1/file?repo=my-repo&path=src/main.py&start=1&end=50"

# Health check
curl http://127.0.0.1:7777/v1/health
```

---

## 🔌 Integration Interfaces

### OpenWebUI

OpenWebUI provides a general-purpose conversational interface with integrated MCP tools:

```bash
# Start OpenWebUI (requires Docker)
just start

# Access at http://localhost:3010
```

OpenWebUI connects to the knowledge base through MCP services and can use configured personas for specialized agents.

### Continue (VSCode)

Continue configurations are generated from persona definitions:

```bash
# Generate Continue agent configurations
personas generate

# This creates individual Continue "agents" from each persona subdirectory
# Each agent has its own system prompt and knowledge base access
```

### Claude Desktop (MCP)

Dolphin provides a Model Context Protocol (MCP) bridge that allows Claude Desktop to search your codebase:

1. **Locate your Claude Desktop config**:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. **Add the MCP server**:

```json
{
  "mcpServers": {
    "pb-kb": {
      "command": "bun",
      "args": [
        "run",
        "/path/to/dolphin/mcp-bridge/src/index.ts"
      ],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

3. **Start the retrieval server** (in a terminal):

```bash
cd /path/to/dolphin
kb-api
```

4. **Restart Claude Desktop** and verify the 🔌 MCP icon appears

### Available MCP Tools

Once configured, Claude can use these tools:

- **`search_knowledge`** — Search your codebase semantically
- **`fetch_chunk`** — Get detailed chunk content by ID
- **`fetch_lines`** — Retrieve specific file lines
- **`get_vector_store_info`** — Check indexed repositories
- **`get_metadata`** — Get chunk metadata
- **`open_in_editor`** — Generate VS Code URIs for quick navigation

### MCP Inspector (Development)

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Start retrieval server (terminal 1)
kb-api

# Start MCP Inspector (terminal 2)
mcp-inspector bun run /path/to/dolphin/mcp-bridge/src/index.ts

# Open browser to test tools
# Navigate to http://localhost:5173
```

---

## ⚙️ Configuration

### Knowledge Store Config

Create or edit `~/.dolphin/knowledge_store/config.toml`:

```toml
[embedding]
provider = "openai"           # "openai" or "stub" (for testing)
batch_size = 100             # Embeddings per API call
api_key_env = "OPENAI_API_KEY"

[embeddings]
default_embed_model = "small"  # "small" (1536d) or "large" (3072d)

[store]
root = "~/.dolphin/knowledge_store"
```

### Per-Repository Config

Create `.dolphin/config.toml` in your repository:

```toml
[embedding]
default_embed_model = "large"  # Override default model for this repo

[chunking]
max_chunk_tokens = 512        # Max tokens per chunk
overlap_tokens = 64           # Overlap between chunks

[indexing]
ignore_patterns = [
  "*.min.js",
  "node_modules/**",
  "dist/**"
]
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenAI API key for embeddings |
| `PB_KB_STORE_ROOT` | `~/.dolphin/knowledge_store` | Storage directory |
| `PB_KB_EMBEDDING_PROVIDER` | `openai` | Embedding provider |
| `PB_KB_EMBEDDING_BATCH_SIZE` | `100` | Batch size for embeddings |
| `KB_TOP_K` | `5` | Default number of search results |
| `KB_REPOS` | (all) | Comma-separated repo filter |

---

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Interfaces                           │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │   Claude        │  │  OpenWebUI   │  │  Continue     │  │
│  │   Desktop       │  │  (Port 3010) │  │  (VSCode)     │  │
│  └────────┬────────┘  └──────┬───────┘  └───────┬───────┘  │
└───────────┼─────────────────┼──────────────────┼──────────┘
            │                 │                  │
            │ MCP Protocol    │ MCP Services     │ Generated
            │                 │                  │ Personas
            ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│           Knowledge Base Services Layer                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │    MCP Bridge (TypeScript)                          │   │
│  │    - Tool implementations (search, fetch, etc.)     │   │
│  │    - Content budget trimming (50KB)                 │   │
│  │    - JSONL logging with rotation                    │   │
│  └────────────────┬────────────────────────────────────┘   │
│                   │ HTTP                                     │
│  ┌────────────────▼────────────────────────────────────┐   │
│  │    Retrieval Server (FastAPI, Port 7777)           │   │
│  │    - 5 REST endpoints                              │   │
│  │    - Database connection initialization            │   │
│  │    - Semantic search and filtering                 │   │
│  └────────────────┬────────────────────────────────────┘   │
└───────────────────┼──────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
    ┌────────────┐      ┌──────────────┐
    │  LanceDB   │      │  SQLite      │
    │ (Vectors)  │      │ (Metadata)   │
    └────────────┘      └──────────────┘
```

### Pipeline Flow

1. **Ingestion**: Scan repos (`kb` commands) → Language-aware chunking → Compute embeddings → Store in LanceDB + SQLite
2. **Retrieval**: Query (`kb-search` commands) → Embed query → Vector search → Re-rank → Return results
3. **MCP Bridge**: Transform REST API responses → MCP protocol messages for Claude/tools

### Key Features

- **Language-aware chunking**: Python, TypeScript, Markdown, with fallback for other languages
- **Semantic search**: OpenAI embeddings + LanceDB vector store
- **Git-aware indexing**: Incremental updates based on commit history
- **Content deduplication**: Hash-based dedup to avoid redundant storage
- **Multi-interface access**: MCP, REST API, CLI, and conversational interfaces
- **Context budget management**: 50KB trimming for optimal LLM context windows

---

## 🧪 Testing

### Run All Tests

```bash
# Run all tests
just test

# Run with coverage
just test-coverage

# Run specific test suites
just test-unit
just test-integration

# Run specific test file
just test-file file=tests/unit/test_search_api.py

# Verbose output
just test-verbose
```

### Test Coverage

Current test coverage: **243/243 tests passing** (100% for entire platform)

**Python Tests**: 191/191 passing
- Chunking (Python, TypeScript, Markdown, fallback)
- Embeddings (OpenAI provider, retry logic, stub provider)
- Storage (LanceDB, SQLite metadata)
- Search (semantic search, filtering, ranking)
- API (REST endpoints, error handling)

**TypeScript Tests**: 52/52 passing
- MCP Bridge tools and protocol compliance
- REST client and error handling
- Logging and concurrency
- Security and connectivity

---

## 🔧 Development

### Project Structure

```
dolphin/
├── bin/                      # CLI tools (kb, kb-search, kb-api)
├── docs/                     # Documentation
├── mcp-bridge/              # TypeScript MCP bridge
│   ├── src/
│   │   ├── index.ts         # MCP server entry point
│   │   ├── kb-cli.ts        # CLI wrapper for retrieval
│   │   └── tools/           # MCP tool implementations
│   └── logs/                # JSONL logs
├── personas/                # AI agent personas
│   ├── my-agent/           # Example persona structure
│   │   ├── system.md       # System prompt
│   │   └── config.json     # Configuration
│   └── generate.sh         # Generate Continue configs
├── src/pb_kb/              # Main Python package
│   ├── api/                # REST API (FastAPI)
│   ├── chunkers/           # Language-specific chunking
│   ├── embeddings/         # Embedding providers
│   ├── ingest/             # Ingestion pipeline
│   ├── retrieval/          # Search and ranking
│   └── store/              # LanceDB + SQLite storage
├── tests/                  # Unit and integration tests
├── justfile               # Task automation
├── pyproject.toml         # Python dependencies
└── README.md              # This file
```

### Development Workflow

```bash
# 1. Set up development environment
just setup-dev

# 2. Run tests in watch mode
pytest --watch tests/

# 3. Index a test repository
just reset test-repo /path/to/test/repo

# 4. Start services for testing
just api     # Terminal 1: Retrieval server
just mcp     # Terminal 2: MCP Bridge

# 5. Test search
just search "test query"

# 6. Watch logs
just tail-mcp
```

### Code Style

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint
ruff check src/ tests/

# Type checking
mypy src/
```

---

## 🐛 Troubleshooting

### Retrieval Server Not Running

```bash
# Check if server is up
curl http://127.0.0.1:7777/v1/health

# If not, start it
kb-api

# Check for port conflicts
lsof -i :7777
```

### No Search Results

```bash
# Check if repositories are indexed
kb-search repos

# Check vector store info
kb-search info

# Re-index repository
just reindex my-repo

# Try with lower score cutoff
curl -X POST http://127.0.0.1:7777/v1/search \
  -d '{"query": "test", "score_cutoff": 0.0}'
```

### MCP Not Connecting

```bash
# Check if kb-api is running
curl http://127.0.0.1:7777/v1/health

# Check MCP bridge logs
tail -f mcp-bridge/logs/mcp.log

# Check Claude Desktop logs (macOS)
tail -f ~/Library/Logs/Claude/mcp*.log

# Verify Bun is installed
bun --version
```

### OpenAI API Errors

```bash
# Verify API key is set
echo \$OPENAI_API_KEY

# Switch to stub provider for testing
# Edit ~/.dolphin/knowledge_store/config.toml:
# [embedding]
# provider = "stub"
```

---

## 📚 Documentation

Dolphin has comprehensive documentation organized into guides and technical references:

- **[User Guide](docs/GUIDE.md)** — Complete guide for installation, indexing, searching, CLI usage, REST API, MCP integration, and troubleshooting
- **[Architecture](docs/ARCHITECTURE.md)** — Technical architecture, implementation status, data models, pipeline flow, and test coverage
- **[Production Readiness](docs/PRODUCTION_READINESS.md)** — Path to production including monitoring, security, and scalability

For historical documentation and implementation plans, see `docs/ignore/`.

---

## 🎯 Roadmap

### Current Status (Phases 1-5b Complete)

- ✅ Knowledge base ingestion pipeline
- ✅ Semantic search with OpenAI embeddings
- ✅ REST API with filtering and ranking
- ✅ MCP bridge implementation
- ✅ CLI tools and Justfile workflows
- ✅ Multi-interface support (MCP, CLI, REST API)
- ✅ Comprehensive test coverage (243/243 tests passing)

### Upcoming Focus Areas

- 🔜 **Production Readiness**: Monitoring, observability, error recovery
- 🔜 **Performance Optimization**: Caching, query optimization, SLA targets
- 🔜 **User Experience**: Installation simplification, performance optimization
- 🔜 **Security Hardening**: Authentication, authorization, encryption at rest
- 🔜 **Scalability**: Distributed indexing, multi-tenant support
- 🔜 **Evaluation Framework**: P@5, R@10, MRR metrics

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Ensure all tests pass (`just test`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Acknowledgments

- Built with [LanceDB](https://lancedb.com/) for vector storage
- Uses [OpenAI](https://openai.com/) for embeddings
- MCP protocol by [Anthropic](https://www.anthropic.com/)
- Powered by [FastAPI](https://fastapi.tiangelo.com/) and [Bun](https://bun.sh/)

---

**Questions?** Open an issue or check the [docs/](docs/) folder for detailed guides.
