# Dolphin

[![PyPi Version](https://img.shields.io/pypi/v/pb-dolphin.svg)](https://pypi.org/project/pb-dolphin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Multi-repo all-in-one semantic search for context efficiency in codebases of any size.

Dolphin helps humans and AI agents find the right code quickly with semantic search, rich context retrieval, and different interface options (CLI, REST API, and MCP).

## Why Dolphin

- **Modern search framework**: hybrid vector + keyword retrieval with optional reranking keeps search relevant as codebases scale.
- **All-in-one context management**: indexing, chunking, metadata, snippets, and graph context in one framework.
- **Practical developer UX**: use from terminal, set up with MCP, or integrate however you like.

## Quick Start

### 1) Install

#### Core Installation

```bash
# install with uv (recommended)
uv pip install pb-dolphin

# ensure OPENAI_API_KEY is set as env var
export OPENAI_API_KEY="sk-your-key-here"
```

The accompanying [MCP server](#mcp-configuration) is available at `bunx dolphin-mcp`.

#### Optional: Cross-Encoder Reranking (~2GB additional)

For advanced search quality improvement (+20-30% MRR):

```bash
uv pip install "pb-dolphin[reranking]"
```

See [Advanced Features](#advanced-features) for more information.

### 2) Index a repository

We recommend using `uv run` for Python command execution.

```bash
# Initialize global knowledge store and index a repository
uv run dolphin init
uv run dolphin add-repo my-project /path/to/project

# Start API server
uv run dolphin serve

# Search your indexed code
uv run dolphin search "authentication logic"
```

## Core Commands

- `dolphin init` - Initialize configuration (auto-creates `~/.dolphin/config.toml`)
- `dolphin init --repo` - Create repo-specific config in current directory
- `dolphin add-repo <name> <path>` - Register a repository for indexing
- `dolphin index <name>` - Index a repository with language-aware chunking
- `dolphin search <query>` - Search indexed code semantically (compact by default, `--verbose` for details, `--json` for scripting)
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

- **File-Watch Indexing** - Indexing is triggered automatically when files change by default
- **Language-Aware Chunking** - Code parsing for Python, TypeScript, JavaScript, Markdown
- **Semantic Search**
  - OpenAI embeddings with LanceDB vector storage
  - Hybrid approximate nn vector + BM25 keyword search with RRF scoring
  - Re-ranking with cross-encoder
  - MMR relevancy enhancement
  - Structured snippet objects with precise context
- **Interfaces**
  - `dolphin` CLI app
  - FastAPI server with search, retrieval, and metadata endpoints
  - MCP server implementation available at `bunx dolphin-mcp`
- **Configuration**
  - Per-repo chunking and ignore configuration

## Configuration

Dolphin uses a multi-level configuration system:

1. **Repo-specific** (`./.dolphin/config.toml`) - Optional per-repository chunking settings
2. **User-global** (`~/.dolphin/config.toml`) - Auto-created on first use

### Configuration TOMLs

Use `dolphin init` to initialize your global config.

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

To generate a repo-specific config for chunking and ignore settings, use `dolphin init --repo` at the repository root.

### Environment Variables

```bash
# Required when using OpenAI embeddings (recommended for production)
export OPENAI_API_KEY="sk-your-openai-api-key-here"
```

### API Key Management

For security and future-proofing, Dolphin automatically manages a KB API key for securing Knowledge Base HTTP endpoints. Running `dolphin init` or `dolphin serve` automatically creates `~/.dolphin/kb_api_key`. The MCP bridge (`bunx dolphin-mcp`) auto-provisions the key on startup.The key is a 64-character hex string with file permissions set to `0600` (user-only)

**Environment Variable Override (Advanced):**

For CI/CD, testing, or remote deployments, you can override the auto-provisioned key:

```bash
export DOLPHIN_API_KEY="your-custom-key-here"
# OR
export DOLPHIN_KB_API_KEY="your-custom-key-here"
```

Environment variables take precedence over the file-based key.

## MCP Configuration

The small companion MCP interface can be run using `bun` without install. Add to your favorite AI application's config:

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

**Note:** Make sure you are running the HTTP retrieval server: `uv run dolphin serve`

Set `DOLPHIN_API_URL` if your server is not running at `http://127.0.0.1:7777`.

Available MCP tools: `search`, `chunk_get`, `file_lines`, `store_info`, `metadata_get`, `repos_list`, `health`

## Advanced Features

### Cross-Encoder Reranking

Cross-encoder reranking improves search result relevance by re-scoring each result pairwise against the query using an ML model, leading to 20-30% improvements in search result ranking quality ([Nogueira & Cho, 2019](https://arxiv.org/abs/1901.04085)).

**Performance Impact:**

- ⚠️ **2-3x slower searches** - cross-encoder is compute-intensive
- ⚠️ **~2GB install size** - requires torch and sentence-transformers

#### Installation

```bash
uv pip install "pb-dolphin[reranking]"
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

Restart the API server to apply changes.

### File-Watching

The Dolphin server includes an integrated file watcher that keeps your Knowledge Bank synchronized in real-time.

- **Automatic**: When you run `dolphin serve`, it automatically starts watching all registered repositories.
- **Git-Aware**: The indexer respects `.gitignore` rules. The watcher handles Git branch switching, updating the index to match the new working tree.

### Configuring Embedding Models

Dolphin uses a consistent embedding model across your repositories to simplify global search. The embedding model can be configured globally in your `config.toml`:

```toml
default_embed_model = "large"  # Options: "small" or "large"
```

Currently only [OpenAI embeddings](https://platform.openai.com/docs/guides/embeddings) are supported.

## Requirements

- Python ≥3.12
- OpenAI API key (for embeddings)
- Bun (for MCP bridge)
- Git (for repository scanning)
- uv (for Python dependencies)

## Testing

```bash
just test
```

See [docs/TESTING.md](docs/TESTING.md) for complete testing procedures.

## Documentation

- High-level architecture: `docs/ARCHITECTURE.md`
- Testing guide: `docs/TESTING.md`
- Benchmarking: `docs/BENCHMARKING.md`
- Profiling: `docs/PROFILING.md`

## Troubleshooting

### Quick Diagnostics

```bash
# Check API server
curl http://127.0.0.1:7777/v1/health

# Check indexed repositories
dolphin status

# Re-index a repository
dolphin index <repo-name> --full --force
```

### Common Issues

**API not responding:**

- Start the server: `dolphin serve`
- Check port conflicts: `lsof -i :7777`

**No search results:**

- Verify repositories are indexed: `dolphin status`
- Try with lower score cutoff in search parameters
- Re-index: `dolphin index <repo-name> --full --force`

**MCP not connecting:**

- Verify API server is running: `curl http://127.0.0.1:7777/v1/health`
- Verify Bun is installed: `bun --version`

For detailed troubleshooting, performance tips, and development workflows, see [AGENTS.md](AGENTS.md).

## Publication

### Versions

Current versions:

- **Python Package (PyPI)**: [`0.2.2`](pyproject.toml:7) - `pb-dolphin`
- **MCP Bridge (npm)**: [`0.2.3`](mcp-bridge/package.json:3) - `dolphin-mcp`

### License

MIT License

### Acknowledgments

Built with [LanceDB](https://lancedb.com/), [OpenAI](https://openai.com/), [FastAPI](https://fastapi.tiangolo.com/), [Bun](https://bun.sh/), and lots of other tech.
