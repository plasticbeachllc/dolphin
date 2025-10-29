# AI Assistant Onboarding Guide for Dolphin Project

## Overview

The dolphin project is a personal AI companion system that integrates multiple MCP (Model Context Protocol) servers with OpenWebUI to provide a customizable AI assistant experience. The core feature is a personas system that allows different AI agent personalities with specific behaviors and configurations.

## Current Phase Status

### ✅ COMPLETED: Phases 1-6
- **Phases 1-3**: Core pipeline bootstrap with Git-aware ingestion
- **Phase 4**: Language-specific chunking (Python, TypeScript, Markdown) with fallback token-windowing
- **Phase 5a**: Repository configuration system with per-repo and global settings
- **Phase 6**: Embeddings integration and full pipeline orchestration

**Status**: All KB pipeline components working; 147/147 tests passing.

### 🔜 IN PROGRESS: Phase 5b (MCP Bridge) — Blocked on Phase 7

**MCP Bridge Status**:
- ✅ Specification complete (`docs/phase-5-mcp-bridge-spec.md`)
- ✅ TypeScript project scaffolding with Bun runtime
- ✅ Unit test framework (mock REST server auto-manages)
- ✅ Tool definitions and error handling
- 🔜 Tool implementations (awaiting REST API)

**Blocker**: MCP Bridge requires REST API at `http://127.0.0.1:7777` with endpoints:
- ❌ `GET /v1/health` (shallow and deep)
- ❌ `GET /v1/repos`
- ❌ `POST /v1/search` (pagination support)
- ❌ `GET /v1/chunks/{id}`
- ❌ `GET /v1/file`

**Next**: Complete Phase 7 (Retriever HTTP API) to unblock Phase 5b.

## Repository Structure

