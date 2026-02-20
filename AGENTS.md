# Agent Guidelines for Dolphin Repository

This document provides guidelines for LLM agents working in the Dolphin codebase.

## Repository Overview

Dolphin is a semantic code search and knowledge management system. Primary components:

- **Python Backend** (`kb/`): FastAPI API, indexing pipeline, embeddings, storage
- **TypeScript MCP Bridge** (`mcp-bridge/`): Model Context Protocol server
- **Shared TypeScript** (`shared/`): IPC and reusable utilities
- **Documentation** (`docs/`): architecture, testing, benchmarking, profiling, security

## Core Rules

### 1. Python command execution

Always use `uv run` for Python commands.

```bash
uv run pytest tests/unit/ -v
uv run ruff check --fix
uv run ruff format
uv run ty check
uv run dolphin serve
```

### 2. JavaScript/TypeScript command execution

Use **Bun** (`bun` / `bunx`) for JS/TS workflows in this repo.

```bash
bun install
cd mcp-bridge && bun test
cd shared && bun test
```

### 3. Documentation management

- Do not add new docs files unless explicitly requested.
- Update existing docs when behavior changes.
- Keep implementation-status docs current (`docs/ARCHITECTURE.md`, `docs/TESTING.md`).

### 4. Test coverage expectations

- New features: add tests.
- Bug fixes: add regression tests.
- Refactors: existing tests must stay green.
- Prefer targeted suites relevant to changed code.

### 5. Before finalizing changes

Run relevant checks:

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
cd mcp-bridge && bun test
cd shared && bun test
uv run ruff check
uv run ty check
```

## Architecture awareness

High-level flow:

`MCP client -> mcp-bridge -> kb/api -> SQLite + LanceDB`

Indexing:

`repo -> scan -> chunk -> embed -> store`

Search:

`query -> embed -> vector/BM25 -> rerank/fuse -> response`

## Security expectations

- Validate user-controlled paths.
- Protect API endpoints with API key checks where required.
- Avoid committing secrets.
- Respect ignore patterns and sensitive-file exclusions.

## Quick operational commands

```bash
# Start API
uv run dolphin serve

# MCP bridge
cd mcp-bridge && bun run src/index.ts

# KB status
uv run dolphin kb status

# Reindex
uv run dolphin kb index <repo-name> --full --force
```
