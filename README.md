# 🐬 dolphin

[![PyPi Version](https://img.shields.io/pypi/v/pb-dolphin.svg)](https://pypi.org/project/pb-dolphin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**⚠️ EXPERIMENTAL - This is a developmental library under active development. APIs and interfaces are unstable and subject to change without notice.**

A semantic code search and knowledge management system for AI interface. This package includes an indexing program managed by the user and an HTTP retrieval server. The companion MCP server is available at `bunx dolphin-mcp`.

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
  * OpenAI embeddings with LanceDB vector storage
  * Hybrid approximate nn vector + BM25 keyword search with RRF scoring
  * Re-ranking with cross-encoder
  * MMR relevancy enhancement
- **Interfaces**
  * `dolphin` CLI app
  * FastAPI server with search, retrieval, and metadata endpoints
  * MCP server implementation available at `bunx dolphin-mcp`
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

See [TESTING-GUIDE.md](docs/TESTING-GUIDE.md) for complete setup instructions.

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

**Current**: Beta (0.1.13)

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

See [TESTING-GUIDE.md](docs/TESTING-GUIDE.md) for complete testing procedures.

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

## Release Process

Dolphin is a monorepo with independently versioned components. Each component (Python package, VSCode extension, MCP bridge) has its own release cadence and version number.

### Component Versions

Current versions:
- **Python Package (PyPI)**: [`0.1.13`](pyproject.toml:7) - `pb-dolphin`
- **VSCode Extension**: [`0.1.0`](vscode-extension/package.json:5) - `dolphin`
- **MCP Bridge (npm)**: [`0.1.2`](mcp-bridge/package.json:3) - `dolphin-mcp`

### Independent Release Workflow

Each component is released independently using Git tags with prefixes:

#### 1. Python Package (`py-v*`)

```bash
# Update version in pyproject.toml
# Run tests
uv run pytest

# Create and push tag
git tag py-v0.1.14
git push origin py-v0.1.14
```

This triggers the [`publish-pypi.yml`](.github/workflows/publish-pypi.yml:1) workflow which:
- Builds the package with `uv build`
- Publishes to PyPI using trusted publishing

**Setup Required**: Configure trusted publishing in PyPI project settings or add `PYPI_API_TOKEN` secret.

#### 2. VSCode Extension (`vscode-v*`)

```bash
# Update version in vscode-extension/package.json
# Test extension locally

# Create and push tag
git tag vscode-v0.1.1
git push origin vscode-v0.1.1
```

This triggers the [`publish-vscode.yml`](.github/workflows/publish-vscode.yml:1) workflow which:
- Installs dependencies with npm
- Builds webview with Bun
- Publishes to VS Code Marketplace

**Setup Required**: Add `VSCE_PAT` (Visual Studio Marketplace Personal Access Token) to repository secrets.

#### 3. MCP Bridge (`mcp-v*`)

```bash
# Update version in mcp-bridge/package.json
# Run tests
cd mcp-bridge && bun test

# Create and push tag
git tag mcp-v0.1.3
git push origin mcp-v0.1.3
```

This triggers the [`publish-mcp.yml`](.github/workflows/publish-mcp.yml:1) workflow which:
- Installs dependencies with Bun
- Builds package
- Publishes to npm registry

**Setup Required**: Add `NPM_TOKEN` to repository secrets.

### Git Flow Integration

The workflows trigger on **git tags**, not branches. Here's the complete Git Flow process:

#### Daily Development

```bash
# Start feature
git flow feature start my-feature

# Work on feature...
# Commit changes

# Finish feature (merges to develop)
git flow feature finish my-feature
git push origin develop
```

#### Releasing Components

**Step 1: Prepare on develop branch**
```bash
# On develop branch
git checkout develop

# Update version(s) in package files
# - pyproject.toml for Python
# - vscode-extension/package.json for VSCode
# - mcp-bridge/package.json for MCP

# Commit version bumps
git add pyproject.toml vscode-extension/package.json mcp-bridge/package.json
git commit -m "chore: bump version(s) for release"
git push origin develop
```

**Step 2: Merge to master**
```bash
# Merge develop to master
git checkout master
git merge develop
git push origin master
```

**Step 3: Create tags (triggers workflows)**
```bash
# IMPORTANT: You must be on master branch when creating tags
git checkout master

# Tag only the component(s) you want to release
git tag py-v0.1.14      # Triggers Python package publish
git tag vscode-v0.1.1   # Triggers VSCode extension publish
git tag mcp-v0.1.3      # Triggers MCP bridge publish

# Push tags - this triggers the GitHub Actions workflows
git push origin --tags
```

**The branch doesn't matter for triggering** - workflows trigger on tags being pushed to the repository. However, **best practice is to tag from master** to ensure you're releasing production-ready code.

#### Quick Reference

```bash
# Complete release flow
git checkout develop
# ... update versions, commit ...
git push origin develop

git checkout master
git merge develop
git push origin master

git tag py-v0.1.14      # Tag what changed
git push origin --tags  # Triggers workflows
```

**Multiple components?** You can create multiple tags and push them all at once:
```bash
git tag py-v0.1.14 vscode-v0.1.1 mcp-v0.1.3
git push origin --tags
# All three workflows run in parallel
```

### Manual Publishing

If you need to publish manually without GitHub Actions:

**Python Package:**
```bash
uv build
uv publish
```

**VSCode Extension:**
```bash
cd vscode-extension
npm install
cd webview && bun install && bun run build && cd ..
npx vsce publish --pat <your-pat>
```

**MCP Bridge:**
```bash
cd mcp-bridge
bun install
bun run build
npm publish --access public
```

### Version Bump Guidelines

- **Patch** (0.0.x): Bug fixes, minor changes
- **Minor** (0.x.0): New features, non-breaking changes
- **Major** (x.0.0): Breaking API changes

Components can be versioned independently based on their actual changes.

## License

MIT License

## Acknowledgments

Built with [LanceDB](https://lancedb.com/), [OpenAI](https://openai.com/), [FastAPI](https://fastapi.tiangolo.com/), [Bun](https://bun.sh/), and lots of other tech.

---

**⚠️ Remember**: This is experimental software under active development. Use at your own risk.
