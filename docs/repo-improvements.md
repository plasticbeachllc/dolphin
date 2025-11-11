# Dolphin Repository — Improvement Proposals (Q4 2025)

This document proposes targeted, high‑impact improvements across the Python KB backend, MCP bridge, Agent Core, VSCode extension, and docs. Each item includes context and concrete first steps.

---

1) End‑to‑End Token & Cost Accounting
- Why: `IndexResponse` currently returns placeholders for `tokens_used` and `cost_usd` (see `kb/api/app.py:1376`). Accurate accounting enables budget caps and better UX.
- Scope: Track tokens at the embedder boundary and aggregate per session. Persist to `sessions` and surface in API, CLI, and extension.
- First steps:
  - Add token counting to `kb/embeddings/provider.py` for OpenAI responses; expose totals alongside vectors.
  - Thread counters through ingestion (`kb/ingest/pipeline.py`) and update session via `SQLiteMetadataStore.bump_session_counters`.
  - Return real `tokens_used` and `cost_usd` in `IndexResponse` and include in `/v1/index/status`.
  - Tests: unit for accounting, integration to confirm session persistence.

2) KB File Sync Delivery (Phases 1–5)
- Why: The implementation spec exists but the endpoints and extension watcher aren’t wired end‑to‑end. This closes drift, crash‑recovery, and mid‑index change gaps.
- Scope: Implement the spec in `docs/kb-index/file-sync-implementation-spec.md` with SQLite change queue, API, VSCode watcher, drift detection, and auto‑sync modes.
- First steps:
  - Add SQLModel tables and migrations (`kb/store/sql_models.py`, `kb/store/sqlite_meta.py`).
  - Implement API endpoints in `kb/api/app.py` for pending changes and drift detection.
  - Build `vscode-extension/src/kb/file-watcher.ts` and `drift-detector.ts`; integrate with activation.
  - Tests: simulate mid‑index edits and restart recovery.

3) Graph Pruning on File Deletions
- Why: Integration test is skipped for deletion cleanup (`tests/integration/test_graph_extraction.py:267`). Stale graph nodes/edges degrade search and waste space.
- Scope: Remove code graph nodes/edges and FTS rows tied to deleted files; cascade on reindex.
- First steps:
  - Implement cascade deletes in metadata store and FTS sync for graph tables.
  - Unskip and complete the deletion test; add coverage for rename/restore flows.

4) Documentation Consistency & Single‑Source Status
- Why: Status is inconsistent (e.g., `docs/ARCHITECTURE.md` says “Production Ready” while `README.md` says “Beta”, and hybrid search status differs).
- Scope: Introduce a single source for status and feature flags; reference it from README/ARCHITECTURE/extension docs.
- First steps:
  - Add `docs/STATUS.md` with current tier (“Beta”), supported features, and WIP list.
  - Replace duplicated status blocks with links; add a lightweight CI check to prevent drift.

5) Retrieval Evaluation Harness (MRR/P@K)
- Why: A measurable, repeatable benchmark lets us gate changes and tune rankers. The repo already has `golden-scenarios/` to build on.
- Scope: Add an eval runner that computes MRR, P@5/10, R@K and outputs JSON/Markdown reports.
- First steps:
  - Add `scripts/eval_retrieval.py` consuming golden scenarios; parametrize reranking and ANN settings.
  - `just eval` target + CI job to publish artifacts.

6) CI/CD Unification & Quality Gates
- Why: Monorepo spans Python + TS/JS. Unified CI improves reliability and review confidence.
- Scope: Single GitHub Actions workflow with matrix jobs and caching (uv, bun/npm). Lint, type‑check, test, and build.
- First steps:
  - Add `.github/workflows/ci.yml` with: ruff/black/mypy, eslint/tsc, pytest, bun tests, extension tests, and webview build.
  - Pre‑commit config to run formatters and linters locally; enforce on PRs.

7) Language Support Expansion via Tree‑sitter
- Why: Supporting Go/Java/JSX/TSX increases usefulness and coverage in modern stacks.
- Scope: New chunkers and registry entries; symbol extraction; tests and docs.
- First steps:
  - Add parsers and chunkers for Go/Java and JSX/TSX; wire in `kb/chunkers/registry.py`.
  - Unit tests for function/class extraction and symbol paths.

8) Observability & Metrics (Opt‑in)
- Why: Diagnosis and performance tuning benefit from cross‑component metrics and structured logs.
- Scope: Consistent JSONL logging and basic counters/latencies across API, MCP, and extension; optional Prometheus endpoint for API.
- First steps:
  - Add API metrics (request counts, latencies, ANN params) and queue depth reporting; expose `/v1/metrics` (text or JSON).
  - Ensure MCP logs include correlation IDs and durations; add `dolphin.kb.enableTelemetry` (false by default) in the extension.

9) CLI Unification + “doctor” Command
- Why: The coexistence of `kb` and `dolphin` subcommands and multiple setup paths can confuse users.
- Scope: Normalize verbs, keep aliases, and add a diagnostic flow that validates env and connectivity.
- First steps:
  - Add `dolphin doctor`: check OpenAI key, FTS5 availability, LanceDB compatibility, server health, and port conflicts.
  - Align docs and `just` targets; ensure errors point to remediation steps.

10) Security Hardening: Secrets & Path Safety
- Why: Prevent accidental ingestion of sensitive files and ensure strict repo‑root boundaries.
- Scope: Expand default ignore patterns and add a lightweight secrets detector with warnings and opt‑out.
- First steps:
  - Extend scanner exclusions (`.env*`, `*.pem`, `.aws/`, `id_rsa*`, `*.key`, `*.p12`), and skip known secrets with a summary in results.
  - Add explicit path boundary checks in file‑serving endpoints and tests for traversal attempts.

---

Notes & References
- Token/cost placeholders: `kb/api/app.py:1376`.
- File sync spec: `docs/kb-index/file-sync-implementation-spec.md`.
- Deletion cleanup test (skipped): `tests/integration/test_graph_extraction.py:267`.
- Status drift example: `docs/ARCHITECTURE.md`, `README.md`.
- Monorepo CI entry points: Python (`pyproject.toml`), TypeScript (`agent-core`, `mcp-bridge`, `vscode-extension`).

