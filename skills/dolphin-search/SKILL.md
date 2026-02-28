---
name: dolphin-search
description: Search across any repositories indexed with Dolphin. Use when searching for code implementations, finding functions or classes across repos, or looking up how something works in the codebase. Also use when the user mentions "search" or asks to look up or find something.
allowed-tools: Bash(uv run dolphin *)
---

# Dolphin Semantic Search

Search indexed codebases using hybrid vector + keyword retrieval via the `dolphin` CLI.

## Quick Reference

### List Indexed Repos

```bash
uv run dolphin repos --json
```

Returns repos with name, path, model, and file/chunk counts. Run this first if you don't know which repos are indexed.

### Search

```bash
uv run dolphin search "your query" --json [options]
```

**Key options:**

| Flag                                 | Description                                               | Default   |
| ------------------------------------ | --------------------------------------------------------- | --------- |
| `--repo NAME` / `-r NAME`            | Filter to specific repo(s) (repeatable)                   | all repos |
| `--path PREFIX` / `-p PREFIX`        | Filter by path prefix (repeatable)                        | none      |
| `--exclude-pattern GLOB` / `-x GLOB` | Exclude glob pattern (repeatable)                         | none      |
| `--lang LANG`                        | Language filter: py, ts, js, md, sql, svelte (repeatable) | all       |
| `--top-k N` / `-k N`                 | Number of results                                         | 8         |
| `--max-snippets N`                   | Include content for top N hits                            | 0         |
| `--context-before N`                 | Context lines before match                                | 0         |
| `--context-after N`                  | Context lines after match                                 | 0         |
| `--graph-context`                    | Include knowledge graph relationships and entities        | off       |
| `--show-content` / `--verbose`       | Enrich results with code snippets (local and remote)      | off       |
| `--local` / `-l`                     | Force local search (rarely needed — auto-fallback exists) | remote    |
| `--json`                             | Machine-readable JSON output                              | off       |

**Always use `--json` when calling from this skill** so results are structured.

### Example Searches

```bash
# Broad semantic search
uv run dolphin search "authentication middleware" --json -k 5

# Scoped to a repo and language
uv run dolphin search "database connection pooling" --json -r myapp --lang py -k 10

# With snippets for top 3 hits
uv run dolphin search "error handling" --json --max-snippets 3 --context-before 2 --context-after 2

# Exclude test files
uv run dolphin search "caching logic" --json -x "*.test.*" -x "tests/*"

# With graph context (shows imports, calls, type relationships)
uv run dolphin search "search backend" --json --graph-context -k 5
```

### Get a Chunk by ID

```bash
uv run dolphin chunk <chunk_id> --json
```

Use chunk IDs from search results to fetch full chunk content.

## JSON Response Format

### Search Response

```json
{
  "query": "the search query",
  "result_count": 5,
  "hits": [
    {
      "rank": 1,
      "chunk_id": "abc123",
      "repo": "myapp",
      "path": "src/auth/middleware.py",
      "file_path": "/absolute/path/to/src/auth/middleware.py",
      "start_line": 42,
      "end_line": 78,
      "score": 0.8721,
      "language": "python",
      "symbol_kind": "function",
      "symbol_name": "verify_token",
      "content": "def verify_token(...):\n    ...",
      "snippet": { "text": "..." }
    }
  ]
}
```

### Follow-Up Workflow

1. **Search** to find relevant code
2. **Read the file** using the `file_path` and line numbers from hits (use the Read tool directly — it's faster than dolphin chunk)
3. **Get chunk by ID** with `dolphin chunk <chunk_id> --json` if you need the exact indexed content

## When to Use

- Searching across multiple indexed repositories simultaneously
- Finding implementations by semantic meaning (not just text matching)
- Discovering code related to a concept, pattern, or feature
- Looking up symbols, functions, or classes across a large codebase

## When NOT to Use

- Searching within a single file you already have open (use Grep instead)
- Finding files by name (use Glob instead)
- Simple text/regex matching in the current project (use Grep instead)

## Troubleshooting

Search auto-falls back to local mode when the API server is unavailable, so most queries work without a running server. If you need to start the server explicitly:

```bash
uv run dolphin serve
```

Use `--local` to force local-only search (bypasses the server entirely, slower startup).
