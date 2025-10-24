# Unified Knowledge Store — Sprint 1 Prompt (.prompt)

Purpose
- Stand up a local-first code/document retrieval pipeline powering Open WebUI and Continue.
- Optimize for simplicity, idempotency, and cost control on macOS Apple Silicon.
- Provide clear seams for future upgrades (hybrid search, reranking, watch mode, routing).

Scope
1) Sources: code and Markdown within repos; no PDFs/OCR in Sprint 1.
2) Languages: TypeScript and Python primary; fallback windowing for others (e.g., Bash, Justfiles, Svelte, plain text).
3) Integrations: Open WebUI via MCP; VS Code Continue via MCP context provider.
4) Storage: LanceDB for vectors; SQLite for metadata; local filesystem under ~/.dolphin/.

Decisions (final for Sprint 1)
1) Repos to index
   - lighthouse (SvelteKit app). Absolute path: /Users/tdc/worktable/lighthouse/
   - dolphin (this project). Absolute path: /Users/tdc/worktable/dolphin/
2) Continue integration
   - Use MCP tool named "search_knowledge". Default scope is the active workspace repo.
3) Open WebUI integration
   - Register retriever via mcpo as tool name "search_knowledge". Use top_k=8 and max_snippet_tokens=240 by default.
4) Ignore/redaction policy
   - Respect repo .gitignore and additionally exclude .env and .env.*. Apply a generic Node/SvelteKit ignore template (see Defaults and configuration → ignore).
5) Embeddings
   - Provider: OpenAI. Default model: text-embedding-3-small. No per-repo override in Sprint 1.
6) Budget and concurrency
   - Per-session spend cap: 10.00 USD. Default concurrency: 3 embedding worker slots.
7) Chunking specifics
   - Target 400 tokens with ~10% overlap. For Markdown, strip headings from embedded chunk content; persist nearest H1–H3 as metadata and optionally prepend to returned snippets (not embedded) for context.
8) LanceDB layout
   - One global collection per embedding dimension (e.g., chunks_small: 1536 dims; chunks_large: 3072 dims). Partition/filter by repo_name; store model and commit metadata per record.
9) Provenance
   - Require a clean working tree at index time; record HEAD commit SHA. Abort with a clear error if dirty.
10) Query defaults
   - Default scope to the active repo when none provided. top_k default 8; score_cutoff default 0.15; max_snippet_tokens default 240.
11) Security
   - API binds to 127.0.0.1 only. No additional auth or telemetry constraints in Sprint 1.
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
1) Implement ignore resolution: combine .gitignore with a default exclude set that includes secrets, build outputs, caches, and SvelteKit artifacts (see Defaults and configuration → ignore).
2) Scanner: enumerate only code and Markdown; detect language; record candidate file set.

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
2) Index: require clean working tree; accept branch and commit inputs; support dry-run and force flags.
3) Writes: vectors+metadata to LanceDB; provenance and cost ledger to SQLite.

Phase 8 — Retriever HTTP API (FastAPI)
1) Endpoints: /v1/health and /v1/search (inputs: query, repos, path_prefix, top_k, max_snippet_tokens, embed_model, score_cutoff).
2) Behavior: embed query with matching model; run KNN in the appropriate collection; filter by repo/path; truncate snippet tokens; return provenance (repo, path, symbol, line range, commit SHA, chunk_id) and meta (model, top_k, latency).

Phase 9 — MCP wrapper and integrations
1) MCP tool: search_knowledge proxying to /v1/search on localhost.
2) Open WebUI: register the tool via mcpo; set default top_k=8 and max_snippet_tokens=240 for agents.
3) Continue: configure MCP-based context provider; default scope is active workspace repo; fetch snippets before code Q&A.

Phase 10 — Safeguards and ergonomics
1) Logging: minimal structured logs for spend, embed calls, and search latency; snippet text in logs not required.
2) Data hygiene: confirm excludes via scanner report; allow per-repo extra ignores.
3) Storage: base ~/.dolphin/ with knowledge_store subtree; document how to relocate via config.

Phase 11 — Testing and validation
1) Unit: chunkers (TS/Python), hashing stability, ignore effectiveness.
2) Integration: index lighthouse and dolphin; /v1/search returns expected snippets; budget enforcement works.
3) Manual: from Open WebUI and Continue, use search_knowledge to answer grounded questions with provenance.

Defaults and configuration
1) store_root: ~/.dolphin/knowledge_store
2) endpoint: 127.0.0.1:7777
3) default_embed_model: small (text-embedding-3-small)
4) concurrency: 3
5) per_session_spend_cap_usd: 10.00
6) ignore (default exclude set applied in addition to .gitignore and explicit .env/.env.*):
   - Secrets and env: .env, .env.*, .secrets
   - Node/NPM/PNPM/Yarn: node_modules, .npm, .pnpm-store, yarn.lock integrity caches
   - Build/outputs: dist, build, coverage, .cache, target, vendor
   - Frameworks (SvelteKit/Vite/Next): .svelte-kit, .vercel, .vite, .next
   - Virtual envs and tooling: .venv, .mypy_cache, .pytest_cache
   - OS/editor: .DS_Store
   - Project-specific: add additional patterns per repo if needed
7) retrieval: top_k default 8; score_cutoff default 0.15; max_snippet_tokens default 240

Tradeoffs and rationale
1) Markdown headings stripped from embedded content
   - Pros: reduces duplicate anchors across chunks; improves token efficiency and ANN recall on content-bearing text.
   - Cons: headings carry topical context; mitigation: store H1–H3 in metadata and optionally prepend to returned snippets without re-embedding.
2) Global per-dimension LanceDB collections
   - Pros: simple cross-repo queries; avoids vector dimension collisions; fewer collections to manage.
   - Cons: collections may grow; mitigated by repo filters and periodic pruning.
3) Require clean working tree
   - Pros: deterministic provenance; prevents indexing of uncommitted secrets.
   - Cons: extra step before indexing; mitigated by an explicit force flag in later sprints.

Operational quick start (concrete)
1) Initialize the knowledge store and configuration under ~/.dolphin/knowledge_store.
2) Register repos with names and absolute paths:
   - Name: lighthouse, Path: /Users/tdc/worktable/lighthouse/, Default model: small
   - Name: dolphin, Path: /Users/tdc/worktable/dolphin/, Default model: small
3) Ensure both repos have a clean working tree on the target branch; record HEAD commit SHAs.
4) Index lighthouse and dolphin within the per-session cap (10 USD) using concurrency 3.
5) Start the retriever API on 127.0.0.1:7777.
6) Register the MCP tool search_knowledge via mcpo and enable it in Open WebUI.
7) Configure Continue to use the MCP tool; default scope should be the active workspace repo; fetch snippets before answering code questions.

Open items (confirm or defer)
1) Return behavior for Markdown heading metadata (always prepend in the snippet payload vs. behind a request flag).
2) Any additional repo-specific ignore patterns beyond the generic set (e.g., .turbo, .netlify) to add now.
3) Timing to add hybrid retrieval (SQLite FTS5 + dense) and an optional reranker after Sprint 1.

This prompt is authoritative for Sprint 1 execution. Keep it updated as we progress.