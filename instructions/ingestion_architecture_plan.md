# Ingestion Architecture Plan — Scanner Integration (Sprint 1)

Purpose
- Wire the repository scanner into the ingestion pipeline to produce a high-fidelity catalog of candidate files for chunking, embedding, and indexing.
- Enforce provenance and security guards (clean working tree, ignore policy).
- Persist file metadata for stability and idempotency.

Scope (this phase only)
- Resolve registered repos and validate a clean working tree.
- Build effective ignore sets, scan tracked files, and classify language.
- Persist/update files table and session counters.
- Defer chunking, hashing, and embeddings to the next phase.

Key principles
- Tracked-only: derive candidate files from Git’s index to implicitly respect .gitignore.
- Hygiene: apply additional ignore rules to tracked files to avoid secrets/caches.
- Idempotency: upsert files by (repo_id, path). No duplicates.
- Provenance: sessions capture commit and branch; require a clean working tree.

Core components
- CLI (kb index)
  - Entry point; loads config and calls IngestionPipeline.run(...).
- RepoResolver (SQLite)
  - Get (repo_id, root_path, default_embed_model) from repos by name; fail if missing.
- WorkingTreeGuard (git)
  - Ensure clean working tree for tracked content; capture commit (40 chars) and branch name.
- IgnoreSetBuilder
  - Merge default ignores + config extras + security hygiene into a pathspec.
- Scanner (existing)
  - Enumerate tracked files; filter submodules, symlinks, ignores, binaries; classify language; return FileCandidate list.
- FileCatalogWriter (SQLite)
  - Upsert into files table; update latest_commit_sha post-success.
- SessionManager (SQLite)
  - Create session row at start; update counters; set status (running/succeeded/failed).

Data contracts
- FileCandidate (scanner output)
  - repo_root: Path
  - rel_path: string (POSIX, e.g., "src/app/main.py")
  - abs_path: Path
  - ext: string | null (lowercased dot-extension)
  - language: string (e.g., "python", "typescript", "markdown", "text")
  - size_bytes: int
  - is_binary: bool (scanner omits true; included for completeness)
- Repo (SQLite.repos)
  - id, name, root_path, default_embed_model
- Session (SQLite.sessions)
  - id, repo_id, commit_sha (40), branch, embed_model, files_indexed, chunks_indexed, vectors_written, status, started_at, ended_at
- File (SQLite.files)
  - id, repo_id, path (POSIX), ext, language, is_binary, size_bytes, latest_commit_sha, created_at, updated_at

Sequence (kb index <repoName>)
1) Resolve repo
- Lookup by name → (repo_id, root_path, default_embed_model).
- Compute session embed_model (repo default for Sprint 1).

2) Guard and provenance
- Clean check (tracked-only):
  - git -C {root} update-index -q --refresh
  - git -C {root} diff-index --quiet HEAD -- (non-zero → abort)
- Capture:
  - commit_sha: git -C {root} rev-parse HEAD (assert 40 chars)
  - branch: git -C {root} rev-parse --abbrev-ref HEAD

3) Start session
- Insert sessions row: (repo_id, commit_sha, branch, embed_model, status=running).
- Capture session_id for counters and final status.

4) Build ignore set
- Base: DEFAULT_IGNORE_PATTERNS (build, caches, venvs, OS) + security hygiene:
  - **/id_rsa, **/*.pem, **/.aws/**, **/gcloud/**, **/secrets/**, **/*keys.json, **/*service_account.json, **/*auth.json
- Merge config.ignore extras.
- Produce a PathSpec (gitwildmatch) matcher for POSIX rel paths.

5) Scan
- Call scan_repo(root, ignores) → [FileCandidate].
- Scanner behavior:
  - List tracked files via git ls-files -z.
  - Detect and skip submodules via git submodule status --recursive.
  - Apply pathspec ignores, skip symlinks and non-files.
  - Skip binary (NUL byte or UTF-8 decode failure), compute size.
  - Classify language via extension/filename mapping.

