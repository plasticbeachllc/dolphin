# Unified Knowledge Store — Sprint 1 Prompt (.prompt)

Purpose
- Stand up a local-first code/document retrieval pipeline powering Open WebUI and Continue.
- Optimize for simplicity, idempotency, and cost control on macOS Apple Silicon.
- Provide clear seams for future upgrades (hybrid search, reranking, watch mode, routing).

Scope
1) Sources: code and Markdown within repos; no PDFs/OCR in Sprint 1.
2) Languages: TypeScript and Python primary; fallback windowing for others (e.g., Bash, Justfiles, plain text).
3) Integrations: Open WebUI via MCP; VS Code Continue via MCP context provider.
4) Storage: LanceDB for vectors; SQLite for metadata; local filesystem under ~/.dolphin/.

Decisions (final for Sprint 1)
1) Repos to index
   - lighthouse: SvelteKit app (TypeScript, Svelte, Markdown, some Bash/Just).
   - dolphin: this project’s repo (Python, TypeScript/TSX, Markdown, Bash/Just).
2) Continue integration
   - Use MCP tool (search_knowledge). Default scope is the active workspace repo.
3) Open WebUI integration
   - Register retriever via mcpo as tool name "search_knowledge". Use top_k=8 and max_snippet_tokens=240 by default.
4) Ignore/redaction policy
   - Respect repo .gitignore and additionally exclude .env (and .env.*). Keep default excludes for build/vendor/caches.
5) Embeddings
   - Provider: OpenAI. Default model: text-embedding-3-small. No per-repo override in Sprint 1.
6) Budget and concurrency
   - Per-session spend cap: 10.00 USD. Default concurrency: 3 embedding worker slots.
7) Chunking specifics
   - Target 400 tokens with ~10% overlap. For Markdown, strip headings from embedded chunk content for performance; capture nearest H1–H3 in metadata and optionally prepend to returned snippets (not embedded) for context.
8) LanceDB layout
   - One global collection per embedding dimension (e.g., chunks_small: 1536 dims; chunks_large: 3072 dims). Partition/filter by repo_name; store model and commit metadata per record.
9) Provenance
   - Require a clean working tree at index time; record HEAD commit SHA. Abort or require --force if dirty (Sprint 1: abort with a clear error).
10) Query defaults
   - Default scope to the active repo when none provided. top_k default 8; score_cutoff default 0.15; max_snippet_tokens default 240.
11) Security
   - API binds to 127.0.0.1 only. No auth/telemetry constraints in Sprint 1.
12) Storage paths
   - Base directory: ~/.dolphin/. Knowledge store root: ~/.dolphin/knowledge_store. SQLite DB and LanceDB collections reside under this root.

High-level architecture (frozen for Sprint 1)
1) Ingestion CLI (kb): scan repos, apply ignores, parse/chunk, canonicalize+hash, embed via OpenAI, write vectors to LanceDB and metadata to SQLite. Enforce budget.
2) Retriever HTTP service: FastAPI app exposes /v1/search and /v1/health; embeds query and searches LanceDB; returns ranked snippets with provenance.
3) MCP wrapper: Thin server exposing search_knowledge that proxies to retriever API for Open WebUI and Continue.
4) Data stores: LanceDB ANN index (global per-dimension collections) + SQLite for repos/files/chunks/sessions ledgers and configuration.

Implementation checklist
Phase 0 — Prerequisites
1) Verify Python ≥3.11, uv installed, and OPENAI_API_KEY available.
2) Ensure outbound HTTPS and Apple Silicon toolchain (Xcode CLT) for tree-sitter.
3) Validate a trivial embeddings call (optional smoke test).

Phase 1 — Project bootstrap
1) Initialize pyproject and src/pb_kb/ module skeleton.
2) Add dependencies (FastAPI, Uvicorn, Typer, LanceDB, Pydantic, tiktoken, OpenAI, tree-sitter, tree-sitter-languages, pathspec, python-dotenv, sqlite-utils).
3) Provide config file template with store_root, endpoint, concurrency, spend cap, ignores.
4) Create entrypoints (kb CLI stub and kb-api HTTP stub). Ensure they run.

Phase 2 — Metadata and storage
1) SQLite knowledge.db: create tables repos, files, sessions, chunks_meta with the specified columns; run migrations in kb init.
2) LanceDB: create chunks_small (1536) and chunks_large (3072) collections with metadata fields; persist model and dimensions.
3) kb status command: show repo count, file counts, vector counts per collection, and DB sizes.

Phase 3 — Ignore rules and scanning
1) Implement ignore resolution: combine .gitignore and default excludes (include .env and .env.* explicitly).
2) Scanner: enumerate only code and Markdown; record language guesses and candidate file set.

