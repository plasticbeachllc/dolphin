# pb-dolphin v0.2.2 Patch Plan

## Scope and Constraints

- Target release: `pb-dolphin` `0.2.2`
- MCP bridge: no version bump in this plan (already at `0.2.3`); only coordinate `0.2.4` if a KB contract change makes it necessary.
- Startup behavior: metadata schema migrations run automatically at startup, with a clear user-facing note.
- Schema support policy: schema `v1` is the first and only supported runtime schema for `pb-dolphin` `0.2.2`.
- Query UX: default CLI output is compact and human-friendly; detailed internals stay behind `--verbose`.
- Interactive query mode: explicitly out of scope for this release.

## Release Goals

1. Improve metadata safety and deletion correctness.
2. Improve end-user CLI clarity and search usability.
3. Improve maintainability through explicit migration/versioning and stronger release gates.
4. Improve product presentation and onboarding docs.

## Non-goals

- New ranking algorithms or major retrieval feature expansion.
- MCP bridge feature development (unless required for compatibility).

## Current State (as of 2026-02-20)

- FK deletion-order regression has been fixed in ingestion deletion flow.
- MCP graph fixture integration test expectation has been updated and integration suite is passing.
- Changelog has pending unreleased entries and should be finalized during release PR.
- MCP dependency hardening has reduced Bun audit findings from 11 to 1 remaining tooling advisory (`eslint` transitively requiring `ajv@6.x`).

## Execution Status (as of 2026-02-20)

- PR1 - Schema Versioning and Migration Framework: completed
  - Added fresh migration registry and startup auto-migration path.
  - Added schema version tracking table and startup migration note logging.
  - Added unit coverage for schema version creation and pending migration auto-apply behavior.
- PR2 - Canonical Migration Set for Existing Metadata: completed
  - Added canonical `v1` migration to normalize known legacy table variants.
  - Added migration coverage for alias-table normalization and FK cascade repair.
  - Established `v1` as the only supported runtime schema in this release line.
- PR3 - Deleted-File Reliability and Integrity Gates: completed
  - Unified sync/async deleted-file handling through a shared cleanup path.
  - Fixed `dry_run` deletion behavior to be non-mutating while still reporting intent.
  - Added actionable FK-deletion diagnostics and integration assertions using `PRAGMA foreign_key_check`.
  - Added regression coverage for bulk deleted-file cleanup across mixed embedding models.
- PR4 - Query UX Upgrade (CLI Search): completed
  - Default `dolphin search` output is now compact and high-signal.
  - Added `--verbose` for expanded metadata/snippet output and stable `--json` output mode for scripting.
  - Added normalized filter flags (`--repo`, `--path`, `--exclude-path`, `--exclude-pattern`, `--lang`) plus context/snippet options.
  - Added CLI unit coverage for JSON schema, compact output, verbose rendering, and language filtering.
- PR5 - Terminal Beautification and Logging Signal Cleanup: completed
  - Added shared terminal status rendering utilities and wired `dolphin serve` + server lifecycle output to consistent high-signal rich formatting.
  - Kept structured logger output JSON-only; removed `DOLPHIN_LOG_FORMAT` mode switching to avoid dual-format complexity.
  - Reduced indexing progress noise by removing duplicate `Indexing file:` lines and keeping one per-file summary line.
  - Demoted chunker per-file completion logs from `INFO` to `DEBUG` to keep default output focused.
  - Improved shutdown reliability by adding explicit watcher stop + executor shutdown handling, preventing Ctrl-C double-interrupt hangs after server shutdown.
  - Added `*.log` to code-level default ignore patterns so log files are excluded even when running without a generated config file.
  - Added env-configurable log level (`DOLPHIN_LOG_LEVEL`) and opt-in traceback payloads (`DOLPHIN_LOG_TRACEBACK=1`).
  - Reduced default logging noise by omitting traceback blobs unless explicitly requested.
  - Added logger unit coverage for env-level wiring and traceback opt-in behavior.
- PR6 - README and Docs Refresh: completed
  - Refreshed README value proposition and quickstart with `uv run` command flow.
  - Added practical CLI query examples (`--verbose`, `--json`, `--lang`, path/pattern filters).
  - Documented canonical schema `v1` + startup auto-migration behavior in user docs and architecture notes.
  - Updated testing guide with focused verification commands for schema/deletion/query/logging changes.
