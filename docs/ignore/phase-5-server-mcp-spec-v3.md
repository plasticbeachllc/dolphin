# Unified Knowledge Store — Phase 5 Server + MCP Interface Specification (Sprint 1)

Status: Draft (for review)
Owner: PB KB Team
Priority: Continue (VSCode) first; OpenWebUI via MCP
Date: 2025-10-29
Version: 0.1.3

Summary
- Implements a local-first retrieval service and a thin MCP bridge to support inference in chat (OpenWebUI) and IDE (Continue) interfaces.
- REST retriever (FastAPI, Python) is the source of truth; MCP bridge (TypeScript/Node) adapts REST to MCP tools and blocks.
- Serves only the most recent commit per repo (latest indexed snapshot). Commit identifiers and indexing timestamps are not exposed to clients.
- Defaults emphasize simplicity, small payloads, and clear seams for future enhancements.

Scope (Phase 5)
- REST API endpoints for health, repo discovery, search, chunk fetch, and file slices.
- MCP server with four Tier-1 tools and two Tier-2 tools.
- Localhost-only, no auth.
- Single embed model per request (default: small). Mixed-model “auto” is deferred.

Out of Scope (Phase 5)
- Streaming results; query embedding cache; hybrid retrieval; reranking; non-localhost deployment; auth; schema migrations; denylist at query-time; commit-specific retrieval.

A. Topology and Roles
- Retriever REST Service (Python/FastAPI)
  - Binds to 127.0.0.1; exposes /v1 endpoints.
  - Embeds queries with OpenAI, queries LanceDB, returns annotated snippets with provenance (path and line ranges).
- MCP Bridge (TypeScript/Node)
  - Exposes MCP tools consumed by Continue and OpenWebUI.
  - Translates MCP tool calls into REST calls and maps responses into MCP blocks (text + citations + embedded resources where small).
  - Stateless; localhost-only.

B. Defaults, Limits, and Behavior
- Bind host: 127.0.0.1; CORS disabled.
- Default embed_model: small (maps to text-embedding-3-small).
- Score semantics: return cosine similarity from LanceDB as-is.
- score_cutoff: global default from config (optional per-request override).
- top_k: default 5; max 20 (clamp with warning).
- Snippets:
  - REST: token-based truncation, default max_snippet_tokens = 240 (server-side hard cap ≤ 500).
  - MCP: optionally apply char-based truncation for compact responses (default ~200 chars) when requested; token limit still enforced first.
- Response size guardrails (MCP): total response ≤ ~50 KB.
- Path scoping: path_prefix supports both prefix and Unix shell-style globs.
- Repo names: case-sensitive (stored and matched with original casing).
- Pagination: cursor (opaque), estimated_total (estimate only), complete (boolean).
- Cursor design: simple offset-based cursor encoded as base64 JSON of {model, repos, path_prefix, offset, top_k, score_cutoff}.
- Index stability: the index is updated only via explicit manual reindexing (kb index command). No automatic updates occur during query sessions, ensuring cursor pagination remains stable.
- Cutoffs: deadline_ms and max_snippets allow clients to trade recall for latency.
- Logging: JSON lines (schema below).
- Latency targets: p50 ≤ 600 ms; p95 ≤ 2 s for search_knowledge end-to-end via MCP.
- Provenance: service operates over the latest indexed snapshot only; commit_sha and last_indexed_at are never returned in client-visible payloads.

C. REST API (FastAPI)
Base URL: http://127.0.0.1:7777

1) GET /v1/health
- Purpose: verify all systems operational (LanceDB connectivity, OpenAI embeddings availability).
- Query params: check (optional, "shallow" | "deep", default "shallow")
  - shallow: fast HTTP server liveness check only
  - deep: verify LanceDB connection and embeddings provider availability
- 200: {"status":"ok", "checks": {"lancedb": "ok", "embeddings": "ok"}} (for deep check)
- 200: {"status":"ok"} (for shallow check)
- 503 if deep check fails with details in error response

2) GET /v1/repos
- Purpose: enumerate registered repos with basic stats.
- 200 body:
```
  {
    "repos": [
      {
        "name": "repoa",
        "path": "/abs/path/to/repoA",
        "default_embed_model": "small",
        "files": 123,
        "chunks": 456
      }
    ]
  }
```

3) GET /v1/repos/{name}/status
- name: case-sensitive repo name.
- 200 body:
  {
    "name": "repoa",
    "path": "/abs/path/to/repoA",
    "default_embed_model": "small",
    "files": 123,
    "chunks": 456
  }