Phase 4 — Chunking
1) Tokenization via tiktoken; target ~400 tokens, ~10% overlap.
2) Chunkers: tree-sitter for TS/TSX and Python (symbol-level); fallback line windows for Bash, Justfiles, Svelte, Markdown, and unknown.
3) Canonicalize text (normalize line endings; strip trailing spaces) pre-hash.

Phase 5 — Hashing and idempotency
1) SHA256 of canonicalized chunk; upsert key includes repo, path, start_line, end_line, text_hash.
2) Pre-embed dedup: compare against chunks_meta to skip unchanged chunks.

Phase 6 — Embeddings and budget control
1) Batch embedding with concurrency 3; exponential backoff with jitter for 429/5xx.
2) Pre-estimate tokens and cost; abort early if projection exceeds remaining session cap of 10 USD.
3) Persist sessions ledger (tokens, estimated_cost_usd, timestamps, model) in SQLite.

Phase 7 — Ingestion CLI (Typer)
1) Commands: init, add-repo, index, status, prune.
2) Index: require clean working tree; accept branch and commit inputs; support --dry-run and --force.
3) Writes: vectors+metadata to LanceDB; provenance and cost ledger to SQLite.

Phase 8 — Retriever HTTP API (FastAPI)
1) Endpoints: /v1/health and /v1/search (inputs: query, repos[], path_prefix[], top_k, max_snippet_tokens, embed_model, score_cutoff).
2) Behavior: embed query with matching model; KNN in appropriate collection; filter by repo/path; truncate snippet tokens; return provenance (repo, path, symbol, line range, commit SHA, chunk_id) and meta (model, top_k, latency).

Phase 9 — MCP wrapper and integrations
1) MCP tool: search_knowledge proxying to /v1/search on localhost.
2) Open WebUI: register the tool via mcpo; set default top_k=8 and max_snippet_tokens=240 for agents.
3) Continue: configure MCP-based context provider; default scope is active workspace repo; fetch snippets before code Q&A.

Phase 10 — Safeguards and ergonomics
1) Logging: minimal structured logs for spend, embed calls, and search latency; no snippet text in logs required.
2) Data hygiene: confirm excludes (.env, secrets, build/vendor/caches) via scanner report; allow per-repo extra ignores.
3) Storage: base ~/.dolphin/ with knowledge_store subtree; document how to relocate via config.

Phase 11 — Testing and validation
1) Unit: chunkers (TS/Python), hashing stability, ignore effectiveness.
2) Integration: kb index on lighthouse and dolphin; /v1/search returns expected snippets; budget enforcement works.
3) Manual: from Open WebUI and Continue, use search_knowledge to answer grounded questions with provenance.

Defaults and configuration
1) store_root: ~/.dolphin/knowledge_store
2) endpoint: 127.0.0.1:7777
3) default_embed_model: small (text-embedding-3-small)
4) concurrency: 3
5) per_session_spend_cap_usd: 10.00
6) ignore: use .gitignore + explicit excludes (.env, .env.*, node_modules, dist, build, .next, .venv, .mypy_cache, .pytest_cache, .DS_Store, .secrets, coverage, .cache, target, vendor)
7) retrieval: top_k default 8; score_cutoff default 0.15; max_snippet_tokens default 240

Tradeoffs and rationale
1) Markdown headings stripped from embedded content
   - Pros: reduces duplicate anchors across chunks, improves token efficiency and ANN recall on content-bearing text.
   - Cons: headings carry topical context; mitigation: store H1–H3 in metadata and optionally prepend to returned snippets without re-embedding.
2) Global per-dimension LanceDB collections
   - Pros: simple cross-repo queries; avoids vector dimension collisions; fewer collections to manage.
   - Cons: large collections may grow over time; mitigated by repo filters and periodic pruning.
3) Require clean working tree
   - Pros: deterministic provenance; prevents indexing of uncommitted secrets.
   - Cons: extra step before indexing; mitigated by explicit --force when needed in later sprints.

Operational quick start (conceptual)
1) Initialize the store and configuration.
2) Register repos lighthouse and dolphin with absolute paths and default model small.
3) Index each repo on the desired branch/commit with a clean working tree.
4) Start the retriever API locally on 127.0.0.1:7777.
5) Register the MCP search_knowledge tool with mcpo and enable in Open WebUI.
6) Configure Continue to use the MCP tool and default scope to the active workspace repo.

Open items (deferred or confirm later)
1) Do we want to capture and return Markdown heading metadata in the snippet payload by default, or expose it as a toggle per request?
2) Any repo-specific extra ignore patterns for lighthouse or dolphin beyond the defaults?
3) Timing for hybrid retrieval (SQLite FTS5 + dense) and reranking after Sprint 1.

This prompt is authoritative for Sprint 1; keep it updated as decisions evolve. 