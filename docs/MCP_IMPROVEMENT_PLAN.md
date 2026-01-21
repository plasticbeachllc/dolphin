# MCP Improvement Plan

## Goals

- Optimize MCP responses for Antigravity and OpenAI Codex: model-visible, low-ambiguity text with easy follow-ups.
- Default to many candidates, while surfacing richer context for higher-ranked results.
- Keep warnings model-visible by default.
- Maintain a minimal, read-only tool surface (no reindex triggers).

## Current State (Baseline)

- Tools: `search_knowledge`, `fetch_chunk`, `fetch_lines`, `get_vector_store_info`, `get_metadata`.
- Responses relied on `_meta` for key follow-up identifiers (e.g., `chunk_id`), which is not always model-visible.
- Warnings were primarily in `_meta`, not guaranteed to be visible to the model.
- Docs drifted from actual MCP tool registration.

## Implemented Changes (✅)

### 1) Search Contract (Model-Visible First)

- Added a `hits_json` text block (default on) to `search_knowledge` with follow-up-ready data:
  - `chunk_id`, `repo`, `path`, `score`, line ranges, `kb://` citations, and suggested `fetch_chunk`/`fetch_lines` inputs.
  - Optional `abs_path` and `vscode://` URIs (default on, configurable).
- Made warnings model-visible in the summary text by default.
- Default behavior now returns many candidates with snippets only for top N results.

### 2) Snippet Strategy

- Search defaults: `top_k=20`, snippets for top `N=8`, context for top `N=3`.
- Snippets fetched in parallel from `/v1/file` to keep search payloads small while still providing rich context for top hits.

### 3) Tool Surface

- Removed `open_in_editor` from MCP tool registration.
- Added read-only tools:
  - `list_repos` (discover valid repo filters and paths)
  - `kb_health` (REST availability check)

### 4) Configuration & Docs

- New MCP defaults added to config template:
  - `top_k_default`, `snippets_top_n_default`, `top_context_n_default`
  - `include_hits_json_default`, `include_warnings_in_text_default`
  - `include_abs_paths_default`, `include_vscode_uris_default`
- Updated docs and tool listings to match actual MCP surface.
- Corrected payload budget wording to ~70KB.

## Planned Follow-Ups (Next)

### A) Tests & Contract Validation

- Add tests for:
  - `hits_json` shape and presence of `chunk_id`
  - Warnings in summary text
  - Snippet top-N and context top-N behavior
  - Payload trimming behavior with `hits_json`
- Confirm `list_repos` and `kb_health` tests pass in Bun.

### B) Response Shape Hardening

- Ensure `search_knowledge` always emits a stable summary + `hits_json` even when snippets fail.
- Consider adding structured warning codes (e.g., `snippet_fetch_failed`) and versioning the JSON schema.

### C) Client-Specific Optimization

- Validate with Antigravity and Codex:
  - Whether `resource` blocks are ignored and should remain optional/off by default.
  - Whether JSON block size should be capped or split for large result sets.

## Non-Goals (Explicitly Excluded)

- No MCP tools that trigger reindexing or mutation.
- No file read/write tools exposed via MCP.

## References (Key Files)

- `mcp-bridge/src/mcp/tools/search_knowledge.ts`
- `mcp-bridge/src/util/config.ts`
- `kb/config_template.toml`
- `mcp-bridge/README.md`
- `docs/ARCHITECTURE.md`