- Errors: 404 repo_not_found

4) POST /v1/search
- Request:
```
  {
    "query": "How do we initialize the scheduler?",
    "repos": ["repoA"],                  // optional; search all if omitted
    "path_prefix": ["src/**", "docs/"], // optional; prefix or glob (max 10)
    "top_k": 5,                           // default 5, max 20
    "max_snippet_tokens": 240,            // hard cap ≤ 500
    "max_snippet_chars": 200,             // optional MCP-facing trim
    "embed_model": "small",              // "small" | "large" (default "small")
    "score_cutoff": 0.15,                 // optional override
    "cursor": "opaque",                  // optional pagination token
    "deadline_ms": 1200,                  // optional soft timeout
    "max_snippets": 5,                    // optional extra cap ≤ top_k
    "include_prompt_ready": false         // optional; default false (opt-in for prompt_ready field)
  }
```
- Behavior:
  - Verify repo names (case-sensitive) exist or 404.
  - Enforce max 10 path_prefix patterns; warn and ignore excess.
  - Single-table search against chosen model (small → chunks_small; large → chunks_large).
  - Filters: repo_name in repos (case-sensitive); path matches any path_prefix (prefix or glob via pathspec).
  - Ranking: cosine similarity (as-is).
  - score_cutoff: applied post-fetch to filter results. If fewer than top_k results pass threshold, return available results with complete=true.
  - Deduplication: by (repo, path, start_line, end_line) after scoring, keeping the highest-scoring entry.
  - max_snippets: applied after deduplication to limit returned results. Cursor offset still increments by top_k (not max_snippets) for consistent pagination.
  - Truncation: token cap first (using tiktoken cl100k_base); optional char cap after.
  - Pagination: returns cursor and estimated_total (estimate only); complete indicates whether results are exhaustive for the page/request.
  - prompt_ready: only included if include_prompt_ready=true (opt-in).
- 200 body:
```
  {
    "hits": [
      {
        "repo": "repoa",
        "path": "src/scheduler/index.ts",
        "lang": "typescript",
        "symbol": {"kind": "function", "name": "initScheduler", "path": "Scheduler.initScheduler"},
        "start_line": 42,
        "end_line": 86,
        "score": 0.71,
        "snippet": "export function initScheduler(...) { ... }",
        "snippet_fenced": "```ts\nexport function initScheduler(...) { ... }\n```",
        "chunk_id": "uuid",
        "resource_link": "kb://repoa/src/scheduler/index.ts#L42-L86"
      }
    ],
    "meta": {
      "top_k": 5,
      "model": "text-embedding-3-small",
      "latency_ms": 24,
      "timing": {
        "embedding_ms": 234,
        "search_ms": 89,
        "processing_ms": 23
      },
      "cursor": "opaque",
      "estimated_total": 123,
      "complete": true,
      "warnings": ["top_k clamped to 20", "path_prefix count clamped to 10"]
    },
    "prompt_ready": "[repoa] src/scheduler/index.ts#L42-L86\n```ts\nexport function initScheduler(...) { ... }\n```\n"
  }
```
- Errors:
  - 400 invalid_params
  - 404 repo_not_found | index_empty
  - 503 embeddings_unavailable
  - 504 deadline_exceeded (if no hits available); if at least one hit, return 200 with complete=false.

5) GET /v1/chunks/{id}
- 200 body:
```
  {
    "chunk_id": "uuid",
    "repo": "repoa",
    "path": "src/scheduler/index.ts",
    "lang": "typescript",
    "symbol": {"kind": "function", "name": "initScheduler", "path": "Scheduler.initScheduler"},
    "start_line": 42,
    "end_line": 86,
    "content": "export function initScheduler(...) { ... }",
    "resource_link": "kb://repoa/src/scheduler/index.ts#L42-L86"
  }
```
- Errors: 404 chunk_not_found

6) GET /v1/file
- Query: repo (string), path (string), start (int), end (int)
- Purpose: read file content slice from disk (always fresh, not from indexed snapshot).
- Range validation:
  - start must be >= 1
  - end must be >= start
  - If end > file line count, auto-clamp to file bounds with warning in meta
  - If start == end, return single line
- 200 body:
```
  {
    "repo": "repoa",
    "path": "src/scheduler/index.ts",
    "start_line": 30,
    "end_line": 120,
    "content": "...file slice...",
    "lang": "typescript",
    "source": "disk",
    "symbol_context": [{"kind": "class", "name": "Scheduler", "path": "Scheduler"}], // pre-computed during indexing; empty array if unavailable
    "_meta": {
      "warnings": ["end_line clamped to file bounds (120 → 115)"]
    }
  }
```
- Errors: 400 invalid_range | 404 file_not_found | 404 repo_not_found

