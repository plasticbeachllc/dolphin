# dolphin-mcp

[![NPM Version](https://img.shields.io/npm/v/dolphin-mcp.svg)](https://www.npmjs.com/package/dolphin-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for Dolphin semantic code search. Conforms to [MCP spec](https://modelcontextprotocol.io/) and targets the `/v1` KB API endpoints.

## Quick Start

No installation needed - use `bunx`:

```bash
bunx dolphin-mcp
```

## Configuration

### Continue.dev

Add to `config.yaml`:

```yaml
mcpServers:
  - name: Dolphin-KB
    command: bunx
    args:
      - dolphin-mcp
    env:
      DOLPHIN_API_URL: "http://127.0.0.1:7777"
      # Optional: Performance optimization for parallel snippet fetching
      MAX_CONCURRENT_SNIPPET_FETCH: "8"
      SNIPPET_FETCH_TIMEOUT_MS: "2000"
      SNIPPET_FETCH_RETRY_ATTEMPTS: "1"
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dolphin-kb": {
      "command": "bunx",
      "args": ["dolphin-mcp"],
      "env": {
        "DOLPHIN_API_URL": "http://127.0.0.1:7777",
        "MAX_CONCURRENT_SNIPPET_FETCH": "8",
        "SNIPPET_FETCH_TIMEOUT_MS": "2000",
        "SNIPPET_FETCH_RETRY_ATTEMPTS": "1"
      }
    }
  }
}
```

## Environment Variables

| Variable            | Default                 | Description                              |
| ------------------- | ----------------------- | ---------------------------------------- |
| `DOLPHIN_API_URL`   | `http://127.0.0.1:7777` | Dolphin API base URL                     |
| `KB_REST_BASE_URL`  | unset                   | Alias for `DOLPHIN_API_URL` (tests/CI)   |
| `LOG_LEVEL`         | `info`                  | Logging level (debug, info, warn, error) |

### API Key Authentication

**Auto-Provisioning (Recommended):**

The MCP bridge automatically provisions a KB API key on startup. **No manual configuration is required for typical usage.**

- Running `bunx dolphin-mcp` automatically creates `~/.dolphin/kb_api_key`
- The key is a 64-character hex string with `0600` permissions (user-only)
- The key is automatically sent in the `X-API-Key` header for all KB requests

**Manual Override (Advanced):**

For CI/CD, testing, or remote deployments, you can override the auto-provisioned key:

```bash
export DOLPHIN_API_KEY="your-custom-key-here"
# OR
export DOLPHIN_KB_API_KEY="your-custom-key-here"
```

Environment variables take precedence over the file-based key.

### Parallel Snippet Fetching Configuration

These variables control the performance optimization for parallel snippet fetching in `search_knowledge`:

| Variable                       | Default | Description                        | Recommended Range |
| ------------------------------ | ------- | ---------------------------------- | ----------------- |
| `MAX_CONCURRENT_SNIPPET_FETCH` | `8`     | Maximum parallel snippet requests  | 4-12              |
| `SNIPPET_FETCH_TIMEOUT_MS`     | `2000`  | Timeout per snippet request (ms)   | 1500-3000         |
| `SNIPPET_FETCH_RETRY_ATTEMPTS` | `1`     | Retry attempts for failed requests | 0-3               |

#### Configuration Presets

**Conservative** (recommended for limited resources):

```bash
MAX_CONCURRENT_SNIPPET_FETCH=4
SNIPPET_FETCH_TIMEOUT_MS=1500
SNIPPET_FETCH_RETRY_ATTEMPTS=1
```

**Recommended** (balanced performance):

```bash
MAX_CONCURRENT_SNIPPET_FETCH=8
SNIPPET_FETCH_TIMEOUT_MS=2000
SNIPPET_FETCH_RETRY_ATTEMPTS=1
```

**Performance** (maximum throughput):

```bash
MAX_CONCURRENT_SNIPPET_FETCH=10
SNIPPET_FETCH_TIMEOUT_MS=3000
SNIPPET_FETCH_RETRY_ATTEMPTS=2
```

## Available Tools

### `search_knowledge`

Semantically query code and docs across indexed repositories and return ranked snippets with citations.

```json
{
  "query": "string (required)",
  "repos": ["string"],
  "path_prefix": ["string"],
  "exclude_paths": ["string"],
  "exclude_patterns": ["string"],
  "top_k": "number (1-100)",
  "max_snippets": "number",
  "deadline_ms": "number",
  "embed_model": "small | large",
  "score_cutoff": "number",
  "mmr_enabled": "boolean",
  "mmr_lambda": "number (0-1)",
  "context_lines_before": "number (0-10)",
  "context_lines_after": "number (0-10)",
  "include_graph_context": "boolean",
  "include_prompt_ready": "boolean",
  "ann_strategy": "speed | accuracy | adaptive | custom",
  "ann_nprobes": "number",
  "ann_refine_factor": "number"
}
```

**Filtering Options**:

- `repos`: Include only specific repositories
- `path_prefix`: Include only paths matching these prefixes (e.g., `["src/", "lib/"]`)
- `exclude_paths`: Exclude paths matching these prefixes (e.g., `["tests/", "node_modules/", "dist/"]`)
- `exclude_patterns`: Exclude files matching glob patterns (e.g., `["*.test.ts", "*.config.json"]`)

**Example**:

```json
{
  "query": "authentication logic",
  "repos": ["myapp"],
  "path_prefix": ["src/"],
  "exclude_paths": ["tests/"],
  "exclude_patterns": ["*.spec.ts", "*.mock.ts"]
}
```

### `fetch_chunk`

Fetch a chunk by chunk_id and return fenced code with citation.

```json
{
  "chunk_id": "string (required)"
}
```

### `get_metadata`

Fetch chunk metadata without returning the full content.

```json
{
  "chunk_id": "string (required)"
}
```

### `fetch_lines`

Fetch a file slice [start, end] inclusive from disk and return fenced code with citation.

```json
{
  "repo": "string (required)",
  "path": "string (required)",
  "start": "number (required, 1-indexed)",
  "end": "number (required, inclusive)"
}
```

### `get_vector_store_info`

Report namespaces, dims, limits, and approximate counts.

```json
{}
```

### `open_in_editor`

Compute a vscode://file URI for a repo path and optional position.

```json
{
  "repo": "string (required)",
  "path": "string (required)",
  "line": "number (1-indexed)",
  "column": "number (1-indexed)"
}
```

### `file_write`

Write content to a file relative to the workspace with an atomic write and optional backup.

```json
{
  "path": "string (required)",
  "content": "string (required)",
  "create_backup": "boolean",
  "create_directories": "boolean"
}
```

### `read_files`

Read multiple files in one request with optional partial failure handling.

```json
{
  "paths": ["string"],
  "max_size_bytes": "number",
  "fail_on_error": "boolean"
}
```

## Installation (Optional)

If you prefer installing globally:

```bash
bun install -g dolphin-mcp
```

Then use `dolphin-mcp` instead of `bunx dolphin-mcp`.

## Requirements

- **Bun** >= 1.0.0 - [Install](https://bun.sh/install)
- **Dolphin API** running on configured endpoint

## License

MIT - see [LICENSE](LICENSE) file for details.

## Links

- [NPM Package](https://www.npmjs.com/package/dolphin-mcp)
- [GitHub Repository](https://github.com/tdc93/dolphin-mcp)
- [MCP Specification](https://modelcontextprotocol.io)
