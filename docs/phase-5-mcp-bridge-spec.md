# Plastic Beach Knowledge Store — MCP Bridge Specification (Phase 5, Sprint 1)

Status: **Implementation in Progress** (v0.2.0)
- ✅ Specification complete and implementation-ready
- ✅ Project structure and TypeScript scaffolding set up
- ✅ Unit test framework with mock REST server
- 🔜 Tool implementations (search_knowledge, fetch_chunk, fetch_lines, open_in_editor) in progress
- 🔜 Awaiting REST API completion (see Phase 5 Appendices for HTTP server status)
Owner: PB KB Team
Date: 2025-10-29
Version: 0.2.0

## Implementation Status

### Phase 5 Blockers
**BLOCKING**: MCP Bridge tools depend on the Retriever REST API at `http://127.0.0.1:7777`:
- ❌ `GET /v1/health` — shallow and deep health checks
- ❌ `GET /v1/repos` — list repositories with metadata
- ❌ `POST /v1/search` — semantic search with pagination
- ❌ `GET /v1/chunks/{id}` — fetch chunk by ID
- ❌ `GET /v1/file` — fetch file slice by path and range

**Status**: REST API skeleton exists (`src/pb_kb/api/app.py`) but lacks endpoint implementations. Must complete before MCP tool implementations can be tested end-to-end.

### Current MCP Bridge Implementation
- ✅ **Project Structure**: TypeScript + Bun runtime, proper directory layout
- ✅ **Protocol Setup**: MCP initialization, capabilities, serverInfo
- ✅ **Test Framework**: Unit tests with mock REST server (auto-starts per suite)
- ✅ **Logging**: JSONL log rotation to `mcp-bridge/logs/mcp.log`
- ✅ **Error Handling**: Tool-level error mappings defined
- ✅ **Type Definitions**: JSON Schema and TypeScript types for all tools
- 🔜 **Tool Implementations**: Awaiting REST API endpoints
- 🔜 **Content Truncation**: 50 KB budget enforcement logic (scaffolded, needs REST data)
- 🔜 **Repo Cache**: Process-lifetime cache for `/v1/repos` (helper ready)
- 🔜 **Integration Tests**: Smoke tests waiting for real REST service

## Quick Start

### Dev Setup

