# dolphin-mcp

[![NPM Version](https://img.shields.io/npm/v/dolphin-mcp.svg)](https://www.npmjs.com/package/dolphin-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for Dolphin semantic code search. Conforms to [MCP spec](https://modelcontextprotocol.io/) and targets the `/v1` KB API endpoints.

## Quick Start

```bash
bunx dolphin-mcp
```

Add to your MCP client config (Claude Desktop, Continue, etc.):

```json
{
  "mcpServers": {
    "dolphin-kb": {
      "command": "bunx",
      "args": ["dolphin-mcp"],
      "env": {
        "DOLPHIN_API_URL": "http://127.0.0.1:7777"
      }
    }
  }
}
```

## Configuration

### Environment Variables

| Variable          | Default                 | Description                              |
| ----------------- | ----------------------- | ---------------------------------------- |
| `DOLPHIN_API_URL` | `http://127.0.0.1:7777` | Dolphin API base URL                     |
| `DOLPHIN_API_KEY` | auto-provisioned        | API key (override for CI/remote deploys) |
| `LOG_LEVEL`       | `info`                  | Logging level (debug, info, warn, error) |

The bridge also reads `~/.dolphin/config.toml` for `[mcp]` settings (limits, snippet fetch, search defaults).

### API Key

The bridge auto-provisions a key at `~/.dolphin/kb_api_key` on startup — no manual setup needed. Override with `DOLPHIN_API_KEY` or `DOLPHIN_KB_API_KEY` env vars for CI/remote use.

### Diagnostics

```bash
dolphin-mcp config --print   # effective config + sources
dolphin-mcp doctor            # connectivity & config checks
```

## Tools

All tools return MCP `content` blocks with `_meta` (tool_version, latency_ms, warnings). Errors set `isError: true`.

| Tool            | Description                                              |
| --------------- | -------------------------------------------------------- |
| `search`        | Semantic search across indexed repos (ranked candidates) |
| `chunk.get`     | Fetch chunk content by ID                                |
| `metadata.get`  | Fetch chunk metadata without content                     |
| `file.lines`    | Fetch a file slice [start, end] from disk                |
| `store.info`    | Report namespaces, dims, limits, counts                  |
| `open_ref`      | Open a `kb://` URI or chunk_id                           |
| `repos.list`    | List indexed repos with paths and counts                 |
| `health`        | Check KB API health (shallow or deep)                    |

### `search`

```json
{
  "query": "authentication logic",
  "repos": ["myapp"],
  "path_prefix": ["src/"],
  "exclude_paths": ["tests/"],
  "exclude_patterns": ["*.spec.ts"],
  "top_k": 10,
  "max_snippets": 5,
  "include_graph_context": true
}
```

Key parameters: `query` (required), `repos`, `path_prefix`, `exclude_paths`, `exclude_patterns`, `top_k` (1-100), `max_snippets`, `score_cutoff`, `context_lines_before/after` (0-10), `include_graph_context`, `output_mode` (prompt_ready | resources | both), `compact`.

## Requirements

- **Bun** >= 1.0.0 — [install](https://bun.sh/install)
- **Dolphin API** running (`dolphin serve`)

## License

MIT
