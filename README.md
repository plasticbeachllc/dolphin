# 🐬 Dolphin

**⚠️ EXPERIMENTAL - This is a developmental library under active development. APIs and interfaces are unstable and subject to change without notice.**

A semantic code search and knowledge management system with AI-native interfaces (MCP, REST API, CLI).

## Quick Start

### Installation

```bash
# Install from source
git clone https://github.com/plasticbeachllc/dolphin.git
cd dolphin
uv sync

# Or install from PyPI (when available)
pip install dolphin
```

### Basic Usage

```bash
# Initialize and index a repository
dolphin init
dolphin add-repo my-project /path/to/project
dolphin index my-project

# Search your code
dolphin search "authentication logic"

# Start API server
dolphin serve
```

## Core Commands

- `dolphin init` - Initialize configuration (auto-creates `~/.dolphin/config.toml`)
- `dolphin init --repo` - Create repo-specific config in current directory
- `dolphin add-repo <name> <path>` - Register a repository for indexing
- `dolphin index <name>` - Index a repository with language-aware chunking
- `dolphin search <query>` - Search indexed code semantically
- `dolphin serve` - Start REST API server (port 7777)
- `dolphin config --show` - Display current configuration

## Architecture

### High-Level Overview

```
┌──────────────────────────────────────────┐
│   AI Interfaces (Claude, Continue, etc)  │
└──────────────┬───────────────────────────┘
               │ MCP Protocol
               ▼
┌──────────────────────────────────────────┐
│          Dolphin Knowledge Base          │
│  ┌─────────────┐    ┌────────────────┐  │
│  │ MCP Bridge  │◄──►│ REST API       │  │
│  │ (TypeScript)│    │ (Python/FastAPI)│  │
│  └─────────────┘    └────────┬────────┘  │
└──────────────────────────────┼───────────┘
                               │
               ┌───────────────┴────────────┐
               ▼                            ▼
          ┌─────────┐                ┌──────────┐
          │LanceDB  │                │ SQLite   │
          │(Vectors)│                │(Metadata)│
          └─────────┘                └──────────┘
```

### Key Features

- **Language-Aware Chunking** - Intelligent code parsing for Python, TypeScript, JavaScript, Markdown
- **Semantic Search** - OpenAI embeddings with LanceDB vector storage
- **MCP Support** - Native Model Context Protocol integration for Claude Desktop
- **REST API** - FastAPI server with search, retrieval, and metadata endpoints
- **Unified CLI** - Single `dolphin` command for all operations
- **Auto-Configuration** - Smart config hierarchy (repo → user → defaults)

## Configuration

Dolphin uses a multi-level configuration system:

1. **Repo-specific** (`./.dolphin/config.toml`) - Per-repository chunking settings
2. **User-global** (`~/.dolphin/config.toml`) - Auto-created on first use
3. **Built-in defaults** - Sensible defaults for all settings

### Example Config

```toml
# ~/.dolphin/config.toml
default_embed_model = "large"  # or "small"

[embedding]
provider = "openai"
batch_size = 100

[retrieval]
top_k = 8
score_cutoff = 0.15
```

## Claude Desktop Integration (MCP)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dolphin": {
      "command": "bun",
      "args": ["run", "/path/to/dolphin/mcp-bridge/src/index.ts"],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

Start the server: `dolphin serve`

Available MCP tools: `search_knowledge`, `fetch_chunk`, `fetch_lines`, `get_vector_store_info`

## REST API

```bash
# Start server
dolphin serve

# Search
curl -X POST http://127.0.0.1:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "top_k": 5}'

# List repositories
curl http://127.0.0.1:7777/v1/repos

# Health check
curl http://127.0.0.1:7777/v1/health
```

## Development Status

**Current**: Pre-alpha (0.1.x)

- ✅ Core indexing and search pipeline
- ✅ Language-aware chunking (Python, TS, JS, Markdown)
- ✅ MCP bridge implementation
- ✅ REST API with 5 endpoints
- ✅ 391 tests passing
- ⚠️  APIs subject to breaking changes
- ⚠️  No stability guarantees
- ⚠️  Documentation may be incomplete

**Upcoming**:
- Performance optimization
- Production hardening
- Evaluation framework
- Expanded language support

## Requirements

- Python ≥3.12
- OpenAI API key (for embeddings)
- Bun (for MCP bridge)
- Git (for repository scanning)

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test suite
uv run pytest tests/unit/
uv run pytest tests/integration/
```

## Contributing

This is experimental software. Contributions welcome, but expect rapid changes:

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## Documentation

- **[User Guide](docs/GUIDE.md)** - Detailed installation and usage
- **[Architecture](docs/ARCHITECTURE.md)** - Technical architecture and design
- **[Testing](tests/TESTING.md)** - Testing strategy and troubleshooting

## License

MIT License

## Acknowledgments

Built with [LanceDB](https://lancedb.com/), [OpenAI](https://openai.com/), [FastAPI](https://fastapi.tiangolo.com/), and [Bun](https://bun.sh/)

---

**⚠️ Remember**: This is experimental software under active development. Use at your own risk.