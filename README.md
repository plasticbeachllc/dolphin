# 🐬 dolphin

[![PyPi Version](https://img.shields.io/pypi/v/pb-dolphin.svg)](https://pypi.org/project/pb-dolphin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A semantic code search and knowledge management system for AI interface. This repository contains an indexing program (Python), an MCP server (TypeScript/Bun), an agent controller for LLM inference (TypeScript/Bun), and a VSCode extension (NodeJs/Svelte).

## Quick Start

### Installation

#### Core Installation (~200MB)

```bash
# install with uv (recommended)
uv pip install pb-dolphin

# ensure OPENAI_API_KEY is set as env var
export OPENAI_API_KEY="sk-your-key-here"
```

#### Optional: Cross-Encoder Reranking (~2GB additional)

For advanced search quality improvement (+20-30% MRR):

```bash
uv pip install "pb-dolphin[reranking]"
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
- **Semantic Search**
  - OpenAI embeddings with LanceDB vector storage
  - Hybrid approximate nn vector + BM25 keyword search with RRF scoring
  - Re-ranking with cross-encoder
  - MMR relevancy enhancement
- **Interfaces**
  - `dolphin` CLI app
  - FastAPI server with search, retrieval, and metadata endpoints
  - MCP server implementation available at `bunx dolphin-mcp`
- **Configuration** - Per-repo chunking and ignore configuration

## Configuration

Dolphin uses a multi-level configuration system:

1. **Repo-specific** (`./.dolphin/config.toml`) - Optional per-repository chunking settings
2. **User-global** (`~/.dolphin/config.toml`) - Auto-created on first use

### Configuration TOMLs

You can use `dolphin init` to initialize your global config and edit from there.

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

To generate a repo-specific config, use `dolphin init --repo` at the repository root.

### Environment Variables

```bash
# Required when using OpenAI embeddings (recommended for production)
export OPENAI_API_KEY="sk-your-openai-api-key-here"
```

### Post-Commit Hook (recommended)

Add this line to the repo's `.git/postcommit` file, inserting the actual repo name.

```
uv run dolphin index {repo-name}
```

Since the indexer walks the git diff, your repository index will always remain fresh.

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

**Note:** In development, make sure you are running the HTTP retrieval server: `uv run dolphin serve`

In production deployments (e.g., VSCode extension), the KB server lifecycle is managed automatically.

Available MCP tools: `search_knowledge`, `fetch_chunk`, `fetch_lines`, `get_vector_store_info`

## VSCode Extension

Dolphin includes a VSCode extension that provides an AI coding assistant with semantic code search integration.

### Features

- **AI Chat Interface**: Interact with Claude AI directly in VSCode
- **Knowledge Bank Integration**: Automatically searches your indexed codebase for context
- **Dual Authentication**: Supports both Claude CLI (subscription) and API key modes
- **Real-time Streaming**: See AI responses as they're generated
- **Tool Call Visualization**: Monitor Knowledge Bank searches and other tool executions

### Installation (Development)

```bash
# 1. Build the extension
cd vscode-extension
npm install
npm run compile

# 2. Build the webview
cd webview
bun install
bun run build
cd ../..

# 3. Launch Extension Development Host
# Open vscode-extension folder in VSCode and press F5
```

### Authentication

The extension supports two authentication modes:

**Option A: Claude CLI (No API Costs)**

```bash
npm install -g @anthropic-ai/claude-code
claude
# Select: "1. Claude account with subscription"
```

**Option B: API Key**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## REST API

```bash
# Start server
dolphin serve

# Health check
curl http://127.0.0.1:7777/health

# List repositories
curl http://127.0.0.1:7777/repos

# Search "authentication"
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "top_k": 5}'
```

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

Restart the API server to apply changes:

```bash
uv run dolphin serve
```

## Development Status

**Current**: Beta (v0.2.0)

- ✅ Core indexing and search pipeline
- ✅ Language-aware chunking (Python, TS, JS, Markdown)
- ✅ REST API with MCP bridge available at `bunx dolphin-mcp`
- ✅ VSCode extension with AI coding assistant
- ✅ Cross-encoder reranking support
- ✅ Hybrid search (BM25 + Vector)
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

See [TESTING.md](TESTING.md) for complete testing procedures.

## Troubleshooting

### Quick Diagnostics

```bash
# Check API server
curl http://127.0.0.1:7777/health

# Check indexed repositories
dolphin kb status

# Re-index a repository
dolphin kb index <repo-name> --full --force
```

### Common Issues

**API not responding:**

- Start the server: `dolphin serve`
- Check port conflicts: `lsof -i :7777`

**No search results:**

- Verify repositories are indexed: `dolphin kb status`
- Try with lower score cutoff in search parameters
- Re-index: `dolphin kb index <repo-name> --full --force`

**MCP not connecting:**

- Verify API server is running: `curl http://127.0.0.1:7777/health`
- Check MCP bridge logs: `tail -f mcp-bridge/logs/mcp.log`
- Verify Bun is installed: `bun --version`

**High embedding costs:**

- Use `small` embedding model (1536d instead of 3072d)
- Check session costs: `dolphin kb status <repo-name>`
- Use stub provider for testing (no OpenAI calls)

For detailed troubleshooting, performance tips, and development workflows, see [AGENTS.md](AGENTS.md).

## Publication

### Versions

Current versions:

- **Python Package (PyPI)**: [`0.2.0`](pyproject.toml:7) - `pb-dolphin`
- **VSCode Extension**: [`0.1.0`](vscode-extension/package.json:5) - `dolphin`
- **MCP Bridge (npm)**: [`0.1.3`](mcp-bridge/package.json:3) - `dolphin-mcp`

### License

MIT License

### Acknowledgments

Built with [LanceDB](https://lancedb.com/), [OpenAI](https://openai.com/), [FastAPI](https://fastapi.tiangolo.com/), [Bun](https://bun.sh/), and lots of other tech.

---

**⚠️ Remember**: This is experimental software under active development. Use at your own risk.
