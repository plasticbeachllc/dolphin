# 🐬 dolphin

[![PyPi Version](https://img.shields.io/pypi/v/pb-dolphin.svg)](https://pypi.org/project/pb-dolphin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**⚠️ EXPERIMENTAL - This is a developmental library under active development. APIs and interfaces are unstable and subject to change without notice.**

A semantic code search and knowledge management system with AI-native interfaces (MCP, REST API, CLI).

## Quick Start

### Installation

#### Core Installation (~200MB)

```bash
# install with uv (recommended)
uv pip install pb-dolphin

# ⚠️ IMPORTANT: Ensure OPENAI_API_KEY is set as env var
export OPENAI_API_KEY="sk-your-key-here"
```

#### Optional: Cross-Encoder Reranking (~2GB additional)

For advanced search quality improvement (+20-30% MRR):

```bash
uv pip install pb-dolphin[reranking]
```

**Trade-off**: Better relevance but 2-3x slower searches. See [Advanced Features](#advanced-features) for configuration.


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
│  ┌─────────────┐    ┌────────────────-┐  │
│  │ MCP Bridge  │◄──►│ REST API        │  │
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

- **Language-Aware Chunking** - Code parsing for Python, TypeScript, JavaScript, Markdown
- **Semantic Search** - OpenAI embeddings with LanceDB vector storage
- **REST API** - FastAPI server with search, retrieval, and metadata endpoints
- **Unified CLI** - Single `dolphin` command for all operations
- **Configuration** - Per-repo chunking and ignore configuration
- **MCP Support** - MCP server implementation available at `bunx dolphin-mcp`

## Environment Variables

```bash
# Required when using OpenAI embeddings (recommended for production)
export OPENAI_API_KEY="sk-your-openai-api-key-here"
```

## Configuration

Dolphin uses a multi-level configuration system:

1. **Repo-specific** (`./.dolphin/config.toml`) - Optional per-repository chunking settings
2. **User-global** (`~/.dolphin/config.toml`) - Auto-created on first use

### Configuration

You can use `dolphin init` to initialize your config and edit from there.

```toml
# ~/.dolphin/config.toml
default_embed_model = "large"  # or "small"

[embedding]
provider = "openai"
batch_size = 100

[retrieval]
top_k = 8
score_cutoff = 0.0
```

## MCP Configuration

The small companion MCP interface can be run via `bun` without install. Add to your favorite AI application's config:

```json
{
  "mcpServers": {
    "dolphin": {
      "command": "bunx",
      "args": ["dolphin-mcp"]
    }
  }
}
```

Make sure you are running the HTTP retrieval server: `uv run dolphin serve`

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

## Advanced Features

### Cross-Encoder Reranking

Cross-encoder reranking improves search result relevance by re-scoring each result pairwise against the query using an ML model, leading to 20-30% improvements in search result ranking quality ([Nogueira & Cho, 2019](https://arxiv.org/abs/1901.04085)).

**Performance Impact:**
- ⚠️ **2-3x slower searches** - cross-encoder is compute-intensive
- ⚠️ **~2GB install size** - requires torch and sentence-transformers

#### Installation

```bash
uv pip install pb-dolphin[reranking]
```

#### Configuration

Enable in your `~/.dolphin/config.toml`:

```toml
[retrieval.reranking]
enabled = true  # Enable cross-encoder reranking
model = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # HuggingFace model
device = ""  # Auto-detect (CPU or CUDA if available)
batch_size = 32  # Higher = faster but more memory
candidate_multiplier = 4  # Rerank top_k × multiplier candidates
score_threshold = 0.3  # Minimum relevance score (0-1)
```

Restart the API server to apply changes:

```bash
uv run dolphin serve
```

## Development Status

**Current**: Beta (0.1.x)

- ✅ Core indexing and search pipeline
- ✅ Language-aware chunking (Python, TS, JS, Markdown)
- ✅ REST API with MCP bridge available at `bunx dolphin-mcp`
- ⚠️ Developmental stage

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

## License

MIT License

## Acknowledgments

Built with [LanceDB](https://lancedb.com/), [OpenAI](https://openai.com/), [FastAPI](https://fastapi.tiangolo.com/), and [Bun](https://bun.sh/)

---

**⚠️ Remember**: This is experimental software under active development. Use at your own risk.
