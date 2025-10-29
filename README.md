# 🐬 Dolphin

A full-stack AI enablement platform that integrates semantic code retrieval with multiple AI interfaces to provide intelligent assistance across development workflows.

## Overview

Dolphin is designed to power intelligent coding and documentation assistance through:

1. **OpenWebUI** — General-purpose conversational AI interface for researching code, planning, and documentation
2. **Continue (VSCode)** — IDE-integrated assistant for real-time code completion, explanation, and refactoring
3. **Custom MCP Servers** — Extensible Model Context Protocol integrations providing domain-specific tools and capabilities

At its core, Dolphin combines:
- **Personas System** — Multiple AI agent personalities with specific behaviors and guardrails
- **Unified Knowledge Store** — Semantic retrieval system for code and documentation with intelligent chunking and embeddings
- **Metadata Management** — SQLite-backed provenance and session tracking
- **Vector Indexing** — LanceDB-powered semantic search for efficient retrieval

---

## 🎯 Current Implementation Status

### ✅ PHASES 1-6 COMPLETE: Knowledge Base Pipeline

**Phase 6 (Embeddings & Pipeline)** — ✅ Complete
- ✅ Full KB pipeline operational and tested (147/147 tests passing)
- ✅ OpenAI embedding integration with exponential backoff retry logic
- ✅ SQLite + LanceDB storage layer working
- ✅ Git-aware incremental indexing
- ✅ Language-specific chunking (Python, TypeScript, Markdown, fallback)
- ✅ Per-repository configuration system
- ✅ Content-based deduplication
- ✅ Idempotent ingestion (safe re-runs)

### 🔜 PHASE 7 (NEXT PRIORITY): Retriever HTTP API

**Status**: Skeleton exists, endpoints not yet implemented.

**Required endpoints**:
- ❌ `GET /v1/health` — shallow check (current) + deep check (lancedb, embeddings status)
- ❌ `GET /v1/repos` — list all repositories with metadata
- ❌ `POST /v1/search` — semantic search with pagination, cursors, filtering
- ❌ `GET /v1/chunks/{id}` — fetch specific chunk by ID
- ❌ `GET /v1/file` — fetch file slice [start, end] from disk

**Location**: `src/pb_kb/api/app.py` (FastAPI, port 127.0.0.1:7777)

### 🔄 PHASE 5b (IN PROGRESS): MCP Bridge

**Status**: Specification complete, scaffolding done, **blocked on Phase 7**.

**Location**: `mcp-bridge/` (TypeScript + Bun runtime)

**Completed**:
- ✅ Specification and design (`docs/phase-5-mcp-bridge-spec.md`)
- ✅ Project structure and scaffolding
- ✅ Unit test framework with mock REST server
- ✅ Tool definitions and error handling
- ✅ JSONL logging with rotation

**Awaiting Phase 7**:
- 🔜 Tool implementations (search_knowledge, fetch_chunk, fetch_lines, open_in_editor, get_vector_store_info, get_metadata)
- 🔜 Integration tests with real REST service
- 🔜 Content truncation logic (50 KB budget enforcement)
- 🔜 Pagination cursor handling

**Tier 1 Tools** (when Phase 7 ready):
- `search_knowledge` — Query repos, return ranked snippets with citations
- `fetch_chunk` — Get full chunk by ID
- `fetch_lines` — Read file slice
- `open_in_editor` — Generate vscode://file URI for Continue

**Tier 2 Tools** (when Phase 7 ready):
- `get_vector_store_info` — Namespaces, dims, limits, counts
- `get_metadata` — Chunk metadata
---

## 🚀 Quick Start

### Prerequisites

- **Python** ≥3.13 with `uv` package manager
- **Bun** (for MCP Bridge)
- **Docker** (for OpenWebUI)
- **Git** (for repository scanning)
- **OpenAI API Key** (for embeddings)

### Setup

1. **Clone and initialize**:

