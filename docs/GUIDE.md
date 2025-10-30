# Dolphin User Guide

Complete guide for using the Dolphin AI enablement platform for semantic code search and retrieval.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Indexing Repositories](#indexing-repositories)
- [Using Justfile Commands](#using-justfile-commands)
- [CLI Reference](#cli-reference)
- [REST API Reference](#rest-api-reference)
- [MCP Integration](#mcp-integration)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Setup environment
just venv && just bun-install

# 2. Initialize knowledge base
just init

# 3. Index a repository
just add-repo my-project /path/to/my-project
just reindex my-project

# 4. Start the API server
just api &

# 5. Search your code
just search "authentication function"
```

---

## Installation

### Prerequisites

- **Python** ≥3.13 with `uv` package manager
- **Bun** (for MCP Bridge)
- **Git** (for repository scanning)
- **OpenAI API Key** (for embeddings)

### Setup Steps

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
# Edit .env and add your API keys

# Initialize the knowledge store
kb init
```

---

## Indexing Repositories

### Using the KB CLI

```bash
# Initialize knowledge base
kb init

# Add a repository
kb add-repo my-api /path/to/my-api --default-embed-model large

# Index the repository
kb index my-api

# Full re-index (force refresh)
kb index my-api --full --force

# Check status
kb status
```

### Using Justfile (Recommended)

```bash
# Complete setup in one command
just reset my-repo /path/to/repo

# Or step by step
just init
just add-repo my-repo /path/to/repo
just reindex my-repo
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

### KB CLI - Knowledge Base Management

```bash
# Initialization
kb init                           # Create store and initialize databases

# Repository Management
kb add-repo <name> <path> [--default-embed-model small|large]
kb list-repos                     # List all registered repos
kb status [name]                  # Show repo status

# Indexing
kb index <name>                   # Incremental index
kb index <name> --full --force    # Full reindex
kb prune <name>                   # Remove deleted files from index
```

### kb-search CLI - Search and Retrieval

Add to your PATH:
```bash
export PATH="$PWD/bin:$PATH"
# Or create symlink:
# ln -s $PWD/bin/kb-search /usr/local/bin/kb-search
```

#### High-Level Commands (requires Bun)

```bash
# Search
kb-search search "authentication"
KB_TOP_K=10 kb-search search "error handling"
KB_REPOS=api-server kb-search search "login"

# Repository info
kb-search repos                   # List indexed repositories
kb-search info                    # Vector store statistics

# Content retrieval
kb-search chunk <chunk-id>        # Fetch chunk by ID
kb-search lines <repo> <path> <start> <end>  # Fetch file lines

# Health
kb-search health                  # Check if kb-api is running
```

#### curl Commands (No Bun Required)

```bash
# Search (returns JSON)
kb-search curl-search "function" | jq '.hits[] | {repo, path, score}'

# List repos
kb-search curl-repos | jq '.repos[] | .name'

# Fetch chunk
kb-search curl-chunk <chunk-id> | jq '.content'

# Fetch file
kb-search curl-file <repo> <path> <start> <end> | jq '.content'
```

#### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KB_TOP_K` | 5 | Number of search results |
| `KB_REPOS` | (all) | Comma-separated repo filter |

---

## REST API Reference

Start the API server:
```bash
kb-api
# Or: just api
```

The API runs on `http://127.0.0.1:7777`

### Endpoints

#### GET /v1/health

Health check endpoint.

```bash
# Shallow check
curl http://127.0.0.1:7777/v1/health

# Deep check (validates LanceDB and embeddings)
curl "http://127.0.0.1:7777/v1/health?check=deep"
```

**Response:**
```json
{
  "status": "ok"
}
```

#### GET /v1/repos

List all indexed repositories.

```bash
curl http://127.0.0.1:7777/v1/repos
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

#### POST /v1/search

Semantic search across indexed repositories.

**Request:**
```bash
curl -X POST http://127.0.0.1:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "JWT token validation",
    "repos": ["my-api"],
    "path_prefix": ["src/"],
    "top_k": 5,
    "embed_model": "small",
    "score_cutoff": 0.15,
    "max_snippet_tokens": 240
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

#### GET /v1/chunks/{id}

Fetch a specific chunk by ID.

```bash
curl http://127.0.0.1:7777/v1/chunks/abc123def456
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

#### GET /v1/file

Fetch file content by line range.

```bash
curl "http://127.0.0.1:7777/v1/file?repo=my-api&path=src/auth/jwt.py&start=1&end=50"
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

Dolphin provides Model Context Protocol (MCP) integration for Claude Desktop and other MCP-compatible clients.

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
    "pb-kb": {
      "command": "bun",
      "args": [
        "run",
        "/absolute/path/to/dolphin/mcp-bridge/src/index.ts"
      ],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

**Important**: Replace `/absolute/path/to/dolphin` with your actual path.

#### 3. Start the REST API

The MCP bridge requires the REST API to be running:

```bash
# Terminal 1: Start API server
cd /path/to/dolphin
kb-api

# Or use Justfile
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
kb-api

# Terminal 2: Start MCP Inspector
mcp-inspector bun run /path/to/dolphin/mcp-bridge/src/index.ts

# Open browser to http://localhost:5173
```

The inspector provides a GUI to test all MCP tools with custom parameters.

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
  -H "Content-Type: application/json" \
  -d '{"query": "test", "score_cutoff": 0.0}'
```

### MCP Not Connecting

```bash
# 1. Check if kb-api is running
curl http://127.0.0.1:7777/v1/health

# 2. Check MCP bridge logs
tail -f mcp-bridge/logs/mcp.log

# 3. Check Claude Desktop logs (macOS)
tail -f ~/Library/Logs/Claude/mcp*.log

# 4. Verify Bun is installed
bun --version
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
