# Unified Knowledge Store — Schema (.prompt)

Purpose
- Define the authoritative metadata and vector store schema for Sprint 1.
- Optimize for idempotency, provenance, and simple cross-repo retrieval.
- Keep implementation seams clear for future hybrid search and reranking.

Scope (Sprint 1)
- Metadata: SQLite at `~/.dolphin/knowledge_store/knowledge.db`.
- Vectors: LanceDB at `~/.dolphin/knowledge_store/lancedb`.
- Collections: one per embedding dimension (global), initially `chunks_small` (1536) and `chunks_large` (3072).
- Provenance: clean working tree required at index time; record HEAD commit.

Invariants
- One global collection per dimension; filter by `repo` and (optionally) `path_prefix` at query time.
- Idempotent ingestion: for a given `(repo, file, commit, start_line, end_line, text_hash, embed_model)`, never re-embed or duplicate metadata.
- Persist chunk text once per unique `text_hash` in SQLite for stable snippet generation independent of filesystem state; H1–H3 heading context is stored as metadata (not embedded) and is always prepended to returned snippets.

---

SQLite schema (authoritative)

Notes
- Enable `PRAGMA foreign_keys = ON`.
- Timestamps are stored as `TEXT` in ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- Keep schema minimal for Sprint 1; defer per-file history beyond current commit.
- Store full 40-character Git commit SHAs; sessions also record branch.
- Scanning is tracked-only: include tracked files not ignored by .gitignore; skip symlinks; follow submodules only if separately registered as repos.

SQL
```sql
-- Enable FK enforcement
PRAGMA foreign_keys = ON;

-- Logical repositories registered for indexing/retrieval
CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  root_path TEXT NOT NULL,
  default_embed_model TEXT NOT NULL DEFAULT 'small',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ingestion sessions are budget/accounting units and capture the HEAD commit
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL CHECK (length(commit_sha) = 40),
  branch TEXT NOT NULL,
  embed_model TEXT NOT NULL DEFAULT 'small',
  files_indexed INTEGER NOT NULL DEFAULT 0,
  chunks_indexed INTEGER NOT NULL DEFAULT 0,
  vectors_written INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running', -- running | succeeded | failed | aborted
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  ended_at TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_repo_commit ON sessions(repo_id, commit_sha);

-- Files deduplicated by (repo, path); keep lightweight attributes
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  path TEXT NOT NULL, -- POSIX-style relative path from repo root
  ext TEXT,           -- e.g., '.py', '.md'
  language TEXT,      -- coarse tag: 'python' | 'typescript' | 'markdown' | 'text' | ...
  is_binary INTEGER NOT NULL DEFAULT 0,
  size_bytes INTEGER,
  latest_commit_sha TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (repo_id, path)
);
CREATE INDEX IF NOT EXISTS idx_files_repo_path ON files(repo_id, path);

-- Deduplicated chunk text stored once per content hash
CREATE TABLE IF NOT EXISTS chunk_texts (
  text_hash TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunk_texts_created_at ON chunk_texts(created_at);

-- Chunk metadata per occurrence (per commit); vectors live in LanceDB
CREATE TABLE IF NOT EXISTS chunks_meta (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL,
  -- location and structure
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  symbol_kind TEXT,     -- e.g., 'function' | 'class' | 'module' | null
  symbol_name TEXT,
  symbol_path TEXT,     -- hierarchical name (e.g., 'pkg.mod:Class.method')
  -- markdown headings (not embedded)
  h1 TEXT,
  h2 TEXT,
  h3 TEXT,
  -- content identity & accounting
  text_hash TEXT NOT NULL REFERENCES chunk_texts(text_hash) ON DELETE RESTRICT, -- sha256(canonicalize_text(chunk_text))
  token_count INTEGER NOT NULL,    -- tokens in chunk_text used for embedding
  embed_model TEXT NOT NULL,       -- 'small' | 'large'
  vector_dim INTEGER NOT NULL,     -- 1536 | 3072
  vector_collection TEXT NOT NULL, -- 'chunks_small' | 'chunks_large'
  vector_id TEXT NOT NULL,         -- primary key of the LanceDB record (chunk_uid)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  -- idempotency: do not duplicate this exact chunk occurrence
  UNIQUE (repo_id, file_id, commit_sha, start_line, end_line, text_hash, embed_model)
);
CREATE INDEX IF NOT EXISTS idx_chunks_repo_file_commit ON chunks_meta(repo_id, file_id, commit_sha);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks_meta(text_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_vector ON chunks_meta(vector_collection, vector_id);
```

Semantics
- `repos`: Declarative registration; `name` is the external scope key used by tools.
- `sessions`: Each `kb index` run creates a session row; budget tracking happens here.
- `files`: Stable identity by `(repo_id, path)`; we update `latest_commit_sha` after a successful session that touches the file.
- `chunks_meta`: One row per chunk occurrence tied to `commit_sha`; references the LanceDB record via `(vector_collection, vector_id)`.

Idempotency and keys
- Compute `text_hash = sha256(canonicalize_text(chunk_text))`.
- Define `chunk_uid = sha256("repo={repo}|path={path}|commit={commit_sha}|start={start_line}|end={end_line}|hash={text_hash}|model={embed_model}")`.
  - Use `chunk_uid` as `vector_id` in LanceDB and store it in `chunks_meta.vector_id`.
  - Upsert rule: if a row with the same `(repo_id, file_id, commit_sha, start_line, end_line, text_hash, embed_model)` exists, skip re-embedding and LanceDB upsert.
