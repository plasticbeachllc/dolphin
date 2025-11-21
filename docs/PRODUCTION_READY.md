# Dolphin Production Release Plan

This plan translates the prior readiness review into a concrete, cross-functional work program for launching Dolphin's public beta. It is organized by objectives, phased milestones, and workstreams with scoped deliverables, owners, and validation steps.

## Objectives and success criteria

- **Delightful first experience**: first-query-to-answer in <3 minutes on a clean machine, with zero dead ends during setup.
- **Reliable multi-surface coverage**: core flows (CLI/REST, MCP bridge, agent-core, VS Code extension) behave consistently with clear recovery paths.
- **Predictable quality and cost**: users understand performance/quality trade-offs, reranking costs, and receive helpful defaults.
- **Evidence-based beta**: published benchmarks, user feedback loops, and regression coverage guard the release.

## Milestones

1. **Beta Prep (Week 0–1)**
   - Finalize scope, owners, and tracking board; freeze blocking dependencies.
   - Publish updated “what’s stable vs experimental” matrix in README/ARCHITECTURE/CHANGELOG.
2. **Experience Hardening (Week 1–2)**
   - Ship guided onboarding, diagnostics, and sample experience across CLI and VS Code.
   - Stabilize KB lifecycle and authentication flows.
3. **Performance & Quality (Week 2–3)**
   - Benchmarks with p95 latencies and reranking modes documented; add CI smoke perf checks.
   - Evaluation harness with golden queries across languages; publish baseline metrics.
4. **Release Readiness (Week 3)**
   - All required tests green in CI; observability/telemetry validated.
   - Final beta changelog, FAQ, and support channels live.

## Workstreams and deliverables

### 1) Onboarding & usability

- **Guided “happy path”**: one-click flow (CLI and VS Code) that initializes KB, adds repo, indexes, and runs a sample query. Include skeleton responses and helpful empty-state tips.
- **Config/credential guardrails**: detect missing OPENAI_API_KEY/Claude credentials; provide inline fixes and reranking cost warnings.
- **Diagnostics panel**: surface API server/Kb health, MCP connectivity, versions (PyPI, extension, MCP), and log links.
- **Zero-config KB lifecycle**: auto-start/health-check KB with progress indicators and retry/backoff; clear recovery prompts on failure.

### 2) Product experience (UX/UI)

- **VS Code polish**: streaming states, tool-call visualization, retry for long searches, and performance/quality toggle (off/auto/aggressive) with latency estimates.
- **Demo content**: bundled sample repo + pre-canned queries to avoid empty search results; “Quick Demo” command in extension.
- **Authentication UX**: dual OpenAI/Claude flows with status badges, error surfaces, and smooth switching.

### 3) Stability, safety, and correctness

- **Health checks**: REST `/health`, MCP bridge connectivity, KB manager readiness, extension detection; add automated integration tests that fail fast if KB unreachable.
- **Config robustness**: validate global/repo TOMLs with safe defaults (small embedding model); reject invalid paths and surface actionable errors.
- **Security/regression tests**: path traversal and symlink edge cases across agent-core/bridge/KB APIs; add negative tests for unsafe inputs.
- **Upgrade safety**: ensure backward-compatible config migrations and clear upgrade notes in CHANGELOG.

### 4) Performance and scalability

- **Latency benchmarks**: measure p50/p95 for EditorWorkflow (<1s target) and Architect phases (<3–5s) with/without reranking; publish in docs and CI dashboards.
- **Search throughput**: benchmark hybrid (BM25+vector) search and reranking across repo sizes; document recommended chunk sizes, candidate multipliers, and hardware profiles (laptop/workstation/server).
- **Content trimming**: profile MCP bridge 50KB budget; ensure deterministic truncation, readable snippets, and tests for long files.
- **Resource footprint**: validate reranking extras install size and cold-start latency; provide opt-in toggles and warnings.

### 5) Evaluation and quality measurement

- **Golden-set harness**: multi-language (Python/TS/JS/Markdown) queries with expected answers for search and chat; automated scoring (MRR/Recall) per model/rerank mode.
- **User dogfood**: internal beta sessions in VS Code capturing time-to-first-answer, helpfulness ratings, and failure modes; prioritize top pain points.
- **Quality dashboard**: track evaluation metrics, latency, error rates, and KB health with weekly review cadence.

### 6) Testing & automation

- **Test coverage enforcement**: unit + integration + e2e across Python, MCP bridge, agent-core, and VS Code extension; include regression tests for fixed bugs.
- **CI gating**: require uv-managed Python tests, bun tests for MCP/agent-core, extension e2e, lint/format checks, and performance smoke tests on main and release branches.
- **Release builds**: reproducible builds for CLI/REST, npm packages, and VS Code extension; signed artifacts where applicable.

### 7) Observability, telemetry, and support

- **Logging & tracing**: structured logs with request IDs across services; optional trace headers to correlate KB, bridge, and extension events.
- **Metrics & alerts**: KB availability, search latency, reranking errors, index queue depth; alerts for sustained degradations.
- **Feedback path**: in-product “Send feedback” with consented telemetry; triage process and SLA for beta issues.
- **Runbooks**: incident playbooks for KB downtime, auth failures, and reranking outages.

### 8) Documentation & comms

- **Docs refresh**: README and ARCHITECTURE status tables updated to reflect beta scope; link to onboarding guide and troubleshooting.
- **Changelog & FAQ**: beta-specific notes on stability, known gaps, performance expectations, and reranking costs.
- **Samples & recipes**: minimal examples for CLI/REST/MCP/extension flows; KB config templates with recommended chunking models.

## Gating checklist (must be true before public beta)

- All core flows validated on clean machines with only documented prerequisites.
- Zero-setup KB auto-start succeeds or surfaces actionable recovery.
- Clear, friendly errors for missing config/auth and KB availability.
- Published benchmarks and evaluation metrics with recommended configs.
- All test suites (unit, integration, e2e, perf smoke) green in CI; lint/format gates enforced.
- Observability and feedback channels live; runbooks tested.
- Updated docs and changelog reflecting actual beta scope and known limitations.

## Risks and mitigations

- **Model/API instability**: cache model availability and provide fallbacks; add canary checks in CI.
- **Large-repo cost/latency surprises**: enforce safe defaults, preflight cost estimates, and user warnings; document tuning.
- **KB lifecycle failures**: implement health-checked retries with exponential backoff and user prompts; add watchdog alerting in extension.
- **Cross-surface drift**: shared contracts/tests for search/index APIs; nightly cross-surface e2e runs.

## Tracking and accountability

- Create a public beta board with workstream swimlanes (UX, stability, performance, evaluation, docs, observability).
- Assign DRI + reviewer for each deliverable; track status (Not started/In progress/Blocked/Done) with weekly burndown.
- Hold twice-weekly release readiness reviews until beta launch; capture risks, mitigations, and owner acknowledgments.