Notes:
- Path matching uses prefix and glob via pathspec. An entry containing wildcard characters is treated as a glob; otherwise treated as a prefix.
- Repo names: stored and matched with original casing (case-sensitive). Paths retain filesystem case sensitivity.
- Snapshot policy: all search responses reflect the latest indexed snapshot (manual reindexing only); no commit IDs or timestamps are exposed. File reads via /v1/file always read from disk (fresh content).
- Token counting: uses tiktoken library with cl100k_base encoding (pre-computed during indexing, stored in chunk metadata).
- Symbol context: pre-computed during indexing via tree-sitter for Py/TS/MD. If parsing failed or language unsupported, returns empty array (no error).

D. MCP Interface (TypeScript/Node)

Tier 1 Tools
1) search_knowledge
- Params:
  - query (string, required)
  - repos (array[string], optional)
  - path_prefix (array[string], optional)
  - top_k (int, default 5, max 20)
  - max_snippets (int, optional; ≤ top_k)
  - deadline_ms (int, optional)
  - embed_model ("small"|"large"; default "small")
  - score_cutoff (float, optional)
- Behavior:
  - Maps directly to POST /v1/search, applying client-side clamping and repo name normalization.
  - Returns MCP blocks:
    - text: one-line summary + stitched prompt_ready (size-capped to ≤ 50 KB total MCP payload).
    - citations: for each hit, a resource_link (kb://repo/path#Lstart-Lend); if snippet ≤ 500 chars, include embedded resource with snippet.
  - data: compact hit list (chunk_id, score, repo, path, start_line, end_line), cursor, estimated_total (estimate), complete, warnings.
- Latency targets: p50 ≤ 600 ms, p95 ≤ 2 s.

2) fetch_chunk
- Params: chunk_id (string, required)
- Maps to GET /v1/chunks/{id}
- Returns:
  - text block: fenced code with language, plus citation resource_link.
  - data: complete chunk payload (no commit metadata).

3) fetch_lines
- Params: repo (string), path (string), start (int), end (int)
- Maps to GET /v1/file
- Returns:
  - text block: fenced code slice with citation.
  - data: slice payload.

4) open_in_editor
- Params: repo (string), path (string), line (int optional), column (int optional)
- Resolves absolute path by fetching repos via GET /v1/repos (cache result locally).
- Returns:
  - data.uri: vscode://file/ABSOLUTE_PATH:line:column (vscode-only by design).

Tier 2 Tools
5) get_vector_store_info
- Returns: namespaces/tables (chunks_small, chunks_large), dims (1536, 3072), counts, limits (top_k_max=20, snippet_caps), model_names, optional rolling latency estimates.

6) get_metadata
- Params: chunk_id (string)
- Returns: metadata for the chunk (same as /v1/chunks/{id} minus content if desired). No commit or indexing timestamps are returned.

E. Resource Link Schemes
- kb://{repo}/{path}#L{start}-L{end}  (implicitly refers to latest indexed snapshot)
- vscode://file/{absolute_path}:{line}:{column}

F. Performance and Timeouts
- Concurrency: query embedding concurrency = 8 (config; supports parallel tool calls from LLMs). Indexing concurrency = 3 (separate config). No server rate limiting in Sprint 1.
- deadline_ms:
  - If exceeded before embedding completes, return 504 deadline_exceeded.
  - If exceeded after embedding, and at least one hit available, return 200 with complete=false and a cursor for continuation.
  - If no hits available, return 504.
- Streaming: not implemented in Sprint 1 (return once all available results are ready).
- Query embedding cache: deferred.

G. Validation, Coercion, and Errors
- Light coercion and warnings:
  - Clamp top_k to [1, 20].
  - Clamp path_prefix count to 10; warn and ignore excess.
  - Clamp snippet tokens to ≤ 500; apply optional MCP char clamp if requested.
  - Ignore invalid path_prefix patterns with a warning.
- Error codes (REST):
  - 400 invalid_params (details)
  - 404 repo_not_found | index_empty | chunk_not_found | file_not_found
  - 409 schema_mismatch (fail fast if LanceDB/SQLite schema mismatch)
  - 503 embeddings_unavailable
  - 504 deadline_exceeded
