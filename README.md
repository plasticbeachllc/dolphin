# 🐬 dolphin

**⚠️ EXPERIMENTAL - This is a developmental library under active development. APIs and interfaces are unstable and subject to change without notice.**

A semantic code search and knowledge management system with AI-native interfaces (MCP, REST API, CLI).

## Quick Start

### Installation

#### Core Installation (~200MB)

```bash
# Install core functionality with pip
pip install pb-dolphin

# Or with uv (recommended)
uv pip install pb-dolphin

# ⚠️ IMPORTANT: Ensure OPENAI_API_KEY is set as env var
export OPENAI_API_KEY="sk-your-key-here"
```

#### Optional: Cross-Encoder Reranking (~2GB additional)

For advanced search quality improvement (+20-30% MRR):

```bash
# With pip
pip install pb-dolphin[reranking]

# With uv (recommended)
uv pip install pb-dolphin[reranking]
```

**Trade-off**: Better relevance but 2-3x slower searches. See [Advanced Features](#advanced-features) for configuration.

#### Optional: MCP Orchestrator

For MCP server management capabilities:

```bash
# With pip
pip install pb-dolphin[orchestrator]

# With uv
uv pip install pb-dolphin[orchestrator]
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

## Advanced Features

### Cross-Encoder Reranking

Cross-encoder reranking improves search result relevance by re-scoring results with a more sophisticated ML model.

**Performance Impact:**
- ✅ **+20-30% improvement** in Mean Reciprocal Rank (MRR)
- ✅ **Better first-result quality** - more relevant top results
- ⚠️ **2-3x slower searches** - cross-encoder is compute-intensive
- ⚠️ **~2GB install size** - requires torch and sentence-transformers

#### Installation

```bash
# With uv (recommended)
uv pip install pb-dolphin[reranking]

# Or with pip
pip install pb-dolphin[reranking]
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
dolphin serve
```

#### When to Use Reranking

**Enable when:**
- Search quality is critical
- Willing to accept higher latency
- Have sufficient compute resources
- Precision matters more than speed

**Don't enable when:**
- Speed is priority
- Install size matters
- Basic vector search + hybrid search is sufficient

#### How It Works

```
Normal Search:
Query → Embeddings → Vector Search → Top Results

With Reranking:
Query → Embeddings → Vector Search → Fetch top_k×4 candidates
      → Cross-encoder re-scores each (query, result) pair
      → Re-sort by cross-encoder scores → Top Results
```

The cross-encoder model evaluates each query-result pair directly, providing more accurate relevance scores than simple vector similarity.

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
