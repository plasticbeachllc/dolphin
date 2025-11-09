# Dolphin User Guide

Complete guide for using the Dolphin AI enablement platform for semantic code search and retrieval.

**Version**: 0.1.13
**Status**: Production Ready
**PyPI**: `pip install pb-dolphin`

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Indexing Repositories](#indexing-repositories)
- [Using Dolphin CLI](#using-dolphin-cli)
- [Using Justfile Commands](#using-justfile-commands)
- [CLI Reference](#cli-reference)
- [REST API Reference](#rest-api-reference)
- [MCP Integration](#mcp-integration)
- [Kilocode Integration](#kilocode-integration)
- [Configuration](#configuration)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### **Option A: Global Installation (Recommended)**

```bash
# Install from PyPI
pip install pb-dolphin

# Initialize knowledge base
dolphin init

# Add and index a repository
dolphin kb add-repo my-project /path/to/my-project
dolphin kb index my-project

# Start API server
dolphin serve &

# Search your code
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication function", "top_k": 5}'
```

### **Option B: Development Setup**

```bash
# Clone repository
git clone https://github.com/plasticbeachllc/dolphin.git
cd dolphin

# Install dependencies
uv sync --group test
cd mcp-bridge && bun install && cd ..

# Initialize and index
uv run dolphin init
uv run dolphin kb add-repo my-project /path/to/my-project
uv run dolphin kb index my-project

# Start services
uv run dolphin serve &
```

---

## Installation

### **Option 1: PyPI Installation (Global)**

```bash
# Install globally with pip
pip install pb-dolphin

# Verify installation
dolphin --help
kb --help
kb-api --help

# Note: Requires Python ≥3.12
```

### **Option 2: Development Installation**

#### Prerequisites

- **Python** ≥3.12 with `uv` package manager
- **Bun** (for MCP Bridge)
- **Git** (for repository scanning)
- **OpenAI API Key** (for embeddings)

#### Setup Steps

```bash
# Clone the repository
git clone https://github.com/plasticbeachllc/dolphin.git
cd dolphin

# Install Python dependencies
uv sync --group test

# Install Bun dependencies for MCP Bridge
cd mcp-bridge && bun install && cd ..

# Configure environment
cp env.example .env
# Edit .env and add your OPENAI_API_KEY

# Initialize the knowledge store
uv run dolphin init
```

---

## Indexing Repositories

### **Using the Unified Dolphin CLI (Recommended)**

```bash
# Initialize knowledge base
dolphin init

# Add a repository
dolphin kb add-repo my-api /path/to/my-api --default-embed-model large

# Index the repository (incremental)
dolphin kb index my-api

# Full re-index (force refresh)
dolphin kb index my-api --full --force

# Check status
dolphin kb status
dolphin kb status my-api
```

### **Using Legacy KB CLI**

```bash
# Also works with kb command directly
kb init
kb add-repo my-api /path/to/my-api --default-embed-model large
kb index my-api
kb status
```

### **Using Justfile (Development)**

```bash
# Complete setup in one command
just reset my-repo /path/to/repo

# Or step by step
just init
just add-repo my-repo /path/to/repo
just reindex my-repo
```

### **Global Installation Workflow**

Once installed globally via `pip install pb-dolphin`:

```bash
# From any directory
dolphin init

# Add multiple repositories
dolphin kb add-repo frontend ~/projects/frontend
dolphin kb add-repo backend ~/projects/backend
dolphin kb add-repo mobile ~/projects/mobile-app

# Index all repositories
dolphin kb index frontend
dolphin kb index backend
dolphin kb index mobile

# Start API server (available to all repos)
dolphin serve
```

### Configuration

Control indexing behavior with repository-specific config:

```bash
# Create .dolphin/config.toml in your repository
cat > /path/to/repo/.dolphin/config.toml <<EOF
[embedding]
default_embed_model = "large"  # or "small"

[chunking]
max_chunk_tokens = 512
overlap_tokens = 64

[indexing]
ignore_patterns = [
  "*.min.js",
  "node_modules/**",
  "dist/**"
]
EOF
```

---

## Using Justfile Commands

The Justfile provides convenient shortcuts for common workflows.

### Setup

```bash
just venv            # Create venv and install Python deps
just bun-install     # Install Bun deps for mcp-bridge
```

### Services

```bash
just api             # Start REST API server
just mcp             # Start MCP bridge
```

### Ingestion

```bash
just init                              # Initialize knowledge store
just add-repo NAME [path="/path"]      # Register repository
just index NAME                        # Incremental index
just reindex NAME                      # Full reindex (force)
just reset NAME [path="/path"]         # init + add + reindex
```

### Search & Tools

```bash
just repos                             # List indexed repos
just info                              # Vector store info
just health                            # API health check
just search "query"                    # Search via CLI
just chunk ID                          # Fetch chunk by ID
just lines REPO PATH START END         # Fetch file lines
just curl-search "query"               # Direct REST search (JSON)
```

### Logs

```bash
just tail-mcp        # Tail MCP bridge logs
```

### Clean (Dangerous)

```bash
just store-clean     # Delete ~/.dolphin/knowledge_store (with 5s warning)
```

---

## CLI Reference

### Unified Dolphin CLI (Recommended)

```bash
# Core Commands
dolphin init                      # Initialize knowledge store
dolphin serve                     # Start API server
dolphin config --show             # Show configuration

# Knowledge Base Management
dolphin kb add-repo <name> <path> [--default-embed-model small|large]
dolphin kb index <name>           # Incremental index
dolphin kb index <name> --full --force  # Full reindex
dolphin kb status                 # Show all repositories
dolphin kb status <name>          # Show specific repo
dolphin kb prune-ignored <name>   # Remove ignored files
dolphin kb list-files <name>      # List indexed files

# Persona Management
dolphin personas preview --list   # List available personas
dolphin personas generate --kilocode  # Generate Kilocode config
dolphin personas generate --continue  # Generate Continue config
```

### Legacy KB CLI

```bash
# Also available as standalone commands
kb init                           # Initialize knowledge store
kb add-repo <name> <path>         # Add repository
kb index <name>                   # Index repository
kb status [name]                  # Show status
```

### Direct API Server

```bash
# Start API server directly
kb-api

# Or with custom host/port
kb-api --host 0.0.0.0 --port 8000
```

### Search via REST API

```bash
# Direct curl commands (API must be running)
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication function", "top_k": 5}' \
  | jq '.hits[] | {repo, path, score}'

# List repos
curl http://127.0.0.1:7777/repos | jq '.repos[]'

# Fetch chunk
curl http://127.0.0.1:7777/chunks/<chunk-id> | jq '.'

# Fetch file lines
curl "http://127.0.0.1:7777/file?repo=my-api&path=src/auth.py&start=1&end=50"
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenAI API key for embeddings |
| `DOLPHIN_API_URL` | `http://127.0.0.1:7777` | API endpoint (for MCP) |
| `LOG_LEVEL` | `info` | Logging verbosity |

---

## REST API Reference

Start the API server:
```bash
# Global installation
dolphin serve

# Development
uv run dolphin serve

# Or via direct command
kb-api

# Or via Justfile
just api
```

The API runs on `http://127.0.0.1:7777`

### Endpoints

#### GET /health

Health check endpoint.

```bash
# Shallow check
curl http://127.0.0.1:7777/health

# Deep check (validates LanceDB and embeddings)
curl "http://127.0.0.1:7777/health?check=deep"
```

**Response:**
```json
{
  "status": "ok"
}
```

#### GET /repos

List all indexed repositories.

```bash
curl http://127.0.0.1:7777/repos
```

**Response:**
```json
{
  "repos": [
    {
      "name": "my-api",
      "path": "/Users/me/projects/my-api",
      "default_embed_model": "small",
      "files": 142,
      "chunks": 1234
    }
  ]
}
```

#### POST /search

Semantic search with hybrid BM25 + Vector search and optional cross-encoder reranking.

**Request:**
```bash
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "JWT token validation",
    "repos": ["my-api"],
    "path_prefix": ["src/"],
    "top_k": 5,
    "embed_model": "small",
    "score_cutoff": 0.15,
    "max_snippet_tokens": 240,
    "mmr_enabled": false
  }'
```

**Request Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | Search query |
| `repos` | string[] | No | (all) | Filter by repositories |
| `path_prefix` | string[] | No | (all) | Filter by path prefix |
| `top_k` | integer | No | 8 | Number of results |
| `embed_model` | string | No | "small" | Embedding model ("small" or "large") |
| `score_cutoff` | float | No | 0.15 | Minimum similarity score |
| `max_snippet_tokens` | integer | No | 240 | Max tokens per snippet |

**Response:**
```json
{
  "hits": [
    {
      "chunk_id": "abc123...",
      "repo": "my-api",
      "path": "src/auth/jwt.py",
      "start_line": 45,
      "end_line": 89,
      "language": "python",
      "symbol_kind": "function",
      "symbol_name": "validate_token",
      "symbol_path": "auth.jwt.validate_token",
      "score": 0.87,
      "commit": "abc123",
      "branch": "main"
    }
  ],
  "meta": {
    "top_k": 5,
    "model": "small",
    "latency_ms": 125,
    "max_snippet_tokens": 240
  }
}
```

#### GET /chunks/{id}

Fetch a specific chunk by ID.

```bash
curl http://127.0.0.1:7777/chunks/abc123def456
```

**Response:**
```json
{
  "chunk_id": "abc123def456",
  "repo": "my-api",
  "path": "src/auth/jwt.py",
  "content": "def validate_token(token: str) -> bool:\n    ...",
  "start_line": 45,
  "end_line": 89,
  "language": "python",
  "symbol_kind": "function",
  "symbol_name": "validate_token"
}
```

#### GET /file

Fetch file content by line range.

```bash
curl "http://127.0.0.1:7777/file?repo=my-api&path=src/auth/jwt.py&start=1&end=50"
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | string | Yes | Repository name |
| `path` | string | Yes | File path |
| `start` | integer | Yes | Start line (1-indexed) |
| `end` | integer | Yes | End line (inclusive) |

**Response:**
```json
{
  "repo": "my-api",
  "path": "src/auth/jwt.py",
  "start_line": 1,
  "end_line": 50,
  "content": "import jwt\nimport datetime\n...",
  "language": "python"
}
```

---

## MCP Integration

Dolphin provides Model Context Protocol (MCP) integration for Claude Desktop, Kilocode, and other MCP-compatible clients.

### Claude Desktop Setup

#### 1. Locate Your Claude Desktop Config

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

#### 2. Add MCP Server Configuration

Edit the config file:

```json
{
  "mcpServers": {
    "dolphin-kb": {
      "command": "bun",
      "args": [
        "run",
        "/absolute/path/to/dolphin/mcp-bridge/src/index.ts"
      ],
      "env": {
        "DOLPHIN_API_URL": "http://127.0.0.1:7777",
        "LOG_LEVEL": "info"
      }
    }
  }
}
## Advanced Features

Dolphin includes state-of-the-art search optimizations from the completed roadmap implementation.

### **Hybrid Search (BM25 + Vector)**

Combines lexical and semantic search for 40% better precision on identifier queries.

**How it works:**
- **BM25**: Exact term matching for identifiers like "UserController"
- **Vector Search**: Semantic matching for concepts like "authentication flow"
- **Reciprocal Rank Fusion**: Combines both rankings optimally

**Enable in config:**
```yaml
retrieval:
  hybrid_search:
    enabled: true
    fusion_method: "rrf"
    fusion_k: 60
```

**Example:**
```bash
# Query for specific class name
curl -X POST http://127.0.0.1:7777/search \
  -d '{"query": "UserController", "top_k": 5}'
# Returns: 80% precision (vs 40% vector-only)
```

### **ANN Parameter Tuning**

Optimized vector search for 40% faster queries.

**Presets:**
- **Speed**: 2x faster, 95% recall (nprobes=10, refine_factor=5)
- **Accuracy**: 99% recall, same speed (nprobes=30, refine_factor=20)
- **Adaptive**: Auto-tuned based on query type and dataset size

**Enable in config:**
```yaml
retrieval:
  ann:
    strategy: "adaptive"
    metric: "cosine"
```

**Expected performance:**
- Latency: ~30ms p50 (vs ~50ms default)
- Recall: ≥95% maintained
- Speedup: 40% reduction in search time

### **Cross-Encoder Reranking**

Improves result ranking quality by 20-30% MRR.

**How it works:**
- Fetches top 20-50 candidates from initial search
- Reranks using fine-grained relevance model
- Returns top 5-10 optimally ordered results

**Enable in config:**
```yaml
retrieval:
  reranking:
    enabled: true
    model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: 32
    score_threshold: 0.3
```

**Performance:**
- MRR improvement: +20-30% (0.45 → 0.65-0.75)
- Latency cost: +20-50ms per query
- Works best with 20-50 initial candidates

### **Performance Benchmarking**

Systematic measurement and regression detection.

**Run benchmarks:**
```bash
# Run ANN parameter benchmarks
python scripts/benchmark_ann.py --iterations 100

# Check version
just version
# Output: Current version: 0.1.7

# Deploy with dynamic version
just deploy-prod
```

**Metrics tracked:**
- Latency (p50, p95, p99)
- Quality (Precision@K, Recall@K, MRR)
- Regression detection with statistical significance

---

```

**Important**: Replace `/absolute/path/to/dolphin` with your actual path.

#### 3. Start the REST API

The MCP bridge requires the REST API to be running:

```bash
# Start API server
dolphin serve

# Or with Justfile (development)
just api
```

#### 4. Restart Claude Desktop

After updating the config and starting the API, restart Claude Desktop. You should see a 🔌 icon indicating MCP is connected.

### Available MCP Tools

Once configured, Claude has access to these tools:

#### search_knowledge

Search your codebase semantically.

```
Use search_knowledge to find authentication functions in the api-server repo
```

#### fetch_chunk

Get detailed chunk content by ID.

```
Use fetch_chunk to show me chunk ID abc123
```

#### fetch_lines

Get specific file lines.

```
Show me lines 100-150 from src/main.py in my-repo
```

#### get_vector_store_info

Check indexed repositories and stats.

```
What repositories are indexed in the knowledge base?
```

#### get_metadata

Get chunk metadata without full content.

```
Get metadata for chunk abc123
```

#### open_in_editor

Generate VS Code URI for opening files.

```
Open src/main.py at line 100 in VS Code
```

### MCP Inspector (Development)

For testing and debugging MCP tools:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Terminal 1: Start REST API
dolphin serve

# Terminal 2: Start MCP Inspector
mcp-inspector bun run /path/to/dolphin/mcp-bridge/src/index.ts

# Open browser to http://localhost:5173
```

The inspector provides a GUI to test all MCP tools with custom parameters.

---

## Kilocode Integration

Dolphin integrates seamlessly with Kilocode for AI-powered code search through MCP.

### Setup for Kilocode

#### 1. Start Dolphin API Server

```bash
# Start in background
dolphin serve &

# Verify API is running
curl http://127.0.0.1:7777/health
```

#### 2. Add Repositories to Index

```bash
# Add your projects
dolphin kb add-repo my-app ~/projects/my-app
dolphin kb index my-app

# Add multiple repositories
dolphin kb add-repo frontend ~/projects/frontend
dolphin kb add-repo backend ~/projects/backend
dolphin kb index frontend
dolphin kb index backend
```

#### 3. Configure Kilocode MCP

Use the provided `kilocode-mcp-config.json` file or manually configure:

**Configuration:**
```json
{
  "command": "bun",
  "args": [
    "run",
    "/absolute/path/to/dolphin/mcp-bridge/src/index.ts"
  ],
  "env": {
    "DOLPHIN_API_URL": "http://127.0.0.1:7777"
  }
}
```

**Important**: Update `/absolute/path/to/dolphin` with your actual Dolphin installation path.

#### 4. Available in Kilocode

Once configured, use these tools in Kilocode:

- **search_knowledge**: "Find authentication functions in my-app"
- **fetch_chunk**: "Show me chunk abc123"
- **fetch_lines**: "Get lines 100-150 from src/main.py in backend"
- **get_vector_store_info**: "What repositories are indexed?"
- **open_in_editor**: "Open src/auth.py at line 45"

### Example Workflow

```
You: "Find JWT token validation in my backend code"


## Deploying to PyPI

For maintainers deploying new versions of Dolphin:

### **Version Management**

```bash
# 1. Update version in pyproject.toml
# Change: version = "0.1.7" → version = "0.1.8"

# 2. Check current version
just version
# Output: Current version: 0.1.8

# 3. Build packages
just build
# Creates: dist/pb_dolphin-0.1.8-py3-none-any.whl
#          dist/pb_dolphin-0.1.8.tar.gz

# 4. Deploy to Test PyPI (optional)
just deploy-test
# Uploads to: test.pypi.org

# 5. Deploy to Production PyPI
just deploy-prod
# Uploads to: pypi.org
```

### **Automated Version Detection**

The Justfile now automatically detects the version from `pyproject.toml` - no manual updates needed:

```bash
# Before: Had to manually edit Justfile with version
# just deploy-prod (would upload 0.1.6 hardcoded)

# After: Automatically uses current version
just deploy-prod
# Output: Deploying version: 0.1.8
# Uploads: dist/pb_dolphin-0.1.8*
```

### **Installation After Deployment**

Users can install globally:
```bash
pip install pb-dolphin
# Or with uv
uv tool install pb-dolphin

# Verify
dolphin --help
```

---

Kilocode: *uses search_knowledge with query: "JWT token validation"*

Found 3 relevant code sections:
1. backend/src/auth/jwt.py (lines 45-89) - Score: 0.87
   Function: validate_token(token: str) -> bool
   
2. backend/src/middleware/auth.py (lines 12-34) - Score: 0.76
   Class: JWTAuthMiddleware
   
3. backend/tests/test_auth.py (lines 67-102) - Score: 0.71
   Test: test_jwt_validation()

You: "Show me the validate_token function"

Kilocode: *uses fetch_lines to retrieve code*

Here's the validate_token implementation from backend/src/auth/jwt.py...
```

See [DOLPHIN_KILOCODE_SETUP.md](../DOLPHIN_KILOCODE_SETUP.md) for detailed integration guide.

---

## Configuration

### Global Configuration

Create `~/.dolphin/knowledge_store/config.toml`:

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

### Per-Repository Configuration

Create `.dolphin/config.toml` in your repository:

```toml
[embedding]
default_embed_model = "large"  # Override for this repo

[chunking]
max_chunk_tokens = 512        # Max tokens per chunk
overlap_tokens = 64           # Overlap between chunks

[indexing]
ignore_patterns = [
  "*.min.js",
  "node_modules/**",
  "dist/**",
  ".venv/**"
]
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenAI API key for embeddings |
| `PB_KB_STORE_ROOT` | `~/.dolphin/knowledge_store` | Storage directory |
| `PB_KB_EMBEDDING_PROVIDER` | `openai` | Embedding provider |
| `PB_KB_EMBEDDING_BATCH_SIZE` | `100` | Batch size for embeddings |
| `KB_TOP_K` | `5` | Default number of search results (CLI) |
| `KB_REPOS` | (all) | Comma-separated repo filter (CLI) |

---

## Troubleshooting

### API Not Running

```bash
# Check if API is up
curl http://127.0.0.1:7777/health

# If not, start it
dolphin serve
# Or: kb-api
# Or: just api

# Check for port conflicts
lsof -i :7777
```

### No Search Results

```bash
# Check if repositories are indexed
dolphin kb status

# Re-index repository
dolphin kb index my-repo --full --force

# Try with lower score cutoff
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "score_cutoff": 0.0}'
```

### MCP Not Connecting

```bash
# 1. Check if API server is running
curl http://127.0.0.1:7777/health

# 2. Check MCP bridge logs
tail -f mcp-bridge/logs/mcp.log

# 3. Check Claude Desktop logs (macOS)
tail -f ~/Library/Logs/Claude/mcp*.log

# 4. Verify Bun is installed
bun --version

# 5. Test MCP server startup
cd /path/to/dolphin/mcp-bridge
bun run src/index.ts
# Should start without errors
```

### Dolphin CLI Import Error

```bash
# If you get ImportError when running dolphin command:
# Error: ImportError: cannot import name 'main' from 'kb.api.server'

# Solution: Use the fixed version
pip install --upgrade pb-dolphin

# Or in development:
cd /path/to/dolphin
uv sync --group test
uv run dolphin init
```

### OpenAI API Errors

```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Switch to stub provider for testing
# Edit ~/.dolphin/knowledge_store/config.toml:
# [embedding]
# provider = "stub"
```

### kb-search: Command Not Found

```bash
# Add bin directory to PATH
export PATH="/path/to/dolphin/bin:$PATH"

# Or create symlink
ln -s /path/to/dolphin/bin/kb-search /usr/local/bin/kb-search
```

### Bun Not Installed

```bash
# Install Bun
curl -fsSL https://bun.sh/install | bash

# Or use curl-* commands that don't require Bun
kb-search curl-search "query"
kb-search curl-repos
```

### Index Takes Too Long / Costs Too Much

```bash
# Use smaller embedding model
kb add-repo my-repo /path --default-embed-model small

# Or use stub provider for testing (no OpenAI calls)
# Edit config.toml: provider = "stub"

# Check session costs
kb status my-repo
```

---

## Example Workflows

### Find and Read Code

```bash
# 1. Search for relevant code
kb-search search "JWT token validation"

# 2. From results, note the chunk ID or file location

# 3. Fetch the chunk
kb-search chunk <chunk-id-from-results>

# Or fetch the file directly
kb-search lines my-repo src/auth/jwt.py 45 89
```

### Explore a Repository

```bash
# 1. List all repositories
kb-search repos

# 2. Search within a specific repo
KB_REPOS=my-repo kb-search search "main function"

# 3. Get more context
kb-search lines my-repo src/main.py 1 100
```

### Check System Status

```bash
# Check API health
kb-search health

# Get store statistics
kb-search info

# See what's indexed
kb-search repos
```

### Use with Claude Desktop

Once MCP is configured:

```
You: "What authentication methods are implemented in my-api?"

Claude: Let me search your codebase for authentication implementations.
[Uses search_knowledge tool]

I found 5 authentication-related code sections:
1. JWT token validation in src/auth/jwt.py (lines 45-89)
2. OAuth2 flow in src/auth/oauth.py (lines 12-67)
...

You: "Show me the JWT validation code"

Claude: [Uses fetch_lines tool to retrieve src/auth/jwt.py lines 45-89]

Here's the JWT validation implementation:
[Shows code]
```

---

## Performance Tips

1. **Use the right embedding model**:
   - `small` (1536d): Faster, cheaper, good for most use cases
   - `large` (3072d): More accurate, use for critical repos

2. **Configure chunk sizes appropriately**:
   - Smaller chunks (256 tokens): Better precision, more chunks
   - Larger chunks (512 tokens): Better context, fewer chunks

3. **Filter searches by repo/path**:
   ```bash
   KB_REPOS=api-server kb-search search "auth"
   # Instead of searching all repos
   ```

4. **Use incremental indexing**:
   ```bash
   kb index my-repo  # Only indexes changed files
   # Instead of: kb index my-repo --full --force
   ```

5. **Monitor costs**:
   ```bash
   kb status my-repo  # Shows embedding costs
   ```

---

## Next Steps

- Explore the [Architecture documentation](ARCHITECTURE.md) to understand how Dolphin works
- Check the main [README](../README.md) for project overview
- Join development by reading [DEVELOPMENT.md](DEVELOPMENT.md) (if available)

---

**Need Help?** Open an issue at https://github.com/plasticbeachllc/dolphin/issues