- Error response schema (all errors):
```json
{
  "error": {
    "code": "repo_not_found",
    "message": "Repository 'nonexistent' not found",
    "details": {
      "available_repos": ["repoa", "repob"]
    },
    "remediation": "Check available repos at GET /v1/repos"
  }
}
```
- MCP error mapping: propagate concise error + remediation hint; include upstream code in data.

H. Logging (JSON Lines)
- Fields:
  - ts: ISO timestamp (machine-readable)
  - level: "debug" | "info" | "warn" | "error"
  - event: canonical action ("search", "fetch_chunk", "fetch_file", "repos_list", "repo_status")
  - context: optional object (e.g., {request_id, client: "mcp"|"rest"})
  - message: short human-readable summary
  - meta: flexible bag (latency_ms, top_k, model, hits_count, repos_count, path_prefix_count, warnings, error_code)
- Emit at info for request start/end with latency; warn for clamping and ignored params; error for provider failures/schema mismatch.

I. Implementation Notes (Server)
- Model routing: use single table per request: small → chunks_small (1536-d), large → chunks_large (3072-d).
- score_cutoff: use global default if not provided per request.
- Snippets: always include snippet_fenced (with language tag) when language is known; also include raw snippet.
- Pagination: cursor encodes table/model, filters, and offset as base64 JSON. estimated_total is an estimate (upper bound or heuristic) and may not be exact. complete indicates whether page fulfills request.
- path_prefix: implement both prefix and glob (pathspec). Wildcards imply glob.

J. Implementation Notes (MCP Bridge)
- Protocol: JSON-RPC 2.0 over stdio (MCP standard)
- Tool mapping:
  - search_knowledge → POST /v1/search (with include_prompt_ready=false by default)
  - fetch_chunk → GET /v1/chunks/{id}
  - fetch_lines → GET /v1/file
  - open_in_editor → compute vscode URI using repos cache (GET /v1/repos)
  - get_vector_store_info → combine static config and lightweight table probes
  - get_metadata → GET /v1/chunks/{id}
- Result shaping per MCP CallToolResult schema:
  - content: array of TextContent and EmbeddedResource blocks
  - For search results: one TextContent summary + EmbeddedResource for each hit (if snippet ≤ 500 chars)
  - Use type "resource" with embedded resource.text for inline code snippets
  - mimeType: language-specific ("text/x-python", "text/x-typescript", "text/markdown", "text/plain")
  - isError: false for successful calls; true for tool-level errors (not MCP protocol errors)
  - _meta: include compact hit list, cursor, estimated_total, complete, warnings
- Safety and caps: enforce MCP-side top_k ≤ 20 and total content payload ≤ ~50 KB (measured as JSON byte length).
- Error handling:
  - Tool execution errors (e.g., repo not found, invalid params): return CallToolResult with isError=true and error details in content
  - MCP protocol errors (e.g., tool not found, invalid request): return JSON-RPC error response
- Tool definitions:
  - All tools include descriptive inputSchema (JSON Schema) and optional outputSchema
  - Annotations for display: title (human-readable), readOnlyHint, openWorldHint as appropriate
  - search_knowledge: openWorldHint=false (closed corpus), readOnlyHint=true
  - fetch_chunk/fetch_lines: readOnlyHint=true, idempotentHint=true
  - open_in_editor: readOnlyHint=false (modifies editor state)

K. MCP Capabilities and Initialization
- Server capabilities:
  - tools: {listChanged: false} (tool list is static for Sprint 1)
  - logging: {} (server supports logging to client)
  - No resources, prompts, or sampling capabilities in Sprint 1
- Initialization flow:
  1. Client sends initialize request with protocolVersion "2025-06-18"
  2. Server responds with InitializeResult: protocolVersion, capabilities, serverInfo
  3. serverInfo: {name: "pb-kb-mcp", version: "0.1.0", title: "Plastic Beach Knowledge Store"}
  4. instructions: brief usage guide for LLM context (optional)
  5. Client sends initialized notification
  6. Connection ready for tool calls
- Progress notifications: not implemented in Sprint 1 (no long-running operations)
- Cancellation: implement CancelledNotification handler for client-initiated cancellation

L. Test Matrix (Phase 5)
- REST
  - /v1/health happy path
  - /v1/repos and /v1/repos/{name}/status
  - /v1/search with: defaults; repo filter; path_prefix (prefix + glob); score_cutoff; pagination; clamping warnings; errors (repo_not_found, invalid_params, embeddings_unavailable, deadline_exceeded)
  - /v1/chunks/{id} (happy and not found)
  - /v1/file (happy, invalid_range, not found)
