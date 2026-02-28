<p align="center">
  <h1 align="center">🐬 Dolphin</h1>
  <p align="center">
    <strong>Hybrid search across all your repositories.</strong><br/>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/pb-dolphin/"><img src="https://img.shields.io/pypi/v/pb-dolphin.svg" alt="PyPI"></a>
    <a href="https://www.npmjs.com/package/dolphin-mcp"><img src="https://img.shields.io/npm/v/dolphin-mcp.svg" alt="npm"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  </p>
</p>

---

Dolphin indexes your repositories and lets you perform hybrid (semantic + keyword) search across them.

## Quickstart

```bash
# Install
uv pip install pb-dolphin

# Set your OpenAI key (used for embeddings)
export OPENAI_API_KEY="sk-..."

# Initialize, add a repo, and search
dolphin init
dolphin add-repo my-project /path/to/project
dolphin index my-project
dolphin search "database connection pooling"
```

Dolphin indexes your code with language-aware chunking, embeds it, and returns ranked results.

Want live re-indexing as you edit files? Start the server:

```bash
dolphin serve
```

## Agent Integration

A small companion MCP server is available at `bunx dolphin-mcp`. Add this to your AI app's MCP config:

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

Make sure `dolphin serve` is running, and your agent can now search, retrieve chunks, and read files from your indexed repos.

Additionally, a Claude skill is available in this repo's marketplace as a personal Plugin.

## How it works

```
  You / Agent
        |
        v
  ┌───────────────────────────────────────┐
  │             Dolphin                   │
  │                                       │
  │   CLI ─── REST API ─── MCP Bridge     │
  │               |                       │
  │        ┌──────┴──────┐                │
  │        v             v                │
  │    LanceDB       SQLite               │
  │   (vectors)    (metadata + BM25)      │
  └───────────────────────────────────────┘
```

**Indexing:** Your code is scanned, split into semantic chunks using language-aware AST parsers, embedded via OpenAI, and stored in LanceDB (vectors) and SQLite (metadata + full-text).

**Searching:** Your query is embedded and matched against both vector similarity and BM25 keyword relevance. Results are fused with Reciprocal Rank Fusion, optionally reranked with a cross-encoder, and returned as structured snippets with file paths, line numbers, and scores.

## Features

**Intelligent hybrid search**

- Hybrid vector + BM25 keyword search with RRF fusion
- Optional cross-encoder reranking for +20-30% ranking improvement
- MMR diversity to reduce redundant results
- Filter by repo, language, path, or glob pattern

**Language-aware indexing**

- AST-based chunking for Python, TypeScript, JavaScript, Markdown, SQL, and Svelte
- Fallback text chunking for everything else
- Respects `.gitignore` and an optional repo-specific Dolphin config (`dolphin init --repo`)

**Live sync**

- File-watching built into `dolphin serve` so edits are re-indexed automatically
- Git-aware: handles branch switches gracefully

**Multiple interfaces**

- `dolphin` CLI with compact, verbose, and JSON output modes
- FastAPI server with full search and retrieval endpoints
- MCP server for integration via `bunx dolphin-mcp`

## Supported chunking languages

Dolphin uses language-aware AST chunkers for the best possible search quality. Files in other recognized languages fall back to token-window chunking, and completely unknown extensions use a generic text chunker.

| Language                       | Extensions                                | Chunker      |
| ------------------------------ | ----------------------------------------- | ------------ |
| Python                         | `.py`, `.pyw`, `.pyi`                     | AST          |
| TypeScript                     | `.ts`, `.tsx`                             | AST          |
| JavaScript                     | `.js`, `.jsx`, `.mjs`, `.cjs`             | AST          |
| Markdown                       | `.md`, `.markdown`                        | AST          |
| SQL                            | `.sql`                                    | AST          |
| Svelte                         | `.svelte`                                 | AST          |
| Go, Rust, Java, C/C++          | `.go`, `.rs`, `.java`, `.c`, `.cpp`       | Token-window |
| Ruby, PHP, C#, Swift, Kotlin   | `.rb`, `.php`, `.cs`, `.swift`, `.kt`     | Token-window |
| Shell                          | `.sh`, `.bash`, `.zsh`                    | Token-window |
| Config (JSON, YAML, TOML, XML) | `.json`, `.yaml`, `.yml`, `.toml`, `.xml` | Token-window |

You can customize extension mappings in `~/.dolphin/config.toml` under the `[languages]` section.

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
| `dolphin rm-repo <name>`         | Remove a repo and its data                |
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
default_embed_model = "small"   # "small" (faster) or "large" (better)

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

Trade-offs: ~2GB disk for model weights, 2-3x slower searches.

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

## License

MIT — [Plastic Beach, LLC](https://github.com/plasticbeachllc)