- Enhancement (tracked for later, not Sprint 1): if any LanceDB record exists with the same `(text_hash, embed_model)`, allow vector reuse to avoid re-embedding across repos.

---

LanceDB schema (authoritative)

Collections
- `chunks_small` — 1536 dimensions (OpenAI `text-embedding-3-small`).
- `chunks_large` — 3072 dimensions (reserved for future larger models).

Record shape (Arrow schema)
- `id: string` — `chunk_uid` (primary key for idempotent upserts).
- `vector: list<float>[D]` — embedding vector (D = 1536 or 3072).
- `repo: string` — logical repo name (matches `repos.name`).
- `path: string` — POSIX relative path from repo root.
- `start_line: int32` — 1-based inclusive.
- `end_line: int32` — 1-based inclusive.
- `text_hash: string` — sha256 of canonicalized chunk text.
- `commit: string` — HEAD commit SHA recorded at index time.
- `branch: string` — branch name captured at session start.
- `embed_model: string` — model bucket: `small` or `large`.
- `language: string?` — coarse language tag.
- `symbol_kind: string?` — function/class/module, etc.
- `symbol_name: string?` — leaf symbol name.
- `symbol_path: string?` — hierarchical symbol path.
- `heading_h1: string?` — nearest H1 (Markdown only).
- `heading_h2: string?` — nearest H2.
- `heading_h3: string?` — nearest H3.
- `token_count: int32` — tokens in embedded content.
- `created_at: timestamp[us, tz=UTC]` — server-side ingest time.

Indexes and filters
- Vector index: default ANN index created by LanceDB per collection.
- Metadata filters at query time: `repo == ?` and optional `path LIKE 'prefix/%'`.
- Score cutoff handled in the retriever; store raw scores only transiently.

Upsert contract
- Primary key: `id = chunk_uid`.
- When inserting, include all metadata columns and `vector`.
- If a record with the same `id` exists, treat as no-op (idempotent re-run of the same commit) and skip write.

---

Search response mapping (for retriever)
- `repo` ← LanceDB `repo`.
- `path` ← LanceDB `path`.
- `start_line`, `end_line` ← LanceDB.
- `provenance.commit` ← LanceDB `commit`.
- `provenance.text_hash` ← LanceDB `text_hash`.
- `snippet`, `truncated`, `snippet_tokens`, `total_tokens` ← computed at query time from the persisted chunk text (via `text_hash` → SQLite `chunk_texts`) to ensure stability across file changes.

---

Operational notes
- Initialization:
  - On `kb init`, ensure SQLite file exists and run the DDL above.
  - Ensure LanceDB root exists; create `chunks_small` and `chunks_large` with the Arrow schema specified (metadata columns + `vector`).
- Tokenization:
  - Use model-specific `tiktoken` for embeddings and `token_count` computation.
  - Snippet construction prepends available H1–H3 heading metadata.
- Scanning rules:
  - Include only tracked files (per Git index) that are not ignored by `.gitignore`.
  - Skip symlinks; follow submodules only when those submodule roots are independently registered as repos.
- Budget (descoped in Sprint 1):
  - No spend cap enforcement; retry with exponential backoff + jitter on transient failures; concurrency default 3.
  - Keep `files_indexed`, `chunks_indexed`, and `vectors_written` counters for status only.
- Provenance:
  - Fail only on tracked changes; ignore untracked/ignored files when checking for a clean working tree.
  - Capture commit SHA (40 chars) and branch at session start; store in `sessions` and per chunk (commit only per chunk).
- Retention and pruning:
  - Eagerly create both LanceDB collections on init.
  - Keep the last N sessions per repo (N configurable later); add `kb prune` in v2.

Open items (documented, can be added later)
- File history table to record per-commit file-level stats for diffs and pruning.
- Global embedding reuse: query LanceDB by `(text_hash, embed_model)` to copy vectors without re-embedding across repos.
- SQLite triggers to auto-update `updated_at` fields.
- Optional JSON column for additional language/tool-specific metadata (e.g., TS import graph pointers).

This schema is authoritative for Sprint 1 and aligns with immediate next steps in execution-1.

---

MCP tool request shapes (proposals)

Option A — Minimal
```
{
  "query": "calibration metrics"
}
```

Option B — Scoped (recommended default)
```
{
  "query": "calibration metrics",
  "repos": ["active"],
  "path_prefix": ["src/", "docs/"],
  "top_k": 8,
  "max_snippet_tokens": 240,
  "score_cutoff": 0.15
}
```

Option C — Advanced overrides
```
{
  "query": "calibration metrics",
  "repos": ["lighthouse", "dolphin"],
  "path_prefix": ["src/widgets/"],
  "top_k": 12,
  "max_snippet_tokens": 320,
  "score_cutoff": 0.10,
  "embed_model": "small"
}
```

Defaults
- Active repo scope when `repos` omitted or includes `"active"`.
- Multiple `path_prefix` values supported; interpreted as OR filters under the chosen repo scope.
- Server applies default `top_k`, `max_snippet_tokens`, and `score_cutoff` but allows per-request overrides.

Security and hygiene additions
- Extend default ignores with common secret paths (examples): `**/id_rsa`, `**/*.pem`, `**/.aws/**`, `**/gcloud/**`, `**/secrets/**`, `**/*keys.json`, `**/*service_account.json`, `**/*auth.json`.
- Avoid logging snippet text; logs should include request ids, counts, and resource identifiers only.
