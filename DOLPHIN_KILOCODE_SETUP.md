# Dolphin + Kilocode MCP Integration Guide

## 🐬 Overview

This guide explains how to integrate Dolphin's semantic code search capabilities with Kilocode using the Model Context Protocol (MCP).

**What you get:**
- AI-powered semantic code search
- Hybrid search (BM25 + Vector) for 40% better precision
- Cross-encoder reranking for improved relevance
- Full repository indexing and retrieval

---

## 📋 Prerequisites

### 1. **Install Bun**
```bash
curl -fsSL https://bun.sh/install | bash
# Restart terminal or source your shell config
bun --version
```

### 2. **Start Dolphin API Server**
```bash
cd /path/to/dolphin
just api
```

The API server should be running on `http://127.0.0.1:7777`

---

## 🚀 Setup Steps

### **Step 1: Index Your Repositories**

```bash
# From the dolphin directory
cd /path/to/dolphin

# Add a repository to the knowledge base
just add-repo my-project /path/to/my-project

# Index the repository
just reindex my-project

# Check status
just repos
```

### **Step 2: Configure Kilocode MCP**

**Option A: Use the prepared config**
1. Copy `kilocode-mcp-config.json` to your Kilocode MCP config directory
2. Update the path in the config from `/Users/tdc/worktable/dolphin` to your actual dolphin directory
3. Configure Kilocode to use this MCP server

**Option B: Manual configuration**
Add this to your Kilocode MCP configuration:

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
```

### **Step 3: Verify Setup**

1. **Check API Health:**
   ```bash
   curl http://127.0.0.1:7777/health
   # Should return: {"status": "ok"}
   ```

2. **Check MCP Server:**
   ```bash
   cd /path/to/dolphin/mcp-bridge
   bun run src/index.ts
   # Should start without errors (then exit with Ctrl+C)
   ```

3. **Test Search:**
   ```bash
   just search "authentication function"
   ```

---

## 🛠 Available MCP Tools

Once configured, Kilocode will have access to these tools:

### **search_knowledge**
Semantic search across your codebase using AI embeddings.
```
Query: "JWT token validation"
Repos: ["my-api"] (optional)
Top_k: 8 (optional)
```

### **fetch_chunk**
Get detailed content of a specific code chunk by ID.
```
chunk_id: "abc123def456"
```

### **fetch_lines**
Get specific file lines by repository and path.
```
repo: "my-project"
path: "src/auth/jwt.py"
start: 45
end: 89
```

### **get_vector_store_info**
Get statistics about indexed repositories and the knowledge base.

### **open_in_editor**
Generate VS Code URIs for opening files directly.
```
repo: "my-project"
path: "src/main.py"
start_line: 100
```

---

## 🔧 Configuration Options

### **Environment Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `DOLPHIN_API_URL` | `http://127.0.0.1:7777` | Dolphin API endpoint |
| `LOG_LEVEL` | `info` | Logging verbosity |

### **Repository Configuration**

Create `.dolphin/config.toml` in your repository:

```toml
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
```

---

## 🚨 Troubleshooting

### **API Server Not Running**
```bash
# Start the API server
cd /path/to/dolphin
just api

# Check if port 7777 is in use
lsof -i :7777

# Check API health
curl http://127.0.0.1:7777/health
```

### **MCP Server Connection Failed**
```bash
# Check MCP server startup
cd /path/to/dolphin/mcp-bridge
bun run src/index.ts

# Check logs
tail -f mcp-bridge/logs/mcp.log

# Verify Bun installation
bun --version
```

### **No Search Results**
```bash
# Check if repositories are indexed
just repos

# Re-index repository
just reindex my-project

# Try with lower score cutoff
just search "test" --score-cutoff 0.0
```

### **High Latency or Costs**
```bash
# Use smaller embedding model
just add-repo my-repo /path --default-embed-model small

# Check current costs
just status my-repo
```

---

## 📊 Performance Features

When you use Dolphin + Kilocode, you get access to all Dolphin roadmap features:

### **ANN Parameter Tuning** - 40% faster searches
- Adaptive parameter selection based on query type
- Optimal speed/accuracy tradeoffs

### **Hybrid Search** - +40% precision on identifiers  
- BM25 for exact term matching
- Vector search for semantic understanding
- Reciprocal Rank Fusion for optimal results

### **Cross-Encoder Reranking** - +30% MRR improvement
- Fine-grained relevance scoring
- Better first-result quality

### **Performance Benchmarking**
- Systematic measurement and regression detection
- CI integration for quality tracking

---

## 🎯 Usage Examples

### **In Kilocode Chat:**
```
User: "Find authentication functions in my API project"

Kilocode: *uses search_knowledge tool*
Found 5 authentication-related sections:

1. JWT token validation in src/auth/jwt.py (lines 45-89)
   - Function: validate_token(token: str) -> bool
   - Score: 0.87

2. OAuth2 flow implementation in src/auth/oauth.py (lines 12-67)
   - Function: exchange_code_for_token()
   - Score: 0.82
```

### **Advanced Search:**
```
User: "Show me how to handle errors in the user registration flow"

Kilocode: *searches with query: "user registration error handling"*
*retrieves relevant code sections with fetch_chunk tool*
```

### **Direct File Access:**
```
User: "Open the main API handler at line 100"

Kilocode: *uses open_in_editor tool*
vscode://file/path/to/src/main.py:100
```

---

## 🔄 Continuous Integration

### **Automated Indexing**
```bash
# Set up git hooks for auto-indexing
echo 'just reindex my-repo' > .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

### **Performance Monitoring**
```bash
# Run benchmarks
python scripts/benchmark_ann.py

# Check system status  
just info
```

---

## 📈 Next Steps

1. **Index multiple repositories** for comprehensive codebase search
2. **Configure repository-specific settings** for optimal chunking
3. **Set up monitoring** for search performance and costs
4. **Enable advanced features** (cross-encoder reranking, caching)
5. **Integrate with CI/CD** for automated indexing

---

## 🆘 Support

- **Documentation**: `docs/GUIDE.md`
- **Architecture**: `docs/ARCHITECTURE.md`  
- **Issues**: https://github.com/plasticbeachllc/dolphin/issues

---

**Ready to supercharge your code search with AI!** 🚀