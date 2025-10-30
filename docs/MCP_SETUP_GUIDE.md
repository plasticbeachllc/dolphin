# MCP Server Setup Guide

This guide shows you how to configure the Plastic Beach Knowledge Store MCP server for different environments.

## Prerequisites

1. **Install dependencies**:
   ```bash
   cd /Users/tdc/worktable/dolphin

   # Python dependencies (REST API)
   pip install -e .

   # TypeScript dependencies (MCP Bridge)
   cd mcp-bridge
   bun install
   ```

2. **Index at least one repository**:
   ```bash
   kb-index /path/to/your/repo --name my-repo
   ```

3. **Optional: Set up OpenAI API key** (for production embeddings):
   ```bash
   export OPENAI_API_KEY=sk-...
   ```

## Option 1: Claude Desktop (Recommended)

Claude Desktop has native MCP support and is the easiest way to use the MCP server.

### Configuration

1. **Locate your Claude Desktop config file**:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Add the MCP server configuration**:

   ```json
   {
     "mcpServers": {
       "pb-kb": {
         "command": "bun",
         "args": [
           "run",
           "/Users/tdc/worktable/dolphin/mcp-bridge/src/index.ts"
         ],
         "env": {
           "OPENAI_API_KEY": "sk-..."
         }
       }
     }
   }
   ```

   **Notes**:
   - Replace the path with your actual dolphin directory path
   - The `env.OPENAI_API_KEY` is optional (falls back to stub embeddings if not provided)
   - You can add other environment variables as needed

3. **Start the REST API server** (in a separate terminal):
   ```bash
   cd /Users/tdc/worktable/dolphin
   source .venv/bin/activate
   kb-api
   ```

4. **Restart Claude Desktop** to load the new configuration

5. **Verify it's working**:
   - Open Claude Desktop
   - Look for a 🔌 icon or "Tools" indicator showing MCP is connected
   - Try asking: "Use search_knowledge to find function definitions in my codebase"

### Available Tools in Claude Desktop

Once configured, Claude will have access to these tools:

- **search_knowledge**: Search your codebase semantically
  ```
  "Search for authentication functions in the api-server repo"
  ```

- **fetch_chunk**: Get detailed chunk content
  ```
  "Use fetch_chunk to show me chunk ID abc123"
  ```

- **fetch_lines**: Get specific file lines
  ```
  "Show me lines 100-150 from src/main.py in my-repo"
  ```

- **get_vector_store_info**: Check indexed repositories
  ```
  "What repositories are indexed in the knowledge base?"
  ```

## Option 2: VS Code (via Claude Code Extension)

The Claude Code extension for VS Code doesn't currently support MCP directly, but you can use it via the REST API.

### REST API Direct Usage

1. **Start the REST API server**:
   ```bash
   cd /Users/tdc/worktable/dolphin
   source .venv/bin/activate
   kb-api
   ```

2. **Make requests from your code or terminal**:

   ```bash
   # Search for code
   curl -X POST http://127.0.0.1:7777/v1/search \
     -H "Content-Type: application/json" \
     -d '{
       "query": "authentication function",
       "top_k": 5,
       "embed_model": "small"
     }'

   # List repositories
   curl http://127.0.0.1:7777/v1/repos

   # Get chunk by ID
   curl http://127.0.0.1:7777/v1/chunks/abc123

   # Get file lines
   curl "http://127.0.0.1:7777/v1/file?repo=my-repo&path=src/main.py&start=1&end=50"

   # Health check
   curl http://127.0.0.1:7777/v1/health
   ```

### Creating a VS Code Task

You can create a VS Code task to start the API server automatically:

1. **Create `.vscode/tasks.json` in your project**:

   ```json
   {
     "version": "2.0.0",
     "tasks": [
       {
         "label": "Start KB API",
         "type": "shell",
         "command": "source .venv/bin/activate && kb-api",
         "isBackground": true,
         "problemMatcher": [],
         "presentation": {
           "reveal": "always",
           "panel": "dedicated"
         }
       }
     ]
   }
   ```

2. **Run the task**: `Cmd+Shift+P` → "Tasks: Run Task" → "Start KB API"

## Option 3: Command Line (MCP Inspector)

For testing and development, you can use the MCP Inspector to interact with the MCP server directly.

### Setup

1. **Install the MCP Inspector**:
   ```bash
   npm install -g @modelcontextprotocol/inspector
   ```

2. **Start the REST API server** (in one terminal):
   ```bash
   cd /Users/tdc/worktable/dolphin
   source .venv/bin/activate
   kb-api
   ```

3. **Start the MCP Inspector** (in another terminal):
   ```bash
   mcp-inspector bun run /Users/tdc/worktable/dolphin/mcp-bridge/src/index.ts
   ```

4. **Open the inspector UI**:
   - The inspector will print a URL like `http://localhost:5173`
   - Open it in your browser
   - You'll see a web UI where you can test all MCP tools

### Using the Inspector

The inspector provides a GUI to:
- List all available tools
- Test tool calls with custom parameters
- View request/response logs
- Debug MCP protocol messages

## Option 4: Direct CLI Tool

A command-line tool is provided for direct access to the knowledge base.

### Setup

Add the bin directory to your PATH (add to your ~/.bashrc or ~/.zshrc):

```bash
export PATH="/Users/tdc/worktable/dolphin/bin:$PATH"
```

Or create a symlink:

```bash
ln -s /Users/tdc/worktable/dolphin/bin/kb-search /usr/local/bin/kb-search
```

### Usage

Use `kb-search` for fast MCP-friendly queries:

```bash
# Search for code
kb-search search "authentication function"
KB_TOP_K=10 kb-search search "error handling"

# List repositories
kb-search repos

# Fetch chunk by ID
kb-search chunk abc123def456

# Fetch file lines
kb-search lines my-repo src/main.py 1 50

# Get vector store info
kb-search info

# Check API health
kb-search health

# Show help
kb-search help
```

### Advanced: Direct REST API Calls (No Bun Required)

For environments without Bun, use the `curl-*` commands:

```bash
# Search (returns JSON)
kb-search curl-search "function" | jq '.hits[] | {repo, path, score}'

# List repos
kb-search curl-repos | jq '.repos[] | .name'

# Fetch chunk
kb-search curl-chunk abc123 | jq '.content'

# Fetch file
kb-search curl-file my-repo src/main.py 1 50 | jq '.content'
```

### TypeScript CLI (Advanced)

For direct TypeScript access:

```bash
cd /Users/tdc/worktable/dolphin/mcp-bridge

# Search
bun run kb-cli.ts search "query text"

# List repos
bun run kb-cli.ts repos

# Fetch chunk
bun run kb-cli.ts chunk abc123

# Fetch lines
bun run kb-cli.ts lines my-repo src/main.py 1 50

# Vector store info
bun run kb-cli.ts info
```

## Troubleshooting

### MCP Server Not Connecting

1. **Check if kb-api is running**:
   ```bash
   curl http://127.0.0.1:7777/v1/health
   ```
   Should return: `{"status":"ok"}`

2. **Check MCP Bridge logs**:
   ```bash
   tail -f /Users/tdc/worktable/dolphin/mcp-bridge/logs/mcp.log
   ```

3. **Verify Bun is installed**:
   ```bash
   bun --version
   ```

4. **Check Claude Desktop logs** (macOS):
   ```bash
   tail -f ~/Library/Logs/Claude/mcp*.log
   ```

### No Repositories Found

1. **Index a repository**:
   ```bash
   kb-index /path/to/repo --name my-repo
   ```

2. **Verify indexing worked**:
   ```bash
   curl http://127.0.0.1:7777/v1/repos
   ```

### Search Returns No Results

1. **Check if embeddings are working**:
   ```bash
   # Deep health check
   curl "http://127.0.0.1:7777/v1/health?check=deep"
   ```

2. **Try lowering score_cutoff**:
   ```bash
   curl -X POST http://127.0.0.1:7777/v1/search \
     -H "Content-Type: application/json" \
     -d '{
       "query": "function",
       "score_cutoff": 0.0,
       "top_k": 10
     }'
   ```

3. **Check if OpenAI API key is set** (if using OpenAI embeddings):
   ```bash
   echo $OPENAI_API_KEY
   ```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No | (stub) | OpenAI API key for embeddings |
| `PB_KB_STORE_ROOT` | No | `~/.cache/pb-kb` | Storage directory |
| `PB_KB_EMBEDDING_PROVIDER` | No | `openai` | Embedding provider (`openai` or `stub`) |
| `PB_KB_EMBEDDING_BATCH_SIZE` | No | `100` | Batch size for embeddings |

## Configuration File

You can create a config file at `~/.config/pb-kb/config.json`:

```json
{
  "store_root": "~/.cache/pb-kb",
  "embedding_provider": "openai",
  "embedding_batch_size": 100,
  "openai_api_key_env": "OPENAI_API_KEY"
}
```

## Next Steps

1. **Index your most important repositories**:
   ```bash
   kb-index ~/projects/my-api --name my-api
   kb-index ~/projects/my-frontend --name my-frontend
   ```

2. **Start using Claude with your codebase**:
   - Open Claude Desktop
   - Ask questions about your code
   - Claude will automatically use the MCP tools when appropriate

3. **Monitor usage**:
   ```bash
   # Watch API logs
   tail -f ~/.cache/pb-kb/logs/api.log

   # Watch MCP logs
   tail -f mcp-bridge/logs/mcp.log
   ```

## Example Claude Desktop Conversation

```
You: "What authentication methods are implemented in my-api?"

Claude: Let me search your codebase for authentication implementations.
[Uses search_knowledge tool]

I found 5 authentication-related code sections:

1. JWT token validation in src/auth/jwt.py (lines 45-89)
2. OAuth2 flow in src/auth/oauth.py (lines 12-67)
3. API key validation in src/auth/api_keys.py (lines 23-45)
...

Would you like me to show you the implementation of any of these?

You: "Yes, show me the JWT validation code"

Claude: [Uses fetch_lines tool to retrieve src/auth/jwt.py lines 45-89]

Here's the JWT validation implementation:
[Shows code with syntax highlighting]
...
```

## Additional Resources

- **MCP Specification**: https://modelcontextprotocol.io
- **Implementation Details**: [MCP_IMPLEMENTATION_COMPLETE.md](MCP_IMPLEMENTATION_COMPLETE.md)
- **REST API Guide**: [SEARCH_API_GUIDE.md](SEARCH_API_GUIDE.md)
- **Architecture**: [mcp_indexing_architecture_detailed.md](mcp_indexing_architecture_detailed.md)

---

**Need help?** Check the logs or open an issue at the project repository.