6) Persist file catalog (dry-run respected)
- If not dry-run:
  - For each candidate: upsert files (UNIQUE(repo_id, path)) with ext, language, is_binary=0, size_bytes.
  - Defer latest_commit_sha update until the full index succeeds (post-embedding), or record now if we treat scan as success milestone (choose one policy; prefer post-embedding).
- Update sessions.files_indexed = number of candidates.

7) Finalize session (scan phase)
- If the pipeline proceeds directly into chunking/embedding, leave status=running and carry session_id forward.
- If scan-only mode ends here, set status=succeeded.
- On any error, set status=failed with notes.

Ignore and language policies
- .gitignore respected implicitly via tracked-only enumeration.
- Additional ignores applied even to tracked files to avoid secrets and large vendor artifacts.
- Language classification is extension/filename-driven with conservative fallback to "text" to keep chunking robust.

Git details
- Clean working tree check (tracked files only):
  - update-index --refresh; diff-index --quiet HEAD --
- Provenance strings:
  - commit SHA: 40 chars; branch: string
- Submodule roots:
  - submodule status --recursive → collect submodule path prefixes; skip files under those prefixes.

Observability
- Minimal structured logging (no snippet content):
  - repo name, session_id, commit_sha, branch
  - counts: files_tracked, files_kept, files_skipped_{ignored,submodule,symlink,binary}, bytes_total_kept
  - final: files_indexed, session status, latency

Error handling
- Repo missing → instruct kb add-repo.
- Not a Git repo or git not installed → fail with guidance.
- Dirty working tree → abort with actionable message (commit/stash; later add --force).
- Pathspec parse issues → warn and continue without offending pattern.
- File I/O errors → skip and count under skipped_other (optional).

Interfaces implemented (SQLiteMetadataStore)
- ✅ get_repo_by_name(name: str) -> {id, root_path, default_embed_model} | None
- ✅ begin_session(repo_id: int, commit_sha: str, branch: str, embed_model: str) -> int
- ✅ set_session_status(session_id: int, status: str, notes: str | None = None) -> None
- ✅ bump_session_counters(session_id: int, *, files_indexed: int | None = None, chunks_indexed: int | None = None, vectors_written: int | None = None) -> None
- ✅ upsert_file(repo_id: int, path: str, ext: str | None, language: str | None, is_binary: bool, size_bytes: int | None) -> int
- ✅ set_file_latest_commit(repo_id: int, path: str, commit_sha: str) -> None

Pipeline API implemented (IngestionPipeline)
- ✅ scan(repo_name: str, *, dry_run: bool = False, force: bool = False) -> dict
  - Orchestrates steps 1–6; returns summary for logging and next phases.
  - Supports --force flag to bypass clean working tree check.
- run(...) will extend scan() with chunking, hashing, embeddings, and persistence in subsequent phases.

Acceptance criteria (implemented)
- ✅ kb index <repo> (clean tree) creates a session and (if not dry-run) upserts file rows; updates files_indexed.
- ✅ Scanner honors .gitignore implicitly and additional ignores explicitly; skips submodules, symlinks, binaries.
- ✅ Language tags align with extension/filename rules.
- ✅ No snippet content is logged.
- ✅ --force flag allows bypassing clean working tree check with warning.

Implementation completed
1) ✅ Extend SQLiteMetadataStore with the new methods (repo lookup, sessions, file upserts, counters).
2) ✅ Implement IngestionPipeline.scan() to orchestrate repo resolution, guard/provenance, ignore merge, scan, and DB writes.
3) ✅ Wire kb index to call scan() (honor --dry-run, --force) and print a concise summary.
4) ✅ Add unit tests for SQLiteMetadataStore methods.

Next phases
- Phase 4: Implement chunking with token-based windowing and language-specific parsers
- Phase 5: Implement hashing and idempotency checks
- Phase 6: Implement embeddings and budget control
- Phase 7: Complete ingestion CLI with full pipeline
- Phase 8: Implement retriever HTTP API
- Phase 9: MCP wrapper and integrations

Notes
- Keep paths POSIX-style for storage consistency.
- Do not follow symlinks during scanning.
- Do not traverse submodules; register them as independent repos when needed.
- Keep this plan minimal and focused; chunking, hashing, and embeddings follow next.
