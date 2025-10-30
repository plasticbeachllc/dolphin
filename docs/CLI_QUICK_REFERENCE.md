# KB CLI Quick Reference

## Setup

```bash
# Add to PATH
export PATH="/Users/tdc/worktable/dolphin/bin:$PATH"

# Or create symlink
ln -s /Users/tdc/worktable/dolphin/bin/kb /usr/local/bin/kb
```

## Basic Commands

```bash
# Check if API is running
kb health

# List indexed repositories
kb repos

# Search for code
kb search "your search query"

# Get vector store information
kb info
```

## Search Examples

```bash
# Basic search
kb search "authentication"

# Search with more results
KB_TOP_K=10 kb search "error handling"

# Search in specific repos
KB_REPOS=api-server,frontend kb search "login"

# Search with environment variables
KB_TOP_K=20 KB_REPOS=backend kb search "database query"
```

## Fetch Content

```bash
# Fetch chunk by ID
kb chunk abc123def456

# Fetch file lines
kb lines <repo-name> <file-path> <start-line> <end-line>

# Example
kb lines my-api src/auth/jwt.py 45 89
```

## Direct REST API (curl-based, no Bun required)

```bash
# Search and parse with jq
kb curl-search "function" | jq '.hits[] | {repo, path, score}'

# List repo names only
kb curl-repos | jq '.repos[] | .name'

# Get chunk content
kb curl-chunk abc123 | jq '.content'

# Fetch file and extract content
kb curl-file my-repo src/main.py 1 50 | jq '.content'

# Raw search response
kb curl-search "authentication" | jq .
```

## Common Workflows

### Find and Read Code

```bash
# 1. Search for relevant code
kb search "JWT token validation"

# 2. From results, note the chunk ID or file location

# 3. Fetch the chunk
kb chunk <chunk-id-from-results>

# Or fetch the file directly
kb lines <repo> <path> <start> <end>
```

### Explore a Repository

```bash
# 1. List all repositories
kb repos

# 2. Search within a specific repo
KB_REPOS=my-repo kb search "main function"

# 3. Get more context
kb lines my-repo src/main.py 1 100
```

### Check System Status

```bash
# Check API health
kb health

# Get store statistics
kb info

# See what's indexed
kb repos
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KB_TOP_K` | 5 | Number of search results to return |
| `KB_REPOS` | (all) | Comma-separated list of repos to search |

## Output Formats

### High-level commands (nicely formatted)
```bash
kb search "function"
# Output:
# 🔍 Searching for: "function"
#
# Found 3 results across 2 repos.
#
# Results:
#
# 1. [my-repo] src/utils.py:10-25
#    Score: 0.892
#    Chunk ID: abc123
```

### curl commands (JSON output)
```bash
kb curl-search "function" | jq .
# Output: Full JSON response
```

## Prerequisites

Before using these commands:

1. **Start the API server**:
   ```bash
   kb-api
   ```

2. **Index at least one repository**:
   ```bash
   kb-index /path/to/repo --name my-repo
   ```

3. **Optional: Set OpenAI API key**:
   ```bash
   export OPENAI_API_KEY=sk-...
   ```

## Tips

- Use `kb help` to see all available commands
- Pipe curl commands to `jq` for better JSON formatting
- Set `KB_TOP_K` higher when you need more results
- Use `KB_REPOS` to narrow search to specific repositories
- Check `kb health` first if commands fail

## Error Messages

| Error | Solution |
|-------|----------|
| "kb-api server is not running" | Run `kb-api` in another terminal |
| "No repositories indexed" | Run `kb-index /path/to/repo --name name` |
| "bun is not installed" | Install from https://bun.sh or use curl-* commands |
| "command not found: kb" | Add bin directory to PATH or create symlink |

## Advanced Usage

### Batch Processing

```bash
# Search multiple terms
for term in "function" "class" "interface"; do
  echo "=== $term ==="
  kb search "$term"
done
```

### Custom Scripts

```bash
#!/bin/bash
# find-todos.sh - Find all TODO comments

kb search "TODO" | grep -A 2 "Results:"
```

### Integration with Other Tools

```bash
# Open found file in editor
result=$(kb search "main function" | grep -m1 "path:" | cut -d: -f2)
code $result

# Copy chunk to clipboard (macOS)
kb chunk abc123 | pbcopy

# Save search results
kb search "authentication" > auth-search.txt
```

## See Also

- [MCP Setup Guide](MCP_SETUP_GUIDE.md) - Full setup instructions
- [MCP Implementation Complete](MCP_IMPLEMENTATION_COMPLETE.md) - System overview
- [Search API Guide](SEARCH_API_GUIDE.md) - REST API documentation
