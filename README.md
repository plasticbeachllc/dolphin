# 🐬 Dolphin

**⚠️ EXPERIMENTAL - This is a developmental library under active development. APIs and interfaces are unstable and subject to change without notice.**

A semantic code search and knowledge management system with AI-native interfaces (MCP, REST API, CLI).

## Quick Start

### Installation

```bash
# Install from PyPI
pip install pb-dolphin

# ⚠️ IMPORTANT: Ensure OPENAI_API_KEY is set as env var
```

### Basic Usage

```bash
# Initialize global knowledge store and index a repository
dolphin init
dolphin add-repo my-project /path/to/project
dolphin index my-project

# Search your indexed code
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

## Environment Variables

Dolphin requires the following environment variables depending on your usage:

### Required for OpenAI Embeddings

```bash
# Required when using OpenAI embeddings (recommended for production)
export OPENAI_API_KEY="sk-your-openai-api-key-here"
```

### Setting Environment Variables

**macOS/Linux (bash/zsh):**
```bash
echo 'export OPENAI_API_KEY="sk-your-key-here"' >> ~/.bashrc
source ~/.bashrc
```

**macOS/Linux (fish):**
```bash
set -Ux OPENAI_API_KEY "sk-your-key-here"
```

**Windows (Command Prompt):**
```cmd
setx OPENAI_API_KEY "sk-your-key-here"
```

**Windows (PowerShell):**
```powershell
[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-your-key-here', 'User')
```

### Getting Your OpenAI API Key

1. Visit [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in to your account
3. Navigate to [API Keys](https://platform.openai.com/api-keys)
4. Click "Create new secret key"
5. Copy the key and set it as `OPENAI_API_KEY`

## Configuration

Dolphin uses a multi-level configuration system:

1. **Repo-specific** (`./.dolphin/config.toml`) - Per-repository chunking settings
2. **User-global** (`~/.dolphin/config.toml`) - Auto-created on first use

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
- ✅ REST API with MCP bridge
- ⚠️ Developmental stage

**Upcoming**:
- Performance optimization
- Production hardening
- Evaluation framework
- Expanded language support

## Requirements

- Python ≥3.12
- OpenAI API key (for embeddings) - **Required**
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

## License

MIT License

## Acknowledgments

Built with [LanceDB](https://lancedb.com/), [OpenAI](https://openai.com/), [FastAPI](https://fastapi.tiangolo.com/), and [Bun](https://bun.sh/)

---

**⚠️ Remember**: This is experimental software under active development. Use at your own risk.
