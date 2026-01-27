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

| Variable           | Default                 | Description                              |
| ------------------ | ----------------------- | ---------------------------------------- |
| `DOLPHIN_API_URL`  | `http://127.0.0.1:7777` | Dolphin API base URL                     |
| `KB_REST_BASE_URL` | unset                   | Alias for `DOLPHIN_API_URL` (tests/CI)   |
| `LOG_LEVEL`        | `info`                  | Logging level (debug, info, warn, error) |

### TOML Configuration File

The MCP bridge reads `~/.dolphin/config.toml` (or `DOLPHIN_CONFIG_PATH`) and supports:

- `[mcp]` base settings (`api_url`, `server_name`, `server_version`, `protocol_version`, `log_level`)
- `[mcp.limits]`, `[mcp.snippet_fetch]`, `[mcp.logging]`, `[mcp.response]`, `[mcp.search]`

### Config & Diagnostics Commands

These commands emit machine-readable JSON by default (designed for LLMs and tooling):

```bash
# Print effective config + sources + diagnostics
dolphin-mcp config --print

# Run configuration checks (no side effects)
dolphin-mcp doctor
```

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

These variables control the performance optimization for parallel snippet fetching in `search`:

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

### Tool Output Shape

All tools return MCP `content` blocks. Success responses include `_meta` with `tool_version`, `latency_ms`, and `warnings`. Errors set `isError: true` and include `_meta.error`:

```json
{
  "code": "string",
  "message": "string",
  "remediation": "string",
  "details": {}
}
```

### `search`

Semantically query code and docs across indexed repositories and return many ranked candidates with follow-up-ready identifiers and citations.

```json
{
  "query": "string (required)",
  "repos": ["string"],
  "path_prefix": ["string"],
  "exclude_paths": ["string"],
  "exclude_patterns": ["string"],
  "top_k": "number (1-100)",
  "max_snippets": "number (top-N results to include snippet text for)",
  "top_context_n": "number (top-N snippet results to include extra context for)",
  "score_cutoff": "number",
  "mmr_enabled": "boolean",
  "mmr_lambda": "number (0-1)",
  "context_lines_before": "number (0-10)",
  "context_lines_after": "number (0-10)",
  "include_graph_context": "boolean",
  "output_mode": "prompt_ready | resources | both",
  "include_prompt_ready": "boolean",
  "include_resource_text": "boolean",
  "include_hits_json": "boolean",
  "include_warnings_in_text": "boolean",
  "include_abs_paths": "boolean",
  "include_vscode_uris": "boolean",
  "ann_strategy": "speed | accuracy | adaptive | custom",
  "ann_nprobes": "number",
  "ann_nprobes": "number",
  "ann_refine_factor": "number",
  "compact": "boolean"
}
```

Note: `embed_model` is no longer a supported search parameter; model selection is configured in the KB/repo settings.

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

### `chunk.get`

Fetch a chunk by chunk_id and return fenced code with citation.

```json
{
  "chunk_id": "string (required)"
}
```

### `metadata.get`

Fetch chunk metadata without returning the full content.

```json
{
  "chunk_id": "string (required)"
}
```

### `file.lines`

Fetch a file slice [start, end] inclusive from disk and return fenced code with citation.

```json
{
  "repo": "string (required)",
  "path": "string (required)",
  "start": "number (required, 1-indexed)",
  "end": "number (required, inclusive)"
}
```

### `store.info`

Report namespaces, dims, limits, and approximate counts.

```json
{}
```

### `open_ref`

Open a reference (kb:// URI or chunk_id) and return the content. Use this to follow up on search results.

```json
{
  "ref": "string (kb://... URI or chunk_id)"
}
```

### `repos.list`

List indexed repositories with their absolute root paths and approximate file/chunk counts.

```json
{}
```

### `health`

Check Knowledge Base REST API health (`/v1/health`).

```json
{
  "check": "shallow | deep"
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
