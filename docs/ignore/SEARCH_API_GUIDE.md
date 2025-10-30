# Search API Quick Start Guide

This guide shows you how to use the semantic search API that was just implemented.

## Prerequisites

1. **Indexed Knowledge Base**: You need to have already indexed at least one repository
   ```bash
   kb init
   kb add-repo /path/to/your/repo
   kb index
   ```

2. **OpenAI API Key** (optional but recommended for production):
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

   Without an API key, the system will use a stub provider (zero-vectors) for testing.

## Method 1: Using the CLI Command (Recommended)

This is the easiest way - the server automatically initializes the search backend on startup.

### Step 1: Configure the Embedding Provider

Edit `~/.dolphin/knowledge_store/config.toml` (create if doesn't exist):

```toml
[embedding]
# Use "openai" for real embeddings, "stub" for testing
provider = "openai"
batch_size = 100
api_key_env = "OPENAI_API_KEY"
```

### Step 2: Start the Server

```bash
kb-api
```

You should see:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:7777 (Press CTRL+C to quit)
```

The server automatically initializes the search backend on startup using your configuration.

### Step 3: Test the API

In another terminal:

```bash
# Health check
curl http://localhost:7777/v1/health

# Search
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I initialize the knowledge base?",
    "top_k": 5
  }'
```

## Method 2: Programmatic Initialization (For Scripts)

If you need to start the server from Python code:

```python
from pb_kb.api.server import main

# This will initialize the backend and start the server
main()
```

## Method 3: Custom Initialization (For Testing)

If you want full control over the backend initialization:

```python
from pathlib import Path
from pb_kb.api.search_backend import create_search_backend
from pb_kb.api.app import app, set_search_backend
import uvicorn

# Create backend with custom settings
store_root = Path.home() / ".dolphin" / "knowledge_store"
backend = create_search_backend(
    store_root,
    embedding_provider_type="openai",  # or "stub"
    api_key="sk-...",  # optional if using env var
    batch_size=50
)

# Set backend for API
set_search_backend(backend)

# Start server
uvicorn.run(app, host="127.0.0.1", port=7777)
```

## API Reference

### POST /v1/search

Search the knowledge base with semantic similarity.

**Request Body:**
```json
{
  "query": "string",              // Required: search query
  "repos": ["string"],            // Optional: filter by repositories
  "path_prefix": ["string"],      // Optional: filter by path prefix
  "top_k": 8,                     // Optional: number of results (default: 8)
  "embed_model": "small",         // Optional: "small" or "large" (default: "small")
  "score_cutoff": 0.15,           // Optional: minimum similarity score
  "max_snippet_tokens": 240       // Optional: max tokens per snippet
}
```

**Response:**
```json
{
  "hits": [
    {
      "chunk_id": "abc123...",
      "repo": "myrepo",
      "path": "src/main.py",
      "start_line": 1,
      "end_line": 10,
      "language": "python",
      "symbol_kind": "function",
      "symbol_name": "main",
      "symbol_path": "main",
      "score": 0.87,
      "commit": "abc123",
      "branch": "main"
    }
  ],
  "meta": {
    "top_k": 8,
    "model": "small",
    "latency_ms": 125,
    "max_snippet_tokens": 240
  }
}
```

## Configuration Options

### Embedding Provider Settings

In `config.toml`:

```toml
[embedding]
# Provider type
provider = "stub"           # Options: "stub" (testing) or "openai" (production)

# OpenAI settings (only used when provider = "openai")
batch_size = 100            # Number of texts to embed per API call
api_key_env = "OPENAI_API_KEY"  # Environment variable containing API key

# Model settings
[embeddings]
default_embed_model = "small"   # Default model for indexing/search
```

### Model Options

- **small**: `text-embedding-3-small` (1536 dimensions, faster, cheaper)
- **large**: `text-embedding-3-large` (3072 dimensions, slower, more accurate)

## Examples

### Example 1: Simple Search

```bash
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database connection pooling",
    "top_k": 3
  }'
```

### Example 2: Filter by Repository

```bash
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication middleware",
    "repos": ["backend-api"],
    "top_k": 5
  }'
```

### Example 3: Filter by Path Prefix

```bash
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "error handling",
    "path_prefix": ["src/", "lib/"],
    "top_k": 10
  }'
```

### Example 4: High-Quality Search with Score Cutoff

```bash
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "logging configuration",
    "score_cutoff": 0.5,
    "top_k": 10
  }'
```

### Example 5: Using Large Model

```bash
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "complex architectural patterns",
    "embed_model": "large",
    "top_k": 5
  }'
```

## Troubleshooting

### Error: "OPENAI_API_KEY not set"

**Problem**: The server tries to use OpenAI provider but can't find the API key.

**Solution**:
```bash
export OPENAI_API_KEY="sk-..."
kb-api
```

Or change to stub provider in config:
```toml
[embedding]
provider = "stub"
```

### Error: No results returned

**Possible causes**:
1. **No data indexed**: Make sure you've run `kb index` first
2. **Wrong model**: If you indexed with "small" model, search with "small" (default)
3. **Score cutoff too high**: Try removing or lowering `score_cutoff`

**Solution**:
```bash
# Check if data is indexed
kb status

# Re-index if needed
kb index --repo /path/to/repo
```

### Performance is slow

**Issue**: Search takes >1 second per query

**Solutions**:
1. Use "small" model instead of "large" (faster, cheaper)
2. Reduce `top_k` value
3. Check OpenAI API status (latency on their side)
4. Consider caching frequently-used queries

### Connection refused

**Problem**: Can't connect to http://localhost:7777

**Solution**:
```bash
# Check if server is running
curl http://localhost:7777/v1/health

# If not, start it
kb-api
```

## Python Client Example

```python
import requests

def search_knowledge(query, top_k=5):
    """Search the knowledge base."""
    response = requests.post(
        "http://localhost:7777/v1/search",
        json={
            "query": query,
            "top_k": top_k
        }
    )
    response.raise_for_status()
    return response.json()

# Use it
results = search_knowledge("How do I configure logging?")
for hit in results["hits"]:
    print(f"{hit['path']}:{hit['start_line']} - {hit['symbol_name']} (score: {hit['score']:.2f})")
```

## Integration with Other Tools

### Continue IDE Extension

Add to `.continue/config.json`:
```json
{
  "contextProviders": [
    {
      "name": "kb-search",
      "params": {
        "serverUrl": "http://localhost:7777",
        "topK": 5
      }
    }
  ]
}
```

### MCP (Model Context Protocol)

Coming in Phase 7 (M3 milestone) - will allow Claude Desktop to query your knowledge base directly.

## Performance Expectations

With OpenAI embeddings:
- **Embedding latency**: ~100-200ms per query
- **Vector search**: <10ms (LanceDB KNN)
- **Total latency**: ~120-300ms end-to-end

With stub embeddings (testing):
- **Total latency**: <50ms

## Next Steps

1. **Phase 7 (M3)**: MCP Integration - Connect to Claude Desktop
2. **Phase 8 (M4)**: Evaluation - Measure retrieval quality (P@5, R@10, MRR)
3. **Phase 9 (M5)**: Production hardening - Monitoring, auto-indexing, recovery

## Need Help?

- Check logs: Server prints errors to stdout
- Test health endpoint: `curl http://localhost:7777/v1/health`
- Run tests: `pytest tests/unit/test_search_api.py -v`
- See [docs/mcp_indexing_implementation_plan_final.md](mcp_indexing_implementation_plan_final.md) for architecture details