- MCP
  - search_knowledge: defaults, filters, char clamp; latency targets (p50 ≤ 600 ms, p95 ≤ 2 s)
  - fetch_chunk by chunk_id
  - fetch_lines by repo/path/range
  - open_in_editor URI formation using repos cache
  - get_vector_store_info, get_metadata
  - Payload guardrails respected

L. Remaining Questions / Areas of Concern
- estimated_total method: We will return an estimate. Implementation detail: use a lightweight count heuristic from LanceDB (e.g., approximate row count or precomputed per-repo counts) to avoid heavy scans. Acceptable if estimates sometimes over/under-count by a modest factor.
- path glob semantics on Windows paths: treat all paths as normalized with forward slashes in the index; ensure matching logic normalizes separators before glob evaluation.
- tokenizer consistency: token-based truncation relies on cl100k_base; ensure this stays consistent with the embedding model for predictable snippet sizes.
- failure modes with empty indexes: if a repo is registered but has no vectors yet (indexing pending), return index_empty with guidance to run `kb index`.
- future mixed-model behavior: current cursor embeds a single model. When we add mixed-model search, cursor format will need a versioned shape to avoid collisions; we’ll reserve a `v` field in the encoded JSON for forward compatibility.

M. Configuration (Relevant Server Options)
- [server]
  - host = "127.0.0.1"
  - port = 7777
  - request_timeout_ms = 30000
- [embeddings]
  - provider = "openai"
  - api_key_env = "OPENAI_API_KEY"
  - default_embed_model = "small"
  - query_concurrency = 8
  - indexing_concurrency = 3
- [database]
  - lancedb_path = "~/.dolphin/knowledge_store/lancedb"
  - sqlite_path = "~/.dolphin/knowledge_store/knowledge.db"
  - cache_size_mb = 512
- [retrieval]
  - top_k_default = 5
  - top_k_max = 20
  - score_cutoff_default = 0.15
  - max_snippet_tokens_default = 240
  - max_snippet_tokens_cap = 500
  - max_path_prefix_count = 10
- [logging]
  - format = "jsonl"
  - level = "info"
  - log_path = "~/.dolphin/knowledge_store/logs"

N. Concrete Schemas (Illustrative)
- SearchRequest (REST):
```
  type: object
  required: [query]
  properties:
    query: {type: string}
    repos: {type: array, items: {type: string}}
    path_prefix: {type: array, items: {type: string}}
    top_k: {type: integer, minimum: 1, maximum: 100}
    max_snippet_tokens: {type: integer, minimum: 1}
    max_snippet_chars: {type: integer, minimum: 1}
    embed_model: {type: string, enum: ["small", "large"]}
    score_cutoff: {type: number}
    cursor: {type: string}
    deadline_ms: {type: integer, minimum: 50}
    max_snippets: {type: integer, minimum: 1}
```
- SearchResponse (REST):
```
  type: object
  properties:
    hits: {type: array, items: {$ref: "#/$defs/Hit"}}
    meta: {$ref: "#/$defs/Meta"}
    prompt_ready: {type: string}
  $defs:
    Hit:
      type: object
      properties:
        repo: {type: string}
        path: {type: string}
        lang: {type: string}
        symbol: {type: object, properties: {kind: {type: string}, name: {type: string}, path: {type: string}}}
        start_line: {type: integer}
        end_line: {type: integer}
        score: {type: number}
        snippet: {type: string}
        snippet_fenced: {type: string}
        chunk_id: {type: string}
        resource_link: {type: string}
    Meta:
      type: object
      properties:
        top_k: {type: integer}
        model: {type: string}
        latency_ms: {type: integer}
        timing: {type: object, properties: {embedding_ms: {type: integer}, search_ms: {type: integer}, processing_ms: {type: integer}}}
        cursor: {type: string}
        estimated_total: {type: integer}
        complete: {type: boolean}
        warnings: {type: array, items: {type: string}}
```
- MCP search_knowledge Result (conceptual):
```
  content: [
    {type: "text", text: "Found 5 results matching your query."},
    {type: "resource", resource: {uri: "kb://repo/path#Lstart-Lend", mimeType: "text/x-python", text: "...snippet..."}},
    {type: "text", text: "[Additional results available via cursor pagination]"}
  ]
  isError: false
  _meta: {
    hits: [{chunk_id, repo, path, start_line, end_line, score}],
    cursor, estimated_total, complete, warnings
  }
```
Note: MCP tools return CallToolResult with content array (TextContent | EmbeddedResource blocks). We use type "resource" with embedded resource for inline snippets, and include metadata in _meta field.
