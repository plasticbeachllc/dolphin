## O. Example API Usage (curl)

### 1) Health check (shallow)
```bash
curl http://127.0.0.1:7777/v1/health
# Response: {"status":"ok"}
```

### 2) Health check (deep)
```bash
curl "http://127.0.0.1:7777/v1/health?check=deep"
# Response: {"status":"ok","checks":{"lancedb":"ok","embeddings":"ok"}}
```

### 3) List repositories
```bash
curl http://127.0.0.1:7777/v1/repos
# Response: {"repos":[{"name":"myrepo","path":"/path/to/repo","default_embed_model":"small","files":123,"chunks":456}]}
```

### 4) Search for code
```bash
curl -X POST http://127.0.0.1:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "scheduler initialization",
    "repos": ["myrepo"],
    "path_prefix": ["src/**"],
    "top_k": 5,
    "include_prompt_ready": false
  }'
```

### 5) Fetch specific chunk
```bash
curl "http://127.0.0.1:7777/v1/chunks/550e8400-e29b-41d4-a716-446655440000"
```

### 6) Fetch file slice
```bash
curl "http://127.0.0.1:7777/v1/file?repo=myrepo&path=src/scheduler.ts&start=10&end=50"
```

### 7) Paginated search
```bash
# First page
curl -X POST http://127.0.0.1:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "top_k": 5}'
  
# Extract cursor from meta.cursor, then:
curl -X POST http://127.0.0.1:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "top_k": 5, "cursor": "<opaque_cursor>"}'
```

## P. Migration and Versioning Strategy

- **API versioning**: all endpoints prefixed with /v1; future breaking changes go to /v2
- **Cursor format versioning**: reserved "v" field in cursor JSON for forward compatibility
  - Current: `{model, repos, path_prefix, offset, top_k, score_cutoff}`
  - Future (mixed-model): `{v: 2, models: ["small", "large"], ...}`
- **MCP protocol version**: "2025-06-18" (current); server checks client version and rejects if incompatible
- **Database schema**: SQLite migrations tracked in alembic; LanceDB schema changes require reindexing
- **Feature flags** for gradual rollout:
  - streaming_results: false (Phase 6)
  - hybrid_search: false (Phase 6)
  - reranking: false (Phase 6)
  - query_cache: false (Phase 6)

## Q. Performance Benchmarks and Targets

### Latency targets (end-to-end search via MCP):
  - p50 ≤ 600 ms (target met with ~250ms embedding + ~100ms search + ~150ms processing)
  - p95 ≤ 2 s (includes tail latency from OpenAI API)
  - p99 ≤ 5 s (with retry backoff)

### Throughput:
  - Single-user: 10-20 QPS sustained
  - With query_concurrency=8: handle burst of 8 parallel tool calls from LLM

### Index size expectations:
  - Small repo (1K files, 50K chunks): <100 MB LanceDB + <5 MB SQLite
  - Medium repo (10K files, 500K chunks): ~1 GB LanceDB + ~50 MB SQLite
  - Large repo (100K files, 5M chunks): ~10 GB LanceDB + ~500 MB SQLite

### Memory usage:
  - Baseline (idle): ~200 MB (FastAPI + LanceDB cache)
  - Under load (8 concurrent): ~500 MB (embedding batches + result buffers)
  - LanceDB cache: configurable (default 512 MB)

### Load testing scenarios (to validate before production):
  - Sustained 10 QPS for 5 minutes
  - Burst of 8 concurrent requests (parallel tool calls)
  - Large result sets (top_k=20, multiple pages)
  - Slow embedding API simulation (2s latency)
  - Error recovery (OpenAI rate limiting, LanceDB connection loss)

## R. Implementation Decision Log

### Core Decisions:
- **estimated_total method**: return estimate using LanceDB approximate row count or precomputed per-repo counts (avoid heavy scans). Acceptable if estimates vary by modest factor; users should rely on complete flag for exhaustiveness.
- **path glob semantics on Windows**: normalize all paths to forward slashes during indexing; matching logic converts backslashes before glob evaluation.
- **tokenizer consistency**: cl100k_base tokenizer (tiktoken) used for both embedding API and snippet truncation; counts precomputed during indexing.
- **Empty index handling**: if repo registered but no vectors (indexing pending/failed), return 404 index_empty with remediation: "Run `kb index <repo>` to index this repository."
- **Mixed-model future**: cursor format includes reserved "v" field for versioning; v1 (current) has single model; v2 will support mixed-model queries.
- **Symbol context**: best-effort via tree-sitter; pre-computed during indexing; empty array if unavailable (no runtime penalty).
- **File content freshness**: /v1/file always reads from disk (fresh); search results reflect indexed snapshot (may be stale until reindex).

### MIME type mapping for MCP:
  - .py → text/x-python
  - .ts, .tsx, .js, .jsx → text/x-typescript (unified for JS family)
  - .md → text/markdown
  - unknown → text/plain

### Error recovery strategy:
  - OpenAI rate limit (429): exponential backoff with jitter; max 3 retries
  - OpenAI timeout (5xx): retry once after 1s
  - LanceDB connection loss: attempt reconnect; fail request if unsuccessful
  - Disk I/O errors (/v1/file): return 404 file_not_found even if metadata exists
