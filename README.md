<p align="center">
  <h1 align="center">Dolphin</h1>
  <p align="center">
    <strong>Semantic code search across all your repositories.</strong><br/>
    Find the right code instantly — from your terminal, your editor, or your AI assistant.
  </p>
  <p align="center">
    <a href="https://pypi.org/project/pb-dolphin/"><img src="https://img.shields.io/pypi/v/pb-dolphin.svg" alt="PyPI"></a>
    <a href="https://www.npmjs.com/package/dolphin-mcp"><img src="https://img.shields.io/npm/v/dolphin-mcp.svg" alt="npm"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  </p>
</p>

---

Dolphin indexes your codebases and lets you search them semantically — not just by filename or keyword, but by _meaning_. Ask for "authentication logic" and get back the actual auth code, ranked by relevance, across every repo you've indexed.

It works three ways: as a **CLI** you run in your terminal, as a **REST API** other tools can call, and as an **MCP server** that plugs directly into AI coding assistants like Claude and Continue.dev.

## Get started in 60 seconds

```bash
# Install
uv pip install pb-dolphin

# Set your OpenAI key (used for embeddings)
export OPENAI_API_KEY="sk-..."

# Initialize, add a repo, and search
dolphin init
dolphin add-repo my-project /path/to/project
dolphin search "database connection pooling"
```

That's it. Dolphin indexes your code with language-aware chunking, embeds it, and returns ranked results.

Want live re-indexing as you edit files? Start the server:

```bash
dolphin serve
```

## Connect to your AI assistant (MCP)

Dolphin speaks [MCP](https://modelcontextprotocol.io/), so Claude Desktop, Continue.dev, and other MCP clients can search your code directly.

Add this to your AI app's MCP config:

```json
{
  "mcpServers": {
    "dolphin": {
      "command": "bunx",
      "args": ["dolphin-mcp"]
    }
  }
}
```

Make sure `dolphin serve` is running, and your AI assistant can now search, retrieve chunks, and read files from your indexed repos.

## How it works

```
  You / AI assistant
        |
        v
  ┌───────────────────────────────────────┐
  │             Dolphin                    │
  │                                        │
  │   CLI ─── REST API ─── MCP Bridge     │
  │               |                        │
  │        ┌──────┴──────┐                 │
  │        v             v                 │
  │    LanceDB       SQLite                │
  │   (vectors)    (metadata + BM25)       │
  └───────────────────────────────────────┘
```

**Indexing:** Your code is scanned, split into semantic chunks using language-aware AST parsers, embedded via OpenAI, and stored in LanceDB (vectors) and SQLite (metadata + full-text).

**Searching:** Your query is embedded and matched against both vector similarity and BM25 keyword relevance. Results are fused with Reciprocal Rank Fusion, optionally reranked with a cross-encoder, and returned as structured snippets with file paths, line numbers, and scores.

## Features

**Search that understands code**

- Hybrid vector + BM25 keyword search with RRF fusion
- Optional cross-encoder reranking for +20-30% ranking improvement
- MMR diversity to reduce redundant results
- Filter by repo, language, path, or glob pattern

**Language-aware indexing**

- AST-based chunking for Python, TypeScript, JavaScript, Markdown, SQL, and Svelte
- Fallback text chunking for everything else
- Respects `.gitignore` — indexes only what matters

**Live sync**

- File-watching built into `dolphin serve` — edits are re-indexed automatically
- Git-aware: handles branch switches gracefully

**Multiple interfaces**

- `dolphin` CLI with compact, verbose, and JSON output modes
- FastAPI server on port 7777 with full search and retrieval endpoints
- MCP server for AI assistant integration via `bunx dolphin-mcp`

## CLI reference

| Command                          | What it does                              |
| -------------------------------- | ----------------------------------------- |
| `dolphin init`                   | Create config at `~/.dolphin/config.toml` |
| `dolphin add-repo <name> <path>` | Register a repository                     |
| `dolphin index <name>`           | Index (or re-index) a repository          |
| `dolphin search <query>`         | Search across indexed repos               |
| `dolphin serve`                  | Start API server with file-watching       |
| `dolphin status`                 | Show indexed repos and stats              |
| `dolphin repos`                  | List registered repositories              |
| `dolphin rm_repo <name>`         | Remove a repo and its data                |
| `dolphin config --show`          | Display current config                    |

### Search options

```bash
dolphin search "error handling" \
  --repo myapp \
  --lang py \
  --path src/ \
  --top-k 10 \
  --verbose          # or --json for scripting
```

## Configuration

Dolphin auto-creates its config at `~/.dolphin/config.toml` when you run `dolphin init`. The defaults work well out of the box.

```toml
default_embed_model = "large"   # "small" (faster) or "large" (better)

[retrieval]
top_k = 8

[retrieval.hybrid_search]
enabled = true
fusion_method = "rrf"
```

For per-repo overrides (custom ignore patterns, chunking settings), run `dolphin init --repo` inside a repository.

Full config reference: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Optional: cross-encoder reranking

For the best possible search quality, enable cross-encoder reranking. This re-scores results pairwise against your query using an ML model.

```bash
uv pip install "pb-dolphin[reranking]"
```

Then in `~/.dolphin/config.toml`:

```toml
[retrieval.reranking]
enabled = true
```

Trade-offs: ~2GB disk for model weights, 2-3x slower searches. Worth it for large codebases where precision matters.

## Requirements

| Dependency                       | Purpose                       |
| -------------------------------- | ----------------------------- |
| Python 3.12+                     | Core runtime                  |
| [uv](https://docs.astral.sh/uv/) | Python package management     |
| OpenAI API key                   | Embedding generation          |
| [Bun](https://bun.sh/)           | MCP bridge runtime (optional) |
| Git                              | Repository scanning           |

## Troubleshooting

**Server not responding?**

```bash
curl http://127.0.0.1:7777/v1/health   # check health
lsof -i :7777                           # check port
dolphin serve                            # start it
```

**No search results?**

```bash
dolphin status                                    # verify repos are indexed
dolphin index <repo-name> --full --force          # force re-index
```

**MCP not connecting?**

- Make sure `dolphin serve` is running
- Check that Bun is installed: `bun --version`
- Set `DOLPHIN_API_URL` if the server isn't at `http://127.0.0.1:7777`

## Contributing

```bash
# Run tests
uv run pytest tests/unit/ -v

# Lint and type-check
uv run ruff check --fix
uv run ty check

# MCP bridge tests
cd mcp-bridge && bun test
```

See [docs/TESTING.md](docs/TESTING.md) for the full testing guide and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the system fits together.

## License

MIT — [Plastic Beach, LLC](https://github.com/plasticbeachllc)