- PR7 - Release Gate, Final QA, and v0.2.2 Cut: completed
  - Executed full release matrix (Python unit/integration/e2e, lint/type, MCP bridge tests, shared tests) with green results.
  - Finalized `CHANGELOG.md` entries for `0.2.2` including schema, deletion integrity, and CLI/logging UX updates.
  - Bumped Python package version to `0.2.2` (`pyproject.toml`, `kb/__init__.py`).
  - Addressed PR #151 review feedback: fixed invalid `graph_metrics` FK diagnostic query, removed CLI snippet magic number via constant, and fixed migration index-rename collision during table rebuilds.
  - Added regression coverage for graph-metrics dependency diagnostics and node-aliases rebuild with legacy index-name collisions.
- PR8 - MCP Dependency Security Hardening (post-v0.2.2 follow-up): in progress
  - Promoted MCP SDK to `^1.26.0` (outside vulnerable `<=1.25.3` range).
  - Added root workspace scoped overrides to force patched transitive runtime deps (`@modelcontextprotocol/sdk>ajv`, `>body-parser`, `>express>qs`, `>hono`, `>qs`) plus `minimatch@10.2.2`.
  - Verified MCP build/tests/lint remain healthy after lockfile regeneration.
  - Remaining advisory is tooling-only (`eslint` -> `ajv@6.x`) and requires lint-stack migration or upstream dependency movement for full elimination.

---

## PR1 - Schema Versioning and Migration Framework

### Objective

Introduce explicit metadata schema versioning and a migration runner with automatic startup execution.

### Implementation Steps

1. Add schema version metadata storage (`schema_version` table or equivalent).
2. Add migration registry with ordered migration IDs and idempotent execution contract.
3. Add migration runner API in KB metadata initialization path.
4. Wire startup auto-migration: run pending migrations before normal init completes.
5. Emit a clear startup note when migration(s) run, including from-version and to-version.

### Expected File Touchpoints

- `kb/store/sqlite_meta.py`
- `kb/store/sql_models.py` (if schema metadata model is used)
- `kb/migrations/` (new package for migration files + registry)
- `tests/unit/store/test_sqlite_meta.py`

### Validation

- `uv run pytest tests/unit/store/test_sqlite_meta.py -v`
- `uv run ruff check`
- `uv run ty check`

### Exit Criteria

- Startup auto-migrates older metadata DBs.
- Repeated startup is idempotent (no re-run side effects).
- Migration execution path is unit tested.

---

## PR2 - Canonical Migration Set for Existing Metadata

### Objective

Create concrete migrations to normalize bootstrap/legacy metadata schemas to canonical schema `v1`.

### Implementation Steps

1. Add migration(s) for canonical table naming and FK constraint normalization.
2. Ensure canonical `ON DELETE` behavior for key relationships.
3. Add migration safety guards: temporary table strategy, transaction wrapping, rollback on failure.
4. Add migration test fixtures representing older schema variants.
5. Verify migrated DB works with normal indexing and query workflows.

### Expected File Touchpoints

- `kb/migrations/*.py`
- `tests/unit/store/` (migration-focused tests)
- `tests/integration/ingest/` (migration compatibility checks)

### Validation

- `uv run pytest tests/unit/store/ -v`
- `uv run pytest tests/integration/ingest/ -v`
- `uv run ruff check`
- `uv run ty check`

### Exit Criteria

- Known legacy schema variants migrate to canonical schema `v1` successfully.
- Post-migration DB reports `schema_version = 1`.
- Post-migration operations (index, delete, search) run without FK errors.

---

## PR3 - Deleted-File Reliability and Integrity Gates

### Objective

Harden deleted-file processing and enforce DB integrity checks in relevant ingestion paths.

### Implementation Steps

1. Keep dependent cleanup before file-row delete for all deletion code paths (sync and async).
2. Ensure deleted-file operations are transaction-safe and deterministic.
3. Add integration tests for bulk deletions and mixed embed-model cleanup.
4. Add integrity assertions (`PRAGMA foreign_key_check`) in deletion-oriented integration tests.
5. Add concise error messaging for deletion failures with actionable context.

### Expected File Touchpoints

- `kb/ingest/pipeline.py`
- `kb/store/sqlite_meta.py`
- `kb/store/graph_store.py` (if cleanup sequencing requires alignment)
- `tests/unit/ingest/test_pipeline_core.py`
- `tests/integration/ingest/test_file_sync_integration.py`

### Validation

- `uv run pytest tests/unit/ingest/test_pipeline_core.py -v`
- `uv run pytest tests/integration/ingest/test_file_sync_integration.py -v`
- `uv run ruff check`
- `uv run ty check`

### Exit Criteria

- Deleted-file flows do not produce FK constraint failures.
- Integrity checks are part of regression coverage.

