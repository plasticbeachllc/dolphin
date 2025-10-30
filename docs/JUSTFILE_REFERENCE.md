# Justfile Reference

This repo includes a Justfile with common KB workflows. Install `just` (brew install just) and run these from the repo root.

## Setup

```
just venv            # create venv and install python deps
just bun-install     # install Bun deps for mcp-bridge
```

## Services

```
just api             # run REST API (kb-api)
just mcp             # run MCP bridge via Bun
```

## Ingestion

```
just init            # initialize store/config/dbs
just add-repo NAME   # register current repo path with name
just index NAME      # incremental index
just reindex NAME    # full reindex (force, cleans/prunes)
just reset NAME      # init + add-repo + full reindex
```

## Search & Tools

```
just repos           # list indexed repos
just info            # vector store info
just health          # API health
just search "term"   # search via MCP CLI
just chunk ID        # fetch chunk by id
just lines REPO PATH START END   # fetch file lines
just curl-search "term"          # direct REST search
```

## Logs

```
just tail-mcp        # tail MCP bridge log
```

## Clean (Dangerous)

```
just store-clean     # rm -rf ~/.dolphin/knowledge_store (with 5s prompt)
```

Notes
- Ensure `OPENAI_API_KEY` is exported if using OpenAI embeddings.
- Defaults to the `large` model; override per repo with `.dolphin/config.toml`.
- `add-repo` defaults to `--default-embed-model large`.