---

## PR4 - Query UX Upgrade (CLI Search)

### Objective

Make command-line querying significantly easier and clearer for end users.

### Implementation Steps

1. Redesign default `dolphin search` output for compact readability.
2. Keep detailed context and diagnostics behind `--verbose`.
3. Normalize common filters/flags (`--repo`, `--top-k`, `--path`, `--lang`, context options).
4. Stabilize `--json` output schema for scripting users.
5. Improve command help text with copy-paste examples.

### Expected File Touchpoints

- `kb/cli.py`
- `tests/unit/cli/test_cli_query.py`
- `tests/unit/cli/test_cli.py`
- `tests/e2e/workflows/test_search_workflow.py`

### Validation

- `uv run pytest tests/unit/cli/test_cli_query.py -v`
- `uv run pytest tests/unit/cli/test_cli.py -v`
- `uv run pytest tests/e2e/workflows/test_search_workflow.py -v`
- `uv run ruff check`
- `uv run ty check`

### Exit Criteria

- Default search output is concise and high-signal.
- `--verbose` and `--json` provide deterministic alternative modes.

---

## PR5 - Terminal Beautification and Logging Signal Cleanup

### Objective

Improve terminal experience and ensure logs communicate clear signal to end users.

### Implementation Steps

1. Add structured terminal formatting (color/rich output where supported).
2. Standardize message levels and wording for status/warnings/errors.
3. Reduce noisy logs in default mode; preserve diagnostics in verbose mode.
4. Add consistent operation summaries for scan/index/search.
5. Ensure non-interactive/script mode remains clean and machine-friendly.

### Expected File Touchpoints

- `kb/cli.py`
- `kb/api/server.py`
- `kb/observability/structured_logger.py` (and related logging utilities)
- `kb/terminal.py`
- `tests/unit/test_logging/test_structured_logger.py`
- `tests/unit/cli/test_cli_smoke.py`

### Validation

- `uv run pytest tests/unit/test_logging/test_structured_logger.py -v`
- `uv run pytest tests/unit/cli/test_cli_smoke.py -v`
- `uv run ruff check`
- `uv run ty check`

### Exit Criteria

- End-user CLI output is readable and actionable.
- Verbose mode preserves detailed debugging context.

---

## PR6 - README and Docs Refresh

### Objective

Clarify value proposition and make first successful query fast for new users.

### Implementation Steps

1. Rewrite README opening section to clearly state user value.
2. Add a 2-minute quickstart from install to first query.
3. Add “common query workflows” section with practical examples.
4. Add troubleshooting for indexing/search basics.
5. Sync architecture/testing docs with implemented behavior.

### Expected File Touchpoints

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`

### Validation

- Manual command verification of README examples.
- `uv run pytest tests/e2e/workflows/test_indexing_workflow.py -v`
- `uv run pytest tests/e2e/workflows/test_search_workflow.py -v`

### Exit Criteria

- New user can follow README and run useful queries quickly.
- Docs reflect real command behavior and testing surface.

---

## PR7 - Release Gate, Final QA, and v0.2.2 Cut

### Objective

Finalize release with one-shot verification and version/changelog updates.

### Implementation Steps

1. Add a single release-check command/target for full validation.
2. Run complete matrix and capture results.
3. Update `CHANGELOG.md` with finalized v0.2.2 entries.
4. Bump package version to `0.2.2`.
5. Validate migration notes are included in release notes.

### Expected File Touchpoints

- `CHANGELOG.md`
- `pyproject.toml` (or equivalent version source)
- `justfile` / `scripts/` / CI workflow files (as needed)

### Validation (must all pass)

- `uv run pytest tests/unit/ -v`
- `uv run pytest tests/integration/ -v`
- `uv run pytest tests/e2e/workflows/ -v`
- `uv run ruff check`
- `uv run ty check`
- `cd mcp-bridge && bun test` (compatibility confidence check)
- `cd shared && bun test` (compatibility confidence check)

### Exit Criteria

- All release gates green.
- v0.2.2 changelog and version metadata finalized.

---

## Dependency Order

1. PR1 -> PR2 (framework before migration content)
2. PR2 -> PR3 (canonical schema before additional deletion hardening)
3. PR3 -> PR4/PR5 (core correctness before UX polish)
4. PR4 + PR5 -> PR6 (docs reflect final UX)
5. PR6 -> PR7 (release cut last)

## MCP Bridge Trigger Rule

Open a separate MCP bridge release path (`0.2.4`) only if pb-dolphin `0.2.2` introduces incompatible response/tool contract changes.
