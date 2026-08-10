# Dolphin 0.3.0 Implementation Plan

**Status:** Frozen for implementation<br>
**Target:** `0.3.0`<br>
**Release branch:** `develop`<br>
**Primary user:** Software-development agents working for solo developers on Apple Silicon macOS<br>
**Compatibility policy:** No backward compatibility is required

## How to use this plan

This document is the frozen product specification, architecture plan, implementation sequence, and release checklist for Dolphin 0.3.0. Confirmed decisions are recorded in Section 3 and propagated through the requirements, reference code, safety invariants, workstreams, tests, and release gates.

The words **must**, **should**, and **may** distinguish release requirements from recommendations and optional work.

## 1. Vision

Dolphin 0.3.0 is the code-discovery layer an agent chooses as a core part of its workflow because it finds relevant implementations, relationships, and context more effectively than built-in filename search, text search, and piecemeal file reads.

For a solo developer, Dolphin should feel like one MCP product:

- Easy to install and connect to an agent.
- Able to explain and repair its own operational state.
- Explicit about which repositories it indexes.
- Safe for an agent to operate autonomously.
- Quiet and low-maintenance after initial setup.
- Measurably useful on real software-engineering tasks.

The Python service, storage engines, indexing pipeline, CLI, and transport details are implementation machinery. The user-facing product is the agent experience.

## 2. Product thesis

Built-in agent tools are effective when the agent already knows a filename, symbol, or exact string. Dolphin should add value when the agent instead needs to discover:

- where an unfamiliar behavior is implemented;
- which files and symbols participate in a feature;
- analogous implementations across a repository or several repositories;
- relevant code despite vocabulary differences between the task and implementation;
- enough ranked context to choose what to inspect next without flooding the context window.

Dolphin succeeds only if agents repeatedly use it for these jobs and achieve better outcomes than they do with built-in tools alone.

## 3. Confirmed product decisions

| ID    | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| D-001 | `develop` is the release-candidate integration branch. Feature work branches from and returns to `develop`; releases reach protected `main` through a pull request.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| D-002 | The next release is 0.3.0.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| D-003 | The Python package, MCP product, and bundled agent integration are versioned and released together.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| D-004 | The primary user is an agent working for a solo developer.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| D-005 | OpenAI is the only embedding provider for 0.3.0.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D-006 | Agent self-sufficiency is a goal, bounded by explicit safety controls.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-007 | Backward compatibility is explicitly not a requirement. Existing commands, configuration, schemas, APIs, storage, and MCP contracts may be replaced.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| D-008 | Dolphin remains primarily an MCP product; a graphical interface is out of scope.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D-009 | macOS is the only required operating system for 0.3.0.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-010 | Repository registration is explicit. An agent calls `repo_add`; Dolphin never silently indexes the working directory.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-011 | The MCP entry point owns operational readiness and initializes the application runtime itself; the user does not launch or supervise a separate backend, daemon, or macOS LaunchAgent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-012 | Dolphin 0.3.0 uses Python exclusively. The TypeScript/Bun MCP bridge, shared TypeScript runtime, npm release, and localhost REST hop are removed from the default product architecture.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| D-013 | Provisioning `DOLPHIN_OPENAI_API_KEY` grants standing consent for Dolphin to send eligible content from explicitly registered repositories to OpenAI. Normal `repo_add` does not require a second human approval step; D-044 applies only after the catastrophic fuse stops an anomalous preflight.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| D-014 | Indexing limits are catastrophic safety fuses, not ordinary cost controls. Dolphin must accept very large legitimate codebases and stop only when preflight strongly suggests mis-scoping, traversal failure, broken ignores, or another runaway condition.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| D-015 | Repository freshness uses a hybrid model: continuous watching while Dolphin is running, a cheap drift check before search, bounded catch-up for small changes, and explicitly stale results with an operation ID when a larger sync remains in progress.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| D-016 | Search hits expose canonical absolute paths by default, alongside repository-relative paths, exact line ranges, and stable Dolphin references. Path validation remains constrained to explicitly registered roots.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| D-017 | Task correctness is the primary 0.3.0 value and release constraint. Latency, tool calls, and context consumption are secondary guardrails; Dolphin call frequency is diagnostic and must not be optimized by forcing tool use.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| D-018 | Dolphin 0.3.0 has no public REST API or `dolphin serve` process. FastAPI routes are removed after reusable domain behavior is extracted into Python application services called directly by MCP and the human maintenance CLI.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| D-019 | Multiple MCP processes may search the same Dolphin store concurrently. Mutating operations are serialized with short-lived interprocess writer locks, and one renewable maintenance lease per workspace owns continuous watching with automatic takeover after expiry.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-020 | Every Git checkout, including each linked worktree, is a first-class Dolphin workspace with its own root, identity, freshness state, watcher, and index namespace. Worktrees sharing one Git common directory must never overwrite or silently search one another's code state.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-021 | Creating a workspace or switching/creating a branch must seed from compatible indexed history in the same repository family and process only Git/worktree deltas. Unchanged content reuses chunk and embedding artifacts; a second worktree at an already indexed commit performs zero embedding API calls.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| D-022 | Workspace resolution follows deterministic precedence: explicit tool scope, one exact client-provided MCP root, session-local scope established by `repo_add` or an earlier explicit selection, then an unambiguous MCP process working directory. Dolphin never guesses among sibling worktrees and instead returns a typed ambiguity with ready-to-use choices.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| D-023 | `DOLPHIN_OPENAI_API_KEY` is the only public OpenAI credential input. Dolphin reads it from the process environment, passes it explicitly to the OpenAI client, and never stores it. 1Password, shell configuration, MCP-client environment settings, and CI are external injection mechanisms rather than Dolphin integrations.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-024 | Missing workspaces are excluded from search immediately and retained for a 30-day recovery window. Automatic garbage collection may then delete only unreachable derived workspace data; reusable clean commit generations use longer LRU/storage-pressure retention. Destructive GC remains unavailable through MCP.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-025 | The MCP `search` contract exposes only task-level query, workspace, path/language scope, result/context budget, and continuation inputs. Fusion, ANN, MMR, reranking, graph enrichment, thresholds, and execution concurrency are internal adaptive policy—not agent-facing knobs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| D-026 | `search` returns compact structured metadata/references for every hit and includes focused indexed-code snippets for the highest-value hits when useful, bounded by one aggregate context budget. Zero context budget produces metadata-only results; deeper content comes from `open_ref`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| D-027 | Default indexing is inclusive of useful first-party text: source, tests, fixtures, docs, examples, configuration, and eligible untracked worktree files. Dependencies, vendor/build/generated noise, minified files, caches/reports, lockfiles, binaries/media, and secret-bearing files are excluded by default.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| D-028 | Dolphin 0.3.0 uses `text-embedding-3-small` globally. The model and dimensions are not configurable through MCP, global config, repository config, or worktree state; mixed-model indexes are invalid.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-029 | The canonical installation is a persistent isolated uv tool environment created with `uv tool install --python 3.13 pb-dolphin`; MCP launches the installed `dolphin mcp` executable and versions remain stable until an explicit `uv tool upgrade pb-dolphin`. `uvx` is reserved for evaluation and troubleshooting, not routine MCP startup.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| D-030 | First-class, release-gated language support covers Python, JavaScript/JSX, TypeScript/TSX, Svelte, SQL, Markdown/MDX, and Rust. Rust receives a parser-based structural chunker, relationship metadata, dedicated fixtures, agent-value evaluation coverage, and full participation in any graph implementation that passes D-040. JSON, YAML, TOML, shell, Justfiles, and other eligible text remain searchable through the generic fallback without a language-specific quality promise.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| D-031 | Production runtime state and the optional human-owned global configuration live under the single macOS-native root `~/Library/Application Support/Dolphin/`; the configuration is exactly `config.toml` there and every other state class uses its typed subpath. Dolphin 0.3.0 neither reads nor migrates legacy global state from `~/.dolphin/`; the narrow repository-local `.dolphin/config.toml` policy remains a separate trust domain and no credential is stored in either location.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| D-032 | Codex and Claude Code are both first-class 0.3.0 client integrations. MCP instructions, tool contracts, agent guidance, examples, and client artifacts are generated as thin adapters from canonical Python-owned specifications, versioned together, and protected by semantic-parity tests; client-specific content is limited to unavoidable packaging and configuration differences.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| D-033 | Dolphin provides human-only, idempotent `dolphin setup codex` and `dolphin setup claude-code` commands. They configure the installed absolute `dolphin mcp` executable through supported client-native mechanisms where possible, never persist the OpenAI key, preserve and validate existing client configuration, support dry-run/structured output, and are verified by `dolphin doctor`; generated manual instructions remain the fallback.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D-034 | Client setup defaults to the user's global Codex or Claude Code configuration so Dolphin is available in every repository and worktree. `--scope project` is an explicit override bound to the exact current worktree. Global availability never registers or indexes a repository; that boundary remains the agent's explicit `repo_add` call.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-035 | Dolphin never publishes or searches a partially built first index. Until a workspace has an atomically committed complete generation, `search` returns typed `INDEX_BUILDING` state with operation progress and built-in-tool guidance, or the more specific blocking error such as D-044's `SCOPE_FUSE_TRIPPED`. Once any complete compatible generation is committed, later drift may use the existing stale-but-complete behavior while a newer generation builds.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-036 | Query embedding follows a strict degradation ladder: use a compatible exact cached embedding first, otherwise attempt OpenAI with bounded retry, then use conspicuously marked local lexical/structural retrieval only for transient provider failures. Missing/invalid credentials and permanent request/contract failures return typed errors rather than fallback results.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| D-037 | `repo_add` accepts exactly the absolute concrete worktree path plus a caller-supplied 256-bit cleanup receipt, freshly generated by the client or a bounded Dolphin next action before registration. The path alone determines repository identity; the receipt is only retry-safe cleanup authority. Dolphin derives deterministic human-readable repository/workspace display labels and disambiguates duplicates with stable short IDs; names are never caller-supplied identity, scope, or conflict keys.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| D-038 | Git submodule working trees are excluded from their parent workspace and require their own explicit `repo_add` with that concrete path and a fresh cleanup receipt when needed. Parent enrollment reports submodule state and ready-to-use enrollment guidance but never initializes, updates, recursively registers, embeds, or implicitly searches submodule contents.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| D-039 | Torch/`sentence-transformers` cross-encoder reranking is evaluation-only until a pre-RC agent-task correctness gate. If it fails to deliver a material gain that lighter ranking cannot recover, all shipped code/dependencies/configuration are removed; if it passes, one fixed implementation becomes part of the standard install with no optional runtime mode.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| D-040 | Cross-file graph extraction, graph storage, community analysis, and graph-enriched retrieval face a binary pre-RC agent-task correctness gate. Structural chunking, symbol metadata, and conservative per-file relationship metadata remain regardless; the graph subsystem is either removed completely with its heavy dependencies or becomes one standard internal behavior with no MCP/config toggle.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| D-041 | Dolphin 0.3.0 removes the Prometheus/OpenTelemetry/Grafana/Loki/Docker observability stack, its network endpoints, and its product dependencies. Production diagnostics are local-only: bounded redacted JSONL logs, a fixed low-cardinality in-process metrics registry summarized through `status` and `doctor`, and explicit development-only profiling/evaluation commands.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-042 | Every independently initialized Git worktree physically nested beneath another registered worktree is a hard repository boundary, whether or not it is a declared submodule. Parent indexing excludes the entire nested subtree, deepest-root resolution selects the child, and the child requires its own explicit `repo_add` path and fresh cleanup receipt; enrollment and search never cascade implicitly.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| D-043 | Optional root-level `.dolphin/config.toml` is a strict, versioned, read-only repository indexing policy limited to ordinary include/exclude patterns. It cannot contain credentials, expand the Git candidate universe, weaken security/boundary/safety rules, raise catastrophic fuses, or configure search output budgets, models, retrieval, storage, runtime, agents, or telemetry; Dolphin never creates or edits it. Human-owned search-budget configuration belongs only to D-076's Application Support file.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| D-044 | An approvable aggregate catastrophic-fuse stop can be released only by a one-shot interactive human CLI approval bound to the exact workspace, operation, preflight fingerprint, observed scope, and expiry, persisted under Application Support. It atomically requeues only that operation; MCP, repository/environment configuration, non-interactive flags, and global limit changes cannot approve or reuse it. Structural/path/security preflight failures are never approvable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-045 | Dolphin installs no LaunchAgent, daemon, detached helper, or always-on watcher. Work runs only inside active MCP or explicit foreground CLI processes; an exiting owner checkpoints and releases leases, compatible live peers may take over, and otherwise durable operations resume automatically on the next launch while watchers reconcile drift.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-046 | Dolphin 0.3.0 retains a split embedded store: SQLite is the authoritative transactional registry for metadata, operations, generation visibility/membership, leases, and FTS5 keyword search; a locally pinned LanceDB adapter stores and searches fixed-contract vectors only. A SQLite publication pointer makes cross-store state visible after verified vector durability. No SQLite-vector rewrite, LanceDB Cloud path, or raw backend access outside strict store interfaces is in scope.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-047 | Dolphin 0.3.0 supports native Apple Silicon (`arm64`) macOS only. Intel Macs, Rosetta-translated execution, source-building native storage dependencies, and universal/x86-64 release qualification are out of scope. Installation documentation, startup diagnostics, CI, and release smoke tests state and enforce this boundary explicitly.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| D-048 | Dolphin 0.3.0 supports only standard GIL-enabled CPython 3.13. Package metadata uses `requires-python = ">=3.13,<3.14"`; the canonical uv command requests `--python 3.13`; development, locks, CI, wheels, and dependency qualification target that minor; and startup rejects other Python minors, implementations, and free-threaded builds before state mutation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-049 | Every published generation retains the exact decoded source text of its chunks in private, immutable, content-addressed local artifacts. Dolphin does not create separate whole-file snapshots, but documentation is explicit that a generation's chunks may collectively retain most or all eligible file text. Published snippets read these verified artifacts—not mutable worktree files—and reachability-based GC removes only artifacts no retained generation, operation, or reader can reach.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-050 | `open_ref` has one non-configurable content behavior: it securely reads a bounded excerpt from the current eligible file in the referenced worktree and reports exact indexed/current fingerprints plus typed drift/alignment metadata. It never returns retained indexed text as though it were current and exposes no indexed/current mode switch; exact published evidence remains in `search` snippets.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| D-051 | Search hits use an opaque versioned URI `dolphin://ref/<stable-id>` for `open_ref`; paths and line ranges remain separate human-readable fields. The token contains no path/source text and resolves only through retained workspace/publication/chunk membership. It is stable for the same target while that originating membership is retained, creates no permanent GC pin merely by being returned, and fails as `REFERENCE_EXPIRED` after collection.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| D-052 | Dolphin 0.3.0 adds no application-level encryption, SQLCipher, encrypted LanceDB/artifact layer, storage passphrase, or storage-key integration. It enforces private ownership/modes under Application Support, accurately discloses retained plaintext-derived data, and reports FileVault as best-effort `on`/`off`/`unknown` advice without enabling it or blocking normal operation. The macOS account/device boundary—not Dolphin cryptography—is the at-rest security boundary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-053 | Dolphin manages derived-data disk pressure automatically with one release-defined internal high/low-water policy and no user quota knob. Active/published state, operations, reader leases, and the full 30-day missing-workspace window are never pressure-evicted. GC reclaims only proven unreachable/expired staging, caches, overlays, and least-recently-adopted reusable generations; if protected state still leaves insufficient reserve, indexing pauses as `DISK_PRESSURE` while committed search remains available.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-054 | `storage-pressure-v1` starts GC below `max(20 GiB, 5% of volume)` user-available space or above `50 GiB` reclaimable inactive data; converges across yielding batches toward `max(30 GiB, 7.5%)` available and at most `40 GiB` reclaimable; admits a growth phase only when its conservative peak plus `5 GiB` crash margin still leaves the start reserve; and starts no new deletion unit after a batch reaches `2 GiB` actual reclamation or two monotonic seconds.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| D-055 | Dolphin 0.3.0 requires native Apple Silicon macOS 14.0 Sonoma or newer. The shared preflight rejects macOS 13 and earlier, non-Darwin, non-`arm64`, Rosetta-translated, or unparseable platform state before storage/provider work. Runtime acceptance is major/minor based rather than latest-patch gated; RC qualifies the latest public security patch of every supported macOS major through the then-current stable release.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| D-056 | Agents may explicitly release the exact workspace-registration epoch whose successful creation response returned a high-entropy cleanup receipt. `repo_forget` requires that epoch-bound receipt, cannot target a registration that predated the authority-issuing call, never mutates Git or source files, atomically removes the workspace from new resolution/search, and makes only now-unshared Dolphin-derived state eligible for ordinary safe GC. There is no MCP force, reset, arbitrary-GC, or receipt-recovery capability.                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| D-057 | Agent cleanup is explicit-only. MCP disconnect, EOF, process exit/crash, timeout, client cancellation, lease expiry, root/session-scope change, and loss of the cleanup receipt never imply `repo_forget`, consume cleanup authority, shorten retention, or unregister a workspace. These events only follow ordinary checkpoint, lease-release/expiry, and later-resume behavior; a disappeared filesystem root independently enters D-024's recoverable `missing` state.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| D-058 | A valid `repo_forget` is the sole agent-facing cancellation path needed for disposal. It atomically cancels queued/paused work for that registration and gives running work the same fixed five-second cooperative checkpoint/drain budget as shutdown, with no new provider submissions while its renewable cleanup-intent lease is live. A foreign/non-draining lease or publication-critical section returns retryable `WORKSPACE_IN_USE` without consuming the receipt; abandoned intent expires safely, and there is no separate general MCP operation-cancel tool.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| D-059 | A consumed cleanup receipt has a minimal 30-day replay tombstone measured from the successful `forgotten_at` transaction. An exact workspace/epoch/receipt replay returns the original bounded `already_forgotten` outcome during that window without extending it; afterward the tombstone is automatically compactable and the same input returns constant-shape `CLEANUP_NOT_AUTHORIZED`. This metadata neither pins nor governs workspace artifacts, generations, or shared-state retention.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D-060 | An unused creation-issued cleanup receipt has no clock-based expiry. It remains valid only for its exact registration epoch until successful `repo_forget`, human cleanup, or another explicit authority-invalidating lifecycle transition supersedes it. Wall-clock changes, inactivity, process/session restarts, software upgrades, and missing-workspace retention do not refresh, expire, transfer, or broaden it; source/Git and later epochs remain outside its authority.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| D-061 | Dolphin has one workspace-registration kind. It records no agent-versus-human provenance, owner, temporary/persistent class, or promotion state, and provides no `repo keep`/promotion command. A cleanup receipt is scoped authorization emitted by the transaction that created one registration epoch—not an ownership label on the repository—and every registration otherwise follows identical indexing, search, reuse, freshness, retention, and human-maintenance behavior.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| D-062 | Logically forgotten registrations are absent from normal MCP `repo_list`, workspace resolution, ambiguity candidates, and repository-boundary enrollment state. MCP `status` exposes only bounded aggregate forgotten/replay-tombstone counts and bytes with no identity/path/receipt data. During the fixed 30-day replay window, the human CLI may inspect bounded audit metadata with `dolphin repo list --include-forgotten`; no MCP include flag exists, and post-window compaction removes the entry from that audit view.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D-063 | Re-adding a forgotten worktree preserves its stable workspace ID only when retained evidence proves the same repository family and concrete Git-worktree identity. It always creates a fresh registration epoch and receipt, never revives old references/operations/authority/publication state, and adopts only independently verified compatible artifacts. A different, forgotten-identity-ambiguous, or insufficiently evidenced path receives a new random workspace ID; path equality alone never merges identities, while active/missing conflicts retain the normal idempotent/ambiguity rules rather than creating duplicates.                                                                                                                                                                                                                                                                                                                                                               |
| D-064 | Forgotten-workspace identity proof shares the cleanup replay tombstone's exact, non-extending 30-day deadline. Before expiry it may preserve a proven workspace ID; at the deadline it becomes logically ineligible even if physical compaction runs later, and re-enrollment receives a new ID. Audit/replay/lookups never extend the window, compaction removes the anchor with the tombstone, and independently retained content-addressed artifacts remain reusable without preserving workspace identity.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| D-065 | Concrete-worktree continuity requires an exact retained/current match of repository-family identity plus no-follow filesystem identities for the resolved Git common directory and concrete worktree gitdir: device, inode, and normalized macOS birth time. Canonical paths are discovery/diagnostic evidence only. Missing/unsupported metadata, object-type change, a raced descriptor, multiple matches, cross-volume copy/move, replacement, or any mismatch is insufficient and yields a new workspace ID; a same-volume rename may preserve identity.                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| D-066 | `cleanup-intent-v1` is a non-configurable 30-second lease from its last successful renewal, renewed every five seconds only by an active explicit `repo_forget` call. A validated retry may attach to and renew the same workspace/epoch intent; at expiry it is logically absent even if its row remains. Ordinary mutation/provider scheduling is blocked only while live, so an abandoned attempt delays new workspace writes for at most 30 seconds, while repeated active authorized calls may keep driving safe drain.                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| D-067 | Cleanup-intent admission is linearized with reader admission. Searches/`open_ref` calls holding reader leases before intent acquisition may finish from pinned state, with prominent lifecycle-change metadata if cleanup advances; new `search`, `open_ref`, `repo_add`, `repo_sync`, watcher, or other workspace work returns retryable `WORKSPACE_IN_USE` before provider/read/mutation work. `repo_list` exposes the bounded `cleanup_pending` overlay, `status` exposes it only for the resolved current workspace plus an aggregate count, `operation_status` and receipt-authorized retry remain available, and a multi-workspace search fails as a whole rather than silently dropping the pending workspace.                                                                                                                                                                                                                                                                                  |
| D-068 | If cleanup intent expires without forget, Dolphin restores the still-active registration autonomously. One compare-and-set recovery marker per workspace/epoch causes a compatible live runtime—or the next startup when none is live—to reacquire maintenance ownership, perform one cheap drift/policy/boundary reconciliation, restore watching, and enqueue at most one new incremental/initial operation only when needed. Cancelled operations never resurrect; verified artifacts/cache entries are reusable, and provider work still requires ordinary credential/scope/disk preflight.                                                                                                                                                                                                                                                                                                                                                                                                        |
| D-069 | The 0.3.0 cleanup UX is frozen at one caller-held opaque receipt supplied to `repo_add`, one optional matching `CleanupAuthority` output, and one two-field `repo_forget(workspace_id, cleanup_receipt)` input. There are no agent-facing temporary/persistent, wait, cancel, force, recursive, source/worktree-delete, GC, TTL, retention, victim, recovery, or tuning controls; all internal cleanup defaults are release-defined, and results clearly distinguish immediate logical release from asynchronous physical reclamation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| D-070 | Dolphin 0.3.0 has exactly one public repository-enrollment entry point: MCP `repo_add`. The legacy `dolphin index`, any `dolphin repo add`/`import` alias, and every other packaged human enrollment/index command are removed; setup and diagnostics never enroll implicitly. Transport-independent application services remain directly testable, while the CLI may act only on already registered or otherwise explicitly authorized state for setup, diagnostics, exact-operation foreground execution, interactive approvals, explicit cleanup, and conservative maintenance.                                                                                                                                                                                                                                                                                                                                                                                                                     |
| D-071 | `repo_sync` remains as the one explicit task-level freshness control. Its request contains exactly `workspace_id`; it is non-blocking, idempotent, and has no wait, full, force, strategy, provider, concurrency, or tuning controls. It runs the same reconciliation and safety path as automatic freshness: return `up_to_date` with no operation/provider work when current, reuse one equivalent active operation when present, or durably create one correctness-preserving operation. Dolphin—not the agent—chooses the smallest safe plan and may internally rebuild only when compatibility or correctness requires it.                                                                                                                                                                                                                                                                                                                                                                        |
| D-072 | `status` and `repo_list` remain separate and narrow. Empty-input `status` returns bounded global runtime/credential/storage health, effective-state counts, forgotten-state aggregates, and at most the one deterministically resolved current workspace; it never enumerates all registrations. `repo_list` accepts only an optional opaque cursor and returns at most 25 actionable workspace records in stable pages. Its cursor binds the actionable-registration set/order revision and fails with restart guidance if malformed, from another store/contract, or invalidated by membership change; neither tool performs provider work, reconciliation, or mutation.                                                                                                                                                                                                                                                                                                                             |
| D-073 | `operation_status` accepts exactly `operation_id` and returns one immediate read-only snapshot; it has no wait, stream, list, history, cancel, resume, retry, or pagination mode. Nonterminal records remain durable until reconciled to a terminal state. A bounded source-free terminal summary remains available for exactly 30 days from `terminal_at`, with a non-extending deadline, then compacts automatically to constant-shape `OPERATION_MISSING`. Status reads create no operation/artifact retention edge, expose no provider request ID, and cannot make a forgotten workspace actionable; receipt-authorized `repo_forget` remains the only agent cancellation path.                                                                                                                                                                                                                                                                                                                    |
| D-074 | The complete 0.3.0 public MCP registry is frozen as the ordered eight-tool set `status`, `repo_list`, `repo_add`, `repo_forget`, `repo_sync`, `operation_status`, `search`, and `open_ref`. Every supported client and runtime state exposes exactly the same names, schemas, annotations, ordering, and descriptions from one Python `ToolSpec` source; unavailable behavior returns typed results rather than hiding a tool. There are no aliases, conditional/dynamic tools, compatibility shims, or alternate resource/prompt/file/index control surfaces. Static generated server instructions remain guidance, not a ninth capability.                                                                                                                                                                                                                                                                                                                                                           |
| D-075 | The `search` query-variant fields are frozen as `query`, nullable `workspace_ids`, `paths`, `exclude_paths`, `languages`, nullable `max_results`, and nullable `max_context_tokens`; continuation is a separate cursor-only variant under D-085. Omitted numeric budgets are not hard-coded protocol defaults: a versioned TOML-backed adaptive output-budget policy selects them from bounded source-free scope statistics such as workspace/file/chunk counts and filters. The 8-result/4,000-token values are the initial experimental baseline, not immutable release settings. Agent-supplied values are honored within the effective policy caps; 50 results and 20,000 context tokens remain the installed protocol ceilings unless a later recorded release decision changes them. Retrieval/ranking internals remain unconfigurable through this surface.                                                                                                                                     |
| D-076 | Production search output-budget authority lives only in optional human-owned `~/Library/Application Support/Dolphin/config.toml`. The checked-in worktree `.dolphin/config.toml` remains indexing-only and cannot affect search budgets or retrieval. Precedence is explicit valid MCP budget within the selected effective cap, then the selected user-config profile, then the shipped signed policy when the user file is absent. Development/evaluation TOMLs may override complete candidate matrices only through explicit non-production commands and isolated stores; production never auto-discovers them. No TOML may raise the installed 50-result/20,000-token ceilings or configure retrieval/ranking internals.                                                                                                                                                                                                                                                                          |
| D-077 | The output-budget TOML is a declarative complete four-profile matrix: ordered `small`, `medium`, `large`, and `massive` profiles each define default/cap results and context tokens; the first three also define strictly increasing inclusive maximum searchable-chunk thresholds, while `massive` is the required unbounded final profile. The selector chooses a base from the exact filtered published scope and may promote by at most one profile when scope spans multiple workspaces or the closed intent is `architecture`, `cross_file`, or `analogous_pattern`; multiple reasons never stack. No formula, script, plugin, TOML-supplied classifier, per-query TOML rule, or retrieval control is accepted.                                                                                                                                                                                                                                                                                  |
| D-078 | MCP startup and every first-page `search` cheaply recheck the human-owned output-budget TOML and pin one immutable validated policy snapshot for the call. A stable valid semantic change takes effect without restart and atomically becomes the durable last-known-good snapshot; in-flight calls keep their prior snapshot. An invalid/unstable edit never replaces it and uses that snapshot with prominent degraded metadata, or the shipped signed policy when none exists. File deletion intentionally deactivates prior user authority and returns to shipped policy. Reads/status checks never extend authority; canonical-equivalent edits preserve the digest, while an effective policy change expires continuations.                                                                                                                                                                                                                                                                      |
| D-079 | Human configuration ergonomics are exactly three CLI subcommands: `dolphin config init`, `dolphin config validate`, and `dolphin config show`, each accepting only optional `--json`. `init` atomically creates the complete shipped four-profile TOML at the fixed Application Support path with private mode and refuses any existing entry without modifying it. `validate` strictly inspects the current candidate or reports valid absence/shipped fallback; `show` reports bounded active, pending, and fallback policy state plus resolved profiles/digest. Neither observational command accepts a pending policy, and there is no custom path, editor, set/unset, reload/watch, overwrite/force/reset, or MCP configuration-write surface.                                                                                                                                                                                                                                                    |
| D-080 | Search intent has one role in 0.3.0: it may promote the adaptive default/effective-cap output profile by one step for broad questions. It cannot change retrieval, ranking, scope, indexing, authorization, or tool routing. A tiny versioned in-process Python classifier reads only the query and returns one closed intent; `rules-v1` uses fixed normalized phrase groups with deterministic precedence, makes no model/provider/source/config call, and defaults unmatched queries to `concept`. Its narrow interface permits a later evaluated local-AI implementation, but changing classifier/version is a release decision rather than a TOML/plugin/runtime choice. Classifier version is observable and cursor/cache/policy-bound.                                                                                                                                                                                                                                                          |
| D-081 | `rules-v1` and intent-based promotion face a preregistered binary RC value gate against otherwise identical scope-size plus multi-workspace selection. Retain them only for a material task-correctness improvement or a material reduction in missing-evidence follow-up searches, with no critical-category correctness regression and context cost inside a fixed guardrail; efficiency can never offset worse correctness. If the comparison is tied or fails, remove the classifier boundary/code, intent metadata/policy identity, promotion rule, tests, and documentation before RC rather than ship dormant scaffolding or a feature flag. Exact thresholds and trials are fixed after baseline measurement and before candidate results.                                                                                                                                                                                                                                                     |
| D-082 | `max_context_tokens` is a hard aggregate ceiling over the exact serialized text in non-null `SearchSnippet.text` fields only. Dolphin sums each snippet's independent count under one bundled, digest-verified, offline `cl100k_base-v1` tokenizer; bounded hit metadata, citations/references, and next actions are outside this number and remain separately schema-bounded. Allocation uses coherent complete-line windows and may shrink at line boundaries or leave a hit's snippet null, but never splits a line/Unicode code point, estimates/falls back, downloads tokenizer data, or exceeds the ceiling. Results expose accounting version, per-snippet count, and aggregate used count; all equal the serialized payload and are cursor/cache/policy-bound.                                                                                                                                                                                                                                 |
| D-083 | Snippet allocation is the deterministic internal `hybrid-v1` policy. It first walks diversified ranked hits and seeds up to three non-overlapping targets with each target's smallest useful complete-line window that fits, skipping rather than blocking on a target that cannot fit. It then greedily chooses fitting whole-window actions by fixed marginal-value tiers: complete a seeded structural unit, add first evidence from a new workspace/path, then add/expand other evidence; ties use original rank, fewer added tokens, and stable target ID. It never backtracks, splits windows, guarantees a snippet per hit, or exposes weights/counts/strategy knobs. Version and closed selection reasons are observable and cursor/cache-bound; task-correctness evaluation may replace the fixed policy only through a release decision.                                                                                                                                                     |
| D-084 | Search result and snippet budgets are per response page. A continuation reuses the first page's exact applied `max_results` and `max_context_tokens`, effective profile/policy, retrieval mode/ranking/relevance calibration, workspace publications/scope, token-accounting version, and snippet-allocation version; neither configuration changes nor continuation inputs can resize or reinterpret them. Each explicit page call gets a fresh snippet allowance for only its next hits, reports page-local use, and excludes every exact target emitted earlier. The final page has no cursor; invalid/expired/mismatched state returns no partial page. Pagination never silently duplicates, drops, or changes ranking of the pinned candidate sequence.                                                                                                                                                                                                                                          |
| D-085 | `search` has one strict-compatible root object with one required `request` property. That property is a nested closed `anyOf`: either `kind = "query"` with the complete first-page fields and no cursor, or `kind = "continue"` with exactly one opaque cursor and no query/scope/filter/budget fields. Every object forbids extras and every declared property is required; query-variant optionals use explicit `null` or empty arrays. This preserves structural mutual exclusion while avoiding a top-level union, matches current OpenAI strict tool-schema constraints, remains ordinary JSON Schema for MCP clients, and never falls back to a permissive/non-strict alternate schema. Runtime and generated-client parity tests freeze the canonical schema.                                                                                                                                                                                                                                  |
| D-086 | Cursor-only search continuation uses immutable private SQLite state and a 256-bit versioned opaque bearer handle. Persistence contains no raw query, source/snippet text, embedding/vector, provider payload, or raw retrieval score: only query/scope fingerprints, ordered bounded target/focus pointers with one-based rank/relevance band, pinned publications/versions/modes/budgets/calibration identity, page position, timestamps, and reachability edges needed to reproduce pages. The entire session and its exact artifacts expire logically 30 minutes after first-page creation; access/replay/restart/clock movement never refreshes it. Issued page handles are digest-only persisted and idempotently replayable; a domain-separated hash chain derives the same successor handle without a signing/encryption key. State works across local runtimes/restarts, becomes `CURSOR_EXPIRED` at `now >= expires_at`, and compacts asynchronously after losing all authority/reachability. |
| D-087 | A first-page search materializes one deduplicated ranked continuation plan containing at most the top 500 exact workspace-publication targets. Candidate generation may inspect a bounded larger internal pool to produce those 500, but continuation never reruns query embedding, vector/FTS retrieval, fusion, ranking, or a provider call beyond that immutable horizon. The 500-target constant is versioned internal retrieval policy, independent of output TOML/profile/page budgets and unavailable through MCP/config. Results report the fixed horizon, retained count, and whether eligible ranked targets were cut at the horizon; after the retained plan is exhausted no cursor remains, and a horizon-hit final page recommends a narrower fresh query rather than implying global exhaustion.                                                                                                                                                                                         |
| D-088 | A complete search page remains successful when optional continuation-state or successor-position persistence cannot be proven. The result's required `continuation` block is exactly `available` with a proven cursor/deadline, `exhausted` with no cursor/reason, or `unavailable` with no cursor and one closed reason (`disk_pressure`, `writer_busy`, `commit_unverified`, or `storage_unavailable`). Cursor persistence gets one short bounded transaction and never triggers provider/retrieval replay, synchronous GC, or page failure. Unavailability does not mark correct hits stale or retrieval degraded; prominent next actions use returned references immediately and either retry the same known continuation cursor or issue a fresh/narrower query later. Any possibly committed but undisclosed state remains unreachable and expires normally.                                                                                                                                     |
| D-089 | MCP search hits expose no floating-point component, fused, normalized, or probability-like score. Each hit carries its stable one-based global rank within the pinned top-500 plan and one closed relevance band: `high`, `medium`, or `exploratory`. A versioned local calibrator is fitted/evaluated separately for each shipped retrieval/ranking mode and maps ephemeral internal ranking features to those action-oriented bands; the band never changes ordering or claims correctness probability. Production discards raw scores before result/cache/cursor persistence and never logs them. Only isolated bounded development/evaluation artifacts may retain source-free raw scores. Calibration version is observable and cursor/cache-bound, unconfigurable through MCP/TOML, and must change with any score semantics.                                                                                                                                                                    |
| D-090 | `high` and `medium` are independent fail-closed release claims. Before candidate results are viewed, Dolphin preregisters precision, uncertainty, minimum-support, stability-stratum, and out-of-distribution rules; each exact shipped retrieval-mode/ranking-policy profile is fitted on non-test judgments and evaluated once on disjoint held-out judgments. A band is enabled only when its complete gate passes. A disabled `high` may fall through to a validated `medium`; any hit not covered by an enabled band or supported calibration distribution is `exploratory`. Failure never changes rank or disables search. There is no online/user-specific fitting, threshold fallback from another mode/policy, post-result target revision, or MCP/TOML override; any later ranking/calibration change requires a new version, fresh held-out gate, and cursor/cache identity.                                                                                                                |
| D-091 | The initial D-090 gate uses exact unrounded one-sided 95% Wilson lower bounds. Per final mode/policy profile, proposed `high` requires at least 50 held-out predictions and lower bound `>= 0.85`; the cumulative proposed `medium`-or-higher set requires at least 75 and `>= 0.65`, so a disabled `high` can safely fall through. For each preregistered critical stratum, a band is supported only with at least 20 predictions and corresponding lower bound `>= 0.75` for `high` or `>= 0.55` for medium-or-higher. Smaller or failing strata lose only that band's authority and fall through conservatively. Counts are unique final judged query-target pairs, no prediction/stratum pooling or weighting rescues a failure, and gate arithmetic is dependency-free, deterministic, and artifact-recorded.                                                                                                                                                                                     |
| D-092 | Held-out relevance uses one final task-utility grade per unique query-target pair: `direct` when the target itself identifies the requested implementation/behavior or indispensable evidence, `supporting` when it adds material task progress but requires other evidence, and `not_useful` when incidental, semantically redundant with adequate higher-ranked evidence, misleading, or unrelated. Grading uses the frozen task/query, pinned snapshot, a canonical bounded target view, and earlier-target views only for redundancy, while hiding numeric rank, retrieval mode/policy, scores/features, provisional/production bands, and gate results. High precision counts only `direct`; cumulative medium-or-higher counts `direct` plus `supporting`. Grades are about actionable evidence rather than lexical/embedding similarity, are immutable after held-out reveal, and include a closed reason for audit without entering production.                                                |
| D-093 | Calibration assumes exactly one human reviewer and uses preregistered test-retest reliability rather than synthetic consensus. Before held-out grading, two independently shuffled/blinded passes over a separate rubric pilot at least seven days apart must achieve quadratic-weighted Cohen's kappa `>= 0.70` and exact-grade agreement `>= 0.80`; a degenerate/undefined statistic fails. The held-out run secretly repeats a deterministic stratified 20% of unique pairs, at least 30, and must clear the same gates. Repeats count once; disagreements finalize to the lower-utility grade. Pilot failure requires a revised rubric/examples and new digest before retry; held-out failure invalidates that run and requires fresh held-out evidence. Model judges may produce separate diagnostics but never grades, tie-breaks, support, or release authority.                                                                                                                                |
| D-094 | Each exact mode/policy profile gates five marginal runtime-known dimensions independently per band: hit language (`python`, `javascript`, `typescript`, `svelte`, `sql`, `markdown`, `rust`, or `generic`), unpromoted base scope-size profile (`small`, `medium`, `large`, `massive`), workspace breadth (`one`, `multiple`), filter shape (`none`, `path`, `language`, `both`), and one-based global-rank bucket (`1-3`, `4-10`, `11-50`, `51-500`). A hit may emit `high` or `medium` only when that profile's global band gate and every applicable marginal cell passed D-091; otherwise it falls through independently. Path shape includes nonempty include or exclude paths, non-first-class/unknown content maps to `generic`, and all cell derivation is deterministic/source-free. Cross-products are reported diagnostically but have no release authority in 0.3.0 and cannot rescue or veto a marginal result.                                                                           |
| D-095 | Calibration partitions are group-disjoint by both repository family and semantic task/query-template family: every revision, branch, worktree, fork/fixture derivative, and near-duplicate task variant stays in one of rubric pilot, fit/tuning, or held-out, and a multi-repository case is held out only when every family is held out. Held-out queries, repositories, labels, features, and outcomes cannot tune retrieval/ranking/calibration, thresholds, strata, or sampling. Within each global or marginal Wilson population, a preregistered domain-separated hash over frozen seed/population/query/target IDs selects at most one provisional target per query before labels; the same selected pair may legitimately serve its applicable marginal gates, while all other correlated hits are diagnostic-only and never add support. Split/sampling manifests are immutable/digested, and contamination invalidates the run.                                                             |
| D-096 | Release-authority calibration fit and held-out corpora use only pinned immutable commits from real permissively licensed public repository families and original human-authored, revision-grounded tasks representative of solo-developer agent work, frozen before retrieval. Dolphin's own family is excluded from held-out. Synthetic/copied micro-fixtures, contrived edge cases, generated or mechanically paraphrased tasks, and model-produced judgments may exercise pilot, unit, robustness, or diagnostic paths but can never fit thresholds, add D-091 support, pass a stratum, or authorize a band. Source-bearing checkouts, target views, tasks, and judgments remain private ephemeral/retention-bounded evaluation artifacts outside production and distributable files; release provenance contains only stable IDs, public origin/license/commit metadata, bounded aggregate outcomes, and cryptographic digests.                                                                    |
| D-097 | Authority-bearing repository scope accepts only SPDX `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, and `Zlib`. Every leaf identifier in a parsed SPDX expression must be in that set; `AND`/`OR` combinations solely of allowed leaves pass, while any copyleft/source-available/custom/deprecated/unknown identifier, `LicenseRef`, `WITH` exception, missing/unparseable expression, or unresolved license file fails. The pinned commit manifest records normalized expression and license-file digest. Nested eligible license/package metadata is discovered conservatively; an independently licensed subtree must pass the same rule or be excluded before task/target generation, and any ambiguous coverage rejects authority rather than inviting legal interpretation. This is an evaluation-admission policy, not legal advice.                                                                                                                                              |
| D-098 | Private source-bearing calibration material from a failed or invalid run expires logically seven days after terminal finalization. Material from the successful 0.3.0 authority run expires at the earlier of 30 days after public release or 90 days after run finalization; learning the release time may shorten but never extend the original deadline. Reads fail after logical expiry. CI teardown removes its run workspace, while local physical reclamation occurs on the next evaluation/cleanup command or an explicit earlier development-only cleanup—never a daemon or installed product/MCP control. Cleanup affects only isolated evaluation copies. Bounded source-free provenance/decision manifests remain retainable.                                                                                                                                                                                                                                                              |

## 4. Goals and non-goals

### 4.1 Release goals

1. **One coherent setup path.** A developer can install Dolphin, configure an OpenAI key, add one MCP entry, and let the agent perform the remaining safe setup.
2. **Autonomous repository enrollment.** Agent instructions make repository discovery and explicit `repo_add` use obvious. Registration and indexing are idempotent and observable.
3. **Self-maintaining runtime.** The Python MCP process initializes storage and application services in-process, reports readiness and failures, and shuts down cleanly without `dolphin serve` or another supervised process.
4. **High-signal agent tools.** The tool set is small, task-oriented, structured, and safe. Results make the next action obvious.
5. **Demonstrated value.** An evaluation suite shows meaningful gains over built-in agent tooling on representative code-discovery tasks.
6. **Unified release.** All public artifacts report 0.3.0 and are validated and published as one release transaction.
7. **Clean implementation base.** Obsolete compatibility code, generated artifacts, backups, stale documentation, and redundant surfaces are removed.
8. **Worktree-native efficiency.** Parallel agent worktrees remain isolated and searchable without paying the time or embedding cost of indexing unchanged repository content again.

### 4.2 Non-goals

- Preserving any 0.2.x CLI, REST, MCP, configuration, or storage contract.
- Supporting embedding providers other than OpenAI.
- Supporting user-selectable embedding models or dimensions.
- Windows or Linux certification.
- Intel macOS, Rosetta-translated execution, macOS 13 or earlier, or source-built native-dependency installation.
- A hosted multi-tenant service.
- A public or private HTTP API and network-server deployment mode.
- An always-on daemon, macOS LaunchAgent, login item, detached worker, or watcher that survives its invoking Dolphin process.
- Remote telemetry collection, a metrics listener, or a bundled monitoring deployment stack.
- A graphical administration interface.
- General-purpose filesystem access outside explicitly registered repositories.
- Giving agents unscoped or source-destructive tools such as store reset, arbitrary workspace deletion, forced GC, or forced repair.
- Agent-owned versus human-owned repositories, temporary/persistent registration modes, or registration promotion/transfer workflows.
- A parallel human CLI workflow for repository enrollment or first indexing.
- Replacing exact text search when exact text search is already the best tool.

## 5. Required user experience

### 5.1 Installation and connection

The 0.3.0 support target is native `arm64` execution on Apple Silicon macOS 14.0 or newer. Documentation and package metadata must say so before installation; setup, MCP startup, CLI entry points, and `doctor` must return a typed `UNSUPPORTED_PLATFORM` diagnostic on a non-Darwin, non-`arm64`, Rosetta-translated, macOS 13-or-earlier, or unparseable runtime rather than attempting partial operation. Release qualification uses native Apple Silicon hosts only and must prove dependency resolution selects wheels without invoking a compiler or native source build.

The final installation flow has one canonical path. It must:

- install one resolved Python distribution containing the MCP server and Dolphin core into a persistent isolated uv tool environment;
- keep the installed version stable across MCP launches until the developer explicitly upgrades it;
- avoid asking the user to launch a second long-running process;
- detect a missing `DOLPHIN_OPENAI_API_KEY` and explain exactly how to provide it for the active launch context;
- place mutable data under a single documented Dolphin application directory;
- provide a machine-readable `doctor` result for both agents and humans;
- print no non-protocol output to MCP stdout;
- avoid requiring the user to understand MCP internals, LanceDB, or SQLite.

The canonical lifecycle is:

```bash
uv tool install --python 3.13 pb-dolphin
dolphin setup codex       # or: dolphin setup claude-code
# The configured client launches: dolphin mcp
uv tool upgrade pb-dolphin
```

The MCP client invokes `dolphin mcp`; it does not invoke `uvx` on every launch. The README must explain that uv downloads a compatible CPython 3.13 when necessary, explain `uv tool update-shell`, and show how to configure the installed executable by absolute path for GUI clients that do not inherit the user's shell `PATH`. An exact-version `uvx --python 3.13 --from 'pb-dolphin==0.3.0' dolphin mcp` example may exist for a disposable trial or diagnostic reproduction, but it is not the supported steady-state installation.

All Dolphin entry points run a shared interpreter preflight before opening storage, starting workers, or resolving credentials. It accepts only CPython 3.13 with the ordinary GIL-enabled ABI and returns typed `UNSUPPORTED_PYTHON` remediation for Python 3.12/3.14+, PyPy or another implementation, and free-threaded/debug variants. Patch-level 3.13 updates are allowed, but the release lock and clean-install gate must prove every native dependency has a compatible wheel.

`DOLPHIN_OPENAI_API_KEY` is read only from the child process environment. README setup must distinguish shell-launched clients, where `.zshrc` may provide it, from GUI-launched clients, which commonly do not source interactive shell files and therefore need an MCP-client `env` entry or an explicit launcher/wrapper. A 1Password `op run` recipe may be documented as an optional injection example, not a Dolphin dependency or default storage backend.

### 5.2 Agent orientation

On connection, the MCP server must provide short server instructions equivalent to:

> Dolphin performs semantic and structural code discovery across explicitly indexed workspaces. Before repository-wide discovery, resolve the current Git worktree. If that exact worktree is absent, call `repo_add` with its absolute root—even when another worktree of the same repository is already registered. Scope searches to the current workspace. Use `search` for concepts, behavior, architecture, and cross-file discovery; use built-in exact search for known strings and filenames. Follow Dolphin results with `open_ref` or the client’s file-reading tool.

The same behavior must be reinforced by tool names, descriptions, examples, and the bundled agent skill. Agents should not need a user to explain the setup sequence.

The canonical guidance also teaches capability-scoped cleanup: obtain a fresh cleanup receipt from the unregistered-worktree next action (or generate one locally), retain it before `repo_add`, reuse those exact arguments if the response is lost, and call `repo_forget` if that exact workspace registration is no longer needed. `cleanup = null` means a different receipt created the registration epoch and this caller has no cleanup authority. This is not an agent/human or temporary/persistent repository classification. Cleanup releases only Dolphin's registration and derived state; deleting a Git worktree remains outside Dolphin.

### 5.3 First repository flow

Repository enrollment is an MCP workflow. Neither `dolphin setup`, `dolphin doctor`, process startup, the current working directory, nor any human CLI indexing command may create or reactivate a registration; the sole public creation path is the agent's explicit `repo_add` call with the concrete path and a fresh cleanup receipt.

1. The agent determines the absolute root of the exact Git worktree in scope.
2. The agent calls `repo_list` or obtains workspace readiness from `status`.
3. If that exact worktree is absent, the agent calls `repo_add` explicitly, even if a sibling worktree is registered.
4. Dolphin validates and canonicalizes the path, detects the worktree and shared Git common directory, evaluates ignore rules, and registers the workspace idempotently.
5. Dolphin performs a bounded preflight, starts indexing without a separate approval prompt, and returns a structured operation identifier plus immediately useful status. If the supplied receipt created or already matches the registration epoch, the result echoes its cleanup authority. Only an approvable aggregate catastrophic-fuse stop pauses in `awaiting_approval` with explicit human remediation.
6. The agent polls immediate `operation_status` snapshots only while task progress depends on them; no MCP call blocks for an entire large index.
7. Search becomes available only when a complete generation is atomically committed. Staged partial index data is never searchable.
8. File watching or bounded refresh keeps the repository useful after initial indexing.
9. If the `repo_add` result included cleanup authority and the agent later knows that exact workspace registration is no longer needed, it calls `repo_forget` with the returned workspace ID and receipt. Registrations are otherwise indistinguishable; a call without the receipt cannot remove one, and source/Git worktree removal is never part of this path.

### 5.4 Returning workflow

- MCP startup acquires safe access to the configured store, initializes schemas and application services in-process, and reports readiness through MCP.
- A second Dolphin process targeting the same writable store must coordinate safely or fail with actionable remediation; it must not start another hidden service.
- Dolphin detects stale, missing, incompatible, or corrupt local state and exposes a specific diagnosis.
- Safe recovery may be automatic. Destructive recovery requires an explicit human-facing CLI action or a separately designed confirmation mechanism.
- An agent can inspect repository freshness without interpreting logs or database state.

### 5.5 Freshness behavior

- Dolphin watches every ready registered repository while the MCP runtime is active.
- Watch events are debounced and submitted through the same durable incremental-sync operation path used by `repo_sync`.
- Every search performs a cheap repository fingerprint/drift check before retrieval; it does not rescan or rechunk the entire repository.
- When drift is small, search waits for a short, bounded incremental catch-up before querying.
- Search never waits indefinitely for indexing. If catch-up exceeds its bound, it queries the last atomically committed index and marks the result stale in structured metadata.
- A stale response includes the indexed revision/fingerprint, observed current revision/fingerprint, pending operation ID, reason, and an agent-ready next action.
- Branch switches and bulk file changes must be distinguished from ordinary edits and may schedule a larger sync while preserving the last committed searchable index.
- `repo_sync` accepts only an exact `workspace_id` and submits freshness work without waiting for indexing to complete. It performs the same cheap drift, policy, boundary, credential, catastrophic-fuse, and disk-reserve checks as automatic reconciliation; it cannot bypass or replace them.
- A current workspace returns `up_to_date` without creating an operation or making a document-embedding call. An exact compatible in-flight target returns that existing operation; otherwise Dolphin creates at most one durable operation for the observed target. Concurrent/repeated requests cannot duplicate parsing, embedding, or publication work.
- The agent cannot request incremental versus full behavior. Dolphin derives the smallest correctness-preserving plan from published compatibility and Git/worktree evidence, reuses all verified artifacts it can, and performs an internal rebuild only when no safe delta/adoption path exists.
- `open_ref` securely reads only current eligible worktree content. It returns indexed/current fingerprints and machine-readable exact-file, unchanged-range, relocated, or unresolved drift alignment; it never silently presents current bytes as the exact indexed match or offers a historical-content mode.

First-generation readiness rules:

- Indexing writes into an unpublished staging generation. Readers, search caches, any retained graph traversal, and reference resolution cannot observe its files, chunks, vectors, or relationships before atomic publication.
- If the workspace has no complete compatible committed generation, `search` returns immediately with typed `INDEX_BUILDING`, unless its operation is blocked by a more specific typed error such as `SCOPE_FUSE_TRIPPED`; it does not issue a query-embedding request or return staged hits.
- `INDEX_BUILDING` includes workspace and operation IDs, durable operation state, current phase, meaningful completed/known-total counters, last-progress time, retryability, and ready-to-use `operation_status` plus built-in-search next actions. It does not invent an ETA when progress data cannot support one.
- An exact reusable commit generation may be adopted atomically as the workspace's first committed generation. If a dirty/untracked overlay is still building, search may use that complete clean generation only through the normal conspicuous `stale` contract.
- For an explicitly requested multi-workspace search, a workspace with no complete generation is not silently omitted. The search returns no combined result set: `SCOPE_FUSE_TRIPPED` takes precedence when any required workspace awaits approval; otherwise `INDEX_BUILDING` carries all unavailable coverage details. The agent may retry with only ready workspace IDs if that narrower scope is correct for its task.
- A crash, cancellation, provider failure, or safety-fuse stop before publication leaves no partially searchable generation. Recovery resumes or restarts the durable operation; prior complete generations remain untouched.
- Once a workspace has a complete committed generation, all later syncs retain the previous complete snapshot until the replacement publishes atomically. This is the only case where stale search succeeds during indexing.

### 5.6 Actionable references and paths

Every search hit must include:

- stable repository-family ID, stable workspace ID, and human-readable names;
- POSIX-style repository-relative path;
- canonical absolute local path;
- one-based inclusive start and end lines;
- opaque Dolphin-issued reference in the form `dolphin://ref/<stable-id>`;
- indexed content fingerprint used to detect later reference drift.

Absolute paths are returned by default because the local agent can use them immediately with built-in file-reading and editing tools. Dolphin references remain the canonical identity for `open_ref` and for clients that cannot directly access local paths. Both forms must derive from the same validated registered root; callers cannot supply or resolve arbitrary absolute paths through `open_ref`.

### 5.7 Target architecture

```text
Agent MCP client ---------> Python MCP adapter ----+
                                                   |
Human maintenance CLI ---> Python CLI adapter -----+--> Application services
                                                           |
                             +-----------------------------+------------------+
                             |                             |                  |
                             v                             v                  v
                    Repository/index service       Search service      Operation service
                             |                             |                  |
                             +-----------------------------+------------------+
                                                           |
                                 SQLite metadata/FTS5 + local LanceDB vectors
                                                           |
                                                           v
                                              OpenAI Embeddings API (index/query)
```

Architecture rules:

- MCP and CLI adapters validate and serialize external contracts but contain no domain workflow logic.
- Application services are transport-independent Python APIs and own transaction boundaries.
- MCP calls application services directly in-process; there is no HTTP serialization or loopback networking.
- Existing FastAPI handlers may be mined for behavior, but endpoint shapes are not compatibility constraints.
- The CLI is limited to setup, diagnostics, explicitly scoped foreground execution of an already-created operation, evaluation/development operations that do not create production registrations, explicit cleanup, and intentionally human-gated destructive maintenance. It exposes no repository-enrollment or first-index command.

### 5.8 Concurrent runtime behavior

- Any number of MCP runtimes may open compatible committed index state for concurrent search.
- Mutations acquire a short-lived interprocess writer lock scoped as narrowly as storage correctness allows; a runtime must not hold the writer lock for its entire lifetime.
- Lock contention returns or waits according to a bounded policy and exposes owner, operation, start time, and retry guidance without leaking unrelated process details.
- Each registered workspace has one renewable maintenance lease for continuous watching. Other runtimes may search it and submit explicit operations but do not run duplicate watchers.
- A lease expires after missed heartbeats. Another healthy runtime may then acquire it and reconcile drift before watching.
- Index publication is atomic: readers observe the previous committed workspace generation or the next committed generation, never a partially written mixture.
- Operation IDs and idempotency keys prevent duplicate `repo_add` or `repo_sync` work when clients race.

### 5.9 Repository and worktree model

Dolphin distinguishes a shared Git repository from a concrete working checkout:

- **Repository family:** stable identity derived from the canonical Git common directory, with optional normalized remote metadata. It groups related worktrees but is never itself a search target.
- **Workspace:** one canonical worktree root with a stable Dolphin ID, current HEAD/branch metadata, dirty-state fingerprint, independent index generation, and freshness state. A normal clone's primary checkout is also a workspace.
- **Commit generation:** an immutable, reusable manifest of file/chunk artifacts for a clean Git commit under one effective indexing configuration.
- **Workspace overlay:** changed, deleted, and untracked content relative to the workspace's clean HEAD generation.
- **Index namespace:** the resolved commit generation plus workspace overlay used to represent one workspace's current code state.

Required behavior:

- `repo_add` accepts any worktree root, discovers both `--show-toplevel` and `--git-common-dir`, and registers the concrete workspace without canonicalizing it to a sibling checkout.
- Two worktrees from the same repository family may contain different branches, commits, uncommitted changes, ignored files, and repository-local Dolphin configuration.
- Search defaults must never merge sibling worktrees implicitly. A query targets one resolved workspace unless the caller explicitly requests several.
- Branch names are mutable metadata, not identity. Workspace identity survives branch switches and detached HEADs while its index updates atomically.
- Each workspace receives a persisted cryptographically random 128-bit internal ID at first registration; safe reactivation reuses that record rather than deriving a public identity from a path, branch, or remote.
- Stable references and absolute paths carry the workspace ID so `open_ref` resolves the exact checkout that produced a hit.
- Deleted or moved worktrees become `missing` and are reported; Dolphin does not silently retarget their IDs to another checkout or automatically destroy their prior index.
- A newly registered or branch-switched workspace must first look for a compatible commit generation in its repository family. Exact matches are adopted without parsing or embedding unchanged files.
- When no exact generation exists, Dolphin chooses a compatible indexed generation and uses Git tree differences to derive the target generation. It processes only added, modified, renamed-as-needed, and deleted paths.
- Dirty tracked files and untracked eligible files form a workspace-specific overlay after the clean HEAD generation is selected or built.
- Identical chunking and embedding inputs reuse content-addressed artifacts across commit generations and workspace overlays. File/chunk membership, paths, retained graph edges, and freshness remain workspace-specific where their meaning differs.
- A full filesystem re-index is permitted only when no compatible family generation exists, the embedding model changes, the effective chunking/index schema is incompatible, or integrity checks prove reuse unsafe.
- Correct isolation always outranks reuse. If Dolphin cannot prove an artifact is compatible with the target workspace, it recomputes that artifact rather than risking cross-worktree contamination.
- Repository-family and workspace display labels are derived presentation metadata. Family labels prefer the canonical primary-checkout/common-directory basename, with normalized remote basename and stable short ID as fallbacks; workspace labels combine the concrete root basename with branch or detached-HEAD context.
- Display-label collisions never prevent registration and never affect resolution. Serialized choices append a stable short ID when needed, while all tool scopes, operations, references, leases, and index namespaces use full stable IDs.
- Branch switches, root moves, or better metadata may change a display label without changing identity. Dolphin exposes no MCP naming/renaming input in 0.3.0.

### 5.10 Current-workspace resolution

Workspace-aware tools use this precedence:

1. An explicit `workspace_id` in the tool call always wins after validation. An explicit list is required for deliberate cross-workspace search.
2. If the client exposes MCP roots, every repository-bearing root must resolve to the same registered worktree to select it. Distinct registered, unregistered, or invalid worktree candidates are ambiguous rather than guessed. Nested subdirectories resolve to their containing worktree.
3. A successful `repo_add` or explicit workspace call establishes a session-local default for that MCP connection.
4. If still unresolved, Dolphin examines the MCP process working directory and selects it only when it belongs unambiguously to one registered worktree.
5. Dolphin does not fall back to a globally registered workspace merely because only one exists.

When resolution fails, the tool returns `WORKSPACE_REQUIRED`, `WORKSPACE_AMBIGUOUS`, or `WORKSPACE_MISSING` with candidate IDs, names, branches, HEADs, roots, and a ready-to-use corrected tool call. Root-change notifications invalidate any lower-precedence inferred scope. Session-local defaults never change global repository metadata and never leak between MCP connections.

### 5.11 Missing-workspace retention and garbage collection

- A registered workspace whose canonical root disappears is marked `missing`, stamped with `missing_since`, excluded from default resolution/search, and shown with remediation in `status` and `repo_list`.
- An explicit authorized `repo_forget` is distinct from disappearance: it marks the registration `forgotten`, bypasses the 30-day workspace-overlay recovery window, and creates a new registration epoch if that worktree is later added again. Shared/reusable reachability protections still apply exactly as normal.
- Re-registering a worktree while sufficient retained evidence proves the same repository-family and concrete-worktree identity preserves its stable workspace ID but creates a fresh registration epoch/receipt. Otherwise it receives a new ID. Compatible generation/artifact reuse is independently verified and never depends on ID reuse.
- Workspace-specific overlay/manifests remain recoverable for 30 days. After that grace period, automatic GC may remove them only if no active workspace, operation, protected generation, or live reader lease reaches them; merely returning an opaque reference creates no permanent pin.
- Clean commit generations are repository-family reuse assets. They are not removed merely because one workspace disappears; inactive generations participate in the longer-lived, release-defined internal LRU/storage-pressure policy in Section 5.32.
- Active workspace generations, in-flight operation inputs, and any artifact reachable from them are always protected.
- GC uses transactional mark-and-sweep or an equivalently auditable reachability algorithm. It must not rely solely on mutable reference counters.
- Automatic GC runs as low-priority maintenance, never blocks MCP startup/search, and records aggregate reclaimed counts/bytes without source content.
- The human CLI provides `dolphin gc --dry-run` and an explicit apply mode with the same reachability engine. MCP exposes no direct GC command or deletion-policy knob; `repo_forget` changes only one authorized registration's reachability and may schedule the ordinary bounded collector without widening what it can delete.
- GC deletes only Dolphin's derived data and metadata. It never touches a Git repository, worktree, source file, or 1Password/OpenAI state.

### 5.12 Default indexing scope

Candidate discovery is Git-aware and evaluates the concrete worktree:

- Include tracked files plus untracked files not excluded by Git's standard ignore rules so an agent can search newly created work before it is committed.
- Include first-party source, tests, test fixtures, documentation, examples, scripts, CI workflows, manifests, and human-authored configuration by default.
- Exclude dependency/vendor directories, virtual environments, package caches, build/dist outputs, generated bundles, minified files, source maps, coverage/test reports, lockfiles, editor caches, binary/media/archive files, and files that fail bounded text/binary checks.
- Treat path classification and file eligibility as versioned pipeline inputs so changing these rules invalidates only affected artifacts/generations.
- Repository `.gitignore`, Git exclude files, and Dolphin's built-in patterns compose deterministically. A repo-local Dolphin configuration may add ignores or override ordinary noise exclusions.
- A repository include rule may re-include tracked or otherwise Git-eligible content excluded only by Dolphin's ordinary built-in noise policy. It cannot re-include Git-ignored untracked files, nested repositories, security exclusions, binary/non-text files, or files rejected by hard safety checks.
- Security exclusions are not overridable through repo-local configuration or MCP. They include actual `.env` variants (while allowing documented templates such as `.env.example`), private-key material, common credential files, and content with high-confidence private-key markers.
- Dolphin must not imply that filename/pattern exclusions constitute comprehensive secret detection. Installation and `repo_add` disclosure state that eligible repository text is sent to OpenAI.
- A skipped-file summary groups reasons and counts without echoing sensitive paths unnecessarily. `status` exposes enough aggregate information to diagnose unexpectedly empty or noisy indexes.
- Per-file text/size checks prevent pathological single files from dominating an index, while the repository-level catastrophic fuse remains intentionally permissive for large legitimate codebases.

### 5.13 Embedding model invariant

- Every document chunk and search query uses OpenAI `text-embedding-3-small` with Dolphin's one release-defined dimensionality.
- The model/dimensionality is a code-level 0.3.0 invariant, not a user, repository, workspace, or MCP setting.
- Model identity, dimensions, exact embedding-input hash, and embedding-contract version remain part of cache/vector keys even though the values are fixed. This makes corruption detectable and permits an intentional future release migration.
- Startup rejects mixed or incompatible vector collections with typed remediation; it never queries across incompatible dimensions.
- Clean initialization is the canonical 0.3.0 path. If a development migration from 0.2.x data is retained for convenience, it may rebuild derived vectors without promising compatibility.
- The evaluation harness may compare alternate models experimentally, but production artifacts and user configuration cannot select them.

### 5.14 Language-support contract

The public language registry uses stable family names. File variants map to a family so agents can filter with ordinary names rather than internal parser identifiers such as `typescriptreact`.

| Public language | Included forms                | Required 0.3.0 behavior                                                                                                                     |
| --------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `python`        | `.py`, `.pyi`, `.pyw`         | Parser-based functions, classes, methods, decorators, imports, and conservative symbol/relationship extraction                              |
| `javascript`    | `.js`, `.jsx`, `.mjs`, `.cjs` | Parser-based modules, exports/imports, functions, classes, methods, and JSX-aware boundaries                                                |
| `typescript`    | `.ts`, `.tsx`, `.mts`, `.cts` | JavaScript behavior plus interfaces, types, enums, namespaces, generics, and TSX-aware boundaries                                           |
| `svelte`        | `.svelte`                     | Component-aware template/script/style regions with JavaScript or TypeScript delegation for script content                                   |
| `sql`           | `.sql`                        | Statement- and definition-aware chunks for schemas, queries, views, routines, and common dialect constructs                                 |
| `markdown`      | `.md`, `.markdown`, `.mdx`    | Heading/section-aware chunks, fenced-code preservation, and useful document hierarchy                                                       |
| `rust`          | `.rs`                         | Parser-based modules, functions, structs, enums, traits, impls/methods, type aliases, constants/statics, macros, imports, and relationships |

Requirements common to every first-class language:

- The language has a dedicated structural chunker, registry entry, versioned parser/chunker identity, unit fixtures, integration coverage, and at least one agent-value scenario.
- Syntax errors or incomplete worktree edits degrade locally and visibly. Dolphin preserves valid surrounding structures and marks fallback chunks as degraded instead of dropping the entire file.
- Leading documentation comments, annotations/attributes, and signatures stay with the definition they describe. Line ranges remain exact and chunks do not silently omit semantically required headers.
- Chunk sizes remain bounded. Oversized structures split at language-appropriate child boundaries before token-window fallback.
- Graph extraction is conservative: uncertain relationships are omitted rather than represented as facts. Graph value must survive the same evaluation gate as other retrieval behavior.
- Language detection, public filter names, extension aliases, parser versions, chunker versions, and fallback status are observable pipeline inputs and participate in compatibility/cache keys.

Rust-specific requirements:

- Use a maintained Tree-sitter Rust grammar (or an equivalently robust embedded parser) distributed with the Python package. A clean macOS installation must not require `rustc`, Cargo, or execution of repository build scripts.
- Preserve outer attributes and doc comments with their item. Represent methods with impl/type/trait context so identically named methods remain distinguishable.
- Extract module declarations, `use` imports/re-exports, definitions, inherent impl relationships, and trait-implementation relationships. Calls or references are emitted only when the syntax provides enough evidence for a conservative edge; Dolphin does not claim compiler-grade name resolution.
- Cover nested modules, multi-crate Cargo workspaces, generics, lifetimes, async/unsafe/extern items, `macro_rules!`, macro-heavy regions, test modules, Unicode, incomplete edits, and parser-error recovery.
- `Cargo.toml` remains eligible generic TOML unless a later evaluated manifest-specific chunker is added; it is not mislabeled as Rust source.

Eligible JSON, YAML, TOML, shell, Justfiles, plain text, and unrecognized text formats use bounded generic chunks and remain available to lexical and semantic retrieval. Their result metadata must say `chunking_mode: "generic"`; Dolphin makes no promise of AST structure or graph completeness for them.

### 5.15 macOS runtime-state layout

The production root is `~/Library/Application Support/Dolphin/`, resolved from the current macOS user's home directory with filesystem APIs rather than shell interpolation. The space in `Application Support` must work in every CLI, MCP, lock, log, cleanup, and diagnostic path.

```text
~/Library/Application Support/Dolphin/
├── metadata.sqlite3       # authoritative registry, operations, FTS5, generations, leases, visibility
├── vectors/               # local LanceDB-derived vector artifacts/indexes; never visibility authority
├── artifacts/             # private immutable content-addressed chunk text and derived artifacts
├── locks/                 # short-lived interprocess coordination records
├── logs/                  # bounded, rotating local diagnostic logs
└── tmp/                   # transaction staging; safe to reconcile after interruption
```

Layout rules:

- This is the only production root for mutable Dolphin runtime data. Subdirectory names may be refined during implementation, but all state classes remain descendants of this root and are reported by `dolphin doctor`.
- Create and verify directories as current-user-owned `0700` and regular files as current-user-owned `0600`; unsupported ownership/type/link semantics or unfixable exposure fail before backend access as specified in Section 5.31.
- Resolve the root once at process initialization, pass a typed layout object into application services, and reject any derived path that escapes the canonical root. Code must not reconstruct storage paths ad hoc.
- The metadata schema version and each artifact's pipeline compatibility keys determine whether state is usable. Startup never guesses based on filenames alone.
- Temporary and unpublished transaction data are reconciled or removed after a crash. Published generations remain atomically readable.
- `dolphin doctor --json` reports the resolved root, existence, writability, available disk space, schema compatibility, and aggregate bytes by state class without exposing source content or secrets.
- Garbage collection and any human-invoked data removal operate only through validated descendants of this root. Repository and worktree paths are never deletion targets.
- The only Dolphin-owned repository policy path is root-level `.dolphin/config.toml`. It may be version controlled, is read-only to Dolphin, and never contains the OpenAI key, mutable global state, or operational overrides.
- Dolphin 0.3.0 does not read, import, or silently delete `~/.dolphin/`. Clean initialization is intentional because 0.2.x compatibility is out of scope.

### 5.16 DRY Codex and Claude Code integrations

The local stdio MCP server is the universal product boundary. Codex and Claude Code receive the same capabilities, safety model, workflows, tool names, schemas, examples, and remediation semantics. Client packages contain no retrieval, repository, indexing, credential, or storage behavior.

Three canonical Python-owned inputs drive every agent-facing artifact:

1. **Tool registry:** names, titles, descriptions, annotations, Pydantic input/output schemas, examples, mutability, and error contracts.
2. **Agent guidance specification:** when Dolphin adds value, when built-in exact tools are better, explicit `repo_add`, worktree scoping, freshness handling, references, and safety boundaries.
3. **Release metadata:** product name, package/executable name, version, supported clients, required environment variable, and documentation links.

Deterministic generation produces:

- the MCP initialization `instructions` string;
- runtime tool registration metadata and inspectable JSON Schemas;
- the Codex plugin/skill wrapper and its local stdio configuration examples;
- the Claude Code plugin/skill wrapper and its local stdio configuration examples;
- shared README quickstart fragments and contract fixtures used by tests;
- release manifests whose version is derived from the Python package version.

Mirroring rules:

- The first 512 characters of MCP `instructions` are self-contained and state the critical decision flow: use Dolphin for semantic/cross-file discovery, call `repo_add` explicitly for the exact worktree when needed, scope sibling worktrees independently, and prefer built-in tools for exact known strings/files.
- Normalized guidance blocks are byte-identical across generated client adapters wherever their host formats permit. Host-specific frontmatter, manifest keys, install commands, and capability labels are isolated in small renderers.
- Tool names, schemas, mutability annotations, examples, error codes, and next-action language come directly from the runtime tool registry. An adapter cannot rename, omit, or redefine a tool independently.
- The canonical source distinguishes required semantics from optional client affordances. If one client lacks an affordance, its adapter documents the equivalent workflow without changing Dolphin behavior.
- Generated files contain a source digest and a do-not-edit marker. Contributors edit canonical sources and rerun one Python generator; CI fails when regeneration changes the worktree or parity checks differ.
- The existing hand-maintained `skills/dolphin-search/SKILL.md` and `.claude-plugin` metadata are replaced by generated 0.3.0 artifacts after useful guidance is incorporated. Stale 0.2.x CLI, REST, `serve`, and low-level tuning instructions are not carried forward.
- Direct stdio MCP configuration remains available even where a plugin surface is unavailable. Hosted/remote ChatGPT plugin behavior is outside the local macOS 0.3.0 support promise.

Required client smoke scenarios are identical: clean connection, missing credential diagnostics, unregistered current worktree, autonomous explicit `repo_add`, non-blocking indexing, semantic search, exact-search deferral, reference follow-up, branch/worktree divergence, stale-index catch-up, structured failures, and restart after interrupted work. The same scenario IDs and expected semantic outcomes run through both client harnesses; only harness plumbing differs.

### 5.17 Client setup and verification

The supported setup commands are:

```bash
dolphin setup codex [--scope user|project] [--dry-run] [--json]
dolphin setup claude-code [--scope user|project] [--dry-run] [--json]
dolphin doctor --client codex|claude-code|all [--json]
```

Omitting `--scope` means `--scope user`. Calling `dolphin setup <client>` without `--dry-run` is explicit authorization to change only Dolphin-owned integration state for that named client; it never enrolls a repository. The command is deterministic and non-interactive so installation scripts and clean-machine tests exercise the same path as humans.

Required behavior:

- Resolve the installed `dolphin` executable to a canonical absolute path before planning changes. Client configuration must not depend on a GUI application's `PATH` finding the executable.
- User scope writes one global client entry and is the canonical quickstart. It makes the server available to all local projects while repository access remains empty until an agent calls `repo_add` for a concrete worktree.
- Project scope is used only when explicitly requested. It resolves and reports the exact current Git worktree root, validates containment for the client-specific project configuration path, and never redirects configuration to the shared Git common directory or a sibling worktree.
- A project-scoped setup may create or modify client configuration inside that worktree. Its dry run and result must identify the path and whether Git sees it as tracked, ignored, or untracked; Dolphin never commits or ignores the file automatically.
- If user and project entries coexist, inspect the client's real precedence rules and report the effective entry, shadowed entries, version/digest differences, and exact remediation. Setup and removal touch only the requested scope.
- Detect the target client's presence, version, supported native configuration commands/APIs, active configuration location, and any existing entry named `dolphin` before mutation.
- Prefer supported client-native configuration/install mechanisms. Target-specific direct file editing is a last resort and must use a format-preserving parser, compare-and-swap precondition, private same-filesystem backup, atomic replacement, post-write parse, and rollback on failed validation.
- A dry run emits the exact semantic changes, target paths, commands, scope, current/desired source digests, and validation plan while redacting all environment values and unrelated configuration.
- Configure only the absolute MCP command, `mcp` arguments, required environment-variable forwarding by name, generated client adapter, and Dolphin-owned metadata. Never place the value of `DOLPHIN_OPENAI_API_KEY` in a command line, generated file, backup report, log, or setup result.
- Setup does not require the key to be present. It may complete configuration and return a typed warning that `doctor` and MCP startup will fail credential readiness until the launch environment provides it.
- Exact desired state is a no-op. A prior Dolphin-managed entry is updated transactionally. An unmanaged or ambiguous entry using the same name is not overwritten; return a conflict with the existing location and explicit preview/replace guidance.
- Before direct mutation, verify the source file still matches the preflight digest. Concurrent or intervening edits abort safely rather than being overwritten.
- Preserve the minimum private backup necessary for lossless rollback, never inspect or log unrelated secret values, and document backup location/retention. Remove a backup only after successful parse plus client-native validation.
- Validate the resulting entry using the target client's supported inspection command and then run Dolphin's non-secret readiness checks. `dolphin doctor --client ... --json` distinguishes executable, configuration, adapter/version, environment-name forwarding, server startup, and credential-presence failures.
- Provide a symmetric explicit removal mode that removes only state carrying Dolphin's ownership marker/source digest. It refuses to delete an unmanaged same-name entry.
- If safe automatic configuration is unavailable, make no partial edit. Emit a generated, version-correct client-native command or configuration fragment plus a `doctor` command that verifies the manual result.
- These setup/removal operations are human CLI capabilities and are never exposed through MCP tools.

### 5.18 Query-time OpenAI degradation

Query execution distinguishes semantic availability from index freshness; a result can be current or stale independently of whether retrieval is hybrid or locally degraded.

Execution order:

1. Validate workspace coverage and complete-generation readiness before computing or fetching a query embedding.
2. Look up the exact query embedding under the fixed model/dimension/contract key. A compatible hit enables normal vector retrieval without an OpenAI request.
3. On a cache miss, call OpenAI under a short bounded timeout/retry policy appropriate for an interactive agent tool.
4. On a classified transient provider failure, run the local lexical/structural branches and return a successful but explicitly degraded result.
5. On missing/invalid credentials or a permanent request, model, dimension, or contract failure, return a typed error and no search hits.

Failure classification and behavior:

| Class                      | Examples                                                                                                               | Search behavior                                                                                     |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Credential absent          | `DOLPHIN_OPENAI_API_KEY` missing/empty                                                                                 | `OPENAI_KEY_MISSING`; no fallback; exact remediation                                                |
| Credential rejected        | Authentication/authorization rejected                                                                                  | `OPENAI_AUTH_FAILED`; no fallback; never echo provider payloads or key material                     |
| Transient provider         | Connection/timeout, throttling, or retryable service failure after bounded retry                                       | `lexical_structural` result with `degraded: true`, retryable provider category, and next actions    |
| Permanent request/contract | Invalid request, wrong model/dimensions, incompatible cached vector, or provider response violating the fixed contract | `OPENAI_REQUEST_FAILED` or `PIPELINE_INCOMPATIBLE`; no fallback that could conceal a product defect |
| Local retrieval failure    | A required keyword, metadata, or retained graph store cannot produce a valid result                                    | `SEARCH_FAILED`; never return a fabricated empty success                                            |

Degraded-result rules:

- Local fallback may use BM25/FTS, symbol/path/language metadata, and—only if D-040 promotes it—conservative graph expansion rooted in locally retrieved candidates. It must not claim semantic/vector coverage.
- `SearchResult.execution` exposes retrieval mode, query-embedding source, degraded reason category, retryability, and omitted branches. The warning is structured and prominent, not buried in prose.
- Degraded hits retain their own mode-specific ordering and relevance calibration. No raw score is exposed or treated as comparable to normal hybrid ranking.
- Exact cached query embeddings are contract-validated. When valid, their vector branch is normal hybrid retrieval and the result is not degraded merely because OpenAI is currently unreachable.
- Freshness and execution degradation compose explicitly. For example, an older complete generation queried through lexical fallback is both `stale` and `degraded`.
- Continuation cursors bind to retrieval mode, policy version, query-embedding fingerprint/source, workspace generations, and filters. A mode change invalidates the cursor with a ready-to-use fresh-search remediation instead of mixing rankings across pages.
- Bounded provider retry and fallback happen within the overall search time budget. The agent is not forced to wait through long exponential backoff.
- Next actions distinguish retrying Dolphin from using built-in exact search. The agent guidance must not overstate lexical fallback as a substitute for semantic discovery.
- Provider error bodies, headers, request identifiers that may contain sensitive data, and credential values are redacted before diagnostics. Local observability records only safe failure categories, counts, latency, and chosen mode.

### 5.19 Git submodules

A Git submodule is a distinct repository/workspace boundary even when its checkout is physically below a registered parent root.

- Discover submodules from Git index entries with gitlink mode plus validated `.gitmodules` metadata, not by blindly treating every nested directory or `.git` file as parent content.
- The parent eligibility engine excludes every declared submodule subtree consistently during initial scan, Git-diff derivation, dirty/untracked overlay construction, watcher handling, drift fingerprints, recovery, and GC reachability. No path may be indexed once as parent content and again as submodule content.
- The parent may index `.gitmodules` itself as eligible generic configuration and may retain non-content gitlink metadata for status. It never chunks or embeds the submodule working tree.
- `repo_add` and `repo_list` use the common bounded repository-boundary summary from Section 5.23. Submodules add expected gitlink commit, observed commit/dirty state, and initialization state without creating a second submodule-only response surface.
- Detection alone performs no network access, checkout, initialization, update, recursive traversal, or embedding request. Dolphin never runs `git submodule init`, `git submodule update`, repository hooks, or build scripts.
- If an agent's task actually requires an initialized submodule, the agent explicitly calls `repo_add` with that submodule's absolute root. The normal standing-key consent, path validation, safety fuse, asynchronous indexing, and first-generation rules then apply to the submodule workspace.
- Resolving a path within an initialized submodule selects the deepest enclosing Git worktree—the submodule—not the parent. An uninitialized gitlink path is not a worktree and returns an actionable validation error rather than enrolling the parent again.
- A registered submodule receives its own repository-family/workspace IDs, generations, overlay, watcher lease, freshness, references, and display labels. Reuse with another checkout occurs only when normal Git-common-directory and pipeline compatibility prove it safe.
- Parent and submodule searches remain separate by default. A task spanning both uses an explicit multi-workspace search list; Dolphin never adds registered submodules implicitly to parent scope.
- Changes inside the submodule working tree affect only the submodule workspace. Changes to the parent's `.gitmodules` or gitlink commit affect parent metadata/freshness but do not cause parent content indexing of the child tree.
- Invalid, escaping, cyclic, missing, deinitialized, or conflicted submodule metadata is reported without following the path. Every reported absolute root must pass containment and canonical path validation.
- Nested submodules follow the same rule recursively only when their immediate parent submodule is separately registered. Registration never cascades.

### 5.20 Cross-encoder reranking evidence gate

The starting 0.3.0 production candidate uses lightweight ranking that installs with Dolphin's normal Python dependency set. The existing Torch/`sentence-transformers` path is retained only long enough to run a controlled ablation; its current existence is not evidence that it belongs in the product.

Before running candidate trials, record:

- the exact lightweight and cross-encoder ranking policies, model/weight identity, dependencies, prompts/tasks, repositories/revisions, agent/model settings, trial count, randomization, and evaluator rubric;
- the minimum material improvement required on primary agent-task correctness, confidence/variance expectations, and critical-category non-regression rules;
- secondary guardrails for time to relevant code, end-to-end latency, peak memory, install/download size, clean setup time, and offline restart behavior;
- the decision deadline before 0.3.0 RC freeze and the owner/artifact that records the irreversible release choice.

Decision rules:

- Offline retrieval metrics such as recall, MRR, or NDCG are diagnostic only. Promotion requires a material improvement in blinded end-to-end agent task correctness under the matched-trial design in Section 9.
- Compare identical candidate generation, fusion inputs, result/context budgets, and agent conditions; the cross-encoder is the only intentional treatment difference.
- Attempt reasonable lighter-policy recovery within the fixed tuning budget. The heavy path passes only when its correctness gain remains material after that comparison.
- If the gate fails, remove the runtime module, optional extra, Torch, `sentence-transformers`, model configuration, lazy imports, fallback branches, tests that preserve the abandoned surface, and user documentation before RC. Preserve the evaluation result as a build artifact, not dormant product complexity.
- If the gate passes, choose and lock one model/weight/version, license/provenance record, scoring contract, and dependency set. Include it in the canonical installation for every user; do not auto-enable it based on whether an optional package happens to be installed.
- A promoted model must be provisioned predictably during documented setup with integrity verification and no surprise download on first search. Clean macOS install, restart without network access, upgrade, disk-use, and uninstall tests become release gates.
- Runtime and evaluation metadata expose one ranking-policy version and whether the fixed reranker actually ran. Missing/corrupt required weights cannot silently change ranking behavior.
- The MCP schema exposes no reranker toggle or model selector in either outcome.

### 5.21 Knowledge-graph evidence gate

Language-aware parsing always retains the local facts needed for useful chunks and citations: symbol kind/name/path, parent context, imports/exports/uses, definitions, and other conservative per-file relationship metadata. The gate applies only to materializing and traversing a cross-file graph and using it to alter retrieval.

The graph candidate includes:

- cross-file node/edge construction and identity resolution;
- graph persistence, versioning, incremental maintenance, and workspace/generation isolation;
- community detection or other whole-graph analysis;
- query-time graph expansion, graph-derived features, graph context, or graph-influenced ranking;
- dependencies used only by that subsystem, currently including `networkx`, `python-louvain`, and SciPy.

Use the same pre-registration discipline as Section 5.20. Compare the best non-graph candidate with that identical candidate plus one fixed graph policy on matched agent tasks. Include cross-file flow tracing, import/re-export navigation, interface/implementation discovery, analogous-pattern discovery, sibling-worktree divergence, stale updates, and every first-class language whose extractor claims graph coverage.

Decision rules:

- Promotion requires a material improvement in blinded end-to-end agent task correctness, not merely more edges, richer-looking context, or better offline retrieval metrics.
- False, cross-workspace, or cross-repository-boundary edges count as correctness failures. Missing an uncertain edge is preferable to asserting a false relationship.
- Secondary guardrails cover initial/incremental indexing time, branch-switch latency, store size, memory, query latency, context tokens, stale-edge rate, and implementation/dependency burden.
- If the gate fails, remove graph schemas/tables, stores, cross-file extractors/resolvers, community analysis, enrichment/ranking branches, graph-specific dependencies, configuration, observability, tests that preserve the abandoned surface, and documentation before RC. Retain only evaluated local symbol/relationship fields used by non-graph behavior.
- If the gate passes, freeze one graph schema/extractor/policy version and define promised language coverage. Graph state becomes part of atomic workspace generations and compatibility keys; an incomplete or cross-contaminated graph cannot publish as a complete standard generation.
- Query-time failure of a retained standard graph branch is explicit in execution metadata and never silently changes ranking. Cursors bind to graph-policy/version/application state just as they bind to other ranking policy.
- A retained graph implementation must prove incremental correctness across edits, renames, deletes, branch switches, worktree overlays, submodule and independent nested-repository boundaries, crashes, and generation reuse.
- In either outcome, MCP exposes no graph search tool, toggle, depth, weighting, or context knob. Agents ask task-level search questions; internal policy owns the implementation.

### 5.22 Local diagnostics without a monitoring stack

Dolphin is a local MCP product, not an operator-managed service. Its production diagnostics must make agent failures and solo-developer maintenance actionable without opening a port, exporting telemetry, running Docker, or asking the user to operate a time-series database.

Remove before RC:

- the `observability/` compose stack, Prometheus configuration, Grafana dashboards/provisioning, Loki/Promtail configuration, stack-management scripts, and deployment instructions;
- `prometheus-client`, all OpenTelemetry API/SDK/instrumentation/exporter packages, trace-context behavior used only by OpenTelemetry, FastAPI metrics middleware and `/metrics`, OTLP/Prometheus environment variables, and their lockfile entries;
- tests and documentation that preserve network scraping, telemetry export, dashboards, or Docker as a Dolphin workflow.

Retain and simplify Python's `StructuredLogger` as the single logging implementation. It emits versioned JSONL events under `StorageLayout.logs`, never MCP stdout. Every event has a timestamp, severity, event code, component, process-instance ID, optional safe workspace/operation IDs, duration/count fields, and a bounded typed failure category. It must never contain credential values, raw queries, source text, snippets, embedding inputs, provider bodies/headers, arbitrary exception payloads, or uncontrolled path values. Human CLI logs may also use stderr; MCP diagnostics use the private log sink and protocol-safe stderr only.

Logging storage follows a fixed, non-public retention policy for 0.3.0: private directories/files, 10 MiB segments, no more than 100 MiB of closed segments in aggregate, and a 14-day maximum age, with the first applicable bound winning. Each process writes its own segment so concurrent MCP clients do not share a file handle. A short interprocess diagnostics-maintenance lock prunes only validated closed segments beneath the canonical log directory; active or ambiguous segments are preserved. Rotation or logging failure cannot alter a tool result, corrupt product state, or trigger an unbounded retry loop. `status`/`doctor` reports the sink as degraded when safely detectable.

Metrics use a small Python-owned registry with a closed set of names and no arbitrary labels. It covers startup, searches, index/sync operations, OpenAI calls and failure classes, embedding-cache reuse, retrieval modes, watcher/lease activity, lock contention, and local diagnostic failures. Each operation family retains only attempts, successes, failures, cumulative/max duration, and bounded counters needed for remediation; there is no production time-series or per-query history. Query strings, file paths, repository names, provider request IDs, exception messages, and user-controlled label values are forbidden.

The serving MCP process exposes its current metric window in compact `status` output. It coalesces a latest-only safe snapshot into its existing runtime ownership record so a separate `dolphin doctor --json` process can summarize active process health without scraping a port. Snapshots identify their process and measurement window, expire with the ownership record, and are never presented as a durable all-time aggregate. Persisted repository-operation counters remain the authoritative history for indexing work.

Development profiling remains explicit and reproducible through documented `uv run` commands and evaluation artifacts. Profiling is off in production, adds no alternate runtime behavior, commits no generated report, and may use a developer's external tools without making them installation requirements. The built wheel must contain no telemetry exporter, metrics HTTP server, dashboard assets, or Docker integration.

Acceptance tests must prove:

- exact secret/source/query redaction, closed event schemas, and bounded metric cardinality;
- per-process concurrent writes, crash-left segments, retention, symlink containment, permissions, unwritable/full-disk behavior, and idempotent pruning;
- stable compact `status` and `doctor --json` snapshots, truthful process/window semantics, expiration, and multi-process isolation;
- no MCP stdout contamination and no telemetry sockets, HTTP metric endpoints, exporter calls, or surprise network traffic;
- diagnostic sink failure cannot change correct search/index outcomes, while still producing an actionable degraded-diagnostics state; and
- the resolved wheel/lockfile and clean macOS smoke test contain none of the removed observability dependencies or deployment assets.

### 5.23 Independent nested Git repositories

An independently initialized nested repository is any Git worktree whose canonical root is a strict descendant of another worktree root and whose path is not already classified as that parent's gitlink/submodule. It may be a completely unrelated repository or a linked worktree that shares Git history with the parent. In both cases it is a separate workspace boundary, not parent content.

Boundary rules:

- Run a bounded metadata-only boundary pass before scanning eligible file contents. Process parent gitlinks first, then inspect descendant `.git` directory/file markers without following directory symlinks or descending beneath a discovered marker.
- A gitlink is authoritative for classifying a boundary as a submodule. A separate valid worktree marker is classified as `nested_git`. The same relative path is never reported or indexed twice.
- Encountering a `.git` marker immediately excludes that subtree from the parent, even if its metadata is invalid, conflicted, unreadable, or points somewhere unsafe. A valid child is enrollable; an invalid marker is a blocked boundary with remediation, never a reason to traverse into the subtree.
- Validation may read only bounded Git metadata needed to establish worktree root and common-directory identity. It performs no fetch, clone, checkout, hook, build, dependency installation, submodule mutation, or other network/process side effect.
- The immutable boundary set is shared by initial scanning, Git-diff generation, dirty/untracked overlays, watchers, drift fingerprints, eligibility diagnostics, reference resolution, graph construction if retained, recovery, and GC. No alternative pipeline may rediscover files beneath it as parent content.
- `repo_add` and `repo_list`, plus the single resolved current-workspace entry in `status`, return one bounded repository-boundary summary shape for both `submodule` and `nested_git`, including kind, relative path, state, validated root when safe, registered workspace ID if any, and a ready-to-use child `repo_add` action. Submodule-only commit metadata remains optional fields on that common shape.
- A nested child is never registered, indexed, embedded, searched, watched, initialized, repaired, or included in multi-workspace scope merely because its parent was registered. An agent explicitly calls `repo_add` with the child's absolute canonical worktree root when the task needs it.
- Deepest-root resolution wins for an explicit path, MCP root, session scope, or process CWD inside the child. If the child is not registered, Dolphin offers its exact `repo_add` action rather than falling back to the registered parent.
- Once separately registered, the child receives its own workspace identity, generation/overlay namespace, watcher lease, freshness, operations, references, and configuration. Repository-family identity is derived normally from the child's validated Git common directory; it may share a family with the parent only when Git metadata proves that relationship.
- Parent/child searches remain separate by default. A task spanning both uses explicit workspace IDs, and results preserve the originating workspace and root.
- A newly created nested marker is a scope-boundary event. Parent search and `open_ref` immediately mask that subtree, mark the parent stale, and schedule a generation that removes former parent artifacts. Removing a marker does not expose descendant content through the parent until a fresh complete parent generation passes normal eligibility and publishes atomically.
- Nested boundaries recurse only after a child is separately registered. A grandchild is discovered and reported by its immediate registered parent; root enrollment never performs unbounded recursive repository registration.

Tests cover ordinary nested repositories, nested linked worktrees, nested repositories with the same remote/basename, creation/removal during active watching, dirty/untracked child files, ignored parents, boundary paths containing spaces/Unicode, invalid and escaping `.git` files, symlink markers, permission failures, duplicate gitlink/marker classification, and explicit parent-plus-child multi-workspace search. In every case, assert that parent embedding inputs, chunks, graph edges, search hits, and references contain no child content.

### 5.24 Narrow repository-local indexing policy

The one optional repository policy file is `.dolphin/config.toml` at the exact concrete worktree root. Dolphin does not search parent directories, the Git common directory, sibling worktrees, the user's home, or environment variables for repository policy. Each worktree reads the file present in its own code state, so branch/worktree differences remain isolated and versionable.

The complete 0.3.0 schema is:

```toml
schema_version = 1

[index]
include = ["generated/client/**/*.py"]
exclude = ["examples/snapshots/**", "testdata/huge-corpus/**"]
```

No other table or key is valid. `include` and `exclude` default to empty lists and use one documented Git-wildmatch-compatible, repository-relative, forward-slash pattern syntax. Absolute paths, parent traversal, empty/NUL-bearing patterns, platform-dependent separators, environment interpolation, and patterns over fixed size/count limits are rejected. For 0.3.0, the file is at most 64 KiB, each list has at most 256 patterns, and each UTF-8 pattern is at most 512 bytes.

Eligibility precedence, highest first:

1. canonical root containment, repository boundaries, Git metadata exclusion, secret/security rules, symlink policy, text/binary detection, and per-file hard bounds;
2. the Git candidate universe: tracked files plus untracked files accepted by standard repository, info, and user-global Git ignore rules;
3. repository `exclude` patterns;
4. repository `include` patterns, which may override only Dolphin's ordinary built-in noise exclusions inside the Git candidate universe; and
5. Dolphin's versioned inclusive defaults and ordinary noise patterns.

After eligibility is resolved, the catastrophic fuse evaluates the aggregate preflight scope and cannot be raised by repository policy. If both repository lists match a candidate, `exclude` wins and diagnostics report a bounded overlap warning. Repository policy can always narrow disclosure but cannot use `include` to expose ignored local state or bypass a higher-precedence denial. Human-owned exceptions outside the repository are a separate trust domain and are never merged into this schema implicitly.

Loading rules:

- Read only a bounded regular UTF-8 file at the canonical root; reject a symlink, special file, oversized file, malformed TOML, unsupported schema version, unknown key/table, duplicate key, or invalid pattern before scanning or making a document-embedding request.
- Parse into one frozen typed model. Do not merge arbitrary legacy/global configuration, inherit from a parent checkout, interpolate values, execute code, or preserve unknown fields.
- Dolphin never creates, reformats, upgrades, deletes, or otherwise writes this file. `repo_add`, MCP tools, `doctor`, and setup commands may report it and provide a human-editable example but never mutate it.
- `REPO_CONFIG_INVALID` returns the exact safe file location plus bounded field/line-oriented validation details, without echoing potentially sensitive arbitrary values. A first registration performs no indexing; an existing workspace keeps its prior complete generation but marks search conspicuously stale with configuration-invalid remediation until a valid policy publishes.
- The validated policy's canonical digest and eligibility-policy version participate in the effective pipeline key. Identical policy at the same commit is reusable across worktrees.
- A valid policy change re-evaluates eligibility incrementally: newly excluded membership is removed, newly eligible files are parsed, exact chunks/embeddings reuse global caches, and unaffected artifacts are retained. It never forces an unconditional full re-embedding.
- Watchers and pre-search drift checks fingerprint the policy independently of ordinary file events. Publication of all policy-driven membership changes is atomic.
- `status`, `repo_list`, `repo_add`, `repo_sync`, and `doctor` expose only schema version, canonical digest, validity, bounded pattern counts, and safe error codes by default—not a second copy of every pattern.

Acceptance tests cover an absent file and a valid empty-list policy; tracked and untracked candidates; repository, info, and global Git ignores; ordinary built-in overrides; exclude-over-include precedence; every hard denial; malformed/oversized/symlinked files; unknown/duplicate keys; unsupported versions; absolute/traversing/Unicode/glob-edge patterns; divergent worktree policies; branch changes; concurrent edits; invalid-after-valid behavior; atomic publication; and exact reuse/embedding-call counts after each policy delta.

### 5.25 Human approval for an extraordinary aggregate scope

The catastrophic fuse remains a last-resort anomaly detector, not a normal repository-size or cost budget. After all fixed security, containment, repository-boundary, configuration, ignore, file-type, and per-file checks pass, preflight may still stop because the aggregate eligible file count, bytes, or estimated embedding tokens is beyond the deliberately massive release threshold. Only those stable aggregate-threshold stops are approvable.

Never approvable are root escape, symlink/traversal cycles, non-convergent enumeration, invalid repository boundaries or policy, special files, unstable snapshots that cannot be fingerprinted, arithmetic overflow, hard secret/binary denials, and internal integrity failures. These return their own typed failures and must be corrected; a human approval cannot convert them into indexing inputs.

On an approvable stop Dolphin:

1. persists the workspace and durable operation in `awaiting_approval` without publishing staged data or making a document-embedding request;
2. creates an opaque, allowlisted preflight ID and a versioned fingerprint covering workspace/root identity, repository-family identity, HEAD/Git-tree identity, dirty/untracked membership metadata, repository-policy digest, eligibility/boundary policy versions and digests, aggregate counts/bytes/token estimate, and the exact thresholds exceeded;
3. stores only IDs, digests, aggregate measurements, expiry, state transitions, and safe audit metadata under Application Support—not source content, pattern copies, credentials, or provider payloads; and
4. returns `SCOPE_FUSE_TRIPPED` with the observed versus allowed measurements, expiry, operation/preflight IDs, built-in-tool guidance, and the path-safe command `dolphin repo approve-scope --preflight-id <id>`.

The approval command is deliberately exceptional:

- It is a human CLI capability and is absent from MCP, generated agent tool schemas, repository policy, environment settings, setup automation, and ordinary agent guidance.
- It requires an interactive terminal. There is no `--yes`, `--force`, piped-stdin, environment-variable, config-file, wildcard, global, or reusable approval path.
- It reloads the durable record, reruns the bounded preflight without holding a writer lock, and requires exact fingerprint/measurement agreement before presenting confirmation. After confirmation it takes only a short writer lock to recheck record state plus the cheap drift fingerprint and atomically claim/requeue. A changed scope is refused and produces a new preflight record rather than silently widening authority.
- The prompt shows the canonical workspace root, measured file/byte/token scope, triggered thresholds, expiry, and the standing-consent reminder that eligible source will be sent to OpenAI. Confirmation requires entering `approve <short-fingerprint>` exactly.
- Approval bypasses only the named aggregate thresholds for this exact preflight. It cannot change eligibility, include a denied file, weaken a boundary, alter the model, or authorize another workspace/operation.
- A pending record expires 24 hours after creation. Exact confirmation atomically claims it for the bound operation; once claimed, the operation may run or resume later only after full snapshot revalidation. Expired, mismatched, already-consumed, cancelled, or forged records cannot start work.
- A successful confirmation atomically marks the approval claimed and moves only the bound operation back to `queued`. A live runtime may resume it; otherwise the next compatible MCP/CLI runtime resumes it through normal interrupted-operation reconciliation.
- Repeated `repo_add`, approval, or runtime races are idempotent. At most one operation claims the approval, and all observers see the same durable state.
- Approval neither requires nor persists `DOLPHIN_OPENAI_API_KEY`. Index execution independently resolves the key from its process environment and can still fail through the normal credential contract.

Immediately before scanning and at file-read boundaries, indexing revalidates the approved snapshot inputs. A meaningful scope/fingerprint change returns the operation to a newly generated `awaiting_approval` preflight; it never stretches the prior approval with a percentage tolerance. Ordinary incremental edits after a complete approved generation use normal delta indexing and encounter the fuse only if their aggregate preflight independently crosses a catastrophic threshold.

Acceptance tests cover every approvable and non-approvable trigger; non-TTY/piped/config/env/MCP bypass attempts; malformed and guessed IDs; wrong workspace/operation; expiry; fingerprint drift; dirty/untracked changes; policy and boundary changes; concurrent approvers/runtimes; crash before/after atomic claim; missing credentials after approval; restart/resume; no document-embedding call before claim; one-shot consumption; bounded audit retention; and proof that approval never affects another workspace or hard denial.

### 5.26 Process-bound execution and durable resume

Dolphin has no independently installed service lifetime. An MCP client launches one stdio process, and a human may deliberately launch a foreground operation runner; every watcher, worker, provider request, and maintenance loop is owned by one of those visible processes. Dolphin never invokes `launchctl`, writes a LaunchAgent plist, registers a login item, forks/detaches, or leaves a child process running after its owner exits.

Runtime ownership:

- Each process creates a durable runtime record containing a random instance ID, PID plus process-start identity, mode (`mcp` or `foreground_cli`), Dolphin/schema versions, start/heartbeat times, and owned leases. PID alone is never sufficient for stale-owner detection because macOS may reuse it.
- Operations and workspace watchers use expiring renewable leases. A lease grants execution ownership, not data ownership; all authoritative progress remains in the shared store.
- Any compatible runtime may search committed generations. Only the lease holder advances an operation or watches a workspace, and short writer transactions protect checkpoints, lease changes, and publication.
- A graceful owner release makes work immediately claimable by another compatible live runtime. If none claims it, the operation is durably `paused` with reason `runtime_absent`; queued and paused work is discovered automatically at the next startup.
- Watcher leases follow the same handoff. When no runtime remains, no filesystem watcher runs. The next owner performs the cheap drift/boundary/policy reconciliation before establishing a fresh watch baseline, so events missed while Dolphin was offline cannot make an index appear current.

Checkpoint contract:

- Every long phase has bounded checkpoint intervals and idempotent units. A checkpoint records the target workspace snapshot/fingerprint, policy/pipeline keys, completed file/chunk artifact keys, exact embedding-cache successes, staging-generation identity, counters, current phase, last progress, and resumable failure/pause reason.
- Checkpoints contain derived identities and safe counters, not source bodies, query text, credentials, or provider payloads. Unpublished source-derived artifacts already governed by normal storage security may remain in the isolated staging generation.
- Provider batches become complete only after their response is validated and exact vectors are committed under content/model-aware cache keys. An interrupted or ambiguous in-flight call is retried safely; Dolphin does not claim that client cancellation prevents provider-side processing or billing.
- Publication is a short non-cancellable transaction. It either makes the complete generation visible and records success or leaves the previous generation authoritative for startup reconciliation. No shutdown path publishes partial membership, vectors, keyword state, references, or graph state.
- Resume first revalidates schema/pipeline compatibility, workspace identity, current snapshot, repository policy/boundaries, approval if applicable, and cached artifacts. It reuses proven completed units and replans only changed or incompatible work rather than restarting the repository wholesale.

Shutdown behavior:

1. Stdio EOF, normal MCP shutdown, `SIGINT`, or `SIGTERM` stops accepting mutating work and marks the runtime as draining; read-only requests already executing receive a bounded opportunity to finish.
2. Workers stop scheduling new units, cancel or finish the current bounded unit, flush durable counters/checkpoints, and release operation/watcher leases.
3. A fixed five-second graceful-shutdown budget applies in production. If a task or provider call does not cooperate, Dolphin records the best available checkpoint, closes what it safely can, and exits; lease expiry plus startup reconciliation handles the remainder.
4. Logging/diagnostic buffers flush without extending the correctness-critical deadline. MCP stdout remains protocol-only throughout shutdown.
5. Process pools, threads, file watchers, database/vector handles, and temporary resources are joined or closed. `atexit` is a last fallback, not the primary correctness mechanism.
6. No shutdown, disconnect, timeout, cancellation, or lease-expiry handler invokes `repo_forget`, consumes a cleanup receipt, changes a registration to `forgotten`, or shortens its retention. Session-local scope may vanish with the session, but the workspace registration and durable operation state persist.

An ungraceful crash leaves the last durable checkpoint plus an expiring owner lease. A new runtime proves the old owner stale using the lease and process-start identity, reconciles any short storage transaction, changes orphaned `running` work to `paused`, and then may claim/resume it. It never assumes that an old PID still names the same process.

The human command `dolphin operation run <operation-id>` runs one existing queued/paused operation to a terminal or newly blocked state in the foreground using the same application services, locks, leases, credentials, checkpoints, and structured outcomes as MCP. It neither creates a daemon nor broadens scope. `awaiting_approval` still requires Section 5.25's separate approval; missing credentials pause with exact remediation rather than destroying reusable progress.

Compatibility and upgrade rules:

- A process resumes only operations whose persisted schema, pipeline, and staging formats it can prove compatible. Otherwise it preserves the prior committed generation and returns typed `OPERATION_INCOMPATIBLE` remediation to safely replan derived work.
- Upgrading the uv tool cannot leave an old Dolphin service behind because none exists. Concurrent old/new MCP processes may read only mutually compatible state; incompatible writers are rejected before claiming work.
- Uninstalling Dolphin removes the executable environment but does not silently delete Application Support data. No background process or launch registration remains to clean up.

Acceptance tests cover clean EOF and every supported signal in every operation phase; the five-second deadline; hung/cancelled provider calls; checkpoint frequency and idempotency; crash around cache/store/publication commits; PID reuse; expired/live leases; active-peer takeover; last-runtime pause; offline edits; watcher reconciliation; next-launch resume; foreground resume; missing credentials; approval-blocked work; version/schema incompatibility; repeated resume; preservation of every registration/receipt/retention deadline across all implicit lifecycle events; and assertions that no launchd plist, login item, detached child, listener, or orphan process exists after shutdown/uninstall.

### 5.27 Split embedded storage and publication protocol

SQLite and LanceDB serve different internal jobs. SQLite owns relational identity, durable workflow state, exact generation membership, keyword/FTS5 state, locks/leases, and the single logical visibility pointer. LanceDB owns fixed-size vector artifacts, vector indexes, and nearest-neighbor execution. The [LanceDB OSS quickstart](https://docs.lancedb.com/quickstart) documents local embedded operation, and its [concurrency guidance](https://docs.lancedb.com/faq/faq-oss) supports concurrent reads while warning about excessive concurrent writers; Dolphin therefore permits concurrent snapshot readers but deliberately keeps its own single-writer discipline.

Backend boundaries:

- Define narrow `MetadataStore`, `KeywordStore`, `VectorStore`, and `GenerationCoordinator` protocols. Application/search/index services depend on those protocols; only `kb/store/` adapters import `sqlite3`, SQLite helpers, `lancedb`, Lance, or PyArrow backend types.
- SQLite is the source of truth for repository/workspace identity, operations/checkpoints, eligibility manifests, chunk/path/reference metadata, clean generations and overlays, published snapshot pointers, reader/worker leases, component-policy versions, GC reachability, and local FTS5/BM25 search.
- LanceDB contains only local vector-related derived state. Dolphin always connects to the validated `StorageLayout.vectors` filesystem path, never a `db://`, HTTP, object-storage, or user-supplied URI; it does not read a LanceDB cloud API key or use LanceDB's embedding-function registry.
- Dolphin's OpenAI adapter computes and validates every vector under the fixed model/dimension contract before the vector adapter receives it. Backend defaults cannot select a model, generate embeddings, or silently sanitize a contract violation.
- No application code receives a raw SQLite connection, LanceDB connection/table, Arrow dataset, or backend query builder. This prevents transport and retrieval code from bypassing workspace/generation scope, publication state, or redaction.
- SQLite FTS5 remains the sole production keyword engine. Dolphin does not maintain a second LanceDB FTS index or choose keyword behavior based on optional backend features.

Logical vector/membership invariants:

- An exact embedding artifact is keyed by provider, model, dimensions, embedding-contract version, and exact input hash. Clean-generation and overlay manifests refer to those artifacts through immutable chunk-instance membership.
- The physical LanceDB layout may use generation projections and/or content-addressed artifacts, but it must make exact same-commit adoption possible without another OpenAI call and must keep divergent workspace membership isolated. Physical optimization cannot weaken the logical model or response citations.
- Every searchable vector row/projection carries enough immutable IDs and policy/version metadata for the adapter to enforce an exact published snapshot. There is no unscoped `query(vector, k)` API.
- A search first acquires/pins the requested SQLite-published snapshot IDs, then runs vector and FTS5 branches against exactly those IDs. Publication may advance a workspace concurrently, but the pinned prior generation remains readable until the search releases its short reader lease.
- ANN/flat choice, index type, training thresholds, probes/refinement, and rebuild policy are one versioned internal retrieval policy tuned by Section 9. Small collections may use exact flat search; any approximate policy must pass recall and end-to-end agent-correctness gates. No backend knob reaches MCP or repository policy.

Cross-store publication deliberately avoids pretending SQLite and LanceDB share one ACID transaction:

1. A short SQLite transaction creates an immutable staging-generation ID, target/pipeline fingerprints, component readiness records, and operation link with `visibility = staging`.
2. Indexing incrementally writes SQLite staging membership/FTS5 rows and LanceDB vector artifacts/projections under that opaque generation ID. Normal readers select only IDs reachable from a published snapshot.
3. The vector adapter durably commits and verifies schema, row/membership counts, model/dimensions, artifact digest, ANN readiness when required, and a backend commit/version token. The coordinator records that token and digest in SQLite without publishing.
4. After every required component independently validates, one short SQLite transaction rechecks the workspace target and operation lease, records the complete manifest, and swaps the workspace's published snapshot pointer from the old generation to the new generation.
5. Query-cache keys include the published snapshot IDs. Post-commit invalidation is idempotent; correctness does not depend on deletion because an old cache entry cannot match the new snapshot key.
6. The old generation remains protected while any workspace, retained reference, in-flight reader, operation, or reuse policy reaches it. GC later removes unreachable SQLite and LanceDB derived state through an idempotent mark/delete/finalize protocol.

Crash/recovery matrix:

| Failure point                                                        | Required recovery                                                                                                                       |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Before any vector commit                                             | Ignore/resume the staging generation; published pointer is unchanged                                                                    |
| After some vector artifacts but before a verified vector token       | Reconcile exact artifact keys, reuse valid rows, and rewrite only missing/invalid rows                                                  |
| After verified LanceDB commit but before SQLite records the token    | Treat vectors as invisible orphans; attach only when generation/digest verification matches, otherwise GC                               |
| After SQLite records vector readiness but before pointer swap        | Resume final validation/publication or leave staging invisible                                                                          |
| During the SQLite pointer transaction                                | SQLite rollback or commit decides visibility; never infer it from LanceDB presence                                                      |
| After pointer commit but before cache invalidation/old-state cleanup | New snapshot is authoritative; snapshot-keyed caches and reachability make retries safe                                                 |
| Published vector token/schema/data missing or corrupt                | Return typed `STORE_INCOMPATIBLE`/`SEARCH_FAILED`, preserve evidence and prior state, and never silently present partial hybrid results |

SQLite opens with foreign keys enabled, WAL mode, a bounded busy timeout, and release-defined durability settings appropriate for task correctness; publication/approval/lease transitions use explicit transactions and compare-and-set predicates. Startup runs bounded schema/quick integrity checks, while deeper checks remain explicit diagnostics so startup does not scan an enormous store on every MCP launch.

All LanceDB writes pass through Dolphin's interprocess writer lease even if the pinned backend supports concurrent writes. Readers use independent handles/snapshots and may run concurrently. Python worker processes use `spawn`, never `fork`, because the embedded vector engine is internally multithreaded. Backend write conflicts, stale table handles, or index rebuilds are classified and retried only under bounded idempotent policies.

Before implementation freeze, choose one exact LanceDB release after clean native Apple Silicon CPython 3.13 wheel installation, vector correctness/recall, multi-process read, serialized-write, crash/reopen, index-build, upgrade, license, vulnerability, disk, and uninstall testing. Pin it in project metadata and the release lock; the current incidental lock version is only a baseline, not automatic approval. No runtime feature detection may select materially different vector behavior.

Acceptance tests inject failure at every numbered publication boundary; hold old readers across publication/GC; race worktree publication and search; verify unpublished and cross-workspace rows are unreachable; corrupt/miss tokens, dimensions, rows, indexes, SQLite pages, and FTS5 state independently; exercise large generation reuse and overlay churn; assert zero OpenAI calls for reusable vectors; and deny all remote/cloud/object-storage URIs and unexpected LanceDB network access. A built-wheel smoke test verifies the exact pin and local macOS vector workflow.

### 5.28 Private content-addressed chunk text

Published search snippets must remain exact even after the worktree changes, disappears, or switches branches. Each chunking result therefore commits its exact decoded source slice to a local immutable artifact before its generation can publish. Dolphin stores neither a second Git checkout nor a separate whole-file snapshot; however, because chunks can cover most eligible lines, setup and repository-enrollment disclosure must accurately say that Dolphin retains derived local source text until safe garbage collection.

Artifact identity and contents:

- Decode and validate a source file once under the eligibility pipeline. Preserve the exact decoded code points and newline sequence used for chunk line accounting; do not Unicode-normalize, rewrite line endings, redact, pretty-print, or regenerate text before artifact hashing.
- Canonically encode each chunk's source text as UTF-8. Its ID is the lowercase SHA-256 digest of a domain-separated artifact-format identifier plus those exact bytes. The format identifier changes whenever serialization semantics change.
- The immutable artifact payload contains only the versioned envelope and exact chunk text needed for verification/materialization. Repository/workspace IDs, paths, branch names, line positions, symbols, language/parser metadata, and generation membership remain in authoritative SQLite rows so identical text can be reused without weakening scope.
- SQLite membership records carry artifact ID, source-file fingerprint, one-based line range, decoded-byte/character counts, language/chunker metadata, and any separately hashed embedding input. An artifact's identity never substitutes for workspace/generation membership authorization.
- Chunk text and embedding input are distinct contracts. If Dolphin adds contextual prefixes for embeddings, it hashes/caches the exact provider input separately and never displays synthesized embedding context as source.

Write, read, and publication rules:

- Write only beneath `StorageLayout.artifacts` through the canonical path validator. Use a private temporary file under the same storage root, restrictive permissions, file synchronization, and atomic no-replace publication; racing writers of the same ID converge after verifying the winner's header, length, and digest.
- Artifacts are immutable. Existing bytes are never updated in place. A digest, length, envelope, decode, or containment mismatch is typed `ARTIFACT_CORRUPT`, preserves diagnostic evidence without logging content, and is never repaired by silently substituting the current worktree file.
- Physical artifact existence does not make content searchable. A staging-generation manifest lists its artifact IDs and aggregate digest; publication revalidates every required artifact and records the verified manifest in the same SQLite visibility transaction described in Section 5.27.
- Search pins a `PublishedSnapshot`, authorizes each hit through that snapshot's SQLite membership, verifies the referenced artifact on read, and materializes snippets only from that payload. It never looks up an artifact directly from a caller-supplied hash.
- No raw source text, artifact payload, snippet, repository path, or embedding input enters logs, diagnostics, operation records, metrics, filenames, or GC audit output. `doctor` and `status` expose aggregate counts/bytes and integrity state only.

Retention and deletion:

- One physical artifact may be shared across repositories, commits, branches, and worktrees when its exact ID matches, while every logical use remains independently scoped by SQLite generation membership.
- Staging operations, published generations, retained missing workspaces, in-flight readers, and reusable clean-generation policy protect their reachable artifacts. Reader leases cover snippet materialization.
- GC derives reachability from authoritative manifests, marks candidates transactionally, rechecks leases/references immediately before unlink, and finalizes metadata idempotently. A crash may leak an unreachable artifact temporarily but cannot delete a reachable one or expose unpublished text.
- Uninstall leaves Application Support data intact as specified in Section 5.26. Human documentation explains `dolphin gc --dry-run`, aggregate disk reporting, and the deliberate local source-text retention; no MCP tool can dump the artifact store or trigger destructive GC.

Acceptance tests cover identical text reused across unrelated repositories without scope leakage; exact Unicode/newline preservation; overlapping and file-spanning chunk sets; dirty/untracked overlays; branch/worktree divergence; concurrent identical writes; crashes before and after artifact publication; corrupt headers/lengths/digests/UTF-8; path and symlink attacks; worktree mutation/deletion after publication; old readers held across GC; aggregate disk accounting; and proof that snippets either match the published artifact byte-for-byte or fail explicitly.

### 5.29 Current-only `open_ref`

`open_ref` helps an agent move from a Dolphin discovery result to code it can act on now. It accepts only a Dolphin-issued reference, resolves the exact registered workspace and indexed membership behind it, and returns a bounded excerpt from the current file. It does not expose a `mode`, generation selector, arbitrary path, caller-selected line range, or raw artifact ID. Exact indexed text stays in the originating `search` snippet; when that snippet is insufficient and current code has drifted, the agent should search/sync or use its built-in file tools rather than ask Dolphin to present old code as current.

Resolution and read rules:

1. Decode the opaque issued reference and resolve it to retained SQLite membership containing workspace ID, relative path, indexed file/range fingerprints, indexed line range, chunk instance, and originating publication identity. Callers cannot synthesize authorization by supplying those fields separately.
2. Require the concrete workspace to be registered and present. Re-run deepest-worktree resolution, nested-repository/submodule masking, current repository policy, hard security exclusions, text/size limits, and canonical containment before opening the file.
3. Use a no-follow open, compare the opened descriptor's identity to the validated path, stream the complete file only within the release's hard eligible-file input bound, and verify identity/size/mtime around the read. The separately bounded output window is selected only after fingerprinting/alignment. Retry one complete read after an ordinary concurrent edit; a second change returns typed `REFERENCE_CHANGED_DURING_READ` rather than a torn excerpt.
4. Compute the release-defined current file fingerprint from the bytes actually read. Never trust a pre-open path stat or watcher fingerprint as proof of returned content.
5. Align the indexed range deterministically: use its original lines when the file fingerprint is exact; otherwise recognize an unchanged range at the same lines; otherwise relocate only when the exact indexed range text has one unambiguous current occurrence. Do not guess from a fuzzy match, symbol name, or nearest line.
6. Return only current decoded text. For unresolved drift, return a small current window at the original coordinates clearly labeled `alignment = unresolved`, plus the indexed/current ranges and a next action to inspect the current absolute path or run `repo_sync`. Never include retained indexed artifact text in the `open_ref` payload.

The success payload distinguishes:

- `exact_file`: the complete current file fingerprint equals the indexed file fingerprint;
- `unchanged_range`: the file changed elsewhere but the referenced range remains byte-for-byte identical at the same lines;
- `relocated`: the exact indexed range occurs once at a different current line range; and
- `unresolved`: the file is readable but the indexed range cannot be mapped without guessing.

All four are successful current reads with `drifted = false` only for `exact_file`; the other modes make drift prominent. A deleted path returns `REFERENCE_TARGET_MISSING`, a missing worktree returns `WORKSPACE_MISSING`, an expired/unresolvable issued reference returns `REFERENCE_EXPIRED`, a newly unsafe/ineligible path returns `REFERENCE_BLOCKED`, and an unstable read returns `REFERENCE_CHANGED_DURING_READ`. These errors contain safe paths/IDs and remediation but no source payload. A symlink, child-repository boundary, binary/secret classification, containment failure, oversized current file, invalid encoding, or reference/membership mismatch is never downgraded to unresolved drift.

Current content is capped by one fixed internal line/byte/token policy around the resolved range. Agents already receive an absolute path for deeper native reads, so 0.3.0 adds neither pagination nor generic file-reading parameters to `open_ref`. Tests cover exact, changed-elsewhere, uniquely relocated, duplicated, deleted, recreated, replaced-inode, edit-during-read, invalidated-policy, newly secret/binary/oversized, symlink-swapped, nested-boundary, missing-worktree, expired-reference, Unicode/newline, huge-line, and concurrent worktree cases.

### 5.30 Opaque reference identity and retention

The public reference grammar is exactly `dolphin://ref/<stable-id>`. `<stable-id>` is a URL-safe, no-padding, versioned opaque token derived from Dolphin's existing random internal workspace, publication, and immutable reference-target identifiers. It contains no repository name, branch, absolute/relative path, line number, fingerprint, artifact hash, source text, or user-provided label. Clients treat the complete URI as an indivisible string; its internal binary layout is not a public field-level contract.

Identity lifecycle:

- A cryptographically random 128-bit `reference_target_id` is assigned while staging each immutable chunk/path/range membership. It binds the generation, relative path, chunk instance, exact indexed file/range fingerprints, line range, and chunk artifact through authoritative SQLite rows; it is not derived from or replaceable by a caller-supplied hash.
- A publication has its own immutable random identity. Serializing a hit combines a format version, exact workspace ID, originating publication ID, and reference-target ID into one opaque token. It performs no metadata write, creates no per-query record, and therefore keeps `search` read-only apart from its existing bounded query cache.
- The same workspace, publication, and target always serialize to the same reference. A sibling worktree, different publication, or different target produces a different token even when it reuses identical chunk/vector artifacts.
- `open_ref` decodes only the token envelope, then requires SQLite proof that the publication was complete, belonged to that workspace, contained that target, and is still retained. A token is a locator, not standalone authorization; all current workspace/path/boundary/eligibility checks from Section 5.29 still run.
- Returning a reference does not create a lease or extend retention. The normal generation policy and any active `open_ref` reader lease govern reachability. Once the originating publication/target is collected, a well-formed token returns `REFERENCE_EXPIRED`; malformed scheme/version/base64/length values return `REFERENCE_INVALID`.
- Unknown random IDs, remixed IDs from real tokens, workspace/publication mismatches, and collected targets use bounded constant-shape failures and disclose no alternate target metadata. The implementation does not scan for a near match or fall back to the current workspace.

The stable ID uses at least 384 bits of underlying random identity before compact encoding, making accidental collision or useful guessing negligible; a short checksum may reject transcription damage but is never treated as authentication. Dolphin stores no separate signing/encryption key merely to encode references. Reference IDs may appear in structured tool results and explicit debug output but are excluded from routine logs/metrics; diagnostics report aggregate valid/expired/invalid counts only.

Acceptance tests cover deterministic repeat serialization; different workspace/publication/target separation; exact clean-generation reuse across worktrees; malformed scheme/version/base64/length/checksum; random guessing; component remix; missing/expired publication; reference use during concurrent publication and GC; process restart and compatible upgrade; storage incompatibility; no search-time write; no path/source leakage in the token; bounded error timing/shape; and exact resolution to the original retained membership before the current-file checks begin.

### 5.31 Local at-rest security boundary

Dolphin's data is local private application state, not an independently encrypted vault. SQLite databases and WAL/SHM files, LanceDB data, chunk text, embedding artifacts, manifests, logs, locks, diagnostics, temporary files, and client-configuration backups use their native formats beneath `~/Library/Application Support/Dolphin/`. There is no storage password, `DOLPHIN_STORAGE_KEY`, 1Password/Keychain lookup, SQLCipher dependency, per-artifact encryption, custom key hierarchy, unlock prompt, remote key escrow, or encrypted export in 0.3.0.

The security promise is deliberately precise:

- Create the Dolphin root and every directory with mode `0700`; create regular state, database, WAL/SHM, log, lock, backup, and temporary files with mode `0600`, independent of a permissive inherited process umask. Atomic replacement must preserve those modes.
- Every state path must be a no-follow, canonically contained descendant owned by the effective user. A symlink, unexpected owner, non-regular state file, or permission state that cannot be made private safely returns typed `STORAGE_PERMISSIONS_UNSAFE` before opening a database, vector table, artifact, log, or backup.
- Dolphin may idempotently set the exact private owner mode on a contained file/directory it owns, then re-stat and verify it. It never changes ownership, follows a symlink, recursively chmods an unresolved tree, adds group/other access, or mutates repository permissions.
- SQLite connection/journal creation and LanceDB's own descendants are followed by mode verification because third-party defaults are not part of Dolphin's contract. Private temporary data remains under the same root and crash reconciliation removes it when unreachable.
- Logs, diagnostics, exception messages, support bundles, shell commands, and status output never include raw source/artifact text. This redaction is required independently of filesystem encryption.

On Apple Silicon, internal storage is encrypted by the platform; enabling FileVault adds credential-protected volume access. Apple's [FileVault security documentation](https://support.apple.com/guide/security/sec4c6dc1b6e/web) is the external authority for that device-level behavior. Dolphin performs a bounded, read-only, no-privilege best-effort probe through one macOS adapter and reports `filevault: on | off | unknown` plus concise human advice in setup and `doctor`. An unsupported/changed/localized response, timeout, sandbox denial, or missing platform command yields `unknown`; Dolphin never guesses, prompts for administrator access, runs a shell, turns FileVault on/off, handles a recovery key, or makes provider/indexing behavior depend on the result.

FileVault `off` or `unknown` is advisory, not a runtime error: the registered repository already exists within the same logged-in user boundary, and D-052 grants no new claim that Dolphin resists a malicious same-user process, administrator, unlocked-session attacker, malware, or a compromised OpenAI/MCP client. Documentation recommends FileVault for sensitive repositories, a strong login password, screen locking, and normal device backups. It must not imply that `0700`/`0600`, content hashes, opaque references, or automatic Apple Silicon volume encryption equal application-level encryption.

Setup disclosure states, before first registration, that Dolphin sends eligible chunk inputs to OpenAI and retains derived source text, metadata, and embeddings locally without Dolphin-managed encryption. `repo_add` repeats a concise version. `doctor --json` reports owner/mode validity, state-class aggregate bytes, FileVault status/advisory, and whether any unsafe path blocked startup; it never reveals a credential, source sample, artifact name, raw platform-command response, login name, or recovery information.

Acceptance tests set permissive umasks; precreate loose modes; exercise safe tightening; inject wrong owners, symlinks, FIFOs/sockets, hard-link surprises, replacement races, SQLite WAL/SHM creation, LanceDB-created descendants, logs, backups, and crash temporaries; prove zero state opens before an unfixable permission failure; verify no repository chmod; and cover FileVault on/off/unknown/timeout/malformed/localized/permission-denied probes with no mutation or privilege request. Clean-install, upgrade, concurrent-process, repair, and uninstall-retains-data tests re-audit the complete state tree.

### 5.32 Automatic storage-pressure management

Dolphin treats disk management as internal reliability work, not developer tuning. The fixed 0.3.0 policy is `storage-pressure-v1`: start collection when current-user-available bytes fall below `max(20 GiB, 5% of the containing volume's bytes)` or reclaimable inactive state exceeds `50 GiB`; continue across yielding batches until available bytes reach `max(30 GiB, 7.5%)` and reclaimable inactive state is at most `40 GiB`; and require a growth phase's conservative peak plus a `5 GiB` crash/reconciliation margin to leave the start free-space reserve intact. GiB means `1024**3` bytes; percentage products round upward with overflow-safe integer arithmetic. No MCP input, environment variable, global/repository setting, or setup option can raise a limit, shorten protection, select victims, or disable the reserve. `status` and `doctor` expose the policy version, constants, and safe aggregate measurements so behavior is predictable.

Protection classes are authoritative and conservative:

1. **Never pressure-evict:** every currently published workspace snapshot and all of its SQLite/FTS5 rows, chunk text, vectors, graph state if promoted, and references; every live reader lease; active/queued/paused operation input, checkpoint, staging units still eligible for resume, embedding result committed to that operation, approval record, and rollback requirement; runtime/lock/schema state; and all data required to prove or recover a cross-store transaction.
2. **Time-protected:** a missing workspace's overlay/manifests and required shared artifacts for the full 30-day recovery window, plus any release-defined short crash-orphan quarantine. Storage pressure never shortens these windows.
3. **Reclaimable after reconciliation:** abandoned temporary files; incomplete or superseded staging generations no resumable operation reaches; expired query/diagnostic caches and excess bounded logs; completed operation detail beyond retention; expired missing-workspace state; unreferenced vector projections/FTS rows/chunk artifacts; and reusable clean generations no active/time-protected state reaches.
4. **Regenerable cache:** exact document/query embedding-cache entries and parser artifacts not required by a protected generation. These remain valuable but may be removed only after safer orphan/expired classes and only through their authoritative membership/index, never by filesystem age alone.

Victim order is deterministic: reconcile first, then expired temporary/staging state, expired bounded caches/logs/operation detail, expired workspace-specific overlays, unreferenced derived projections/artifacts, least-recently-adopted inactive clean generations, and finally inactive regenerable caches. Reusable-generation recency is updated on creation/adoption/release under existing writer transactions—not on every search—so read-only search does not become a metadata writer. Within a tier, sort by protection expiry, last adoption/use, recomputation cost class, descending reclaimable bytes, and stable ID. Physical modification time, directory order, branch name, repository size, and caller preference never decide safety.

Pressure evaluation and operation behavior:

- Measure the actual volume containing `StorageLayout.root` using bounded local filesystem APIs. Capture free/available bytes, total Dolphin bytes by state class, currently protected/reclaimable estimates, and measurement time; use saturating arithmetic and treat impossible/overflowing values as `STORAGE_MEASUREMENT_FAILED`, never as abundant space.
- Before any new indexing phase that can materially grow state—and before document embedding calls—estimate its conservative staging, vector-index, SQLite/WAL, artifact, and crash-recovery peak. Run bounded GC if the post-write reserve would be violated. Estimates are safety inputs, not cost forecasts, and are revised from measured bytes after each durable phase.
- A newly registering workspace that still cannot reserve its first complete generation pauses durably with `pause_reason = disk_pressure` and returns typed `DISK_PRESSURE` remediation. It sends no further provider input until space is safe. An existing workspace retains its prior complete generation and becomes explicitly stale while its update is paused.
- Disk pressure never blocks read-only search/open-reference access to already committed state. Query-cache/log writes become best-effort and may be skipped; search may still call OpenAI for the query embedding if it can execute without a durable write. No search path triggers a large synchronous GC.
- A compatible active MCP or explicit foreground CLI process automatically reevaluates paused operations after bounded GC or observed free-space change. There is no daemon. Resume uses the normal lease/checkpoint/target revalidation and never assumes the original estimate is still valid.
- If a write reports `ENOSPC`, quota exhaustion, or an equivalent backend error despite preflight, stop scheduling/provider calls, checkpoint only if safely possible, reconcile partial native writes, retain the old published pointer, and enter `disk_pressure`. Never respond by deleting an unverified target or active generation.

GC uses the same SQLite-authoritative reachability model as Sections 5.27–5.28. A short writer transaction records a policy-versioned plan and candidate tombstones from one consistent metadata snapshot. Before each physical delete, GC reacquires/validates its maintenance lease and rechecks publication pointers, operations, protection deadlines, reader leases, and shared artifact reachability. It then deletes backend-derived data through idempotent adapters and finalizes metadata. A crash may leave a tombstoned or physically orphaned reclaimable item for retry, but cannot make it searchable or authorize deletion of a newly reachable item.

Automatic GC runs only inside an active Dolphin process, at low priority, in bounded batches, and yields to search and foreground mutation. Concurrent runtimes share one GC maintenance lease. `dolphin gc --dry-run` returns the exact aggregate tier/order/estimated-byte plan with protected/reclaimable totals and reasons; explicit human apply uses the identical engine and cannot override protection. MCP may inspect pressure/plan state but exposes no direct GC trigger, quota, keep/delete selector, or force flag; `repo_forget` only releases one authorized registration and submits any resulting unreachable state to this unchanged collector.

Each automatic batch records actual reclaimed bytes and elapsed monotonic time and begins no new atomic deletion unit after either reaches `2 GiB` or two seconds. A deletion already started is allowed to finish, verify, and finalize even if one unusually large backend unit crosses a bound; its overshoot is reported and the collector yields immediately afterward. Subsequent bounded batches run only after pressure remeasurement, lease validation, and an opportunity for foreground/search work. Hysteresis requires both target conditions before pressure clears; exhausting all safe candidates without meeting the write-reservation formula pauses the operation as specified above.

Acceptance tests model volumes one byte above, at, and below every D-054 absolute/percentage/cap/target/reservation boundary; percentage rounding; active and missing worktrees; divergent/shared generations; live/expired readers and operations; approvals; first index and stale update; concurrent publisher/GC; reactivation during the 30-day window; exact boundary expiry; shared artifacts with mixed reachability; wrong estimates; `ENOSPC` during every backend phase; crash at mark/delete/finalize; batches below/at/over both scheduling bounds including one oversized atomic unit; repeated retries; low-priority yielding; no-daemon resume; deterministic plans; zero provider calls after pause; continued committed search; no path/source leakage; and proof that every deleted item was reclaimable in both the plan snapshot and immediate pre-delete recheck.

### 5.33 Native macOS support floor and qualification matrix

Dolphin's platform predicate is `Darwin AND native arm64 AND macOS >= 14.0`. Version comparison parses numeric components and compares padded integer tuples; it never compares strings, assumes a marketing name, or treats an empty/unparseable version as supported. The platform check and D-048's standard CPython 3.13 check form one side-effect-free startup preflight that runs before resolving credentials, creating Application Support, opening SQLite/LanceDB, starting workers/watchers, probing FileVault, or contacting OpenAI.

Required behavior:

- Read operating-system and machine identity from bounded local APIs. Detect Rosetta translation independently where macOS exposes it; `arm64` text alone is insufficient if translation state is contradictory or unknown. A fixed adapter returns normalized system, machine, `(major, minor, patch)`, translation state, and evidence category without shell execution or uncontrolled command output.
- Accept native Apple Silicon macOS `14.x`, `15.x`, `26.x`, and later numerically compatible stable releases. Reject macOS `13.x` and earlier, Intel, Rosetta, non-Darwin, missing/contradictory fields, and version overflow with one typed `UNSUPPORTED_PLATFORM` result and no state mutation.
- Do not require the latest patch at runtime, perform a network update check, or block an otherwise supported `14+` host because Apple later publishes another patch. Setup/`doctor` report the exact detected version and recommend current security updates without claiming whether an offline host is current.
- Public beta/developer-seed macOS is outside the release qualification promise. If it reports a valid `14+` numeric version, Dolphin may run under the same contract but diagnostics label it unqualified when that state is detectable; there is no beta-specific workaround path.
- Package metadata, README, generated client setup, `--help`, `doctor`, release notes, and support templates state “Apple Silicon macOS 14 or newer; CPython 3.13 provisioned by uv.” A pure-Python wheel tag cannot express the OS floor, so documentation and the runtime preflight remain mandatory rather than implying PyPI will reject every unsupported install.

At RC, run the complete clean-install/core/MCP/storage/watch/process/search/uninstall smoke suite on the latest publicly available security patch of every macOS major from 14 through the current stable major. At the time of this plan, Apple's [security releases](https://support.apple.com/100100) list maintained Sonoma 14, Sequoia 15, and Tahoe 26 releases; if another stable major ships before RC, add it without dropping 14. Test hosts/runners must be native Apple Silicon, not Rosetta or an Intel runner presenting a target deployment flag.

Dependency qualification inspects the resolved distribution set and every native Mach-O wheel/library for `arm64`, a deployment target no newer than macOS 14.0, standard CPython 3.13 ABI compatibility, and absence of an install-time compiler/source build. Run the exact wheel under each matrix host because a permissive wheel tag does not prove runtime behavior. Validate SQLite/FTS5, LanceDB create/index/reopen, Tree-sitter grammars including Rust, `watchfiles`, process-start identity, `spawn`, no-follow file operations, permissions, FileVault probe degradation, `statvfs`, linked worktrees, signals, and GUI-client absolute executable launch on each major.

Negative tests inject Darwin 13.6 and boundary tuples around 14.0; multi-digit minors; empty/malformed/huge/non-numeric versions; `x86_64`; translated/unknown/contradictory state; Linux/Windows; missing platform APIs; CPython mismatch; and a dependency tagged for a newer deployment target. They assert identical early failure across MCP, setup, CLI maintenance commands that require the store, and foreground operation execution. `doctor --json` remains available in a preflight-only diagnostic mode to report safe detected facts and remediation, but it does not open or repair Dolphin state on an unsupported host.

### 5.34 Capability-scoped workspace cleanup

`repo_forget` lets an agent clean up the exact Dolphin workspace-registration epoch whose creation transaction returned a receipt, without giving it general deletion authority. The authority is a capability, not repository ownership or provenance and not an inference from a path, process, branch name, MCP root, repository family, or current session. The registration schema and behavior do not otherwise distinguish whether a human or agent caused enrollment, or whether anyone considers the workspace temporary or persistent.

Authority issuance and persistence:

- Before `repo_add`, the caller generates 32 bytes with a cryptographically secure random source, encodes them as unpadded base64url, and prefixes the value with `dolphin-cleanup-v1_`. The strict input contract rejects missing, malformed, short, overlong, or non-base64url-shaped receipts. The absolute path remains the sole repository/workspace identity input; the receipt is only a capability and idempotency proof.
- In the winning new-registration transaction, Dolphin binds a domain-separated digest of the supplied receipt to the workspace ID and random registration epoch. A retry presenting the same path and receipt returns the same cleanup authority; this remains safe after a lost response because the caller already holds the secret. A call presenting a different receipt receives `cleanup = null` and cannot acquire cleanup authority for the pre-existing workspace.
- A fresh receipt candidate may appear only in an unregistered-worktree next action before it has authority. Once bound, the raw receipt is echoed only in a matching `repo_add` result and is excluded from `repo_list`, `status`, ordinary `operation_status`, logs, metrics, errors, generated examples, and analytics. SQLite stores the digest and lifecycle metadata, not a recoverable raw receipt. There is no MCP receipt listing, rotation, or server-side recovery operation.
- The agent should retain the receipt only for the lifetime of the task that created a disposable registration. It is a local, narrowly scoped capability rather than an OpenAI credential, but Dolphin still redacts values matching its prefix from diagnostics and logs.
- The receipt authorizes one registration epoch only and has no `expires_at` deadline. It remains usable across long-running work, inactivity, client/process restarts, supported upgrades, and wall-clock movement until successful forget or an explicit human lifecycle action consumes/revokes that epoch's authority. Re-registering the same canonical worktree after forget creates a fresh epoch and receipt; an old receipt can neither remove nor control the new registration.

The MCP request contains only `workspace_id` and `cleanup_receipt`; it has no path, repository-family target, recursive selector, GC mode, force, source-delete, worktree-delete, or confirmation-bypass input. Tool annotations set `destructiveHint = true` because searchability changes, `idempotentHint = true`, and `openWorldHint = false`. Its description states that it deletes no repository content.

The service executes this lifecycle protocol:

1. Parse the receipt with strict length/alphabet/version bounds, look up the exact workspace/registration epoch, compare its digest in constant time, and return one constant-shape `CLEANUP_NOT_AUTHORIZED` error for missing, malformed, guessed, mismatched, pre-existing, or superseded authority.
2. Under the workspace lifecycle lock, durably record a cancellation request scoped to the registration's currently queued/paused/running operation IDs and acquire `cleanup-intent-v1` for that registration epoch. Its lease deadline is 30 seconds after the last successful renewal; the active call renews every five seconds. While live, it prevents new index/sync/watcher claims and further document-provider submissions. Atomically cancel queued/paused operations. Cooperatively stop a watcher owned by the current runtime and give running local work the same fixed five-second checkpoint/drain budget as shutdown. A short publication transaction already in its non-cancellable commit region may finish, but can publish nothing after logical forget.
3. A live foreign mutation/maintenance lease, a local operation that does not drain within five seconds, or a publication-critical section that does not finish within that budget returns retryable `WORKSPACE_IN_USE` with bounded operation/state metadata. The operation-scoped cancellation request remains durable, but the receipt is not consumed and the workspace is not reported forgotten; the agent retries the same call. Another explicit call presenting the valid receipt for the same workspace/epoch may attach to the existing intent and renew it without creating another cancellation request. At `now >= intent_expires_at`, every path treats the intent as absent even if its row remains, so caller loss can block new mutations for at most 30 seconds from the last renewal. The foreign owner observes the request at its next bounded checkpoint, stops the named operation, and releases its lease; after intent expiry, new ordinary work may be submitted if cleanup was abandoned and is not captured by the old request. There is no force path and no separate MCP cancellation tool.
4. Once mutation ownership is drained, use one SQLite transaction to revalidate the epoch, live cleanup-intent lease, operation states, and receipt; remove the workspace's published pointer from new resolution and search; mark the registration `forgotten`; consume the receipt; clear applicable session-local defaults; and record a minimal idempotency tombstone. Searches or `open_ref` calls that acquired reader leases before the transition may finish from their pinned state; no new call can select the forgotten workspace.
5. Recompute reachability after commit. Workspace-only overlays, staged data, manifests, watcher state, and other now-unshared derived objects become immediately GC-eligible rather than receiving the 30-day missing-workspace recovery window. Clean generations, chunks, embeddings, vectors, or metadata reachable from another workspace, retained operation, reader lease, or reusable-generation policy remain protected. Validated embedding responses committed before cancellation remain ordinary reusable cache artifacts; Dolphin does not pretend an already submitted provider request was recalled.
6. Run at most the normal bounded low-priority GC opportunity and return promptly. Physical reclamation is asynchronous, crash-recoverable, and resumed by later Dolphin processes under `storage-pressure-v1`; `repo_forget` is not a force-GC operation and promises logical release rather than immediate byte reclamation.

The result reports `forgotten` or `already_forgotten`, the consumed registration epoch, cancelled operation IDs, whether shared state remains, estimated newly reclaimable aggregate bytes, and the fixed idempotent-replay deadline. It exposes no physical-GC operation to manage. The successful transaction sets `forgotten_at` and `replay_expires_at = forgotten_at + 30 days`; neither successful nor failed replay extends that deadline.

The cleanup replay tombstone stores only workspace ID, registration epoch, receipt digest, timestamps, and the bounded original result fields needed for deterministic retry. During the window, only an exact constant-time digest match for that workspace and epoch returns `already_forgotten`; it never resolves against a newly registered epoch. At or after the deadline, automatic metadata compaction may remove it, after which the same input returns constant-shape `CLEANUP_NOT_AUTHORIZED`. The tombstone contains no path or raw receipt and creates no artifact, generation, reference, operation, or GC reachability edge. Forgotten-workspace identity metadata and shared derived state are retained or collected independently by their own policies.

Human operators retain a separate `dolphin repo forget <workspace-id>` CLI path for abandoned, receipt-lost, or otherwise selected registrations. It shows a dry-run, requires an interactive exact workspace-ID confirmation, invokes the same lifecycle and reachability service, and still cannot remove source files or override active-use/GC protections. An agent cannot invoke that human authority through MCP. There is no registration promotion, ownership transfer, `temporary`/`persistent` flag, or `repo keep` command.

Cleanup is explicit-only. Disconnect, EOF, process exit/crash, timeout, cancellation, lease expiry, client-root change, and loss of session-local scope perform no implicit cleanup and never consume the receipt. They preserve the registration and use Section 5.26's checkpoint/resume behavior. If the worktree root actually disappears, the separate D-024 missing-workspace policy applies; disappearance is not treated as consent to bypass its 30-day recovery window.

The intent row contains only random intent ID, workspace ID, registration epoch, scoped operation IDs, lifecycle state, owner runtime/call identity, and lease timestamps; it never contains the raw receipt. Acquisition, attachment, five-second renewal, completion, and expiry use compare-and-set transitions under the ordinary short writer lock. Expired rows are ignored immediately and removed through idempotent metadata maintenance. The constants are not MCP/config/environment/repository settings, and renewing an intent changes no cleanup-receipt or replay/identity-anchor deadline.

Acceptance tests cover first creator versus concurrent loser; repeat `repo_add` with matching and different receipts; missing, malformed, guessed, logged, swapped, stale-epoch, and replayed receipts; lost-response retry; re-registration of the same root; absent/moved/deleted worktrees; queued/paused/running work; exact drain boundaries; active local/foreign watchers and operations; abandoned and renewed cleanup-intent leases; reader races; publication and GC boundaries; shutdown/crash at every transition; shared generations/artifacts across worktrees; immediate logical invisibility; bounded physical reclamation; exact source/Git non-mutation; session-scope invalidation; constant-shape failures; human CLI parity; and proof that no MCP input can target a registration for which its caller does not hold the matching cleanup capability.

### 5.35 Forgotten-registration visibility

Forgotten is an internal/audit lifecycle state, never an actionable MCP workspace state. Normal `repo_list` serializes active, indexing, ready, missing, and failed registrations only. Resolution by explicit workspace ID, MCP root, session scope, or process CWD cannot select a forgotten epoch; ambiguity/candidate lists omit it, and a root that remains on disk is presented as enrollable through a fresh `repo_add`. Parent repository-boundary summaries likewise treat a forgotten child as unregistered and may offer only ordinary enrollment guidance including fresh receipt generation.

MCP `status` reports only low-cardinality aggregates: current replay-tombstone count, aggregate tombstone metadata bytes, and count awaiting physical derived-state reclamation. It returns no forgotten workspace ID, repository ID, display label, root/path, branch, commit, receipt/digest, operation ID, timestamp, or per-entry reclamation estimate. `repo_list` has no `include_forgotten` input, and no continuation token or error remediation can be used to enumerate forgotten entries.

The human CLI supports `dolphin repo list --include-forgotten` and the equivalent bounded JSON output. During each entry's 30-day replay window it may show workspace ID, repository/display labels, last canonical root, `forgotten_at`, `replay_expires_at`, aggregate logical/reclamation state, and a safe ready-to-use MCP `repo_add` action when the root still validates. It never shows the raw receipt, receipt digest, source content, artifact names, or unbounded operation history. Results are newest-first, paginated/bounded, and read-only. At the deadline the entry becomes ineligible for this audit view; physical compaction removes its replay tombstone and identity anchor together, without depending on or changing artifact retention.

An exact old `repo_forget` replay continues through the constant-shape D-059 path rather than `repo_list`. A normal MCP call naming a forgotten workspace fails as `WORKSPACE_MISSING` with no forgotten-state detail and may offer `repo_add` only when the current path independently validates. `open_ref` follows normal reference retention and returns `REFERENCE_EXPIRED` once its originating membership is no longer retained; audit visibility never restores search/reference authority or creates a GC pin.

Acceptance tests cover every MCP listing/resolution/candidate/boundary surface; aggregate-only status serialization; guessed IDs and pagination; CLI text/JSON limits and redaction; one instant before/at/after replay compaction; roots that remain, disappear, move, or become another repository; same-path re-enrollment; concurrent forget/list/status/re-add; retained and collected references; and proof that audit inspection neither changes reachability nor makes a forgotten epoch searchable.

### 5.36 Identity-safe re-enrollment after forget

`repo_add` first validates the current path as a concrete Git worktree exactly as for a first enrollment. It resolves the Git common directory and concrete worktree gitdir to validated, no-follow-opened directories, records each object's normalized `(st_dev, st_ino, birthtime_ns, directory-kind)` identity, and repeats the descriptor/stat checks after Git discovery. Missing birth time, unsupported/overflowing fields, symlinks, non-directories, descriptor/path disagreement, or a changed before/after tuple makes continuity evidence insufficient without blocking safe enrollment under a new ID.

It then performs a read-only lookup among forgotten identity anchors; a matching canonical path alone is never proof. Workspace-ID continuity requires one unique candidate whose repository-family ID, common-directory filesystem identity, and concrete-worktree-gitdir filesystem identity all exactly match current validated facts. For a primary worktree the common directory and worktree gitdir may legitimately be the same object; linked worktrees normally share the first identity and have distinct second identities. Branch name, HEAD commit, dirty fingerprint, display label, remote URL alone, root/gitdir pathname, directory basename, and caller claims are mutable hints and cannot establish identity.

An identity anchor is eligible only while `now < replay_expires_at`, using the same immutable deadline created by the successful forget transaction. Lookup, failed or successful identity comparison, audit listing, old-receipt replay, and GC inspection never refresh it. At `now >= replay_expires_at`, queries must behave as though the anchor does not exist even if a delayed compactor has not removed its row; physical compaction then removes the replay tombstone and identity anchor atomically or through an idempotently reconcilable pair. No late race can preserve a workspace ID after the logical deadline.

When there is exactly one proven match, one writer transaction:

1. preserves the prior stable workspace ID and repository-family ID;
2. creates a new random registration epoch and cleanup receipt;
3. records current root/branch/HEAD/policy/boundary facts as a new registration lifecycle;
4. leaves the old cleanup replay tombstone keyed to the old epoch and never copies its receipt digest into the new authority record; and
5. creates a normal indexing/adoption operation with no published pointer until a complete compatible generation is independently verified and atomically adopted or built.

Old references remain bound to their originating publication/target membership and stay expired or expire through normal retention; workspace-ID reuse never makes them current again. Old queued/running operations remain cancelled and cannot resume into the new epoch. Search caches, session defaults, watcher leases, approvals, cleanup intents, and failure state are epoch/publication-scoped and are not inherited. Display labels are recomputed from current facts. Content-addressed chunks, embeddings, vectors, and clean generations may be reused only through the normal pipeline/model/policy/artifact verification, whether the workspace ID was preserved or newly allocated.

If there is no eligible proven forgotten match—or current facts match a different family/worktree, produce multiple forgotten candidates, lack required evidence, or arrive at/after anchor expiry—Dolphin allocates a new random workspace ID and reports a bounded safe `workspace_id_reused = false` reason. It does not expose forgotten candidate IDs through MCP. A same-volume rename/move may preserve its ID when both Git administrative objects and family continuity still match; a cross-volume move/copy, remove/recreate, Git-admin repair/replacement, or same-path replacement receives a new ID. Exact active registration is returned idempotently, normal missing-workspace reactivation follows D-024, and a conflicting active/missing identity returns the existing typed ambiguity/remediation rather than creating a duplicate workspace.

Concurrent `repo_add` calls serialize the identity decision. Exactly one supplied receipt is bound to the fresh epoch. Later calls observe that active registration and cannot start a second first-index operation; a call with the bound receipt receives the same cleanup authority, while every different receipt receives `cleanup = null`. A concurrent old-receipt replay can return only the old epoch's `already_forgotten` result and has no locking or authorization path to the fresh epoch.

The result exposes only `workspace_id_reused: bool` plus the closed safe reasons in `WorkspaceIdentitySummary`; it never reveals a non-selected forgotten workspace ID or identity-anchor material. Acceptance tests cover primary and linked worktrees; branch/HEAD/dirty changes; safe moves/renames; remove/recreate at the same path; clones/copies; changed remotes; common-directory replacement; inode/birth-identity changes; multiple candidates; concurrent add/forget/replay/GC; pre/post tombstone compaction; old references/operations/leases/approvals; exact and corrupt artifact reuse; zero-call compatible adoption; and cross-worktree contamination.

### 5.37 Cleanup-pending admission and read behavior

`cleanup_pending` is a transient presentation/admission overlay on one otherwise ordinary registration epoch, not another registration kind. Its underlying lifecycle state remains recorded unchanged. A live `cleanup-intent-v1` makes the effective state `cleanup_pending`; successful forget makes it `forgotten`, while intent expiry removes the overlay and reveals the then-current underlying state. A stale physical intent row never produces the overlay.

Reader admission and cleanup-intent acquisition use one SQLite ordering point:

- A `search` or `open_ref` call that atomically acquired all required publication reader leases before cleanup intent may complete against those pinned snapshots/current-read descriptors. Cleanup does not wait for it, but reachability protects everything needed until result serialization releases the reader lease.
- After intent acquisition, a new single-workspace `search` or `open_ref` fails before query embedding, cache lookup/write, vector/FTS execution, reference resolution, or current-file read. A new multi-workspace search containing any cleanup-pending workspace returns no combined hits and makes no query-provider call; it never silently omits that workspace.
- `repo_add` for that worktree, `repo_sync`, automatic watcher/drift work, and every other new workspace mutation fail before scan, provider, staging, or lock-heavy work. `repo_forget` with valid authority may attach/renew; `operation_status`, `repo_list`, `status`, and human diagnostics remain available.
- Source files remain untouched and directly usable by the agent's built-in filesystem tools. `WORKSPACE_IN_USE` includes safe retry timing plus built-in-tool guidance, but no receipt, intent owner, process identity, query, path beyond one the caller already supplied, or cancelled-operation internals.

An admitted read rechecks the registration epoch/lifecycle immediately before serialization. If cleanup intent appeared or forget committed after admission, it may still return its pinned result, but marks `changed_after_admission = true`, identifies only `cleanup_pending` or `forgotten_after_admission`, suppresses continuation as appropriate, and directs follow-up to returned validated paths/built-in reads rather than promising that a Dolphin reference will remain resolvable. It never relabels a pre-intent read as post-intent coverage. A reader admitted after intent expiry proceeds normally only after atomically proving the intent logically dead.

`repo_list` serializes effective state `cleanup_pending`, the underlying state, `intent_expires_at`, a bounded retry interval, and safe next actions. `status` serializes those per-workspace fields only when that workspace is the deterministically resolved current workspace; otherwise it contributes only to the `cleanup_pending` count. Neither exposes a receipt/digest, cancellation-operation IDs, cleanup caller/owner, or per-process detail. Resolution may identify the workspace for diagnostics but cannot admit blocked work. At expiry, the overlay disappears without a registration transition; at successful forget, D-062 removes the entry from normal MCP listing entirely.

Acceptance tests linearize readers immediately before/at/after intent acquisition and expiry; cover search/open-reference and single/multi-workspace scopes; verify zero query/document-provider calls and zero file/vector/FTS reads for rejected calls; exercise serialization before/after forget; validate reader-reachability under concurrent GC; inspect lifecycle warnings and continuation/reference behavior; cover every allowed/blocked tool; and prove no stale intent row, status request, or ambiguity path admits post-intent work.

When intent expires without a committed forget, the expiry observer records one `cleanup_abandoned_recovery` marker by compare-and-set for the exact workspace/epoch. A compatible live runtime that can acquire the normal maintenance lease claims it; if none is live, startup reconciliation claims it later. The recovery never resurrects the cancelled operation IDs. It creates at most one new operation after a cheap current root/Git/policy/boundary/fingerprint comparison: no drift clears the marker and establishes a fresh watcher baseline with zero provider calls; drift queues one ordinary incremental sync; a workspace with no complete generation queues one ordinary initial operation. Existing compatible chunks, validated embeddings, and staging-independent artifacts remain reusable.

Recovery acquires watching and performs a bounded snapshot/reconciliation handshake so edits racing the new baseline become events or appear in the reconciled fingerprint. Before any document-provider call it repeats the normal credential, catastrophic-scope, policy, snapshot-stability, and D-054 disk-reserve checks. It never turns a cancelled operation back to queued, assumes a cancelled provider request produced no billable work, or forces a full index when a delta is provable. A renewed cleanup intent wins normal admission ordering and may cancel the recovery operation like any other workspace operation.

`repo_list` and exact `operation_status` expose bounded recovery state and the new operation ID when one exists; `status` does so only for the deterministically resolved current workspace and otherwise reports aggregate state. Recovery requires no `repo_sync`, daemon, configuration, or user action. Tests cover no-drift and every drift class; no/one/many live runtimes; no complete generation; watcher-baseline races; duplicate expiry observers; cancellation/recovery/renewed-cleanup races; crash before/after marker claim and operation creation; missing credentials/disk pressure/fuse state; zero-call reuse; and next-startup recovery after all clients exit.

### 5.38 Frozen cleanup UX

The entire agent-facing cleanup workflow is intentionally small:

1. Generate a fresh cleanup receipt and call `repo_add` with it and the concrete path.
2. If its result includes `cleanup`, retain the opaque value for the task.
3. When that exact registration is genuinely no longer needed, call `repo_forget` with only `workspace_id` and `cleanup_receipt`.
4. Treat `forgotten` as immediate logical completion, `already_forgotten` as idempotent success, and `WORKSPACE_IN_USE` as a bounded retry while built-in filesystem tools remain available.

There is no cleanup setup step, mode, policy choice, confirmation prompt, companion cancellation call, or GC follow-up. Agents do not parse, persist in repository files, display, transform, rotate, recover, or manufacture receipts. `repo_forget` exposes no `wait`, `timeout`, `force`, `recursive`, `delete_source`, `delete_worktree`, `gc`, `retention`, `ttl`, `victim`, `cancel_operation`, `dry_run`, or tuning input; unknown fields fail schema validation. The server owns every deadline, lease, cancellation, recovery, reachability, and reclamation decision described above.

The result states that source/Git were untouched, whether logical release occurred, whether shared state remains, estimated newly reclaimable aggregate bytes, and safe next actions. Physical byte reclamation is explicitly asynchronous and never required for cleanup success. Tool descriptions, generated guidance, Codex/Claude adapters, examples, and tests use this same four-step explanation and never expose internal policy as a decision the agent must make.

### 5.39 One canonical enrollment surface

The Python MCP adapter is the only packaged public adapter that exposes the registration-creation transition, as `repo_add(path, cleanup_receipt)`. The transport-independent enrollment application service remains an internal, directly testable Python boundary; it is not a supported import API, executable, or second user workflow. Removing the HTTP and TypeScript layers must not accidentally promote that internal service into a human CLI surface.

The retained CLI commands operate on configuration or state that already exists:

- `dolphin setup ...` installs or verifies the MCP client entry but never inspects the current directory to enroll it;
- `dolphin doctor` and read-only list/audit commands may report that a worktree is unregistered and show the exact MCP `repo_add` action an agent should take, but cannot execute it;
- `dolphin operation run <operation-id>` may resume only an existing durable operation and cannot synthesize a registration or first-index operation;
- interactive scope approval, explicit human cleanup, GC, and other maintenance remain bound to their already-existing exact records and cannot create or reactivate a workspace.

The 0.3.0 command registry, help, completions, package entry points, release-facing guidance, and executable tests contain no callable `dolphin index`, `dolphin repo add`, repository `import`, `kb ingest`, or equivalent alias. Setup, startup, diagnostics, search, a validated current working directory, and evaluation tooling never enroll as a side effect. Development and evaluation harnesses may invoke the internal service in isolated test storage, or preferably exercise MCP, but are not shipped as alternate enrollment commands.

### 5.40 Bounded health and repository inventory

`status` has an exact empty input schema. It reports the running Dolphin version and bounded readiness for platform/interpreter, credential presence, private storage, local backends, active runtime ownership, diagnostics, disk pressure, and operation recovery. It includes effective workspace-state counts plus the aggregate-only forgotten/tombstone fields from Section 5.35. If the standard resolution rules identify exactly one current actionable workspace, it includes that workspace and its bounded repository-boundary summary; otherwise it returns only a closed resolution state and a safe next action such as MCP `repo_add` or `repo_list`. Ambiguity does not prevent global health from being returned and never causes `status` to dump candidates.

`status` reads existing bounded local state only. It makes no OpenAI call, scans or fingerprints no repository content, starts/resumes no operation or watcher, runs no GC, acquires no mutation authority, and never treats a current directory as consent to enroll. Credential reporting is presence/absence plus the variable name, not online authentication. Its current-workspace facts are the last observed/published facts and are labeled as such; `repo_sync` or search owns active freshness reconciliation.

`repo_list` has one optional opaque `cursor`, a release-fixed page size of 25, and no page-size, filter, sort, expansion, path, repository, state, or `include_forgotten` input. Each item pairs one repository-family summary with one actionable workspace summary and the existing bounded boundary/policy/freshness fields. Ordering is deterministic by normalized repository display label plus stable repository ID, then normalized workspace display label plus stable workspace ID. Display-name changes or membership creation/reactivation/forget increment the actionable-list revision before another page can be issued.

The cursor is versioned, bounded, integrity-protected, and bound to the store identity, contract version, actionable-list revision, and last stable sort key. A malformed, remixed, cross-store, or wrong-contract cursor returns `CURSOR_INVALID`; a valid cursor whose list revision changed returns `CURSOR_EXPIRED` with the exact action to restart at the first page. A page is all-or-nothing: it never silently skips or duplicates an item after concurrent membership changes and never reveals a forgotten identity. Cursor handling grants no workspace authority and creates no retention edge.

### 5.41 Minimal operation inspection and retention

Every operation-creating result returns a high-entropy opaque operation ID. `operation_status` accepts only that ID and returns the latest committed operation checkpoint immediately. It never holds the MCP call open for state change, subscribes or streams, enumerates operations, cancels/retries/resumes one, or treats polling as ownership. The response includes the closed operation kind/state/phase, bounded progress and reuse counters, pause or failure classification, last-progress time, terminal time/deadline when applicable, a bounded recommended polling interval for nonterminal work, and safe next actions. It contains no source/query text, raw exception, credential, cleanup receipt, provider request ID, staging/artifact name, process command line, or unbounded event history.

Queued, running, `awaiting_approval`, and paused records are nonterminal and remain until ordinary execution/recovery proves one terminal transition; time alone never declares success or deletes resumable state. `succeeded`, `failed`, and `cancelled` set `terminal_at` in the terminal compare-and-set transaction and `status_expires_at = terminal_at + 30 days`. Reads, restarts, foreground execution, diagnostics, and references do not extend that deadline. At logical expiry the MCP lookup behaves as absent even if physical compaction lags; later bounded metadata maintenance removes the terminal detail idempotently.

Terminal-summary retention is diagnostic only. It creates no reachability edge to generations, vectors, chunk artifacts, staging, caches, worktrees, cleanup authority, or replay/identity tombstones; each follows its own policy. If the associated registration is forgotten, exact-ID inspection may still report the terminal operation state until its deadline but sets workspace availability false and omits workspace path, labels, repository identity, and other forgotten-entry metadata. A malformed, guessed, unknown, cross-store, or expired ID returns the same bounded `OPERATION_MISSING` error and no existence detail.

### 5.42 Frozen MCP registry

The installed 0.3.0 server always answers MCP tool discovery with exactly the eight tools in D-074, in that canonical order. Credential absence, unsupported repository state, disk pressure, an unavailable backend, cleanup pending, or an incompatible operation never removes or replaces a tool; invoking it returns the appropriate typed contract. Codex and Claude Code receive the same registry digest and cannot rename, omit, wrap, or add client-specific tools.

One Python-owned immutable `ToolSpec` tuple defines each name, description, input/output schema, mutability/destructive/idempotent/open-world annotations, handler binding, guidance/example references, and release version. MCP registration, generated integration artifacts, documentation fragments, parity fixtures, and release inspection consume it directly. Startup fails before serving if handlers/specs are missing, duplicated, misordered, or not at the expected 0.3.0 digest; the generator check fails if committed adapters differ.

No legacy alias remains callable, including the removed 0.2.x names in Section 6. There is no runtime feature flag, installed-extra detection, repository setting, client setting, credential state, graph/reranker decision, or environment variable that changes the public tool set. If graph enrichment or a reranker passes its binary evaluation gate, it changes internal `search` policy only. MCP resources or prompts may not perform, proxy, or parameterize repository enrollment, file retrieval, indexing, search, cleanup, or maintenance; the static initialization instructions generated from the canonical agent contract are the only non-tool guidance surface in 0.3.0.

### 5.43 Adaptive search output budgets

The public search shape stays simple while Dolphin chooses useful output sizes dynamically. `max_results` and `max_context_tokens` are nullable request overrides: omission asks the server to resolve an effective default, while an explicit value asks for that exact budget and fails clearly if it exceeds the effective cap. Dolphin never silently clamps an agent request. `max_context_tokens = 0` remains the explicit metadata/reference-only path.

One versioned output-budget policy maps bounded source-free facts to a named profile and effective defaults/caps. Its inputs are the number of requested workspaces, the exact filtered published searchable-chunk count, and one closed query-intent class produced from the query alone. It never reads additional source merely to select a budget, uses current published metadata only, and cannot alter workspace scope, eligibility, embedding model, retrieval branches, ranking, safety fuses, authorization, or tool routing. Multi-workspace statistics are aggregated without leaking one workspace's facts into another caller's response.

For a first page, Dolphin counts the exact published chunks remaining after the requested workspace, path, exclusion, and language scope—before query embedding or candidate retrieval. The first inclusive `max_searchable_chunks` threshold containing that count selects `small`, `medium`, or `large`; a larger count selects `massive`. The local classifier returns `local_symbol`, `concept`, `architecture`, `cross_file`, or `analogous_pattern`. More than one requested workspace or one of the last three broad intents promotes the base by exactly one profile, capped at `massive`; two simultaneous reasons still promote once. Continuations reuse the cursor-bound selection rather than recounting/reclassifying.

The installed `rules-v1` classifier is deliberately small. It case-folds and collapses whitespace, checks fixed broad-intent phrase groups in the stable order `analogous_pattern`, `architecture`, then `cross_file`, checks explicit symbol-location signals next, and otherwise returns `concept`. Any broad match promotes, so it needs no numerical confidence threshold; category ties are only explanatory because all broad categories have the same budget effect. It reads no repository content or metadata, invokes no embedding/model/provider, and is not configurable through either TOML. A narrow `IntentClassifier.classify(query) -> SearchIntent` boundary allows a later packaged local classifier, but 0.3.0 has no discovery, plugin, download, training, or runtime model-selection mechanism.

This classifier is an RC candidate, not complexity justified by this document alone. The Phase 5 ablation holds repositories, queries, candidate retrieval/ranking, profile values, and agent conditions constant and changes only intent promotion. D-081 decides the result. Failure removes the complete intent concept from the shipped contract and selector; it does not leave a disabled implementation, version field, configuration switch, or compatibility alias.

Every profile satisfies `1 <= default_results <= cap_results <= 50` and `0 <= default_context_tokens <= cap_context_tokens <= 20_000`. `small`, `medium`, and `large` thresholds are positive and strictly increasing; `massive` must omit the threshold, and all four profiles are required in a present config. A profile's cap limits both an explicit request and its own default. Values are integers only; TOML floats, strings, expressions, interpolation, duplicate tables, missing profiles, extra profiles, or unknown keys are invalid.

The starting experiment maps all profiles to 8 results and 4,000 context tokens with the protocol ceilings as their effective caps; initial threshold candidates are 25,000, 250,000, and 2,500,000 searchable chunks. These are sweep seeds, not release promises. Section 9 tunes thresholds, defaults, and effective caps. RC must ship a signed policy version and canonical TOML digest and retain distinct profiles only where repeated task-correctness evidence supports them. Every search reports the base/selected profile, selection reason, version/digest, scope chunk count, effective defaults/caps, and final applied budgets without exposing source content. Continuation cursors bind those facts so a policy/config change returns `CURSOR_EXPIRED` rather than mixing page budgets or rankings.

The MCP schema retains absolute installed ceilings of 50 results and 20,000 context tokens to keep payloads bounded. Human/evaluation TOML configuration may tune effective defaults and caps within those ceilings; isolated development experiments may test larger candidate ceilings but cannot silently change the installed schema.

`max_context_tokens` counts only returned snippet text, not query echo, paths, rank/relevance, references, freshness, budget/execution metadata, validation details, or next actions. Those excluded structures remain independently bounded by their closed schemas, string limits, and `max_results`; exclusion is not permission for unbounded prose. The aggregate is `sum(snippet.token_count for non-null snippets)`, where each count encodes the exact serialized `snippet.text` independently with `cl100k_base-v1`. It must equal `SearchBudget.context_tokens_used` and never exceed the applied budget, including after final serialization.

The `cl100k_base-v1` mergeable ranks and special-token definition are bundled in the Dolphin wheel with a release digest and loaded without network access. Missing, corrupt, or mismatched assets fail startup/readiness rather than substituting character estimates or another tokenizer. The release lock pins the tokenizer implementation; changing either implementation or asset creates a new public accounting version and invalidates incompatible caches/continuations. A coherent candidate shrinks only by removing complete outer lines around its relevant center; if even one required source line does not fit, that hit remains useful through metadata/reference with `snippet = null`.

`hybrid-v1` consumes the already diversified ranked hits and a finite smallest-to-largest sequence of authorized complete-line windows for each hit. Two targets are redundant for seeding only when they belong to the same workspace publication and path and their source-line intervals overlap; identical content in another file/workspace remains distinct evidence. The seed pass walks rank order until three windows have been accepted or candidates end, continuing past a window that does not fit. The remainder pass is greedy and whole-action only: structural completion outranks first evidence from a new workspace/path, which outranks other addition/expansion; original rank, lower incremental token cost, and stable opaque target ID break ties. No unused remainder is filled with partial lines or lower-level unbounded prose.

Applied budgets are page-local, not a lifetime allowance. Page zero and every successful continuation may return at most `applied_max_results` new hits and independently use at most `applied_max_context_tokens` snippet tokens. The continuation binding preserves one finite ranked target sequence plus the exact set/offset already emitted; `hybrid-v1` runs anew over only that page's hit slice and fresh snippet allowance. A target identity is its retained workspace-publication target ID, not a mutable path/line tuple. `continuation.next_cursor` is non-null only when another target remains and its state is durably proven; exhaustion or unavailable persistence cannot issue one.

The first page atomically persists one source-free continuation session only when another page exists. Its fixed deadline is `created_at + 30 minutes`; no status/read/page/retry operation updates either timestamp or reachability. The session pins only the exact workspace publications, target memberships, focus/window metadata, and verified chunk artifacts needed for its bounded target plan. At `now >= expires_at`, admission treats the session and every page handle as absent before materialization, immediately drops their logical reachability, and returns `CURSOR_EXPIRED`; later idempotent compaction removes rows/artifacts made unreachable by that expiry.

Each cursor is a version prefix plus 256 random bits. SQLite stores only a domain-separated digest mapped to one immutable `(session_id, offset, page_index)` position. Replaying a live handle returns the same page and same next handle without extending the deadline. When another page exists, its handle is a domain-separated SHA-256 derivation of the presented raw handle, random session identity, and successor offset; compare-and-set issuance makes concurrent/retried calls converge on one successor row. No application signing/encryption key, raw cursor, query text, or caller/session identity is persisted.

The ranked plan contains at most 500 unique retained target pointers after fusion/ranking/deduplication. Producing it is part of first-page local retrieval and uses the same one query embedding as the visible page; later pages perform only state validation, authorized target/artifact resolution, and snippet materialization. `ranked_horizon_reached = true` means otherwise eligible ranked targets existed beyond rank 500, not that a second hidden ranking can be resumed. The final page then directs the agent to narrow or reformulate a new query if it still lacks evidence. The horizon is not derived from or changeable by output-budget TOML.

Continuation persistence is optional derived write work after a page is complete. Dolphin attempts one short transaction only when another retained target exists. A proven commit returns `continuation.state = available`, its opaque `next_cursor`, and the session's unchanged `expires_at`; true plan exhaustion returns `exhausted`. Disk-reserve denial, writer timeout, definite storage failure, or ambiguous commit returns the complete page as `unavailable` with the corresponding closed reason and no cursor. It never guesses that an uncertain row exists, retries retrieval/provider work, performs synchronous cleanup, or changes freshness/execution quality metadata.

### 5.44 Search-budget configuration authority

The optional production file is exactly `~/Library/Application Support/Dolphin/config.toml`, resolved through `StorageLayout` rather than `$PWD`, parent-directory search, environment redirection, or legacy `~/.dolphin/`. It is human-owned local configuration, must satisfy the same current-user/no-follow/private-path checks as other Application Support state, contains no credential, and affects every Dolphin runtime using that store. Absence is normal and selects the shipped signed output-budget policy.

The file has one strict versioned schema and, for 0.3.0, may configure only search output-budget selection/default/cap data. It cannot name a workspace/path, alter eligibility, choose an embedding/ranking/retrieval/graph/reranker policy, configure storage/runtime/network/telemetry, raise MCP protocol ceilings, or add a tool. Unknown tables/keys and unsafe types fail validation rather than being ignored. The same canonical semantic model produces the policy digest independent of TOML whitespace, comments, or key ordering.

The checked-in `<worktree>/.dolphin/config.toml` remains exactly Section 5.24's include/exclude indexing policy. Dolphin does not merge search settings from it, a parent, Git common directory, sibling worktree, client config, environment variable, or source repository. Worktree/repository size still changes the profile automatically because the human-owned policy consumes bounded published statistics; no per-repository file needs authority over output behavior.

Development and evaluation may load another TOML only through an explicit development-only command argument and an isolated test/evaluation store. That path is never consulted by `dolphin mcp`, setup, `doctor`, ordinary foreground resume, or installed client adapters. Evaluation artifacts record the exact canonical candidate digest and CLI invocation; a winning candidate becomes production only by updating the shipped policy or the developer's human-owned file, never through runtime auto-discovery.

MCP startup and each first-page search perform a cheap no-follow stat comparison against the last observed file identity/size/mtime/ctime tuple. An unchanged tuple reuses the immutable in-memory/durable semantic snapshot without rereading TOML. A changed entry is opened no-follow as a bounded regular file, read once, and checked for stable descriptor metadata before and after parsing; a raced or replaced entry receives one bounded retry and is otherwise `unstable`. A validated model is canonicalized and digested before a short compare-and-set transaction installs its semantic snapshot as last known good. Raw TOML is never persisted.

Every search pins one `EffectiveOutputBudgetPolicy` before counting scope or embedding the query. A valid semantic digest change affects only subsequently admitted calls; an in-flight call completes with its pinned digest. A continuation cursor remains valid across whitespace/comment/key-order edits whose semantic digest is unchanged, but returns `CURSOR_EXPIRED` after an effective policy change. Multiple runtimes may temporarily finish calls on old/new valid snapshots according to admission order, but compare-and-set generations and stable-file revalidation prevent a partial model, mixed call, or invalid snapshot from becoming authoritative.

If a present file is malformed, unsafe, unsupported, or unstable, Dolphin uses the durable last-known-good semantic snapshot and reports `invalid_using_last_known_good`; if none has ever been accepted, it uses the shipped signed policy and reports `invalid_using_shipped`. Neither fallback promotes the invalid bytes or refreshes a stored snapshot. Deleting the file is different from invalidity: an observed stable absence atomically marks user policy inactive, invalidates/removes its last-known-good fallback authority, and selects `absent_using_shipped`, so a later invalid recreation cannot unexpectedly resurrect an older policy.

`status` and `doctor` inspect the current file through a side-effect-free validation path: they report presence, validity/state, active source, semantic digest, last accepted time, and bounded path/field/line remediation without applying a pending valid edit or mutating last-known-good state. `status.readiness` is `degraded` for either invalid fallback state, while search remains available and makes the fallback prominent in `SearchBudget`. Search metadata and diagnostics never echo arbitrary TOML values. The next startup or first-page search is the only production path that accepts/deactivates a policy; continuations reuse their cursor-pinned policy and do not hot-reload mid-pagination.

### 5.45 Simple human configuration CLI

The retained human CLI has one `config` group and exactly three subcommands. All resolve `StorageLayout.config_file`; none accepts a path, store, workspace, repository, profile, field/value, or environment override. Their only option is `--json`, which changes serialization rather than behavior. Text and JSON use one typed result model, stable outcome codes, bounded validation details, and no arbitrary TOML value echo.

- `dolphin config init` performs shared platform/interpreter/storage preflight, creates the private Application Support root when safely absent, and installs the complete shipped four-profile policy through a private temporary file plus atomic no-replace operation. The final file is current-user-owned `0600`; existing regular files, symlinks, directories, or other entries return a typed refusal and are never opened for writing, backed up, replaced, or chmodded. Success does not apply the policy to a running search or start Dolphin; the next MCP startup/first-page search accepts it normally.
- `dolphin config validate` runs the side-effect-free stable loader against the current candidate. Absence is a successful `absent_using_shipped` outcome; a valid file returns its candidate semantic digest/profiles and whether it differs from the active snapshot; invalidity exits nonzero with bounded code/field/line remediation. It never persists last known good, deactivates authority, or expires cursors.
- `dolphin config show` combines the durable active semantic snapshot with side-effect-free current-file inspection. It reports shipped/user/last-known-good source, active digest/accepted time/profiles, candidate state/digest when valid, invalid fallback state/code, and whether the next startup/search would accept, retain, or deactivate policy. It omits raw TOML, file contents, source/query data, history, and internal retrieval policy.

`dolphin setup ...` and `doctor` may print the fixed config path and suggest these commands, but never call `config init` implicitly. Manual editing with an ordinary editor remains the only way to change values after initialization. There is no `edit`, `apply`, `reload`, `watch`, `set`, `unset`, `delete`, `reset`, `migrate`, `import`, or `export` command in 0.3.0.

### 5.46 Agent-facing rank and relevance

Every search hit exposes a stable one-based `rank` in the first page's pinned top-500 plan plus one closed `relevance` value: `high`, `medium`, or `exploratory`. Rank is global across pages rather than page-relative: if page one ends at rank 8, page two begins at rank 9. The three bands are action guidance, not a probability of correctness:

- `high`: the strongest available evidence for this query and execution mode; inspect first.
- `medium`: plausible useful evidence that should be considered with the task and neighboring results.
- `exploratory`: weak, long-tail, unsupported-calibration, or out-of-distribution evidence that must be validated before reliance.

The relevance label never changes ordering, scope, authorization, continuation membership, or snippet allocation. It is computed only after final ranking from transient internal ranking features. Production discards component, fused, normalized, calibrated-scalar, and probability-like scores before constructing a `SearchHit`, cache entry, cursor state, log event, diagnostic, or terminal summary. Isolated development/evaluation runs may retain bounded source-free score artifacts solely for preregistered comparison and calibrator fitting.

The 0.3.0 candidate uses a tiny deterministic pure-Python monotonic calibration table with no runtime model or ML-library dependency. A separately fitted profile is required for every exact shipped retrieval mode and ranking-policy combination; a profile for hybrid retrieval cannot silently label lexical/structural fallback. Its semantic version and canonical artifact digest are observable in `SearchExecution`, are bound into search caches and continuations, and change whenever feature meaning, fit data, thresholds, or mapping semantics change. Neither MCP nor TOML can select, tune, disable, or override calibration. Missing, invalid, mismatched, or unsupported calibration can only conservatively return `exploratory`; it cannot expose a raw score or inherit another mode's thresholds.

Calibration data is split before fitting into non-test judgments and a disjoint held-out gate set. Precision, uncertainty treatment, minimum support, required source-free stability strata, and the operational out-of-distribution rule are preregistered before inspecting candidate outcomes. `high` and `medium` pass independently for each exact mode/policy profile: a failed `high` threshold may fall through to a validated `medium`, while a failed or unsupported `medium` falls through to `exploratory`. An inconclusive or underpowered gate is failure for that band, not permission to lower the target. Ranking and search remain fully usable when no confidence band passes.

The fixed initial gate computes a one-sided 95% Wilson lower bound without rounding before comparison. `high` needs at least 50 unique held-out query-target judgments and a bound of at least 0.85. The medium gate is cumulative over every provisional prediction at or above the medium threshold, needs at least 75 judgments, and requires at least 0.65; this cumulative definition proves that a provisional `high` remains covered if the high-only gate fails and it is emitted as `medium`. Each preregistered critical stratum independently needs at least 20 predictions and bounds of 0.75 for high or 0.55 for medium-or-higher. An underpowered or failing stratum is unsupported for only the affected band; passing strata and the underlying rank remain usable. Dolphin does not pool, weight, interpolate, or round strata to rescue a miss.

Held-out precision is task-oriented. Each unique query-target pair receives one final `direct`, `supporting`, or `not_useful` grade against the frozen task and pinned snapshot. `direct` means the target itself locates the requested implementation/behavior or indispensable evidence. `supporting` means it adds material evidence but cannot complete that discovery alone. `not_useful` covers incidental, misleading, unrelated, and semantically redundant targets that add no material evidence beyond an adequate higher-ranked target. High treats only `direct` as success; cumulative medium-or-higher treats both `direct` and `supporting` as success. Surface similarity, symbol-name overlap, or a high internal score is never sufficient.

The reviewer receives one canonical bounded target view from the pinned artifact plus only the repository/task context required by the frozen rubric and, solely for redundancy assessment, digest-identified canonical views of earlier targets in the same ranked plan. The view omits numeric rank, retrieval mode, policy, component/fused/calibrated features, candidate thresholds, provisional or final bands, and gate results. A closed audit reason distinguishes `direct_evidence`, `supporting_context`, `incidental`, `redundant`, `misleading`, and `unrelated`; neither grades nor reasons ship in production state.

There is one human reviewer. Before any held-out work, the reviewer completes the same non-held-out pilot twice under independent deterministic shuffles and fresh opaque presentation IDs, with at least seven full days between passes. The rubric advances only when quadratic-weighted Cohen's kappa is at least 0.70 and exact grade agreement is at least 0.80; an undefined/degenerate kappa is failure. Failure permits rubric/example clarification followed by a new rubric digest and new pilot, never selective reconciliation of pilot answers.

The held-out presentation then secretly duplicates `max(30, ceil(0.20 * unique_pairs))` pairs chosen by a preregistered deterministic stratified seed, spaced and relabeled so no repeat is intentionally adjacent. The same kappa/agreement gates apply before relevance precision is read. Each repeated pair contributes one final judgment and one unit of D-091 support; disagreement resolves mechanically to the lower-utility grade under `direct > supporting > not_useful`. A repeatability miss invalidates the entire held-out run and requires fresh protected evidence. An OpenAI or other model judge may be run only on a separately labeled diagnostic copy after human finalization and cannot change a grade, rescue support, or authorize a band.

Each hit resolves exactly five marginal calibration cells. Language is its public first-class family or `generic` for every eligible non-first-class/unknown text format. Scope size is the unpromoted base profile selected from filtered published chunk count, not the possibly breadth/intent-promoted output profile. Workspace breadth is `one` or `multiple`. Filter shape is `path` when either `paths` or `exclude_paths` is nonempty, `language` when `languages` is nonempty, `both` when both conditions hold, and `none` otherwise. Global one-based rank maps to `1-3`, `4-10`, `11-50`, or `51-500`.

The calibration artifact records passing cell keys separately for high and medium. A provisional high hit emits `high` only when high passed globally and in all five cells; otherwise it attempts the cumulative-medium threshold and its distinct global/cell support before becoming `medium`, then falls to `exploratory`. Cross-products may reveal future evaluation gaps but cannot enable, disable, pool, or override a marginal cell in 0.3.0. These inputs are bounded existing metadata and never require source inspection, another classifier, or a provider call.

Calibration uses group-disjoint rubric-pilot, fit/tuning, and held-out partitions. Repository-family grouping keeps every revision, branch, worktree, fork, copied fixture derivative, and multi-repository case containing that family together. Independently, semantic task/query-template grouping keeps paraphrases, parameter substitutions, and structurally equivalent task variants together. A held-out case may reference multiple repositories only when all of their families belong to held-out. No held-out identity, label, feature, result, or failure may influence retrieval/ranking/calibration design, thresholds, strata, stopping, or sampling.

Only real public repository families at pinned immutable commits may contribute to fitting or release gates, and each must pass the frozen permissive-license policy before acquisition. Authority-bearing tasks are original human-authored questions grounded in observable behavior of that exact revision, written for realistic solo-developer discovery/change work and frozen before Dolphin retrieval. Dolphin itself is never a held-out family. Generated or mechanically paraphrased prompts, synthetic/copied micro-fixtures, and deliberately contrived edge cases remain valuable for rubric training, deterministic tests, robustness checks, and diagnostics but contribute no fit input or held-out support.

The calibration license allowlist is exactly `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, and `Zlib`. An SPDX expression passes only when it parses canonically without `WITH`/`LicenseRef` and every identifier leaf is in that set; thus `MIT OR Apache-2.0` passes, while `MIT OR GPL-3.0-only` fails despite its permissive branch. Missing, custom, ambiguous, deprecated, source-available, copyleft, or unparseable licensing is ineligible rather than interpreted. The manifest binds the normalized expression and exact license-file digest to the pinned commit.

Evaluation preparation discovers root and nested license/copying notices plus declared package-license metadata within the otherwise eligible source tree. A nested independently licensed subtree either passes the same allowlist and receives its own coverage record or is excluded before task creation, target generation, scope statistics, and retrieval. If coverage remains ambiguous, or an exclusion would remove evidence required by an authority-bearing task, the repository/task cannot contribute to fitting or gates. This conservative admission rule does not claim to be general license analysis or legal advice.

Repository checkouts, canonical source views, full task text, and judgment records live only in an isolated evaluation workspace with an explicit bounded retention policy; they are absent from the wheel, plugin/skill, production Application Support store, committed report, and public release asset. A bounded provenance manifest may retain stable opaque family/task IDs, public origin, pinned commit, normalized license identifier/license-file digest, source/task/view-builder digests, partition, counts, and aggregate gate outcomes. It never republishes source, target snippets, raw judgments, or model diagnostic payloads.

Failed/invalid run material expires seven days after its terminal finalization. The successful 0.3.0 authority run expires at `min(finalized_at + 90 days, released_at + 30 days)`; until a release exists, the 90-day deadline applies, and recording an earlier release-derived deadline can only shorten it. Reads are denied at logical expiry even when deletion lags. CI removes its isolated run workspace at teardown; local evaluation startup and the development-only cleanup command reclaim expired runs, while an explicit developer cleanup may remove them sooner. No installed CLI/MCP command or background process manages evaluation retention, and cleanup never touches an original checkout outside the evaluation workspace. Source-free provenance/decision manifests are outside this content-retention deadline.

Before labels, each global and marginal provisional-band population selects at most one target per query using the lowest domain-separated SHA-256 key over the frozen sampling seed, population ID, query-judgment ID, and target ID. This estimates query-weighted usefulness and prevents a search returning many correlated hits from manufacturing Wilson support. One selected pair may count once in the global population and once in each of its applicable marginal populations because those are separate declared gates; it never counts twice inside any population. Every nonselected eligible target remains diagnostic-only. Split groups, seeds, population membership, and selected IDs are canonicalized/digested before blinded presentation, and any overlap or later mutation invalidates the run.

The fitted release artifact records which bands passed, the validation-manifest digest, supported-distribution identity, fit/gate dataset digests, and immutable thresholds without retaining judgments or source. Production performs no learning, user adaptation, threshold discovery, telemetry feedback, or cross-profile fallback. A ranking, feature, judgment-set, threshold, supported-distribution, or calibration-code change creates a new calibration identity and must repeat the held-out gate before it may emit `high` or `medium`.

## 6. Frozen MCP tool surface

The 0.3.0 registry is the exact ordered set below. `repo_add` is the sole public enrollment surface across MCP and CLI, not merely the MCP spelling of a parallel human command.

| Tool               | Purpose                                                                                                                                | Mutability                                                                             | Required safety behavior                                                                                                         |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `status`           | Report compact global readiness and at most the resolved current workspace                                                             | Read-only                                                                              | Exact empty input; no network/reconciliation/mutation; redact secrets; aggregate rather than enumerate                           |
| `repo_list`        | Page through repository families and actionable registered workspaces                                                                  | Read-only                                                                              | Optional opaque cursor only; fixed 25-item stable pages; make sibling worktrees unambiguous; omit forgotten epochs               |
| `repo_add`         | Explicitly register the concrete Git worktree at a local path and seed/index it                                                        | Writes local Dolphin state and sends only cache-missing embedding inputs to OpenAI     | Worktree-root validation, idempotency, delta reuse, bounded scope, structured operation result                                   |
| `repo_forget`      | Release the exact workspace-registration epoch authorized by a creation-issued receipt and make its unshared derived state GC-eligible | Writes only local Dolphin lifecycle/derived state; never source or Git state           | Epoch-bound receipt, active-use checks, idempotent logical removal, no force or arbitrary target                                 |
| `repo_sync`        | Explicitly ensure one registered workspace is being brought to a current semantic snapshot                                             | Writes index state and sends only cache-missing inputs to OpenAI when work is required | Exactly `workspace_id`; non-blocking; idempotently reuse/create one operation; no wait/full/force/tuning or source-tree mutation |
| `operation_status` | Inspect one exact indexing/sync operation snapshot                                                                                     | Read-only                                                                              | Exactly `operation_id`; immediate bounded result; no wait/list/cancel; 30-day non-extending terminal summary                     |
| `search`           | Hybrid semantic, keyword, and structural discovery with task-level scope and budgets                                                   | Read-only except internal query cache                                                  | Clear citations, compact structured output, predictable limits; no engine-tuning knobs                                           |
| `open_ref`         | Resolve a Dolphin-issued result reference to a bounded current-worktree excerpt with drift metadata                                    | Read-only                                                                              | Current eligibility, registered-root containment, stable no-follow read; no historical/current mode                              |

Potentially redundant 0.2.x tools (`chunk_get`, `file_lines`, `metadata_get`, `store_info`, `health`, and `repos_list`) should be removed or folded into this task-oriented surface rather than retained for compatibility.

### 6.1 Tools not exposed in 0.3.0

- Unscoped workspace/repository deletion or deletion of a Git worktree/source tree.
- Reset-all or database deletion.
- Forced repair/rebuild.
- General operation cancellation unrelated to receipt-authorized `repo_forget`.
- Direct or forced garbage collection.
- Arbitrary file reads.
- Arbitrary command execution.
- Configuration writes unrelated to the active workflow.

Broadly targeted maintenance, where provided, remains human CLI territory, and no interface can force GC past reachability protections. The narrow `repo_forget` capability is the MCP exception: it releases only the exact registration epoch whose creation returned the presented receipt, and all physical derived-data deletion still follows the shared GC protections.

`dolphin operation run <operation-id>` is also CLI-only: it is a foreground lifecycle host for an already authorized durable operation, not another agent capability. MCP runtimes already resume eligible work automatically, so exposing a second agent trigger would add no value.

## 7. Preliminary contracts and reference code

The following snippets communicate intended behavior, not final module placement. The implementation should use Pydantic models as the common contract between MCP tools and application services.

### 7.1 `repo_add` request and response

```python
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceState(StrEnum):
    REGISTERED = "registered"
    INDEXING = "indexing"
    READY = "ready"
    MISSING = "missing"
    CLEANUP_PENDING = "cleanup_pending"
    FORGOTTEN = "forgotten"
    FAILED = "failed"


class OperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RepositoryBoundaryKind(StrEnum):
    SUBMODULE = "submodule"
    NESTED_GIT = "nested_git"


class RepositoryBoundaryState(StrEnum):
    ENROLLABLE = "enrollable"
    UNINITIALIZED = "uninitialized"
    MISSING = "missing"
    CONFLICTED = "conflicted"
    INVALID = "invalid"


class RepoAddInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path = Field(description="Absolute path to the concrete Git worktree root")
    cleanup_receipt: str = Field(
        repr=False,
        description=(
            "Caller-generated dolphin-cleanup-v1_ receipt containing 32 random "
            "bytes encoded as unpadded base64url; retain and reuse it after a lost response"
        ),
    )


class WorkspaceScope(BaseModel):
    workspace_ids: list[str] | None = Field(
        default=None,
        description="Explicit workspace scope; omit only when Dolphin can resolve the current worktree",
    )


class RepositoryFamilySummary(BaseModel):
    id: str
    display_name: str


class CleanupPendingSummary(BaseModel):
    underlying_state: Literal[
        "registered", "indexing", "ready", "missing", "failed"
    ]
    intent_expires_at: str
    retry_after_ms: int = Field(ge=250, le=5_000)


class WorkspaceSummary(BaseModel):
    id: str
    repository_id: str
    display_name: str
    root: Path
    branch: str | None
    head_commit: str
    state: WorkspaceState
    missing_since: str | None = None
    cleanup_pending: CleanupPendingSummary | None = None


class ReuseSummary(BaseModel):
    source_generation_id: str | None
    reused_files: int
    reused_chunks: int
    parsed_files: int
    embedding_cache_hits: int
    embedding_cache_misses: int
    embedding_tokens_submitted: int


class OperationSummary(BaseModel):
    id: str
    kind: str
    state: OperationState


class NextAction(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class RepositoryBoundarySummary(BaseModel):
    kind: RepositoryBoundaryKind
    relative_path: str
    root: Path | None = None
    state: RepositoryBoundaryState
    expected_commit: str | None = None
    observed_commit: str | None = None
    dirty: bool | None = None
    workspace_id: str | None = None
    next_actions: list[NextAction]


class CleanupAuthority(BaseModel):
    workspace_id: str
    registration_epoch: str
    cleanup_receipt: str = Field(
        repr=False,
        description="One-time capability for repo_forget; retain only for this task",
    )
    expires_at: Literal[None] = None
    tool: Literal["repo_forget"] = "repo_forget"


class WorkspaceIdentitySummary(BaseModel):
    workspace_id_reused: bool
    reason: Literal[
        "existing_registration",
        "reactivated_missing",
        "proven_same_worktree",
        "first_seen",
        "different_worktree",
        "ambiguous_forgotten_identity",
        "insufficient_evidence",
    ]


class RepoAddResult(BaseModel):
    repository: RepositoryFamilySummary
    workspace: WorkspaceSummary
    identity: WorkspaceIdentitySummary
    reuse: ReuseSummary
    operation: OperationSummary
    cleanup: CleanupAuthority | None
    detected_repository_boundary_count: int
    repository_boundaries: list[RepositoryBoundarySummary]
    repository_boundaries_truncated: bool
    next_actions: list[NextAction]
```

Required semantics:

- Repeating the same canonical worktree path must not create a second workspace.
- `cleanup` is present for the call that won creation of a new registration epoch and for a retry that presents the exact receipt already bound to that epoch. An existing registration returns `cleanup = null` for every different receipt.
- A bounded unregistered-worktree next action may generate a fresh, not-yet-authoritative receipt candidate. Bound receipts are excluded from logs and every listing/status response. Because the caller retains the exact request arguments before submission, retrying after a lost response safely recovers the same authority without storing plaintext in Dolphin.
- Receipt presence is authorization metadata only. Repository/workspace schemas expose no creator kind, owner, temporary/persistent mode, promotion state, or behavior conditional on whether a human or agent initiated enrollment.
- `identity` reports only the current workspace ID's safe origin category. A forgotten-identity lookup never serializes a non-selected prior workspace ID or its anchor evidence.
- Sibling worktrees share a repository-family identity but never a workspace identity or mutable index namespace.
- `name` and every other unknown input are rejected; the agent supplies no alias or identity hint.
- Display labels are derived deterministically, may be duplicated before serialization disambiguation, and never cause a registration conflict.
- A path inside a worktree must canonicalize to that worktree's root—not its shared Git common directory—or return a clear validation error.
- Registration must not mutate the source repository.
- Parent registration excludes every submodule and independent nested-repository subtree and returns bounded common discovery metadata; enrolling any child always requires another explicit `repo_add` call using its own root.
- A configured OpenAI key is standing consent; the tool must disclose external embedding behavior but must not request per-repository confirmation.
- Preflight limits must be high enough for very large monorepos and are intended to catch pathological scope, not manage normal embedding cost.
- A safety-fuse failure must report eligible file, byte, and estimated-token counts plus the limit that fired.
- Agents cannot bypass a safety fuse through an MCP argument or repository policy. A developer may release only one exact approvable preflight through the explicit human-owned mechanism outside the repository after inspecting its measurements.
- A compatible existing commit generation must be reused before scanning unchanged files or requesting embeddings.
- The result must expose reuse/cache counters so zero-re-embedding behavior is observable and testable.
- Initial indexing must run asynchronously and survive a single MCP request ending.
- Failures must retain enough state for `operation_status` to explain recovery.

### 7.2 In-process MCP runtime state machine

```text
STARTING
   |
   +--> load and validate runtime state
   +--> resolve credential without disclosing it
   +--> initialize/validate storage under short writer transactions
   +--> register runtime owner and reconcile stale leases/checkpoints
   +--> construct indexing and search services
   +--> READY
           |
           +--> claim queued/paused operation leases
           +--> acquire workspace watcher leases
           +--> serve concurrent committed-state readers
           |
           +--> EOF / shutdown / SIGINT / SIGTERM
                    |
                    +--> DRAINING
                    +--> stop new mutation scheduling
                    +--> checkpoint work and release leases
                    +--> close workers/watchers/stores
                    +--> STOPPED

Any failed transition --> FAILED_WITH_REMEDIATION --> clean shutdown
Crash/kill --> lease expiry --> next runtime reconciliation --> PAUSED --> eligible resume
```

Rules:

- Never allow two uncoordinated writers against the same store.
- Use a per-store lock with process identity and stale-lock recovery.
- Use bounded initialization, operation-cancellation, and shutdown timers.
- Reconcile operations interrupted by a prior crash before accepting mutations.
- Run workers and watchers only while this visible process is alive; never daemonize or register a launch/login service.
- Persist phase checkpoints and release leases within the fixed shutdown budget; another compatible runtime may claim them immediately.
- Keep MCP request handlers thin; they call application services rather than HTTP endpoints.
- The human foreground operation runner must use the same service layer, checkpoints, credentials, leases, and locking rules.
- Send operational logs to stderr or files, never MCP stdout.

### 7.3 Structured tool errors

```python
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class Remediation(BaseModel):
    action: str
    command: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] | None = None


class IndexBuildingDetails(BaseModel):
    workspace_id: str
    operation_id: str
    operation_state: Literal["queued", "running", "paused"]
    phase: Literal["preflight", "scan", "chunk", "embed", "store", "publish"]
    pause_reason: Literal[
        "runtime_absent", "credential_missing", "disk_pressure", "awaiting_approval", "shutdown"
    ] | None = None
    processed_files: int = 0
    known_eligible_files: int | None = None
    embedded_chunks: int = 0
    known_chunks: int | None = None
    last_progress_at: str | None = None
    has_committed_generation: Literal[False] = False


class ScopeLimitObservation(BaseModel):
    metric: Literal["eligible_files", "eligible_bytes", "estimated_embedding_tokens"]
    observed: int = Field(ge=0)
    limit: int = Field(ge=0)


class ScopeFuseDetails(BaseModel):
    workspace_id: str
    workspace_root: Path
    operation_id: str
    preflight_id: str
    fingerprint: str
    measurements: list[ScopeLimitObservation] = Field(min_length=1, max_length=3)
    expires_at: str
    approval_command: str


class WorkspaceInUseDetails(BaseModel):
    workspace_id: str
    reason: Literal[
        "cleanup_pending",
        "mutation_lease",
        "publication_critical",
        "operation_draining",
    ]
    retry_after_ms: int = Field(ge=250, le=5_000)
    intent_expires_at: str | None = None


class SearchBudgetLimitDetails(BaseModel):
    field: Literal["max_results", "max_context_tokens"]
    requested: int = Field(ge=0)
    effective_cap: int = Field(ge=0)
    profile: Literal["small", "medium", "large", "massive"]
    policy_version: str


class DolphinToolError(BaseModel):
    code: Literal[
        "CONFIG_MISSING",
        "UNSUPPORTED_PLATFORM",
        "UNSUPPORTED_PYTHON",
        "OPENAI_KEY_MISSING",
        "OPENAI_AUTH_FAILED",
        "OPENAI_REQUEST_FAILED",
        "PATH_INVALID",
        "PATH_OUT_OF_SCOPE",
        "REPOSITORY_BOUNDARY_INVALID",
        "REPO_CONFIG_INVALID",
        "SCOPE_FUSE_TRIPPED",
        "SUBMODULE_UNINITIALIZED",
        "WORKSPACE_REQUIRED",
        "WORKSPACE_AMBIGUOUS",
        "WORKSPACE_MISSING",
        "WORKSPACE_IN_USE",
        "CLEANUP_NOT_AUTHORIZED",
        "INDEX_BUILDING",
        "PIPELINE_INCOMPATIBLE",
        "STORE_LOCKED",
        "STORE_INCOMPATIBLE",
        "STORAGE_PERMISSIONS_UNSAFE",
        "STORAGE_MEASUREMENT_FAILED",
        "DISK_PRESSURE",
        "ARTIFACT_CORRUPT",
        "REFERENCE_INVALID",
        "REFERENCE_EXPIRED",
        "REFERENCE_TARGET_MISSING",
        "REFERENCE_BLOCKED",
        "REFERENCE_CHANGED_DURING_READ",
        "CURSOR_INVALID",
        "CURSOR_EXPIRED",
        "OPERATION_MISSING",
        "OPERATION_INCOMPATIBLE",
        "OPERATION_FAILED",
        "SEARCH_BUDGET_EXCEEDED",
        "SEARCH_FAILED",
    ]
    message: str
    retryable: bool
    remediations: list[Remediation] = Field(default_factory=list)
    index_building: list[IndexBuildingDetails] = Field(default_factory=list)
    scope_fuse: ScopeFuseDetails | None = None
    workspace_in_use: list[WorkspaceInUseDetails] = Field(default_factory=list)
    search_budget: SearchBudgetLimitDetails | None = None
```

Agents must be able to distinguish retry, alternate-tool, and human-action failures without parsing prose. `INDEX_BUILDING` always carries one detail record for every unavailable requested workspace plus remediations for `operation_status` and appropriate built-in discovery. `SCOPE_FUSE_TRIPPED` is non-retryable by the agent, carries exactly one `scope_fuse` record and a human-CLI remediation plus built-in-search guidance, and leaves `index_building` empty. `WORKSPACE_IN_USE` is retryable, includes one bounded detail per blocked requested workspace, uses a 250–5,000 ms retry interval derived from remaining intent life, and reports no caller/receipt/process data. `CLEANUP_NOT_AUTHORIZED` is non-retryable through MCP and deliberately does not distinguish an absent workspace from a malformed, mismatched, lost, or superseded receipt. `CURSOR_INVALID` and `CURSOR_EXPIRED` return no partial page and provide a ready-to-use restart action with the cursor omitted. `OPERATION_MISSING` likewise does not distinguish malformed, unknown, cross-store, compacted, or expired operation IDs. `SEARCH_BUDGET_EXCEEDED` identifies only the rejected field, requested value, effective cap, and public profile/version so an agent can retry without learning internal ranking facts. Errors leave unrelated detail collections empty.

### 7.4 Search freshness metadata

```python
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SearchFreshness(BaseModel):
    workspace_id: str
    state: Literal["current", "stale"]
    indexed_fingerprint: str
    observed_fingerprint: str
    pending_operation_id: str | None = None
    reason: str | None = None


class SearchBudget(BaseModel):
    policy_version: str
    policy_digest: str
    config_state: Literal[
        "valid_user",
        "absent_using_shipped",
        "invalid_using_last_known_good",
        "invalid_using_shipped",
    ]
    config_error_code: Literal[
        "malformed", "unsafe", "unsupported", "unstable"
    ] | None = None
    scope_searchable_chunks: int = Field(ge=0)
    intent_class: Literal[
        "local_symbol", "concept", "architecture", "cross_file", "analogous_pattern"
    ]
    intent_classifier_version: Literal["rules-v1"]
    base_profile: Literal["small", "medium", "large", "massive"]
    profile: Literal["small", "medium", "large", "massive"]
    selection_reason: Literal[
        "scope_size", "multi_workspace", "broad_intent", "multi_workspace_and_broad_intent"
    ]
    default_max_results: int = Field(ge=1, le=50)
    cap_max_results: int = Field(ge=1, le=50)
    applied_max_results: int = Field(ge=1, le=50)
    max_results_source: Literal["adaptive_default", "request"]
    default_max_context_tokens: int = Field(ge=0, le=20_000)
    cap_max_context_tokens: int = Field(ge=0, le=20_000)
    applied_max_context_tokens: int = Field(ge=0, le=20_000)
    max_context_tokens_source: Literal["adaptive_default", "request"]
    token_accounting_version: Literal["cl100k_base-v1"]
    snippet_allocation_version: Literal["hybrid-v1"]
    page_index: int = Field(ge=0)
    context_tokens_used: int = Field(ge=0, le=20_000)


class SearchExecution(BaseModel):
    retrieval_mode: Literal["hybrid", "lexical_structural"]
    query_embedding_source: Literal["live", "cache", "unavailable"]
    ranking_policy_version: str
    relevance_calibration_version: str
    relevance_calibration_digest: str
    ranked_target_horizon: Literal[500]
    ranked_targets_retained: int = Field(ge=0, le=500)
    ranked_horizon_reached: bool
    degraded: bool
    reranker_id: str | None = None
    reranker_applied: bool = False
    graph_policy_version: str | None = None
    graph_applied: bool = False
    degraded_reason: Literal["transient_provider_failure", "graph_branch_failure"] | None = None
    retryable: bool = False
    omitted_branches: list[Literal["vector", "graph"]] = Field(default_factory=list)


class ReadLifecycle(BaseModel):
    workspace_id: str
    changed_after_admission: bool
    state: Literal["unchanged", "cleanup_pending", "forgotten_after_admission"]
    continuation_allowed: bool
    references_may_expire: bool


class SearchSnippet(BaseModel):
    text: str
    start_line: int
    end_line: int
    content_fingerprint: str
    token_count: int = Field(ge=0, le=20_000)
    truncated: bool
    selection_reason: Literal[
        "seed_window", "structural_completion", "new_scope_evidence", "other_evidence"
    ]


class SearchHit(BaseModel):
    repository_id: str
    repository_display_name: str
    workspace_id: str
    workspace_display_name: str
    workspace_root: Path
    relative_path: str
    absolute_path: Path
    start_line: int
    end_line: int
    ref: str
    content_fingerprint: str
    rank: int = Field(ge=1, le=500)
    relevance: Literal["high", "medium", "exploratory"]
    snippet: SearchSnippet | None = None


class SearchContinuation(BaseModel):
    state: Literal["available", "exhausted", "unavailable"]
    next_cursor: str | None
    expires_at: str | None
    unavailable_reason: Literal[
        "disk_pressure", "writer_busy", "commit_unverified", "storage_unavailable"
    ] | None

    @model_validator(mode="after")
    def fields_match_state(self) -> "SearchContinuation":
        if self.state == "available":
            valid = (
                self.next_cursor is not None
                and self.expires_at is not None
                and self.unavailable_reason is None
            )
        elif self.state == "exhausted":
            valid = self.next_cursor is None and self.expires_at is None and self.unavailable_reason is None
        else:
            valid = self.next_cursor is None and self.expires_at is None and self.unavailable_reason is not None
        if not valid:
            raise ValueError("continuation fields do not match state")
        return self


class SearchResult(BaseModel):
    hits: list[SearchHit]
    freshness: list[SearchFreshness]
    lifecycle: list[ReadLifecycle]
    execution: SearchExecution
    budget: SearchBudget
    continuation: SearchContinuation
    next_actions: list[NextAction]
```

`stale` is a successful, degraded search result—not an untyped warning and not an exception. Agents must be able to branch on `freshness.state` without parsing prose.

`budget` makes adaptive behavior reproducible without turning it into an engine knob. Policy resolution and effective-cap validation occur before query embedding or retrieval; a rejected explicit budget produces zero provider/retrieval work. The cursor binds the policy digest, selected profile, applied per-page budgets, token-accounting version, snippet-allocation version, and exact relevance-calibration version/digest; a change invalidates continuation rather than combining differently interpreted pages. `page_index` starts at zero, while `context_tokens_used` is local to that page, equals the sum of every non-null snippet's `token_count`, and is at most `applied_max_context_tokens`.

`config_error_code` is present exactly for the two `invalid_*` states. An invalid fallback does not set retrieval execution to lexical/structural degradation—the selected retrieval policy remains intact—but the budget block and top-level next action make the configuration degradation prominent. `status` independently reports overall degraded readiness until the file is valid or absent.

`SearchResult` exists only when every requested workspace has a complete committed generation. A workspace without one produces the structured `INDEX_BUILDING` tool outcome from Section 7.3, or `SCOPE_FUSE_TRIPPED` when its operation awaits the exceptional human approval; it is never represented as an empty `hits` list, because that would incorrectly imply a complete search with no matches.

The result does not echo the raw query. The agent already owns its input, omitting the echo saves context, and cursor-only continuation therefore needs no persisted query text. Query identity appears only as an internal domain-separated fingerprint in cache/continuation validation and is absent from logs, diagnostics, MCP results, and retained terminal summaries.

`SearchContinuation` is total rather than inferred from cursor nullability. `available` requires non-null `next_cursor`/`expires_at` and null reason; `exhausted` requires all three nullable fields null; `unavailable` requires a closed reason and null cursor/deadline. The production model enforces those combinations. `unavailable` describes optional pagination persistence only and does not change `freshness`, `execution.degraded`, hits, references, snippets, or page accounting.

`execution.degraded` is false for both live and compatible cached query embeddings under a healthy selected ranking policy. It becomes true when vector retrieval is omitted after a classified transient provider failure or when a graph branch promoted by D-040 fails and is explicitly omitted. Credential or embedding-contract failures do not produce `SearchResult` at all.

`execution.ranked_targets_retained` is the unique ranked-plan size before page slicing. `ranked_horizon_reached` is true only when eligible post-ranking targets were cut by the fixed 500-target horizon. It remains consistent on every continuation page. Exhausting a smaller plan means no more retained matches; exhausting a horizon-hit plan means the agent may issue a narrower fresh query, never that Dolphin can continue the old cursor beyond 500.

Hit `rank` is one-based over that complete retained plan and remains stable across continuation pages. `relevance` is the closed action-oriented band from Section 5.46, not a score or correctness probability. `execution.relevance_calibration_version` and `execution.relevance_calibration_digest` identify the exact local mapping that produced every label; rank remains authoritative for ordering.

Snippet semantics:

- Snippets come from the exact indexed workspace generation that produced the hit, never an unverified current-disk read.
- `hybrid-v1` seeds up to three fitting, non-overlapping ranked targets with their smallest useful windows, then chooses fitting structural-completion, new-scope, and other-evidence actions in that fixed priority.
- Prefer complete definitions or coherent line windows containing the relevant symbol/match. Preserve line boundaries and never truncate in the middle of a Unicode code point.
- Count each exact serialized snippet independently with the bundled `cl100k_base-v1` tokenizer; no estimate or character fallback is a valid production result.
- Redundant snippets should be omitted in favor of another distinct candidate or unused budget.
- Every snippet carries its own exact line range and content fingerprint. Stale search metadata remains authoritative when the current worktree differs.
- `selection_reason` is one closed `hybrid-v1` action class; it is not a score explanation or free-form chain-of-thought.
- A zero context budget returns the same ranked hit metadata and references with all `snippet` fields null.
- `open_ref` is the only tool for requesting deeper or current file content and must apply the reference-drift behavior in Section 5.5.

### 7.5 Worktree seeding and incremental indexing algorithm

```python
def build_workspace_generation(workspace: Workspace, target: WorktreeSnapshot) -> Generation:
    pipeline_key = PipelineKey(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        chunker_version=CHUNKER_VERSION,
        effective_config_hash=workspace.effective_config_hash,
    )

    exact = generations.find_exact(
        repository_id=workspace.repository_id,
        commit=target.head_commit,
        pipeline_key=pipeline_key,
    )
    if exact is not None:
        clean_generation = generations.adopt_manifest(exact, workspace.id)
    else:
        base = generations.find_best_compatible_base(
            repository_id=workspace.repository_id,
            target_commit=target.head_commit,
            pipeline_key=pipeline_key,
        )
        clean_generation = generations.derive_from_git_diff(
            base=base,
            target_commit=target.head_commit,
            changed_paths=git.diff_tree(base.commit, target.head_commit),
        )

    overlay = index_worktree_overlay(
        workspace=workspace,
        base_commit=target.head_commit,
        changed_paths=git.diff_worktree(target.head_commit),
        artifact_cache=content_addressed_artifacts,
        embedding_cache=model_aware_embeddings,
    )
    return generations.publish_atomically(clean_generation, overlay)
```

Normative details:

- `PipelineKey` compatibility must include every setting that can change file eligibility, chunk boundaries, embedding input, dimensions, or retrieval correctness.
- For repository policy, `effective_config_hash` means the canonical validated `.dolphin/config.toml` model plus the fixed eligibility-policy version. Raw formatting, comments, and key order do not invalidate reuse; semantic include/exclude changes do.
- `find_best_compatible_base` operates only inside one repository family and prefers an exact commit, then a generation minimizing the Git tree delta. It must never infer sameness from branch names.
- Clean generations contain only committed Git-tree state. Dirty tracked and untracked files are workspace overlays and must not contaminate reusable commit generations.
- Artifact identity is based on the exact semantic input: file content hash plus language/chunker/config for chunk artifacts, and provider/model/dimensions plus the exact text sent to OpenAI for embeddings.
- Git renames and copies should preserve compatible artifacts; path-dependent metadata and graph relationships are recalculated where necessary.
- A model change legitimately invalidates embeddings. A chunker/config change invalidates affected chunk artifacts but may still hit the embedding cache when the exact embedding input is unchanged.
- A missing compatible base falls back to full local parsing, but global content-addressed caches are still consulted before any OpenAI request.
- All counters in `ReuseSummary` are recorded from actual work, not estimates.

Acceptance cases:

| Scenario                                                                            | Required embedding behavior                                       |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Register a second clean worktree at an already indexed commit and compatible config | Zero embedding API calls                                          |
| Create a branch at the current indexed HEAD with no file changes                    | Zero embedding API calls                                          |
| Create/switch to a branch with changed files                                        | Embed only changed/new chunk inputs that miss cache               |
| Rename an unchanged file                                                            | Reuse embeddings; update path-dependent metadata                  |
| Delete files                                                                        | No embedding calls                                                |
| Add dirty or untracked eligible files                                               | Embed only new chunk inputs that miss cache                       |
| Return to an already indexed compatible commit                                      | Adopt/reuse its generation with zero embedding calls              |
| Change embedding model                                                              | Re-embed required content for the new model                       |
| No compatible generation exists                                                     | Full local indexing allowed; content/embedding caches still apply |

### 7.6 Credential boundary

```python
import os

from openai import OpenAI


DOLPHIN_OPENAI_API_KEY = "DOLPHIN_OPENAI_API_KEY"


def create_openai_client(environ: dict[str, str] | None = None) -> OpenAI:
    source = os.environ if environ is None else environ
    api_key = source.get(DOLPHIN_OPENAI_API_KEY, "").strip()
    if not api_key:
        raise ConfigurationError.missing_secret(DOLPHIN_OPENAI_API_KEY)
    return OpenAI(api_key=api_key)
```

Rules:

- Do not fall back to `OPENAI_API_KEY`, config files, Keychain, or application-managed secret files; 0.3.0 has one explicit credential contract.
- Pass the resolved value directly to the OpenAI client rather than copying it to another environment variable.
- Never include the value in exceptions, model representations, debug logs, tracing attributes, subprocess arguments, or diagnostic output.
- Tests use an injected environment mapping or provider stub and assert that redaction holds on every failure path.
- `dolphin doctor` reports `present: true|false` and `variable: "DOLPHIN_OPENAI_API_KEY"` only.

### 7.7 Public search input

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["query"]
    query: str = Field(min_length=1, max_length=2_000)
    workspace_ids: list[str] | None = Field(
        description="Explicit workspace scope; null requests deterministic current-workspace resolution"
    )
    paths: list[str] = Field(description="Repo-relative include globs; [] means no include narrowing")
    exclude_paths: list[str] = Field(description="Repo-relative exclude globs; [] means none")
    languages: list[str] = Field(description="Normalized language names; [] means all eligible languages")
    max_results: int | None = Field(ge=1, le=50, description="Null selects the adaptive page default")
    max_context_tokens: int | None = Field(
        ge=0, le=20_000, description="Null selects the adaptive page default"
    )


class SearchContinuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["continue"]
    cursor: str = Field(min_length=1, description="Opaque cursor returned by the prior page")


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request: SearchQueryRequest | SearchContinuationRequest
```

Contract rules:

- The root is always `{ "request": ... }`; its nested `anyOf` is discriminated by `kind`. A top-level union, loose nullable sentinel object, mixed query/cursor request, missing declared query field, extra field, or retired engine parameter fails schema validation rather than being ignored.
- Every query-variant key is present for strict tool calling: `workspace_ids` and the two budgets use `null` for automatic behavior, while the three filter arrays use `[]` for no narrowing. Continuation is exactly `{ "request": { "kind": "continue", "cursor": "..." } }`.
- Paths are workspace-relative globs normalized through one matcher shared by indexing and search. Absolute paths are not filter inputs.
- Language names use one canonical registry and return valid alternatives on error.
- Explicit `max_results` limits returned candidates, while explicit `max_context_tokens` bounds aggregate snippet/resource content. Omission resolves the versioned adaptive defaults from Section 5.43; metadata and citations remain available when the explicit or resolved content budget is zero.
- Both applied budgets are per page. A continuation cannot change them and receives a fresh snippet allowance only for the next non-duplicated target slice; `budget.page_index` and page-local use make this explicit.
- An explicit budget above the effective TOML policy cap returns a typed validation outcome containing the allowed cap and selected policy profile; Dolphin never silently clamps it. The schema-level 50/20,000 ceilings remain absolute installed-product bounds.
- Cursors are opaque, signed or integrity-protected, bound to the effective query/workspace generations/filters, and expire predictably. They cannot be replayed against another workspace state.
- Internal policy may choose retrieval branches, candidate depth, fusion, diversity, reranking, graph enrichment, and time budgets. Applied policy/version and degraded fallbacks are observable in response metadata for evaluation, not controllable by the agent.
- Advanced tuning remains available only through development/evaluation configuration and is not part of the installed product's MCP contract.

The schema intentionally places the union below an object property. Current OpenAI strict function schemas require an object root, every field required, and `additionalProperties: false`, while supporting nested `anyOf`; optionals are represented with `null`. Dolphin follows that strict-compatible subset in its canonical MCP schema rather than generating client-specific variants. See the official OpenAI [function-calling strict-mode guidance](https://developers.openai.com/api/docs/guides/function-calling#strict-mode) and [supported Structured Outputs schemas](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas).

### 7.8 Fixed embedding contract

```python
from typing import Final


EMBEDDING_MODEL: Final = "text-embedding-3-small"
EMBEDDING_DIMENSIONS: Final = 1_536
EMBEDDING_CONTRACT_VERSION: Final = 1


def embedding_cache_key(exact_input: str) -> str:
    return stable_hash(
        EMBEDDING_CONTRACT_VERSION,
        EMBEDDING_MODEL,
        EMBEDDING_DIMENSIONS,
        exact_input,
    )
```

All embedding requests pass these constants explicitly. Tests must fail if provider output dimensions differ, if another model enters a production request, or if incompatible vectors become visible to a workspace generation.

### 7.9 Language registry and Rust chunking boundary

```python
from dataclasses import dataclass
from typing import Final, Literal


LanguageName = Literal[
    "python", "javascript", "typescript", "svelte", "sql", "markdown", "rust"
]


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    name: LanguageName
    extensions: frozenset[str]
    parser_id: str
    chunker_version: int


FIRST_CLASS_LANGUAGES: Final = (
    LanguageSpec("python", frozenset({".py", ".pyi", ".pyw"}), "tree-sitter-python", 1),
    LanguageSpec("javascript", frozenset({".js", ".jsx", ".mjs", ".cjs"}), "tree-sitter-javascript", 1),
    LanguageSpec("typescript", frozenset({".ts", ".tsx", ".mts", ".cts"}), "tree-sitter-typescript", 1),
    LanguageSpec("svelte", frozenset({".svelte"}), "dolphin-svelte", 1),
    LanguageSpec("sql", frozenset({".sql"}), "dolphin-sql", 1),
    LanguageSpec("markdown", frozenset({".md", ".markdown", ".mdx"}), "markdown-it", 1),
    LanguageSpec("rust", frozenset({".rs"}), "tree-sitter-rust", 1),
)
```

The exact parser package versions are locked in the release dependency graph and included in the effective pipeline key. The Rust chunker walks structural item nodes, includes attached outer attributes/doc comments, emits independently useful impl methods with parent context, and falls back only around parser-error regions. Parser or chunker changes invalidate affected chunk artifacts; unchanged exact embedding inputs may still hit the global embedding cache.

### 7.10 Runtime storage layout

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StorageLayout:
    root: Path
    config_file: Path
    metadata_db: Path
    vectors: Path
    artifacts: Path
    locks: Path
    logs: Path
    temporary: Path


def macos_storage_layout(*, home: Path) -> StorageLayout:
    root = (home / "Library" / "Application Support" / "Dolphin").resolve()
    return StorageLayout(
        root=root,
        config_file=root / "config.toml",
        metadata_db=root / "metadata.sqlite3",
        vectors=root / "vectors",
        artifacts=root / "artifacts",
        locks=root / "locks",
        logs=root / "logs",
        temporary=root / "tmp",
    )
```

Production obtains `home` from the operating-system user context; tests pass an isolated temporary home explicitly. Initialization validates every member with the canonical containment helper, creates only the required state directories/files with private permissions, and treats `config_file` as optional human-owned input that it never overwrites implicitly. The resulting `StorageLayout` is a required dependency of configuration, storage, logging, locking, operation, and GC services.

### 7.11 Canonical agent contract and adapter generation

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class ClientTarget(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude-code"


CRITICAL_GUIDANCE: Final = (
    "Dolphin is for semantic, architectural, and cross-file code discovery. "
    "Resolve the exact Git worktree first; if it is not registered, call repo_add "
    "with its absolute root. Treat sibling worktrees as separate workspaces. Use "
    "built-in filename or exact-text search for known names and strings. Follow "
    "Dolphin hits by their validated path or open_ref reference."
)


@dataclass(frozen=True, slots=True)
class AgentContract:
    critical_guidance: str
    workflow_blocks: tuple["GuidanceBlock", ...]
    tool_specs: tuple["ToolSpec", ...]
    release_version: str


def render_all(contract: AgentContract) -> dict[ClientTarget, "GeneratedAdapter"]:
    assert len(contract.critical_guidance) <= 512
    return {
        target: renderer_for(target).render(contract)
        for target in ClientTarget
    }
```

The MCP instruction renderer prepends `CRITICAL_GUIDANCE` verbatim, then adds compact shared workflow blocks. Client renderers wrap the same blocks and runtime-derived tool summaries in target-specific packaging only. Each generated adapter records a canonical-source digest; a parity test parses both outputs back into a normalized representation and compares every required block, tool name, example ID, environment-variable name, and release version.

At implementation and RC time, validate the Codex adapter against the current [official Codex MCP documentation](https://developers.openai.com/codex/mcp/), including stdio configuration, environment forwarding, shared local-client configuration, server instructions, and plugin-provided MCP behavior. Validate Claude Code independently against its current official specification without allowing target-specific details to leak into the canonical behavior contract.

### 7.12 Client setup transaction

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class ClientSetupPlan:
    client: ClientTarget
    scope: Literal["user", "project"]
    executable: Path
    args: tuple[str, ...]
    forwarded_environment_names: tuple[str, ...]
    target: Path | None
    precondition_digest: str | None
    disposition: Literal["create", "update", "no-op", "conflict", "manual"]
    source_digest: str


def desired_setup(
    client: ClientTarget,
    *,
    executable: Path,
    scope: Literal["user", "project"] = "user",
) -> ClientSetupPlan:
    return adapter_for(client).plan(
        scope=scope,
        executable=executable.resolve(strict=True),
        args=("mcp",),
        forwarded_environment_names=("DOLPHIN_OPENAI_API_KEY",),
        source_digest=canonical_agent_contract_digest(),
    )
```

Application follows a plan/apply/verify transaction: construct and redact a plan; reject conflicts; recheck the precondition digest; create a private rollback point when direct mutation is necessary; apply without a shell; validate client parsing and inspect the installed entry; run Dolphin readiness checks; then either commit the result or restore the rollback point. `--dry-run` stops after planning. Structured results contain names and presence booleans, never environment values or unrelated client configuration.

### 7.13 Query embedding and degraded retrieval

```python
async def execute_search(request: SearchInput, context: SearchContext) -> SearchResult:
    snapshots = context.require_complete_generations(request.workspace_ids)
    key = embedding_cache_key(request.query)

    cached = context.embedding_cache.get_valid(key)
    if cached is not None:
        return context.hybrid_search(request, snapshots, cached, embedding_source="cache")

    try:
        vector = await context.openai.embed_query_bounded(request.query)
    except (CredentialMissing, CredentialRejected) as exc:
        raise typed_credential_error(exc) from None
    except TransientProviderFailure as exc:
        return context.lexical_structural_search(
            request,
            snapshots,
            degraded_reason=safe_provider_category(exc),
        )
    except (PermanentProviderFailure, EmbeddingContractViolation) as exc:
        raise typed_request_or_contract_error(exc) from None

    context.embedding_cache.put(key, vector)
    return context.hybrid_search(request, snapshots, vector, embedding_source="live")
```

The cache read validates model, dimensions, contract version, vector shape, and exact input hash before use. The bounded OpenAI adapter classifies failures once; retrieval code never branches on raw exception strings. Local degraded retrieval emits its own mode-calibrated scoring metadata and a cursor that cannot be resumed under a different retrieval mode.

### 7.14 Repository-boundary discovery

```python
GITLINK_MODE = 0o160000


def plan_parent_scan(workspace: Workspace, git: GitReader) -> ParentScanPlan:
    boundaries: dict[str, RepositoryBoundary] = {}

    # Gitlinks are classified first and remain authoritative as submodules.
    for entry in git.index_entries(workspace.root, mode=GITLINK_MODE):
        relative_path = validate_repository_relative_path(entry.path)
        candidate = resolve_contained_descendant(workspace.root, relative_path)
        boundaries[relative_path] = inspect_submodule_without_mutation(
            parent=workspace,
            relative_path=relative_path,
            candidate=candidate,
            expected_commit=entry.object_id,
        )

    # The walker yields a boundary marker and never descends beneath it.
    for marker in discover_nested_git_markers_without_descent(
        workspace.root,
        excluded_subtrees=frozenset(boundaries),
    ):
        relative_path = validate_repository_relative_path(marker.parent_relative_path)
        boundaries.setdefault(
            relative_path,
            inspect_nested_git_marker_without_mutation(
                parent=workspace,
                relative_path=relative_path,
                marker=marker,
            ),
        )

    ordered_boundaries = tuple(boundaries[path] for path in sorted(boundaries))
    return ParentScanPlan(
        workspace=workspace,
        excluded_subtrees=frozenset(boundaries),
        repository_boundaries=ordered_boundaries,
    )
```

The Git index is authoritative for submodule classification. `.gitmodules` enriches display/remediation metadata but cannot cause Dolphin to follow a path absent from validated gitlink entries. A descendant `.git` marker is authoritative only for stopping parent traversal; safe Git probing determines whether it describes an enrollable independent worktree. The same immutable `excluded_subtrees` set is passed to scanning, delta calculation, overlays, watchers, drift checks, graph extraction, reference resolution, and recovery. Probing uses read-only bounded Git/filesystem operations with hooks disabled and never invokes repository initialization, submodule mutation, or remote access.

### 7.15 Binary component decisions

```python
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, model_validator


class ComponentDisposition(StrEnum):
    REMOVED = "removed"
    STANDARD = "standard"


class RetrievalComponentDecision(BaseModel):
    component: Literal["cross_encoder", "knowledge_graph"]
    disposition: ComponentDisposition
    evaluation_artifact: str
    policy_version: str | None = None

    @model_validator(mode="after")
    def require_policy_only_for_standard(self) -> "RetrievalComponentDecision":
        if (self.policy_version is None) != (self.disposition is ComponentDisposition.REMOVED):
            raise ValueError("standard components require exactly one policy version")
        return self
```

The two signed decisions are release inputs checked by dependency validation, generated metadata, runtime policy construction, tests, documentation, and the wheel inspection job. No `auto`, `optional`, or `available` disposition exists. Production code cannot inspect installed packages to choose a different policy.

### 7.16 Local diagnostic snapshot

```python
from typing import Literal

from pydantic import BaseModel, Field


class OperationMetric(BaseModel):
    name: Literal[
        "runtime_start",
        "search",
        "index",
        "sync",
        "openai_embedding",
        "embedding_cache_hit",
        "lexical_fallback",
        "watcher_reconcile",
        "writer_lock_wait",
        "diagnostic_write",
    ]
    attempts: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    duration_ms_total: int = Field(ge=0)
    duration_ms_max: int = Field(ge=0)


class DiagnosticSnapshot(BaseModel):
    schema_version: Literal[1] = 1
    process_instance_id: str
    window_started_at: str
    generated_at: str
    metrics: list[OperationMetric] = Field(max_length=16)
    recent_failure_codes: list[str] = Field(default_factory=list, max_length=16)
    log_sink_state: Literal["healthy", "degraded"]
```

Production construction validates `recent_failure_codes` against the closed shared failure-code registry before serialization; the deliberately small reference model must not become a generic key/value telemetry envelope. `status` omits zero-value metric families when necessary to protect the agent's context budget, while `doctor --json` uses the same schema and semantics.

### 7.17 Repository policy model and loader

```python
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepositoryIndexPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    include: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    exclude: tuple[str, ...] = Field(default_factory=tuple, max_length=256)

    @field_validator("include", "exclude")
    @classmethod
    def validate_patterns(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in patterns:
            validate_repository_pattern(pattern, max_utf8_bytes=512)
        return patterns


class RepositoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    index: RepositoryIndexPolicy = Field(default_factory=RepositoryIndexPolicy)


def load_repository_config(worktree_root: Path) -> RepositoryConfig:
    path = resolve_contained_descendant(worktree_root, ".dolphin/config.toml")
    entry = lstat_optional(path)
    if entry is None:
        return RepositoryConfig(schema_version=1)

    raw = read_bounded_regular_file_without_following_symlinks(
        path,
        expected_entry=entry,
        max_bytes=64 * 1024,
    )
    return RepositoryConfig.model_validate(tomllib.loads(raw.decode("utf-8")))
```

`validate_repository_pattern` rejects leading `/`, negation syntax, `..` segments, backslashes, NUL, empty patterns, and non-canonical constructs before compiling the shared Git-wildmatch matcher. Production maps parse/validation failures to bounded `REPO_CONFIG_INVALID` details and computes the effective policy digest from a canonical serialization plus the fixed eligibility-policy version—not raw TOML formatting.

### 7.18 One-shot scope approval

```python
from enum import StrEnum

from pydantic import BaseModel


class ScopeApprovalState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ScopeApprovalRecord(BaseModel):
    id: str
    workspace_id: str
    operation_id: str
    preflight_fingerprint: str
    measurements: tuple[ScopeLimitObservation, ...]
    created_at: str
    expires_at: str
    state: ScopeApprovalState


def claim_scope_approval(
    *,
    preflight_id: str,
    confirmed_fingerprint: str,
    cheap_drift_fingerprint: str,
) -> str:
    with writer_lock.short_transaction():
        record = approvals.require_pending_unexpired(preflight_id)
        operations.require_state(record.operation_id, OperationState.AWAITING_APPROVAL)
        approvals.require_exact_fingerprint(record, confirmed_fingerprint)
        workspaces.require_unchanged_drift_fingerprint(record.workspace_id, cheap_drift_fingerprint)
        approvals.mark_claimed(record.id)
        operations.compare_and_set(
            record.operation_id,
            expected=OperationState.AWAITING_APPROVAL,
            replacement=OperationState.QUEUED,
        )
        return record.operation_id
```

Before calling this transaction, the CLI verifies a real TTY, reruns the full bounded preflight, compares it with the durable record, displays the warning, and obtains the exact fingerprint confirmation. The claim transaction is short and contains no terminal wait or repository traversal. Index execution then revalidates the full approved snapshot before reading/sending documents; a mismatch cannot consume broader authority.

### 7.19 Durable operation checkpoint

```python
from typing import Literal

from pydantic import BaseModel, Field


class OperationCounters(BaseModel):
    known_eligible_files: int | None = Field(default=None, ge=0)
    processed_files: int = Field(default=0, ge=0)
    parsed_files: int = Field(default=0, ge=0)
    reused_chunks: int = Field(default=0, ge=0)
    embedding_cache_hits: int = Field(default=0, ge=0)
    embedding_cache_misses: int = Field(default=0, ge=0)
    embedded_chunks: int = Field(default=0, ge=0)


class OperationCheckpoint(BaseModel):
    schema_version: Literal[1] = 1
    operation_id: str
    workspace_id: str
    target_fingerprint: str
    pipeline_key: str
    phase: Literal["preflight", "scan", "chunk", "embed", "store", "publish"]
    staging_generation_id: str | None = None
    completed_manifest_id: str | None = None
    counters: OperationCounters
    pause_reason: Literal[
        "runtime_absent", "credential_missing", "disk_pressure", "awaiting_approval", "shutdown"
    ] | None = None
    checkpointed_at: str
    resume_count: int = Field(default=0, ge=0)
```

The checkpoint references normalized durable manifest/artifact membership rather than serializing an unbounded list into the operation row. Claiming, checkpoint replacement, pause, and publication use compare-and-set state transitions under short transactions. On resume, target/pipeline revalidation decides which completed units remain compatible; counters are reconstructed or integrity-checked from authoritative membership rather than blindly trusted.

### 7.20 Store interfaces and publication coordinator

```python
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class PublishedSnapshot:
    workspace_id: str
    publication_id: str
    clean_generation_id: str
    overlay_generation_id: str | None
    publication_version: int
    vector_commit_tokens: tuple[str, ...]
    pipeline_key: str


@dataclass(frozen=True)
class VerifiedVectorCommit:
    generation_id: str
    backend_token: str
    manifest_digest: str
    row_count: int
    model: str
    dimensions: int


@dataclass(frozen=True)
class VerifiedChunkManifest:
    generation_id: str
    manifest_digest: str
    artifact_count: int
    total_utf8_bytes: int


class MetadataStore(Protocol):
    def pin_published_snapshot(self, workspace_id: str) -> PublishedSnapshot: ...

    def publish_if_current(
        self,
        *,
        operation_id: str,
        expected_target_fingerprint: str,
        chunk_manifests: Sequence[VerifiedChunkManifest],
        vector_commits: Sequence[VerifiedVectorCommit],
    ) -> PublishedSnapshot: ...


class ChunkArtifactStore(Protocol):
    def put_exact_text(self, text: str) -> "ChunkTextArtifact": ...

    def read_verified(self, artifact_id: str) -> str: ...

    def verify_generation(self, generation_id: str) -> VerifiedChunkManifest: ...


class VectorStore(Protocol):
    def stage(self, generation_id: str, vectors: Sequence[EmbeddingArtifact]) -> None: ...

    def verify_and_commit(self, generation_id: str) -> VerifiedVectorCommit: ...

    def search(
        self,
        *,
        snapshot: PublishedSnapshot,
        query_vector: Sequence[float],
        limit: int,
        policy: VectorSearchPolicy,
    ) -> list[VectorHit]: ...


def publish_generation(operation: IndexOperation) -> PublishedSnapshot:
    chunk_manifests = tuple(
        chunk_artifact_store.verify_generation(generation_id)
        for generation_id in operation.required_chunk_generations
    )
    vector_commits = tuple(
        vector_store.verify_and_commit(generation_id)
        for generation_id in operation.required_vector_generations
    )
    keyword_store.verify_staging_membership(operation.staging_generation_id)
    return metadata_store.publish_if_current(
        operation_id=operation.id,
        expected_target_fingerprint=operation.target_fingerprint,
        chunk_manifests=chunk_manifests,
        vector_commits=vector_commits,
    )
```

`publish_if_current` is the sole logical visibility transition. It runs one short SQLite transaction that checks the operation lease/state, target/pipeline identity, chunk-artifact manifests, SQLite membership/FTS5 readiness, and exact verified LanceDB tokens before swapping the published pointer. `VectorStore.search` requires a pinned `PublishedSnapshot`; its implementation rejects missing/mismatched tokens and cannot construct an unscoped backend query. Reader-lease release and query-cache invalidation are omitted from the snippet but required by Sections 5.27–5.28.

### 7.21 Chunk-text artifact identity and authorized materialization

```python
from dataclasses import dataclass
from hashlib import sha256


CHUNK_TEXT_FORMAT = "dolphin-chunk-text-v1"
CHUNK_TEXT_DOMAIN = b"dolphin:chunk-text:v1\x00"


@dataclass(frozen=True, slots=True)
class ChunkTextArtifact:
    artifact_id: str
    format: str
    utf8_bytes: int
    characters: int
    lines: int


def identify_chunk_text(text: str) -> ChunkTextArtifact:
    payload = text.encode("utf-8", errors="strict")
    return ChunkTextArtifact(
        artifact_id=sha256(CHUNK_TEXT_DOMAIN + payload).hexdigest(),
        format=CHUNK_TEXT_FORMAT,
        utf8_bytes=len(payload),
        characters=len(text),
        lines=text.count("\n") + (1 if text else 0),
    )


def materialize_published_chunk(
    *,
    read_lease_id: str,
    chunk_instance_id: str,
) -> str:
    snapshot = generation_coordinator.snapshot_for_lease(read_lease_id)
    membership = metadata_store.require_chunk_membership(
        snapshot=snapshot,
        chunk_instance_id=chunk_instance_id,
    )
    text = chunk_artifact_store.read_verified(membership.artifact_id)
    if identify_chunk_text(text).artifact_id != membership.artifact_id:
        raise ArtifactCorrupt(membership.artifact_id)
    return text
```

`put_exact_text` uses the same identity function, writes a versioned envelope through a private same-root temporary file, synchronizes it, and atomically installs it without replacing an existing artifact. An existing/racing artifact is accepted only after full verification. `materialize_published_chunk` requires an unexpired reader-lease ID and resolves its exact snapshot from SQLite rather than trusting caller-supplied snapshot fields; it receives an internal chunk-instance ID from that snapshot-scoped search result, and no MCP input accepts a raw artifact ID. Production code returns a bounded typed error rather than placing the ID, path, or payload in an uncontrolled exception.

### 7.22 Current-reference result and alignment

```python
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class SourceRange(BaseModel):
    start_line: int
    end_line: int


class OpenRefResult(BaseModel):
    ref: str
    workspace_id: str
    relative_path: str
    absolute_path: Path
    content_source: Literal["current_worktree"] = "current_worktree"
    alignment: Literal["exact_file", "unchanged_range", "relocated", "unresolved"]
    drifted: bool
    indexed_file_fingerprint: str
    current_file_fingerprint: str
    indexed_range: SourceRange
    current_range: SourceRange
    text: str
    truncated: bool
    lifecycle: ReadLifecycle
    next_actions: list[NextAction]


def open_ref(reference: str) -> OpenRefResult:
    with reference_store.resolve_and_pin_issued(reference) as target:
        workspace = workspace_store.require_present(target.workspace_id)
        current = secure_reader.read_current_eligible_file(
            workspace=workspace,
            relative_path=target.relative_path,
        )
        indexed_range_text = chunk_artifact_store.read_verified(
            target.range_artifact_id
        )
        alignment = align_exact_range_only(
            indexed_file_fingerprint=target.indexed_file_fingerprint,
            indexed_range=target.indexed_range,
            indexed_range_text=indexed_range_text,
            current=current,
        )
        excerpt = bounded_current_excerpt(current, alignment.current_range)
        return OpenRefResult(
            ref=reference,
            workspace_id=workspace.id,
            relative_path=target.relative_path,
            absolute_path=current.validated_path,
            alignment=alignment.kind,
            drifted=alignment.kind != "exact_file",
            indexed_file_fingerprint=target.indexed_file_fingerprint,
            current_file_fingerprint=current.fingerprint,
            indexed_range=target.indexed_range,
            current_range=excerpt.source_range,
            text=excerpt.text,
            truncated=excerpt.truncated,
            next_actions=alignment.next_actions,
        )
```

`resolve_and_pin_issued` validates a Dolphin-created reference against retained authoritative membership and holds the originating generation/artifact lease until alignment completes. `secure_reader` applies the path, repository-boundary, eligibility, stable-descriptor, and bounded-input rules from Section 5.29. `align_exact_range_only` may compare retained indexed text internally but returns no historical text; its `relocated` outcome requires exactly one byte-for-byte occurrence. Exception mapping uses the typed reference errors in Section 7.3.

### 7.23 Opaque reference codec

```python
from base64 import b64decode, b64encode
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from uuid import UUID


REFERENCE_PREFIX = "dolphin://ref/"
REFERENCE_VERSION = 1
REFERENCE_PAYLOAD_BYTES = 1 + (16 * 3)
REFERENCE_CHECKSUM_BYTES = 4
REFERENCE_DOMAIN = b"dolphin-reference-v1\x00"


@dataclass(frozen=True, slots=True)
class ReferenceIdentity:
    workspace_id: UUID
    publication_id: UUID
    reference_target_id: UUID


def encode_reference(identity: ReferenceIdentity) -> str:
    payload = b"".join(
        (
            bytes((REFERENCE_VERSION,)),
            identity.workspace_id.bytes,
            identity.publication_id.bytes,
            identity.reference_target_id.bytes,
        )
    )
    checksum = sha256(REFERENCE_DOMAIN + payload).digest()[:REFERENCE_CHECKSUM_BYTES]
    token = b64encode(payload + checksum, altchars=b"-_").decode("ascii").rstrip("=")
    return REFERENCE_PREFIX + token


def decode_reference(reference: str) -> ReferenceIdentity:
    if not reference.startswith(REFERENCE_PREFIX):
        raise ReferenceInvalid()
    token = reference.removeprefix(REFERENCE_PREFIX)
    padding = "=" * (-len(token) % 4)
    try:
        raw = b64decode(token + padding, altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise ReferenceInvalid() from error
    if len(raw) != REFERENCE_PAYLOAD_BYTES + REFERENCE_CHECKSUM_BYTES:
        raise ReferenceInvalid()
    payload = raw[:-REFERENCE_CHECKSUM_BYTES]
    supplied = raw[-REFERENCE_CHECKSUM_BYTES:]
    expected = sha256(REFERENCE_DOMAIN + payload).digest()[:REFERENCE_CHECKSUM_BYTES]
    if not compare_digest(supplied, expected) or payload[0] != REFERENCE_VERSION:
        raise ReferenceInvalid()
    return ReferenceIdentity(
        workspace_id=UUID(bytes=payload[1:17]),
        publication_id=UUID(bytes=payload[17:33]),
        reference_target_id=UUID(bytes=payload[33:49]),
    )
```

Production decoding additionally applies a strict maximum input length before any allocation and maps every malformed case to the same bounded `REFERENCE_INVALID` shape. The checksum detects transcription/copy damage only. Authenticity and scope come from high-entropy persisted IDs plus the SQLite proof that this exact target belongs to this exact retained workspace publication; `open_ref` never trusts decoded components by themselves.

### 7.24 Local storage-protection diagnostics

```python
import os
import stat
from typing import Literal, Protocol

from pydantic import BaseModel


class StorageProtectionStatus(BaseModel):
    application_encryption: Literal["none"] = "none"
    private_permissions: Literal["valid", "unsafe"]
    filevault: Literal["on", "off", "unknown"]
    advisory: str | None = None


class FileVaultProbe(Protocol):
    def status(self) -> Literal["on", "off", "unknown"]: ...


def enforce_private_descriptor(fd: int, *, expect_directory: bool) -> None:
    before = os.fstat(fd)
    expected_type = stat.S_ISDIR if expect_directory else stat.S_ISREG
    expected_mode = 0o700 if expect_directory else 0o600
    if before.st_uid != os.geteuid() or not expected_type(before.st_mode):
        raise StoragePermissionsUnsafe()
    if not expect_directory and before.st_nlink != 1:
        raise StoragePermissionsUnsafe()
    if stat.S_IMODE(before.st_mode) != expected_mode:
        os.fchmod(fd, expected_mode)
    after = os.fstat(fd)
    if (
        (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or after.st_uid != os.geteuid()
        or stat.S_IMODE(after.st_mode) != expected_mode
    ):
        raise StoragePermissionsUnsafe()
```

Callers obtain descriptors with `O_NOFOLLOW`, `O_CLOEXEC`, and `O_DIRECTORY` where applicable, after canonical containment and before any backend opens state. New paths use exclusive creation and are verified through their descriptors. The production tree auditor applies bounded traversal without following links, has explicit rules for backend-created files, and holds the storage initialization/writer lock while repairing modes. `FileVaultProbe` is a macOS-only read adapter with a fixed absolute executable/API, no shell, minimal environment, strict timeout/output cap, and closed parser; every probe failure maps to `unknown` rather than an exception or security claim.

### 7.25 Storage-pressure plan and write reservation

```python
from dataclasses import dataclass
from enum import IntEnum
from typing import Final


GIB: Final = 1024**3
PERCENT_BASIS: Final = 10_000


def ceil_mul_div(value: int, numerator: int, denominator: int) -> int:
    if value < 0 or numerator < 0 or denominator <= 0:
        raise StorageMeasurementFailed()
    return (value * numerator + denominator - 1) // denominator


class ReclaimTier(IntEnum):
    ORPHAN_TEMP_OR_STAGING = 1
    EXPIRED_BOUNDED_CACHE_OR_LOG = 2
    EXPIRED_WORKSPACE_OVERLAY = 3
    UNREACHABLE_DERIVED_PROJECTION = 4
    INACTIVE_CLEAN_GENERATION = 5
    INACTIVE_REGENERABLE_CACHE = 6


@dataclass(frozen=True, slots=True)
class StoragePressurePolicy:
    version: str
    start_free_floor_bytes: int
    start_free_basis_points: int
    target_free_floor_bytes: int
    target_free_basis_points: int
    reclaimable_soft_cap_bytes: int
    reclaimable_target_bytes: int
    crash_reserve_bytes: int
    max_batch_bytes: int
    max_batch_seconds: float

    def start_free_bytes(self, total_bytes: int) -> int:
        return max(
            self.start_free_floor_bytes,
            ceil_mul_div(total_bytes, self.start_free_basis_points, PERCENT_BASIS),
        )

    def target_free_bytes(self, total_bytes: int) -> int:
        return max(
            self.target_free_floor_bytes,
            ceil_mul_div(total_bytes, self.target_free_basis_points, PERCENT_BASIS),
        )

    def should_collect(self, measured: "DiskMeasurement") -> bool:
        return (
            measured.available_bytes < self.start_free_bytes(measured.total_bytes)
            or measured.reclaimable_bytes > self.reclaimable_soft_cap_bytes
        )

    def targets_hold(self, measured: "DiskMeasurement") -> bool:
        return (
            measured.available_bytes >= self.target_free_bytes(measured.total_bytes)
            and measured.reclaimable_bytes <= self.reclaimable_target_bytes
        )


PRESSURE_POLICY: Final = StoragePressurePolicy(
    version="storage-pressure-v1",
    start_free_floor_bytes=20 * GIB,
    start_free_basis_points=500,
    target_free_floor_bytes=30 * GIB,
    target_free_basis_points=750,
    reclaimable_soft_cap_bytes=50 * GIB,
    reclaimable_target_bytes=40 * GIB,
    crash_reserve_bytes=5 * GIB,
    max_batch_bytes=2 * GIB,
    max_batch_seconds=2.0,
)


@dataclass(frozen=True, slots=True)
class DiskMeasurement:
    total_bytes: int
    available_bytes: int
    dolphin_bytes: int
    protected_bytes: int
    reclaimable_bytes: int
    measured_at: str


@dataclass(frozen=True, slots=True)
class GcCandidate:
    candidate_id: str
    tier: ReclaimTier
    reclaimable_since: str
    last_adopted_or_used_at: str
    recomputation_cost_class: int
    reclaimable_bytes: int


def reserve_index_write(operation: IndexOperation, peak_write_bytes: int) -> None:
    measured = storage_meter.measure_authoritative()
    required = saturated_add(
        peak_write_bytes,
        PRESSURE_POLICY.crash_reserve_bytes,
        PRESSURE_POLICY.start_free_bytes(measured.total_bytes),
    )
    while measured.available_bytes < required:
        outcome = gc_engine.run_bounded(
            max_bytes=PRESSURE_POLICY.max_batch_bytes,
            max_seconds=PRESSURE_POLICY.max_batch_seconds,
        )
        if outcome.actual_reclaimed_bytes == 0:
            break
        operation_runner.cooperative_yield()
        measured = storage_meter.measure_authoritative()
    if measured.available_bytes < required:
        operations.pause(
            operation.id,
            reason="disk_pressure",
            measurement=measured,
            required_available_bytes=required,
        )
        raise DiskPressure()


def ordered_gc_plan() -> list[GcCandidate]:
    reachability = metadata_store.snapshot_gc_reachability()
    candidates = gc_catalog.reconciled_candidates(reachability)
    eligible = [item for item in candidates if not reachability.protects(item)]
    return sorted(
        eligible,
        key=lambda item: (
            item.tier,
            item.reclaimable_since,
            item.last_adopted_or_used_at,
            item.recomputation_cost_class,
            -item.reclaimable_bytes,
            item.candidate_id,
        ),
    )
```

`ceil_mul_div`, `saturated_add`, and measurement validation reject negative/impossible values and use overflow-safe integer operations throughout. `measure_authoritative` measures the actual storage volume and reconciled metadata rather than trusting cached estimates. `run_bounded` starts no new atomic deletion after either bound, uses one maintenance lease and the mark/recheck/delete/finalize protocol, and reports actual reclaimed bytes. The maintenance scheduler applies `should_collect` and continues yielding batches until both D-054 targets hold or no candidates remain. `reserve_index_write` independently collects only until the stricter write-admission formula holds, runs before provider submissions in a growth phase, and is idempotent on resume. Production timestamps are typed UTC instants rather than free-form strings.

### 7.26 Native platform preflight

```python
from dataclasses import dataclass
from typing import Literal


MINIMUM_MACOS = (14, 0, 0)


@dataclass(frozen=True, slots=True)
class PlatformFacts:
    system: str
    machine: str
    macos_version: tuple[int, int, int]
    translation: Literal["native", "translated", "unknown"]
    release_channel: Literal["stable", "seed", "unknown"]


def parse_macos_version(raw: str) -> tuple[int, int, int]:
    parts = raw.split(".")
    invalid_component = any(
        not part.isascii() or not part.isdigit() for part in parts
    )
    if not 1 <= len(parts) <= 3 or invalid_component:
        raise UnsupportedPlatform()
    values = tuple(int(part, 10) for part in parts)
    if any(value > 1_000_000 for value in values):
        raise UnsupportedPlatform()
    return (values + (0, 0))[:3]


def require_supported_platform(facts: PlatformFacts) -> None:
    if (
        facts.system != "Darwin"
        or facts.machine != "arm64"
        or facts.translation != "native"
        or facts.macos_version < MINIMUM_MACOS
    ):
        raise UnsupportedPlatform()
```

One platform adapter constructs `PlatformFacts` from fixed local APIs with bounded parsing; tests inject the structure directly. The production preflight then verifies standard GIL-enabled CPython 3.13 and package/backend ABI expectations before returning a typed immutable runtime-capability record. All entry points consume that one result. A seed/unknown release channel is diagnostic rather than a platform rejection when the other facts pass; no code path downloads compatibility data or infers support from a dependency import.

### 7.27 Registration-epoch cleanup capability

```python
import hashlib
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CLEANUP_RECEIPT_PREFIX = "dolphin-cleanup-v1_"
CLEANUP_RECEIPT_BYTES = 32
CLEANUP_DIGEST_DOMAIN = b"dolphin:workspace-cleanup:v1\x00"
CLEANUP_REPLAY_RETENTION = timedelta(days=30)
CLEANUP_INTENT_TTL = timedelta(seconds=30)
CLEANUP_INTENT_RENEW_INTERVAL = timedelta(seconds=5)
CLEANUP_DRAIN_BUDGET = timedelta(seconds=5)


class RepoForgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    cleanup_receipt: str = Field(repr=False)


class RepoForgetResult(BaseModel):
    workspace_id: str
    registration_epoch: str
    state: Literal["forgotten", "already_forgotten"]
    cancelled_operation_ids: list[str]
    shared_state_retained: bool
    estimated_newly_reclaimable_bytes: int = Field(ge=0)
    idempotent_replay_until: str
    source_and_git_untouched: Literal[True] = True
    next_actions: list[NextAction]


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8", errors="strict")
    return len(encoded).to_bytes(4, "big") + encoded


def cleanup_receipt_digest(
    workspace_id: str,
    registration_epoch: str,
    receipt: str,
) -> bytes:
    return hashlib.sha256(
        CLEANUP_DIGEST_DOMAIN
        + _frame(workspace_id)
        + _frame(registration_epoch)
        + _frame(receipt)
    ).digest()
```

The caller creates `CLEANUP_RECEIPT_PREFIX + secrets.token_urlsafe(CLEANUP_RECEIPT_BYTES)` before invoking `repo_add` and retains it until cleanup is no longer needed. Production parsing first enforces the exact prefix and bounded base64url payload shape, then performs `secrets.compare_digest` against the stored digest. Binding the caller's receipt and inserting the registration share one SQLite transaction; a matching retry re-echoes the authority without persisting plaintext. Forget uses the lifecycle-lock/revalidation/consume transaction from Section 5.34; this helper does not itself authorize deletion. The registration epoch is a random opaque ID, and neither it nor a workspace ID substitutes for the receipt.

### 7.28 Forgotten-worktree identity anchor

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class FilesystemObjectIdentity:
    device: int
    inode: int
    birthtime_ns: int
    kind: Literal["directory"] = "directory"


@dataclass(frozen=True, slots=True)
class WorktreeIdentityFacts:
    repository_family_id: str
    common_dir: FilesystemObjectIdentity
    worktree_gitdir: FilesystemObjectIdentity


@dataclass(frozen=True, slots=True)
class ForgottenWorktreeIdentityAnchor:
    workspace_id: str
    facts: WorktreeIdentityFacts
    replay_expires_at: datetime


def proves_same_forgotten_worktree(
    anchor: ForgottenWorktreeIdentityAnchor,
    current: WorktreeIdentityFacts,
    *,
    now: datetime,
) -> bool:
    return now < anchor.replay_expires_at and anchor.facts == current
```

The macOS adapter builds `FilesystemObjectIdentity` only from stable no-follow directory descriptors, normalizes birth time to integer nanoseconds at the highest native precision available, and rejects missing, negative, overflowing, contradictory, or changed fields. It captures before/after facts around bounded local Git discovery and accepts a descriptor only when both snapshots match. Paths are validated separately and may be retained temporarily for human audit, but are not fields in the identity comparison. Candidate selection must find exactly one eligible matching anchor before calling `proves_same_forgotten_worktree`; the helper's boolean alone does not authorize a merge.

### 7.29 Explicit freshness request

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RepoSyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str


class RepoSyncResult(BaseModel):
    workspace_id: str
    outcome: Literal["up_to_date", "operation_created", "operation_reused"]
    published_fingerprint: str | None
    observed_fingerprint: str
    operation: OperationSummary | None
    next_actions: list[NextAction]
```

`operation` is `None` if and only if `outcome == "up_to_date"`; that path performs no document-embedding call and creates no durable operation. `operation_reused` requires an existing nonterminal operation whose target/reconciliation fingerprint covers the newly observed workspace state. Otherwise one compare-and-set submission creates `operation_created`, and racing callers return that same operation rather than duplicate it.

The handler returns after observation and durable submission, never after the indexing work itself. It exposes no implicit workspace resolution and no `wait`, `timeout`, `full`, `force`, `strategy`, `model`, `concurrency`, or tuning field. Internally selected full reconstruction is allowed only when pipeline incompatibility, missing/corrupt required state, or insufficient delta evidence makes it necessary for correctness; this is an operation plan, not a public control. `operation_status` carries progress, reuse, pause, failure, and completion details.

### 7.30 Bounded status and repository-list contracts

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


REPO_LIST_PAGE_SIZE = 25


class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EffectiveWorkspaceCounts(BaseModel):
    registered: int = Field(ge=0)
    indexing: int = Field(ge=0)
    ready: int = Field(ge=0)
    failed: int = Field(ge=0)


class ToolAvailability(BaseModel):
    status: Literal["available", "unavailable"]
    repo_list: Literal["available", "unavailable"]
    repo_add: Literal["available", "unavailable"]
    repo_forget: Literal["available", "unavailable"]
    repo_sync: Literal["available", "unavailable"]
    operation_status: Literal["available", "unavailable"]
    search: Literal["available", "unavailable"]
    open_ref: Literal["available", "unavailable"]


class RuntimeHealth(BaseModel):
    active_processes: int = Field(ge=0, le=1_024)
    operation_executors: int = Field(ge=0, le=1_024)


class StatusResult(BaseModel):
    version: str
    readiness: Literal["ready", "degraded", "blocked"]
    credential_present: bool
    credential_variable: Literal["DOLPHIN_OPENAI_API_KEY"]
    tool_availability: ToolAvailability
    runtime: RuntimeHealth
    workspace_counts: EffectiveWorkspaceCounts
    current_workspace_resolution: Literal[
        "resolved", "unregistered", "ambiguous", "outside_worktree", "unavailable"
    ]
    current_workspace: WorkspaceSummary | None
    current_repository_boundaries: list[RepositoryBoundarySummary]
    next_actions: list[NextAction]


class RepoListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: str | None


class RepoListItem(BaseModel):
    repository: RepositoryFamilySummary
    workspace: WorkspaceSummary
    repository_boundaries: list[RepositoryBoundarySummary]


class RepoListResult(BaseModel):
    items: list[RepoListItem] = Field(max_length=REPO_LIST_PAGE_SIZE)
    next_cursor: str | None
```

`current_workspace` is non-null if and only if `current_workspace_resolution == "resolved"`; `status` never substitutes a candidate when resolution is ambiguous. The shipped counts include only the durable mutually exclusive states the current registry can represent: `registered`, `indexing`, `ready`, and `failed`. Missing, cleanup-pending, and forgotten aggregates must not appear as fabricated zeros; they may be added only with their durable state implementation and corresponding contract update. Production models may group detailed runtime/storage diagnostics into bounded typed submodels, but may not add workspace enumeration or credential values to this result.

The initial `repo_list` request sends `{"cursor": null}`. Every non-final page contains exactly 25 items and a `next_cursor`; the final page contains 0–25 items and `next_cursor = None`. Cursor decoding is bounded before allocation, and validation occurs before any list items serialize. A concurrent actionable-membership/order change invalidates the whole continuation with `CURSOR_EXPIRED`; the agent restarts with `{"cursor": null}` rather than merging inconsistent pages.

Production projections also bound every string and nested collection rather than relying on the 25-item page cap alone. Repository/workspace IDs are at most 64 characters, display labels at most 512, roots at most 4,096, branches at most 1,024, and head identifiers at most 64. Each workspace carries at most eight boundary summaries, each boundary has at most six bounded string fields, and cursors are capped at 8,192 characters on both input and output; cursor generation fails closed before exceeding that limit.

### 7.31 Exact operation snapshot

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OperationStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=128)


class OperationStatusResult(BaseModel):
    operation_id: str = Field(min_length=1, max_length=128)
    kind: Literal["initial_index", "sync", "recovery"]
    state: OperationState
    attempt: int = Field(ge=1)
    target_head_commit: str = Field(min_length=1, max_length=64)
    workspace_available: bool
    workspace_id: str | None = Field(default=None, min_length=1, max_length=64)
    phase: Literal["preflight", "scan", "chunk", "embed", "store", "publish"] | None
    counters: OperationCounters
    reuse: ReuseSummary | None
    pause_reason: Literal[
        "runtime_absent",
        "credential_missing",
        "disk_pressure",
        "awaiting_approval",
        "shutdown",
    ] | None
    failure: DolphinToolError | None
    created_at: str = Field(min_length=1, max_length=64)
    last_progress_at: str | None = Field(default=None, max_length=64)
    terminal_at: str | None = Field(default=None, max_length=64)
    status_expires_at: str | None = Field(default=None, max_length=64)
    recommended_poll_after_ms: int | None = Field(default=None, ge=250, le=5_000)
    next_actions: list[NextAction] = Field(max_length=8)
```

`terminal_at` and `status_expires_at` are both present exactly for `succeeded`, `failed`, or `cancelled`, and the latter is always 30 days after the former. `attempt` starts at one and increases only when a failed/cancelled target is explicitly requeued as a new operation; successful and active exact-target work remains deduplicated. `recommended_poll_after_ms` is present only for nonterminal states; it is response guidance, not a server-side wait. `failure` is present only for `failed`, while approval and resource pauses use typed state/pause details and remediations rather than masquerading as terminal errors.

While its registration remains actionable, `workspace_available` is true and `workspace_id` names that exact workspace. After forget, the retained operation summary sets `workspace_available = false` and `workspace_id = None`; exact inspection never reintroduces the forgotten workspace to resolution or listings. Logical expiry is checked before serialization. Physical compaction deletes only bounded operation/checkpoint/audit detail proven unnecessary to nonterminal recovery and never follows operation fields into derived data.

### 7.32 Frozen public tool registry

```python
from collections.abc import Mapping, Sequence
from typing import Final


PUBLIC_MCP_TOOL_NAMES: Final = (
    "status",
    "repo_list",
    "repo_add",
    "repo_forget",
    "repo_sync",
    "operation_status",
    "search",
    "open_ref",
)


def require_frozen_public_registry(
    specs: Sequence[ToolSpec],
    handlers: Mapping[str, object],
) -> None:
    names = tuple(spec.name for spec in specs)
    if names != PUBLIC_MCP_TOOL_NAMES:
        raise RuntimeError(f"invalid Dolphin 0.3.0 tool registry: {names!r}")
    if set(handlers) != set(PUBLIC_MCP_TOOL_NAMES):
        raise RuntimeError("public tool handlers do not match the frozen registry")
```

Runtime registration preserves tuple order and consumes the same immutable specs used to compute the committed canonical registry digest. Tests compare exact names, order, input/output JSON Schemas, annotations, descriptions, guidance/example links, and version across runtime discovery, generated Codex/Claude artifacts, and documentation fixtures. A handler's typed readiness failure changes only its call result, never discovery output.

The production MCP server registers no additional callable alias, prompt-backed operation, resource-backed file read, or capability discovered from optional dependencies. Development-only harness functions are not placed in the installed registry. Any post-0.3.0 tool addition/removal/rename requires a new recorded product decision, canonical-registry update, regenerated artifacts, and contract/evaluation review.

### 7.33 Declarative adaptive output-budget policy

The starting candidate TOML is deliberately explicit; evaluation replaces its values before RC when evidence supports a better policy:

```toml
schema_version = 1

[search.output_budgets]
selector_version = 1

[search.output_budgets.small]
max_searchable_chunks = 25000
default_results = 8
cap_results = 50
default_context_tokens = 4000
cap_context_tokens = 20000

[search.output_budgets.medium]
max_searchable_chunks = 250000
default_results = 8
cap_results = 50
default_context_tokens = 4000
cap_context_tokens = 20000

[search.output_budgets.large]
max_searchable_chunks = 2500000
default_results = 8
cap_results = 50
default_context_tokens = 4000
cap_context_tokens = 20000

[search.output_budgets.massive]
default_results = 8
cap_results = 50
default_context_tokens = 4000
cap_context_tokens = 20000
```

```python
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


BudgetProfileName = Literal["small", "medium", "large", "massive"]
SearchIntent = Literal[
    "local_symbol", "concept", "architecture", "cross_file", "analogous_pattern"
]
PROFILE_ORDER: tuple[BudgetProfileName, ...] = ("small", "medium", "large", "massive")
BROAD_INTENTS = frozenset({"architecture", "cross_file", "analogous_pattern"})


class IntentClassifier(Protocol):
    version: str

    def classify(self, query: str) -> SearchIntent: ...


class RulesIntentClassifier:
    version = "rules-v1"
    _signals: tuple[tuple[SearchIntent, tuple[str, ...]], ...] = (
        (
            "analogous_pattern",
            ("similar implementation", "other examples", "elsewhere", "same pattern"),
        ),
        (
            "architecture",
            ("architecture", "components interact", "data flow", "end to end"),
        ),
        (
            "cross_file",
            ("across files", "all callers", "all references", "dependency chain"),
        ),
        (
            "local_symbol",
            ("where is", "defined in", "definition of"),
        ),
    )

    def classify(self, query: str) -> SearchIntent:
        normalized = " ".join(query.casefold().split())
        for intent, phrases in self._signals:
            if any(phrase in normalized for phrase in phrases):
                return intent
        return "concept"


class OutputBudgetProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_searchable_chunks: int | None = Field(default=None, ge=1)
    default_results: int = Field(ge=1, le=50)
    cap_results: int = Field(ge=1, le=50)
    default_context_tokens: int = Field(ge=0, le=20_000)
    cap_context_tokens: int = Field(ge=0, le=20_000)

    @model_validator(mode="after")
    def defaults_fit_caps(self) -> "OutputBudgetProfile":
        if self.default_results > self.cap_results:
            raise ValueError("default_results exceeds cap_results")
        if self.default_context_tokens > self.cap_context_tokens:
            raise ValueError("default_context_tokens exceeds cap_context_tokens")
        return self


class SearchOutputBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selector_version: Literal[1]
    small: OutputBudgetProfile
    medium: OutputBudgetProfile
    large: OutputBudgetProfile
    massive: OutputBudgetProfile

    @model_validator(mode="after")
    def thresholds_are_complete_and_ordered(self) -> "SearchOutputBudgets":
        bounded = (
            self.small.max_searchable_chunks,
            self.medium.max_searchable_chunks,
            self.large.max_searchable_chunks,
        )
        if any(value is None for value in bounded):
            raise ValueError("small/medium/large require thresholds")
        low, medium, high = bounded
        assert low is not None and medium is not None and high is not None
        if not (low < medium < high):
            raise ValueError("profile thresholds must increase")
        if self.massive.max_searchable_chunks is not None:
            raise ValueError("massive must be unbounded")
        return self


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_budgets: SearchOutputBudgets


class DolphinUserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    search: SearchConfig


def select_budget_profile(
    policy: SearchOutputBudgets,
    *,
    searchable_chunks: int,
    workspace_count: int,
    intent: SearchIntent,
) -> tuple[BudgetProfileName, BudgetProfileName]:
    base_index = 3
    for index, name in enumerate(PROFILE_ORDER[:-1]):
        threshold = getattr(policy, name).max_searchable_chunks
        if threshold is not None and searchable_chunks <= threshold:
            base_index = index
            break
    promote = workspace_count > 1 or intent in BROAD_INTENTS
    selected_index = min(base_index + int(promote), len(PROFILE_ORDER) - 1)
    return PROFILE_ORDER[base_index], PROFILE_ORDER[selected_index]
```

Production additionally requires `workspace_count >= 1`, a non-negative overflow-safe chunk count derived from the authorized published scope, and one closed intent value from the installed classifier. The canonical policy digest hashes the fully validated semantic model plus selector and classifier implementation versions—not raw TOML. Search metadata exposes `rules-v1`; cache and continuation identity bind that version. Selection reason is derived from the two promotion predicates and reports both when both hold, even though the profile advances only once.

The reference phrases are seeds, not an invitation to grow an unreviewed synonym library. Evaluation may edit the finite groups before RC, with missed-evidence failures weighted above surplus context. Tests freeze normalization, precedence, unmatched fallback, and zero provider/source/config access. A later local-AI classifier implements the same synchronous closed-output interface, ships inside the qualified wheel, receives a new version, and must pass the same deterministic/offline/privacy and task-correctness gates before replacing `rules-v1` in a future release.

### 7.34 Atomic output-budget policy reload

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


ConfigState = Literal[
    "valid_user",
    "absent_using_shipped",
    "invalid_using_last_known_good",
    "invalid_using_shipped",
]
ConfigErrorCode = Literal["malformed", "unsafe", "unsupported", "unstable"]


@dataclass(frozen=True, slots=True)
class EffectiveOutputBudgetPolicy:
    policy: SearchOutputBudgets
    policy_version: str
    semantic_digest: str
    config_state: ConfigState
    config_error_code: ConfigErrorCode | None
    accepted_at: datetime | None


def policy_for_first_page(
    *,
    layout: StorageLayout,
    shipped: EffectiveOutputBudgetPolicy,
    snapshots: OutputBudgetPolicySnapshotStore,
) -> EffectiveOutputBudgetPolicy:
    observed = stable_lstat_optional(layout.config_file)
    if observed is None:
        snapshots.deactivate_user_policy_compare_and_set()
        return shipped_with_state(shipped, "absent_using_shipped")

    try:
        config, fingerprint = read_stable_validated_user_config(
            layout.config_file,
            observed=observed,
            max_bytes=64 * 1024,
            retries=1,
        )
    except BudgetConfigError as error:
        previous = snapshots.active_last_known_good()
        if previous is not None:
            return previous.as_effective(
                state="invalid_using_last_known_good",
                error_code=error.safe_code,
            )
        return shipped_with_state(
            shipped,
            "invalid_using_shipped",
            error_code=error.safe_code,
        )

    digest = canonical_budget_policy_digest(config.search.output_budgets)
    accepted = snapshots.accept_compare_and_set(
        fingerprint=fingerprint,
        semantic_digest=digest,
        policy=config.search.output_budgets,
    )
    return accepted.as_effective(state="valid_user")
```

The real loader first reuses a cached snapshot when the no-follow file tuple is unchanged and performs stable descriptor checks around the bounded read/parse when it changed. `accept_compare_and_set` persists only the frozen semantic policy, digest, safe file fingerprint, generation, and acceptance time; it never stores raw TOML or arbitrary validation text. It resolves a concurrent winner by rechecking the current stable file and returns either one complete prior or new generation.

`inspect_output_budget_config` shares parsing/validation but performs no snapshot-store write and is the only path used by `status`/`doctor`. A continuation bypasses this loader and resolves the already-authorized cursor-bound semantic digest; a first-page request pins the returned object for its complete read lease, query embedding, retrieval, materialization, and serialization lifetime.

### 7.35 Configuration CLI result and create-only initialization

```python
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class BudgetPolicySummary(BaseModel):
    source: Literal["shipped", "user", "last_known_good"]
    semantic_digest: str
    accepted_at: str | None
    profiles: dict[BudgetProfileName, OutputBudgetProfile]


class ConfigCommandResult(BaseModel):
    command: Literal["init", "validate", "show"]
    outcome: Literal[
        "created",
        "already_exists",
        "valid_user",
        "absent_using_shipped",
        "invalid",
        "shown",
    ]
    config_path: Path
    active: BudgetPolicySummary | None = None
    candidate: BudgetPolicySummary | None = None
    candidate_differs: bool | None = None
    next_activation: Literal["accept", "retain", "deactivate", "none"]
    validation_errors: list[SafeConfigValidationError] = Field(max_length=20)
    next_actions: list[NextAction]


def config_init(layout: StorageLayout, shipped_toml: bytes) -> ConfigCommandResult:
    require_supported_runtime()
    ensure_private_application_support_root(layout.root)
    validate_absent_no_follow(layout.config_file)
    atomic_install_regular_file_no_replace(
        destination=layout.config_file,
        content=shipped_toml,
        mode=0o600,
        temporary_root=layout.temporary,
    )
    return inspect_config_command_result(command="init", outcome="created", layout=layout)
```

`atomic_install_regular_file_no_replace` uses a contained private temporary file, verifies the complete shipped bytes/digest, fsyncs as required by the selected durability policy, and uses a macOS no-replace primitive so a concurrent creator or path substitution wins safely rather than being overwritten. Cleanup removes only its own proven temporary file. The command never serializes `shipped_toml` in logs/output and never calls the snapshot acceptance path.

`validate` and `show` use `inspect_output_budget_config` plus read-only snapshot-store access. JSON serialization is the exact `ConfigCommandResult`; text is a thin renderer over it. `SafeConfigValidationError` contains a closed code, field path, optional bounded line/column, and remediation, never the rejected value or raw line.

### 7.36 Exact snippet-token accounting

```python
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from tiktoken import Encoding as TiktokenEncoding


TOKEN_ACCOUNTING_VERSION: Final = "cl100k_base-v1"
SNIPPET_ALLOCATION_VERSION: Final = "hybrid-v1"


class SnippetTokenCounter(Protocol):
    version: str

    def count(self, text: str) -> int: ...


class Cl100kBaseV1Counter:
    version = TOKEN_ACCOUNTING_VERSION

    def __init__(self, encoding: TiktokenEncoding) -> None:
        self._encoding = encoding

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))


@dataclass(frozen=True)
class SnippetAction:
    target_id: str
    hit_rank: int
    kind: Literal["structural_completion", "new_scope_evidence", "other_evidence"]
    added_tokens: int
    replacement: SearchSnippet


ACTION_TIER = {
    "structural_completion": 0,
    "new_scope_evidence": 1,
    "other_evidence": 2,
}


def choose_next_fitting_action(
    actions: list[SnippetAction], remaining_tokens: int
) -> SnippetAction | None:
    fitting = [action for action in actions if action.added_tokens <= remaining_tokens]
    if not fitting:
        return None
    return min(
        fitting,
        key=lambda action: (
            ACTION_TIER[action.kind],
            action.hit_rank,
            action.added_tokens,
            action.target_id,
        ),
    )


def finalize_snippet_budget(
    snippets: list[SearchSnippet | None],
    *,
    counter: SnippetTokenCounter,
    applied_max_context_tokens: int,
) -> int:
    used = 0
    for snippet in snippets:
        if snippet is None:
            continue
        exact = counter.count(snippet.text)
        if snippet.token_count != exact:
            raise RuntimeError("snippet token count does not match serialized text")
        used += exact
    if used > applied_max_context_tokens:
        raise RuntimeError("serialized snippets exceed the admitted context budget")
    return used
```

Production constructs the encoding only from Dolphin's bundled, digest-verified `cl100k_base-v1` asset and never through a network-capable tokenizer registry lookup. The allocator works on source text split with line endings preserved, chooses only contiguous complete-line windows authorized by the pinned indexed artifact, and invokes `finalize_snippet_budget` on the final serialized strings. A non-empty source line that cannot fit remains unreturned rather than being byte/token sliced. Empty snippets are represented as `None`, not as misleading zero-length evidence.

The seed pass is a separate rank-order walk because it has no scoring or weights: accept the smallest window for the next non-overlapping target only when it fits, continue past failures, and stop at three accepted seeds. The remainder pass regenerates valid whole replacement/addition actions after every choice and applies `choose_next_fitting_action`; a replacement's `added_tokens` is its exact new count minus the target's current count. Stable action construction plus the closed lexicographic key makes identical inputs byte-for-byte deterministic. `finalize_snippet_budget` remains the independent final guard rather than trusting allocator arithmetic.

### 7.37 Per-page search continuation binding

```python
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SEARCH_CURSOR_PREFIX = "dolphin-search-v1_"
SEARCH_CURSOR_BYTES = 32
SEARCH_CURSOR_TTL = timedelta(minutes=30)
SEARCH_RANKED_TARGET_HORIZON = 500
CURSOR_DIGEST_DOMAIN = b"dolphin/search-cursor/digest/v1\0"
CURSOR_SUCCESSOR_DOMAIN = b"dolphin/search-cursor/successor/v1\0"


class RankedTargetPointer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str
    focus_id: str | None
    rank: int = Field(ge=1, le=SEARCH_RANKED_TARGET_HORIZON)
    relevance: Literal["high", "medium", "exploratory"]


class SearchContinuationState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal[1]
    session_id: str
    store_id: str
    query_fingerprint: str
    normalized_scope_fingerprint: str
    workspace_publication_ids: tuple[str, ...]
    retrieval_mode: Literal["hybrid", "lexical_structural"]
    ranking_policy_version: str
    relevance_calibration_version: str
    relevance_calibration_digest: str
    output_policy_digest: str
    token_accounting_version: Literal["cl100k_base-v1"]
    snippet_allocation_version: Literal["hybrid-v1"]
    applied_max_results: int = Field(ge=1, le=50)
    applied_max_context_tokens: int = Field(ge=0, le=20_000)
    ranked_targets: tuple[RankedTargetPointer, ...] = Field(
        min_length=1, max_length=SEARCH_RANKED_TARGET_HORIZON
    )
    ranked_horizon_reached: bool
    ranked_sequence_digest: str
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def ranked_plan_is_canonical(self) -> "SearchContinuationState":
        target_ids = tuple(pointer.target_id for pointer in self.ranked_targets)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("ranked continuation targets must be unique")
        if tuple(pointer.rank for pointer in self.ranked_targets) != tuple(range(1, len(target_ids) + 1)):
            raise ValueError("ranked continuation ranks must be one-based and contiguous")
        if self.ranked_horizon_reached and len(target_ids) != SEARCH_RANKED_TARGET_HORIZON:
            raise ValueError("a horizon-hit continuation plan must fill the horizon")
        return self


class SearchCursorPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cursor_digest: bytes
    session_id: str
    offset: int = Field(ge=1)
    page_index: int = Field(ge=1)


def digest_cursor_secret(secret: bytes) -> bytes:
    return hashlib.sha256(CURSOR_DIGEST_DOMAIN + secret).digest()


def new_cursor_material() -> tuple[bytes, datetime, datetime]:
    created_at = datetime.now(UTC)
    return secrets.token_bytes(SEARCH_CURSOR_BYTES), created_at, created_at + SEARCH_CURSOR_TTL


def derive_successor_secret(
    current_secret: bytes, *, session_id: str, successor_offset: int
) -> bytes:
    return hashlib.sha256(
        CURSOR_SUCCESSOR_DOMAIN
        + current_secret
        + session_id.encode("ascii")
        + successor_offset.to_bytes(8, "big")
    ).digest()


def select_page_targets(
    state: SearchContinuationState,
    position: SearchCursorPosition,
    *,
    now: datetime,
) -> tuple[RankedTargetPointer, ...]:
    if now >= state.expires_at:
        raise CursorExpired("search continuation expired")
    if position.session_id != state.session_id:
        raise CursorInvalid("cursor session mismatch")
    target_ids = tuple(pointer.target_id for pointer in state.ranked_targets)
    if digest_ranked_target_sequence(state.ranked_targets) != state.ranked_sequence_digest:
        raise CursorExpired("ranked target sequence changed")
    if len(target_ids) != len(set(target_ids)):
        raise RuntimeError("ranked target sequence contains duplicates")
    start = position.offset
    stop = min(start + state.applied_max_results, len(state.ranked_targets))
    return state.ranked_targets[start:stop]
```

First-page admission obtains one UTC `created_at` inside the SQLite transaction and fixes `expires_at = created_at + SEARCH_CURSOR_TTL`. It generates `session_id` and the first 32-byte secret with `secrets.token_bytes`, returns only the versioned base64url encoding of that secret, and persists its domain-separated digest plus immutable position. The session row stores bounded pointers/metadata only; target/focus IDs resolve through the same retained-membership and artifact-verification paths as first-page hits.

Before materialization, continuation parses the exact prefix/length, hashes the presented secret, resolves one live position, then revalidates store, session deadline, every workspace registration/publication and read admission, modes/versions/budgets, complete sequence digest, and exact offset. It returns the full next slice or one typed cursor/lifecycle error with no hits. If a successor exists, `derive_successor_secret` plus a short compare-and-set transaction installs the successor digest/position; retrying the same cursor derives and returns the same token/page. Exhaustion returns `continuation.state = exhausted`.

`created_at`, `expires_at`, position, and reachability never update on read. Runtime clock rollback cannot rewrite the deadline; implementations also retain a process-local monotonic remaining-time bound so a backward wall-clock jump cannot extend a live process's authority. At logical expiry all positions fail before target/artifact reads and their reachability is ignored even if asynchronous compaction has not deleted the rows. No cursor or fingerprint appears in logs, diagnostics, status, or metrics.

The session's exact relevance-calibration version and artifact digest are validated before any target read. Its pointers persist only the already assigned one-based rank and closed relevance band; no raw or calibrated scalar is recoverable from continuation state. The ranked-sequence digest covers target ID, focus ID, rank, and relevance so neither order nor labels can drift between pages.

### 7.38 Versioned relevance calibration

The runtime interface stays deliberately smaller than a general classifier. Fitting produces one reviewed canonical monotonic table per exact retrieval-mode/ranking-policy pair; production verifies and loads that bundled artifact, performs a deterministic lookup, returns a band, and immediately drops the input feature and internal calibrated scalar.

```python
from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite
from typing import Literal


Relevance = Literal["high", "medium", "exploratory"]
ValidatedRelevance = Literal["high", "medium"]
RetrievalMode = Literal["hybrid", "lexical_structural"]
PublicHitLanguage = Literal[
    "python", "javascript", "typescript", "svelte", "sql", "markdown", "rust", "generic"
]
BaseScopeProfile = Literal["small", "medium", "large", "massive"]


@dataclass(frozen=True)
class CalibrationPoint:
    feature_min: float
    calibrated_value: float


@dataclass(frozen=True)
class CalibrationContext:
    language: PublicHitLanguage
    base_scope_profile: BaseScopeProfile
    workspace_count: int
    has_path_filter: bool
    has_language_filter: bool
    global_rank: int


@dataclass(frozen=True)
class RelevanceCalibration:
    version: str
    artifact_digest: str
    validation_manifest_digest: str
    supported_distribution_digest: str
    retrieval_mode: RetrievalMode
    ranking_policy_version: str
    points: tuple[CalibrationPoint, ...]
    medium_min: float
    high_min: float
    enabled_bands: frozenset[ValidatedRelevance]
    high_supported_cells: frozenset[str]
    medium_supported_cells: frozenset[str]


def calibration_cell_keys(context: CalibrationContext) -> frozenset[str]:
    if context.workspace_count <= 0 or not 1 <= context.global_rank <= 500:
        raise ValueError("invalid calibration context")
    workspace_breadth = "one" if context.workspace_count == 1 else "multiple"
    if context.has_path_filter and context.has_language_filter:
        filter_shape = "both"
    elif context.has_path_filter:
        filter_shape = "path"
    elif context.has_language_filter:
        filter_shape = "language"
    else:
        filter_shape = "none"
    if context.global_rank <= 3:
        rank_bucket = "1-3"
    elif context.global_rank <= 10:
        rank_bucket = "4-10"
    elif context.global_rank <= 50:
        rank_bucket = "11-50"
    else:
        rank_bucket = "51-500"
    return frozenset(
        {
            f"language:{context.language}",
            f"base_scope:{context.base_scope_profile}",
            f"workspace_breadth:{workspace_breadth}",
            f"filter_shape:{filter_shape}",
            f"rank:{rank_bucket}",
        }
    )


def band_is_supported(
    profile: RelevanceCalibration,
    *,
    band: ValidatedRelevance,
    context: CalibrationContext,
) -> bool:
    if band not in profile.enabled_bands:
        return False
    supported = profile.high_supported_cells if band == "high" else profile.medium_supported_cells
    return calibration_cell_keys(context) <= supported


def classify_relevance(
    profile: RelevanceCalibration | None,
    *,
    retrieval_mode: RetrievalMode,
    ranking_policy_version: str,
    transient_ranking_feature: float,
    context: CalibrationContext,
) -> Relevance:
    if (
        profile is None
        or profile.retrieval_mode != retrieval_mode
        or profile.ranking_policy_version != ranking_policy_version
        or not isfinite(transient_ranking_feature)
    ):
        return "exploratory"

    index = bisect_right(
        tuple(point.feature_min for point in profile.points),
        transient_ranking_feature,
    ) - 1
    if index < 0:
        return "exploratory"

    calibrated_value = profile.points[index].calibrated_value
    if calibrated_value >= profile.high_min and band_is_supported(
        profile, band="high", context=context
    ):
        return "high"
    if calibrated_value >= profile.medium_min and band_is_supported(
        profile, band="medium", context=context
    ):
        return "medium"
    return "exploratory"
```

Artifact validation requires non-empty finite points, strictly increasing `feature_min`, nondecreasing bounded `calibrated_value`, `high_min > medium_min`, exact mode/policy identity, a supported semantic version, matching canonical/validation/distribution digests, and proof that every member of `enabled_bands` passed its global gate and every serialized supported cell passed its matching held-out gate. Cell keys must come from the exact closed D-094 universe; an empty enabled set or cell set is valid and produces only `exploratory` where unsupported.

Fitting and threshold selection live only in the isolated evaluation workflow; production has no fitting dependency or fallback profile. The initial scalar feature is a versioned output of the final ranking policy rather than an agent-visible score. `CalibrationContext` is constructed from validated request/result metadata, never caller-supplied calibration fields, and support cannot be inferred optimistically from a high transient feature. A future multi-feature or local-AI calibrator must pass the same interface, determinism, value, leakage, held-out validation, and release gates and receive a new semantic version.

## 8. Safety specification

1. All repository paths must pass the canonical Python path validator and an equivalent boundary check at every external interface.
2. Repository registration must resolve symlinks and bind the canonical concrete worktree root without collapsing it to the Git common directory.
3. All file retrieval must remain contained within a registered root after symlink resolution.
4. Dolphin must never modify indexed source files.
5. `DOLPHIN_OPENAI_API_KEY` must never appear in logs, MCP content, diagnostics, child-command arguments, or persisted operation records. Diagnostics report only presence/absence and the expected variable name.
6. `repo_add` and `repo_sync` must state that eligible source content is embedded through OpenAI in their descriptions and results. Provisioning the API key is the consent boundary; these calls do not pause for additional human confirmation.
7. Index operations must have concurrency, retry, timeout, and catastrophic scope bounds. Scope bounds must not reject a merely large codebase and must be calibrated well above the largest supported benchmark corpus.
8. Writes to metadata and vector storage must remain transactional or recoverable after interruption.
9. Writer locks and maintenance leases must tolerate stale processes and crashes.
10. Every runtime-state write, cleanup target, lock, and log path must remain under the canonical Application Support root after symlink resolution.
11. Client setup may modify only an explicitly named Dolphin integration through the human CLI, with ownership/conflict checks and rollback; client configuration writes are never MCP capabilities.
12. Parent indexing must treat gitlinks and descendant Git-worktree markers as non-overridable repository boundaries. Invalid markers are excluded rather than traversed; Dolphin never initializes, updates, checks out, recursively registers, or executes code from a child repository.
13. Newly discovered child-repository boundaries must be masked from parent search/reference resolution immediately and removed from parent derived state by the next atomic generation.
14. Repository policy is a strictly parsed, read-only narrowing/ordinary-eligibility input. It cannot expand beyond Git-eligible candidates, weaken a security or repository boundary, or alter credentials, fuses, providers, retrieval, storage, runtime, agent setup, or diagnostics.
15. An invalid repository policy prevents new indexing and document-embedding calls. Existing complete state remains only as explicitly stale prior-policy coverage until a valid policy is atomically published; query embedding follows the normal search-time contract.
16. Aggregate fuse approval is one-shot, interactive, exact-snapshot-bound, expiring, and stored only in user-owned runtime state. No MCP call, repository/environment setting, non-interactive option, or approval for another operation can widen it; non-aggregate integrity/safety failures remain unapprovable.
17. No production worker, watcher, child process, listener, LaunchAgent, or login item may outlive the MCP/foreground process that owns it. Exit checkpoints derived work, releases leases, and preserves atomic committed generations; later compatible runtimes explicitly reconcile before resume.
18. SQLite alone authorizes logical generation visibility. LanceDB is local derived vector state behind a scoped adapter; no cloud/object-store URI, raw connection, unscoped query, backend embedding function, or unverified vector token may enter production behavior.
19. Cross-store corruption or mismatch fails explicitly and preserves the last proven complete state. Dolphin never hides missing vector/keyword coverage by publishing or returning a partial normal hybrid result.
20. Receipt-authorized `repo_forget` is the only MCP lifecycle-removal capability. It requires the creation-issued receipt for the exact registration epoch, performs logical release only, and cannot delete source/Git state, force GC, target a registration that predated the authority-issuing call, or override leases/reachability. All broader destructive maintenance stays outside MCP.
21. Retained chunk text is private derived source data: it remains under the canonical Application Support root, uses restrictive permissions and content-only hashed filenames, never enters diagnostics/logs, and is disclosed accurately during setup and enrollment.
22. A published snippet is authorized through exact snapshot membership and verified against its immutable artifact. Missing or corrupt artifact text fails explicitly; Dolphin never relabels mutable current-disk content as the indexed result.
23. `open_ref` accepts only a valid Dolphin-issued retained reference, revalidates current containment/boundaries/eligibility with a stable no-follow read, and labels every returned byte as current worktree content with explicit drift. It exposes neither arbitrary path/range reads nor historical-content selection.
24. Opaque reference tokens contain no source/path fields and grant no authority by decoding alone. Resolution requires exact retained workspace-publication-target membership; malformed, remixed, guessed, expired, and mismatched tokens disclose no target metadata or fallback content.
25. All Dolphin state is current-user-owned private local data with explicit modes and no application encryption claim. Unsafe ownership/type/link/mode state blocks backend access unless Dolphin can safely tighten only its own contained path and verify the result.
26. FileVault inspection is advisory and read-only. Dolphin never requests privilege, changes disk security, handles recovery material, or weakens/blocks indexing based on `on`, `off`, or `unknown` status.
27. Storage pressure never evicts a published snapshot, live/paused operation requirement, reader lease, recovery/transaction evidence, or missing workspace inside its 30-day window. Neither humans nor agents can override this invariant through a quota or force selector.
28. Every automatic or explicit GC deletion requires SQLite-authoritative reachability at planning and an immediate pre-delete recheck under the maintenance lease. Filesystem age/name alone never authorizes deletion, and cleanup remains contained to private Dolphin-derived state.
29. Insufficient protected-space reserve pauses indexing before further document-provider calls and preserves the last complete generation. It does not degrade a partial index into search, block committed read-only search, or trigger destructive emergency eviction.
30. The native platform/CPython preflight is deterministic and side-effect-free. Unsupported or unparseable OS, architecture, translation, interpreter, or ABI state fails before credentials, storage, workers, repository reads, or network access; diagnostic mode reports only bounded safe facts.
31. Cleanup receipts use at least 256 bits of randomness, are persisted only as domain-separated digests, are compared in constant time, and are redacted from all non-creation outputs. Consuming or superseding one receipt can never authorize a later registration epoch, even when the canonical worktree path and stable workspace identity are reused.
32. Only an explicitly authorized `repo_forget` transaction may consume cleanup authority or set a registration to `forgotten`. Implicit runtime/session lifecycle handlers and missing-workspace detection are structurally unable to call that transition or bypass the 30-day disappearance recovery policy.
33. A renewable short-lived cleanup-intent lease stops new scheduling/provider submissions for the exact registration before cancellation. Queued/paused work cancels atomically; running work checkpoints for at most five seconds; non-draining or foreign ownership returns `WORKSPACE_IN_USE` without consuming authority. Intent expires if the explicit caller disappears, so an incomplete attempt cannot freeze a workspace indefinitely. Cleanup never tears through the atomic publication region, affects another workspace's operation, or claims to cancel an external request already submitted.
34. A cleanup replay tombstone is retained for exactly 30 days from successful forget, never refreshed by access, and authorizes only deterministic replay of the original bounded result. It creates no reachability pin; compaction cannot delete or retain artifacts by implication, and an expired receipt cannot fall through to a later registration epoch.
35. Unused cleanup authority is registration-epoch-bound, not time-bound. Clock changes, inactivity, missing-state transitions, process/client lifecycle, and compatible upgrades cannot expire or refresh it; only an explicit authorized lifecycle transition can consume or supersede it, and no transition can transfer it to a later epoch.
36. Cleanup capability state never becomes repository provenance or ownership. All registrations use one schema and identical indexing/search/reuse/freshness/retention behavior; no MCP or CLI input can label, promote, or transfer a workspace between human/agent or temporary/persistent classes.
37. A forgotten registration is never serialized as an MCP workspace, resolution candidate, registered child boundary, or per-entry status record. Human audit visibility is bounded/read-only and creates no authority or retention edge; aggregate MCP accounting contains no forgotten identity, path, timestamp, operation, or receipt material.
38. Workspace-ID restoration after forget is fail-closed: it requires one proven repository-family/concrete-worktree match, always rotates the registration epoch and cleanup receipt, and carries no publication/reference/operation/lease/approval authority forward. Path/name/branch/HEAD/remote equality cannot by itself merge workspace identities, and artifact reuse is separately content/pipeline verified.
39. Forgotten identity proof is usable only before the cleanup replay deadline and is compacted with that tombstone. Logical expiry is immediate even if physical cleanup lags; no access extends it, no delayed row can restore an ID, and removing the anchor neither removes nor retains reusable content-addressed artifacts.
40. Git administrative identity capture uses validated no-follow directory descriptors and stable before/after `(device, inode, birth time, kind)` facts for both common directory and concrete worktree gitdir. Missing/changed/ambiguous facts fail to a new isolated workspace ID; paths and mutable Git metadata never substitute, and no identity probe runs hooks, repository code, or network operations.
41. Cleanup intent uses fixed 30-second TTL/five-second renewal constants and compare-and-set ownership for one workspace/epoch. Only an active explicitly authorized cleanup call may renew it; logical expiry immediately restores normal mutation admission, stale rows grant no authority, and intent renewal cannot consume a receipt or extend any other retention deadline.
42. Reader-versus-cleanup admission is atomic. Readers admitted first may finish under leases and must disclose later lifecycle change; cleanup admitted first rejects all new workspace reads/mutations before provider, backend, or file work. Multi-workspace reads never drop pending coverage, rejected reads return no partial payload, and listing/status access cannot bypass admission.
43. Abandoned-cleanup recovery is deduplicated by workspace/epoch, never resurrects cancelled operations, and performs cheap reconciliation before creating at most one new ordinary operation. It restores watching without a daemon and cannot bypass credentials, scope fuses, policy/boundary validation, snapshot stability, disk reserve, or artifact verification.
44. Cleanup's MCP schema remains exactly two required inputs with unknown fields forbidden. No agent-facing control can alter cleanup scope, timing, cancellation, retention, reclamation, recovery, or source/Git state; logical success never waits for or implies immediate physical deletion.
45. MCP `repo_add` is the only public adapter allowed to create or reactivate a repository registration. Setup, startup, diagnostics, current-directory discovery, foreground operation execution, evaluation helpers, and every retained CLI maintenance command must be side-effect-free with respect to enrollment unless acting on an exact registration or operation that already exists; no removed CLI name or alias may bypass the creation receipt and canonical agent workflow.
46. `repo_sync` is scoped to one explicit registered workspace and cannot select execution strategy or bypass cleanup admission, eligibility, boundaries, credentials, catastrophic fuses, snapshot stability, storage reserve, or publication verification. Up-to-date and equivalent-operation paths create no duplicate operation or provider work; an internally required rebuild remains delta/reuse-aware and preserves the last complete generation until atomic replacement.
47. `status` and `repo_list` are observational local reads: they cannot validate a credential online, reconcile worktree drift, start/resume/cancel work, enroll/reactivate a workspace, collect data, or create retention authority. `status` exposes no multi-workspace identities beyond aggregate counts; `repo_list` exposes only actionable registrations in fixed pages, and any malformed/cross-store/stale continuation fails before partial serialization rather than weakening forgotten-state or workspace-isolation rules.
48. `operation_status` is an exact opaque-ID observational read and has no control transition. Nonterminal recovery evidence cannot expire by age; terminal visibility expires exactly 30 days after the atomic terminal transition and no read extends it. The retained summary contains no source/provider/secret material, cannot enumerate or revive a forgotten workspace, and pins no derived object; malformed, unknown, and expired IDs are constant-shape indistinguishable.
49. Tool discovery is a fixed contract, not an authorization or feature-negotiation mechanism. Every runtime exposes the exact D-074 registry and returns typed denial/readiness outcomes inside those contracts; credentials, repository contents/configuration, client identity, optional dependencies, internal retrieval-component decisions, persisted state, or failures can never reveal a hidden alias, remove a safety-critical tool, or introduce an alternate operation through an MCP resource or prompt.
50. Adaptive search-budget selection uses only bounded already-published metadata and a closed planner classification; it cannot read more source, expand workspace/file eligibility, change retrieval/ranking/provider policy, or bypass any admission/safety rule. Explicit values above the effective cap fail before query-provider/retrieval work, omitted values and their policy digest remain observable, continuation cannot cross a policy change, and the installed 50-result/20,000-token ceilings remain invariant regardless of TOML contents.
51. Only the validated human-owned Application Support TOML may alter production output-budget profiles within protocol ceilings. Repository/client/environment/evaluation files have no production authority; the loader never follows links, searches parents/worktrees, interpolates/executes values, or accepts unknown settings. Development overrides require an explicit non-production entry point plus isolated storage and can never be discovered by the installed MCP runtime.
52. Adaptive-budget configuration is declarative and total: exactly four named profiles, strictly increasing finite thresholds followed by one unbounded profile, defaults no greater than caps, and values no greater than protocol ceilings. Selection uses exact authorized published-scope counts and one closed intent; breadth can promote only one step and cannot stack, execute config-supplied logic, or create a query-dependent authorization/retrieval path.
53. Hot reload admits only one stable fully validated semantic snapshot before a search and pins it through serialization. Invalid/unstable bytes never replace durable last known good; absence explicitly revokes user-policy fallback authority; status/doctor inspection cannot mutate acceptance state; concurrent runtimes use compare-and-set generations; raw TOML and arbitrary errors are never persisted. A policy change can invalidate continuation but cannot alter an already-admitted call.
54. Human config CLI mutation is create-only at the one fixed Application Support path. Initialization uses private contained no-replace installation and cannot follow, chmod, back up, overwrite, delete, or repair an existing entry; validation/show are side-effect-free and cannot accept/deactivate policy or expire cursors. MCP, setup, and doctor have no configuration-write path, and structured/text results disclose only bounded semantic summaries.
55. Intent classification is a pure, bounded, in-process query operation with a closed result and a versioned implementation. It cannot read source/repository metadata, invoke a model/provider, discover code/plugins, accept TOML/environment/repository instructions, or affect anything except the one-step output-budget promotion. Classifier/version changes invalidate incompatible cache/cursor identity and require release evaluation.
56. Snippet accounting is exact at the final serialization boundary: the sum of independently tokenized returned snippet strings must equal reported use and remain at or below the admitted aggregate ceiling. The one tokenizer asset is bundled, digest-verified, offline, and version-bound; missing/corrupt assets fail closed, and metadata exclusion cannot create an unbounded alternate content channel. Snippet selection preserves indexed-artifact authority, complete source lines, Unicode validity, and null evidence when no coherent window fits.
57. Snippet allocation consumes only authorized ranked targets and bounded line-window candidates. Its seed count, redundancy relation, action tiers, and tie-breakers are fixed/versioned; it cannot expand retrieval scope, synthesize source, expose a tuning surface, partially apply an action, or make allocation nondeterministic through unordered iteration. Final accounting independently fails any allocator defect before serialization.
58. Search continuation is all-or-nothing over one pinned finite target sequence. Page budgets, scope/publications, modes, policy/accounting/allocation versions, sequence digest, offset, and page index are integrity-bound and revalidated before reads; callers cannot resize a later page, replay an earlier offset as new evidence, introduce/omit a workspace, or receive duplicated/partial targets after invalidation. Page-local snippet accounting is independently enforced every time.
59. Public tool schemas use one canonical strict-compatible JSON Schema subset across MCP runtime, OpenAI ingestion, generated clients, tests, and docs. `search` keeps its mutually exclusive modes inside one required nested `request` union; every object rejects extras and every declared field is required, with null used only where semantically optional. No client-specific loosening, top-level union, ambiguous sentinel combination, or best-effort schema fallback may reach production.
60. Search-cursor authority is a short-lived read capability, never mutable session policy. Handles have 256 bits of entropy, are persisted only as domain-separated digests, resolve one immutable page position, and derive deterministic successor capabilities without an application key. The source-free state and exact reachability expire together after a fixed non-extending 30 minutes; replay is idempotent, expiry is enforced before reads, and compaction lag cannot restore authority or reachability.
61. A search continuation plan is finite and bounded to 500 deduplicated exact targets. Continuation cannot trigger query embedding, provider access, vector/FTS retrieval, fusion, reranking, graph traversal, or candidate expansion; it may only revalidate the pinned source-free plan and materialize its authorized targets. Horizon truncation is explicit, creates no false global-exhaustion claim, and cannot be raised through output config or MCP input.
62. A cursor is disclosed only after its exact state/position commit is proven. Optional continuation-write failure cannot discard or corrupt a complete admitted page, relabel its retrieval/freshness quality, trigger provider/retrieval repetition, block on maintenance, or invoke GC. Ambiguous/orphan state grants no caller authority, remains undisclosed, and loses reachability at the original deadline; unavailable continuation is closed, prominent metadata rather than a fabricated exhausted state.
63. Agent-facing ranking contains only immutable one-based global rank and the closed relevance band. Calibration is local, deterministic, exact-mode/policy-bound, versioned, digest-verified, and incapable of changing ordering, authorization, scope, or snippets. Raw component/fused/normalized/calibrated scalar scores are transient production values and must cross no result, cache, cursor, persistence, logging, diagnostic, or terminal-summary boundary; absent, mismatched, invalid, or unsupported calibration fails conservatively to `exploratory`.
64. `high` and `medium` authority comes only from an immutable artifact proving that the individual band passed its preregistered disjoint held-out gate for the exact shipped mode/policy and supported distribution. Missing support, insufficient samples, uncertainty failure, unstable strata, distribution mismatch, identity change, or an inconclusive result removes that band's authority without changing rank. Runtime data, user behavior, telemetry, configuration, or another calibration profile can never enable or retune a band.
65. Gate arithmetic uses the fixed one-sided 95% Wilson implementation and exact D-091 sample/bound constants over unique final judged query-target pairs. Medium support is cumulative over provisional medium-or-higher predictions, while critical strata are evaluated independently and cannot borrow global or sibling support. Duplicate counting, post-result strata, rounded decision values, weighting, pooling, or threshold changes cannot turn a failure into a pass.
66. Calibration truth is the frozen D-092 task-utility rubric, never score or surface-similarity agreement. The held-out reviewer cannot see rank numbers, retrieval/calibration identity, internal features/scores, bands, thresholds, or gate outcomes; redundancy context is bounded to earlier canonical target views. After reveal, grades/reasons and rubric/view-builder identities are immutable, source-bearing review material remains isolated from production, and only digest/count/decision manifests may enter release provenance.
67. Single-reviewer authority requires D-093's preregistered pilot and hidden-repeat gates before precision is revealed. Repeat presentations are blinded, shuffled, non-adjacent, deterministic/stratified, and never counted twice; an undefined statistic, missed kappa/agreement threshold, or undersized repeat set fails closed. Disagreement can only lower utility, failed held-out evidence is never reused as fresh, and model-generated judgments remain diagnostic artifacts with zero gate authority.
68. Every emitted non-exploratory band requires the exact D-094 global and five marginal band-specific support records derived from validated runtime metadata. Unknown language maps only to `generic`; filter, workspace, base-size, and rank cells cannot be caller-forged as calibration inputs. A missing/failed cell can only lower the affected hit's band, and diagnostic cross-products can neither grant nor revoke authority.
69. Calibration pilot/fit/held-out boundaries are disjoint by repository family and semantic task/template family, not path, revision, or individual target. Held-out material has no tuning/control path, and any family overlap or post-freeze membership/seed change invalidates the run. Each Wilson population admits at most one label-blind hash-selected target per query; nonselected correlated hits and hidden repeat copies grant zero additional support.
70. Only license-validated pinned real public repositories and frozen original human tasks may fit or gate production calibration. Synthetic/generated/copied/contrived material and model judgments are structurally diagnostic-only. Source-bearing corpus data stays in isolated bounded-retention evaluation storage and cannot enter Git, distributable artifacts, release assets, production state, logs, or provenance; retained manifests are bounded, source-free, origin/license/commit aware, and digest-verifiable.
71. Calibration license admission is exact-allowlist and fail-closed. Every parsed SPDX leaf and independently licensed eligible subtree must satisfy D-097, with no exception, custom reference, prose inference, permissive-branch shortcut, network-time mutation, or ambiguous-coverage override. License/nested-coverage digests bind the admitted scope; exclusion happens before tasks/targets, and changed or unresolved coverage invalidates authority.
72. Evaluation retention deadlines are exact, non-extending, and enforced before content reads. Physical cleanup is manifest-driven and contained to one validated isolated run workspace; it can never target an original repository, production Application Support state, Git, a broad/globbed path, or another run. CI/local cleanup requires no daemon and preserves only the explicitly source-free provenance/decision manifest.

## 9. Agent-value evaluation specification

### 9.1 Evaluation question

Does an agent with Dolphin complete representative code-discovery and code-change tasks more successfully or efficiently than the same agent using built-in filesystem tools alone?

### 9.2 Test design

For each scenario, run matched trials with:

- **Control:** built-in filename search, exact text search, and file reads;
- **Treatment:** the same tools plus Dolphin, with normal Dolphin server instructions and no forced per-task tool call.

Use fixed repository revisions, task prompts, model configuration, context limits, and maximum attempts. Record tool traces and judge outcomes independently of whether Dolphin was called.

Scenario categories must include:

- concept-to-implementation discovery;
- cross-file behavior tracing;
- architecture/component identification;
- analogous-pattern discovery;
- multi-repository discovery;
- exact-symbol tasks where Dolphin should correctly defer to built-in tools;
- stale-index recovery and explicit repository enrollment;
- first-index in-progress behavior where the agent receives no partial hits and correctly continues with built-in tools or operation status;
- catastrophic-preflight behavior where the agent receives typed human escalation, does not attempt a bypass, continues safely with built-in tools, and resumes after an independently completed exact-scope approval;
- query-time provider degradation covering cached semantic retrieval, transient lexical/structural fallback, and hard credential failure;
- concurrent agents operating in sibling worktrees with divergent code and dirty changes;
- language-specific structural discovery across every first-class family, including trait/impl and module/re-export tasks in a multi-crate Rust workspace;
- creation and registration of a new branch/worktree where only its delta should require embedding;
- result-page use across hybrid and lexical/structural modes where global ranks remain stable, relevance bands guide inspection without being treated as correctness probabilities, and unsupported calibration yields only `exploratory`;
- receipt-authorized cleanup of a workspace registration, including correct pre-request receipt retention/use, matching lost-response retry, refusal without the bound receipt, and proof that Git/source state remains unchanged;
- parent/submodule and independent nested-repository discovery where child contents remain excluded until a separate explicit enrollment and multi-workspace scope.

### 9.3 Required metrics

- **Primary:** task success and correctness, scored from task outputs by an evaluator blind to treatment assignment.
- Time to first relevant file and first relevant symbol.
- Number of tool calls and files opened.
- Input/output tokens consumed by discovery.
- Recall of a human-curated relevant-file set.
- Irrelevant-result/context rate.
- Per-mode relevance-band precision, coverage, ordering consistency, label stability, and agent reliance/error rate.
- Dolphin adoption rate when it is useful, used diagnostically rather than as a release target.
- Correct deferral rate when built-in tools are more appropriate.
- Ordinary setup/recovery success without human intervention, plus correct human escalation for the deliberately exceptional catastrophic fuse.

### 9.4 Release-gate hierarchy

1. Treatment must materially improve task correctness on discovery-heavy scenarios compared with the control.
2. Treatment must not cause a meaningful correctness regression in any critical scenario category, including tasks where exact built-in search is preferable.
3. Ordinary setup, enrollment, freshness, and recovery scenarios must meet their reliability thresholds without human intervention; catastrophic-fuse trials pass by escalating correctly and resuming after the modeled human approval, never by bypassing it.
4. Latency, tool calls, and context consumption must remain within agreed regression budgets. Efficiency gains cannot compensate for worse correctness.
5. Dolphin adoption and deferral rates explain agent behavior but cannot pass or fail the release by themselves.

The `rules-v1` ablation is subordinate to this hierarchy. Before viewing candidate results, preregister a material correctness/follow-up threshold, critical-category non-regression bound, context-cost guardrail, trial count, and uncertainty rule. Retain intent only if it clears that complete gate; an inconclusive result counts as failure and triggers the clean removal path in D-081.

The D-090 relevance-band gate is independently subordinate to task correctness. Split judgments before fitting, freeze dataset/split/profile/code digests, and preregister per-band precision, uncertainty, support, stability, and distribution rules before candidate held-out results. Evaluate each exact final mode/policy once on the untouched gate set. Failure or insufficient evidence disables only that band and cannot be repaired by relabeling the same held-out set, weakening a target, pooling an unsupported mode, or tuning against end-to-end agent outcomes; a new attempt requires a new preregistered artifact and fresh held-out judgments.

Exact numerical thresholds and trial counts must be fixed after the 0.2.x baseline is measured and before 0.3.0 retrieval tuning begins. They must not be changed after viewing candidate results without documenting the reason and rerunning the baseline.

### 9.5 Heavy-reranker ablation

Run a pre-registered paired comparison between the best lightweight candidate and that same candidate plus the fixed cross-encoder. Report primary task correctness by scenario category and overall, uncertainty/variance, individual regressions, and the install/runtime guardrails from Section 5.20. The signed release decision is binary: `removed` or `standard`; `optional`, environment-dependent, and undecided-at-RC are failing outcomes.

### 9.6 Knowledge-graph ablation

Run the same style of pre-registered paired comparison between the best non-graph candidate and that candidate plus one fixed graph policy. Grade end-to-end task correctness and audit returned graph relationships for false, stale, cross-workspace, cross-submodule, and cross-independent-nested-repository edges. Report the indexing, storage, memory, query, context, and maintenance guardrails from Section 5.21. The signed decision is likewise only `removed` or `standard`.

### 9.7 Relevance-band calibration gate

For each exact final retrieval-mode/ranking-policy profile, freeze the rubric/examples, canonical target-view builder, provisional thresholds, and critical-stratum membership rules before reading held-out labels. Count one final outcome per unique `(query_judgment_id, target_id)`; hidden repeat presentations never increase sample size. The high gate evaluates only provisional `high` predictions and counts only `direct`. The medium gate evaluates the cumulative provisional `high` plus `medium` population and counts `direct` or `supporting`. Apply the same computation to every preregistered stratum without pooling failures into the global population.

```python
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, sqrt
from typing import Literal


ONE_SIDED_95_Z = 1.6448536269514722
JudgmentGrade = Literal["direct", "supporting", "not_useful"]
GateBand = Literal["high", "medium"]
GRADE_INDEX: dict[JudgmentGrade, int] = {
    "not_useful": 0,
    "supporting": 1,
    "direct": 2,
}
GATE_SAMPLE_DOMAIN = b"dolphin/relevance-gate/sample/v1\0"


@dataclass(frozen=True)
class GateCandidate:
    query_judgment_id: str
    target_id: str


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def gate_sample_key(candidate: GateCandidate, *, population_id: str, seed: bytes) -> bytes:
    return hashlib.sha256(
        GATE_SAMPLE_DOMAIN
        + len(seed).to_bytes(2, "big")
        + seed
        + _frame(population_id)
        + _frame(candidate.query_judgment_id)
        + _frame(candidate.target_id)
    ).digest()


def select_one_target_per_query(
    candidates: Sequence[GateCandidate], *, population_id: str, seed: bytes
) -> tuple[GateCandidate, ...]:
    grouped: dict[str, list[GateCandidate]] = {}
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        identity = (candidate.query_judgment_id, candidate.target_id)
        if identity in seen:
            raise ValueError("duplicate gate candidate")
        seen.add(identity)
        grouped.setdefault(candidate.query_judgment_id, []).append(candidate)
    selected = [
        min(
            group,
            key=lambda item: gate_sample_key(item, population_id=population_id, seed=seed),
        )
        for group in grouped.values()
    ]
    return tuple(sorted(selected, key=lambda item: (item.query_judgment_id, item.target_id)))


def conservative_final_grade(first: JudgmentGrade, second: JudgmentGrade) -> JudgmentGrade:
    return min((first, second), key=GRADE_INDEX.__getitem__)


def exact_grade_agreement(first: Sequence[JudgmentGrade], second: Sequence[JudgmentGrade]) -> float:
    if not first or len(first) != len(second):
        raise ValueError("grade passes must have equal nonzero length")
    return sum(left == right for left, right in zip(first, second, strict=True)) / len(first)


def quadratic_weighted_kappa(
    first: Sequence[JudgmentGrade], second: Sequence[JudgmentGrade]
) -> float | None:
    if not first or len(first) != len(second):
        raise ValueError("grade passes must have equal nonzero length")
    size = len(GRADE_INDEX)
    observed = [[0 for _ in range(size)] for _ in range(size)]
    rows = [0 for _ in range(size)]
    columns = [0 for _ in range(size)]
    for left, right in zip(first, second, strict=True):
        row = GRADE_INDEX[left]
        column = GRADE_INDEX[right]
        observed[row][column] += 1
        rows[row] += 1
        columns[column] += 1

    total = len(first)
    divisor = float((size - 1) ** 2)
    observed_disagreement = sum(
        ((row - column) ** 2 / divisor) * observed[row][column]
        for row in range(size)
        for column in range(size)
    ) / total
    expected_disagreement = sum(
        ((row - column) ** 2 / divisor) * rows[row] * columns[column]
        for row in range(size)
        for column in range(size)
    ) / (total * total)
    if expected_disagreement == 0.0:
        return None
    return 1.0 - observed_disagreement / expected_disagreement


def repeatability_passes(first: Sequence[JudgmentGrade], second: Sequence[JudgmentGrade]) -> bool:
    kappa = quadratic_weighted_kappa(first, second)
    return (
        kappa is not None
        and kappa >= 0.70
        and exact_grade_agreement(first, second) >= 0.80
    )


def hidden_repeat_count(unique_pairs: int) -> int:
    if unique_pairs < 30:
        raise ValueError("held-out set cannot supply the minimum hidden repeats")
    return max(30, ceil(0.20 * unique_pairs))


def grade_is_success(grade: JudgmentGrade, *, band: GateBand) -> bool:
    if band == "high":
        return grade == "direct"
    return grade in {"direct", "supporting"}


def wilson_lower_bound(successes: int, total: int) -> float:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("invalid binomial counts")
    proportion = successes / total
    z2 = ONE_SIDED_95_Z**2
    denominator = 1.0 + z2 / total
    center = proportion + z2 / (2.0 * total)
    margin = ONE_SIDED_95_Z * sqrt(
        proportion * (1.0 - proportion) / total + z2 / (4.0 * total**2)
    )
    return (center - margin) / denominator


def passes_gate(
    *, successes: int, total: int, minimum_support: int, minimum_lower_bound: float
) -> bool:
    return total >= minimum_support and wilson_lower_bound(successes, total) >= minimum_lower_bound
```

The pilot contains deliberately diverse non-held-out rubric examples and uses two independently seeded permutations with opaque presentation IDs at least seven full days apart. `repeatability_passes` is evaluated before held-out presentation generation. A degenerate pilot with zero expected disagreement returns `None` and fails even at 100% exact agreement because it does not demonstrate discrimination among grades.

Held-out repeat selection uses a frozen deterministic seed and stratifies across mode/policy, provisional band population, and every declared critical dimension as far as integer counts permit. Repeats receive unrelated opaque presentation IDs, are non-adjacent by construction, and are indistinguishable from ordinary work. The repeatability gate is computed before any precision result is disclosed. Each repeated pair then finalizes through `conservative_final_grade` and appears once in every support/precision calculation. A held-out repeatability failure invalidates all band decisions from that run; the already viewed evidence cannot be recycled as a fresh held-out set.

The D-094 stratum manifest contains exactly five marginal dimensions and their closed cells: public hit language (`python`, `javascript`, `typescript`, `svelte`, `sql`, `markdown`, `rust`, `generic`), unpromoted base scope-size profile (`small`, `medium`, `large`, `massive`), workspace breadth (`one`, `multiple`), filter shape (`none`, `path`, `language`, `both`), and one-based global-rank bucket (`1-3`, `4-10`, `11-50`, `51-500`). A path filter means nonempty `paths` or `exclude_paths`; a language filter means nonempty `languages`. Each provisional band population is evaluated globally and once within each cell containing it.

The release artifact stores separate high and cumulative-medium passing-cell sets. Runtime emission requires membership in all five applicable sets after the global band gate. A failed high cell does not contaminate medium evidence; the hit falls through and is tested against the independently validated cumulative-medium cell sets. Cross-product tables are emitted only as bounded diagnostics and are ignored by artifact generation, preventing either a combinatorial support requirement or post-hoc subgroup veto/rescue.

The split manifest assigns stable repository-family IDs and semantic task/query-template-family IDs to exactly one partition before any candidate tuning. All Git/worktree/fixture derivatives inherit their source family. Paraphrases and structural task variants inherit their template family. The validator computes both dimensions independently, rejects any pilot/fit/held-out overlap, and rejects a held-out multi-repository query if even one referenced family is non-held-out. Evaluation orchestration exposes held-out material only to the frozen runner and reviewer-presentation builder, never to tuning commands.

For each `(mode_policy_profile, band_population, global_or_cell_key)` population, call `select_one_target_per_query` before labels or hidden-repeat insertion. The frozen 256-bit sampling seed and population ID are manifest fields. The returned selection alone supplies D-091 successes/support; all other targets may be summarized only in clearly diagnostic tables. Hidden repeats are selected from the union of authority-bearing pairs, then deduplicated back to those same stable pair IDs before every population count. Any split/member/seed/candidate change produces a new digest and requires a fresh protected run.

The release evaluator uses `(50, 0.85)` for profile-level high, `(75, 0.65)` for profile-level medium-or-higher, `(20, 0.75)` for stratum-level high, and `(20, 0.55)` for stratum-level medium-or-higher. Comparisons use the full binary64 result; reports may round only a separate display field. The immutable validation manifest records code/version/rubric/view-builder digests, profile and provisional-threshold identity, held-out dataset/split digest, unique counts, successes, exact `float.hex()` bound, every stratum result, and the enabled-band decision. Any missing manifest field, duplicate judged pair, changed code/data/profile/rubric/view builder, or non-finite result fails closed.

The held-out judgment record stores only stable IDs/digests, the closed grade, one closed reason, repeatability/finalization metadata, and stratum labels in the isolated evaluation artifact. It never enters the production store. A `redundant` outcome references the digest of one adequate earlier target shown to the reviewer; the reviewer never sees numeric rank or any score/band signal. Rubric examples include hard lexical false friends, conceptually relevant but non-actionable context, duplicated implementations, direct definitions, call sites, tests, and cross-file supporting evidence for every first-class language.

### 9.8 Calibration corpus provenance and isolation

Authority-bearing repository and task manifests are source-free, canonical, and frozen before candidate retrieval. The implementation may use equivalent strict models, but must preserve this boundary:

```python
from dataclasses import dataclass
from typing import Literal


CalibrationPartition = Literal["fit", "held_out"]
CALIBRATION_LICENSE_ALLOWLIST = frozenset(
    {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib"}
)


def license_symbols_are_allowed(*, symbols: frozenset[str], has_exception: bool) -> bool:
    return (
        bool(symbols)
        and not has_exception
        and symbols <= CALIBRATION_LICENSE_ALLOWLIST
    )


@dataclass(frozen=True)
class CalibrationRepositoryManifest:
    family_id: str
    public_origin: str
    commit_sha: str
    source_tree_digest: str
    normalized_license_expression: str
    license_file_digest: str
    nested_license_coverage_digest: str
    partition: CalibrationPartition


@dataclass(frozen=True)
class CalibrationTaskManifest:
    task_id: str
    task_family_id: str
    repository_family_ids: tuple[str, ...]
    grounded_revision_digest: str
    task_text_digest: str
    author_kind: Literal["human"]
    partition: CalibrationPartition
```

Validation resolves every public origin and license during an explicit evaluation-preparation step, pins the commit and complete eligible-tree digest, and then runs the frozen evaluation without repository updates or mutable branch references. A standards-conforming SPDX-expression parser supplies the normalized expression, leaf-symbol set, and exception presence to `license_symbols_are_allowed`; Dolphin does not infer SPDX identifiers from license prose. Repository family—not URL spelling—controls D-095 grouping; mirrors, forks, vendored/copy-derived fixtures, and shared-history worktrees cannot be split across partitions. The Dolphin repository family is rejected from held-out authority.

The preparation scanner inventories bounded root/nested `LICENSE*`/`COPYING*` notices and package-license declarations without executing repository code. Every eligible nested coverage region is either bound to an independently passing expression/digest or removed by the frozen evaluation eligibility manifest before task/target creation. Unknown, conflicting, missing, or changed coverage rejects the authority-bearing repository/task. The nested coverage manifest is canonicalized into `nested_license_coverage_digest` and reverified against the pinned tree before every fit/gate run.

An authority-bearing task must be authored by the human reviewer before retrieval, name its grounded revision digest, and describe realistic discovery/change intent without copying a known answer into the query. Generated, model-rewritten, mechanically paraphrased, or synthetic tasks have a distinct diagnostic manifest whose schema cannot set `partition` to `fit` or `held_out`. Likewise, diagnostic judgments and targets are structurally excluded from calibration fitting and `passes_gate` inputs.

The evaluation workspace is separate from Dolphin production state and release staging. Each run fixes `finalized_at`, terminal validity/outcome, logical deadline, and optional `released_at` in a private retention record. Invalid/failed runs use `finalized_at + 7 days`; the successful authority run starts with `finalized_at + 90 days` and compare-and-set shortens that deadline to `min(existing_deadline, released_at + 30 days)` when release occurs. Reads check logical expiry before opening content, and access never refreshes a deadline.

CI teardown deletes only its exact run workspace. Local evaluation admission first reclaims logically expired run directories through a contained manifest-driven plan; a development-only cleanup command applies the same plan and may explicitly remove an unexpired run sooner. There is no daemon, timer, MCP tool, installed end-user cleanup command, broad path/glob deletion, or authority to touch original repositories. Cleanup removes source checkouts, canonical target views, full tasks, raw features/scores, judgments, and model diagnostics while preserving the bounded source-free provenance/decision manifest. Build, wheel-content, plugin/skill, Git-tree, and release-asset inspections fail if source-bearing corpus material is present.

## 10. Engineering workstreams

### 10.1 Repository and architecture cleanup

- Remove tracked test backups, generated coverage reports, and generated JS declaration/source-map artifacts that are build outputs.
- Remove the `mcp-bridge/` and `shared/` TypeScript runtime after every retained contract and outcome test has a Python replacement.
- Remove every packaged repository-enrollment/indexing CLI surface, including `dolphin index`, `kb ingest`/`kb.ingest.cli`, and any `dolphin repo add`/`import` alias; retain ingestion behavior only behind internal application services exposed publicly by MCP `repo_add`.
- Consolidate the retained setup, diagnostic, exact-operation, approval, cleanup, and maintenance CLI commands behind one command registry.
- Extract reusable behavior from `kb/api/` into transport-independent application services, then remove the FastAPI application, routes, middleware, task queue, and server entry point.
- Break up oversized storage, search, and ingestion modules along transactional/domain boundaries.
- Replace direct/raw cross-layer SQLite and LanceDB access with the `MetadataStore`, `KeywordStore`, `VectorStore`, and `GenerationCoordinator` protocols; keep backend types inside `kb/store/`.
- Remove REST-only dependencies, configuration, authentication middleware, CORS, host/port settings, and HTTP client code after verifying they have no remaining consumers.
- Convert endpoint tests into application-service and MCP contract tests; delete tests whose only purpose was preserving HTTP behavior.
- Remove dead compatibility aliases and unsupported configuration paths.
- Replace the broad legacy global/repository configuration merger with two strict non-merging schemas: human-owned Application Support search output budgets and worktree-owned `.dolphin/config.toml` indexing include/exclude policy. Remove every other global/repository key for embeddings, retrieval/ranking, storage, runtime, credentials, telemetry, and retired behavior.
- Replace stale version literals with one generated/read source of truth.
- Update existing architecture, testing, publishing, README, MCP README, changelogs, and plugin metadata.

### 10.2 Runtime lifecycle

- Replace the TypeScript/Bun MCP bridge with a Python MCP entry point.
- Route MCP tools directly to Python application services without localhost HTTP.
- Introduce one typed `StorageLayout` rooted at `~/Library/Application Support/Dolphin/` and inject it into every stateful service.
- Remove production reads/writes of legacy `~/.dolphin/` global state without adding migration behavior.
- Implement per-store ownership locking and interrupted-operation reconciliation.
- Initialize SQLite as the visibility authority with foreign keys, WAL, bounded busy handling, and integrity checks; connect LanceDB only to the validated local vector directory and validate both backend schemas/contracts before claiming work.
- Enforce current-user ownership, no-follow containment, and exact private modes across every Application Support state class and backend-created descendant; add no storage-encryption/key path.
- Implement authoritative volume/state-class measurement, conservative peak-write reservation, one renewable GC maintenance lease, bounded low-priority collection, and durable `disk_pressure` pause/resume without a daemon.
- Implement runtime-instance records, operation/watcher leases, normalized durable checkpoints, stale-owner detection using PID plus process-start identity, and compatible peer takeover.
- Implement bounded startup reconciliation and the five-second drain/checkpoint/release shutdown path for EOF and supported signals.
- Add foreground `dolphin operation run <operation-id>` through the same service layer; install no LaunchAgent, daemon, detached helper, or always-on watcher.
- Define log locations, rotation, and structured diagnostic events.
- Ensure MCP startup remains responsive and protocol-safe.
- Add `doctor` checks that exercise the exact production startup path.

### 10.3 Repository lifecycle tools

- Add typed repository-family, workspace, generation, lease, and operation models.
- Implement empty-input bounded `status` separately from cursor-only fixed-page `repo_list`; centralize actionable-registration ordering/revision and forgotten-state redaction.
- Implement idempotent `repo_add` and expose its registration-creation transition publicly only through the Python MCP adapter.
- Implement receipt-scoped `repo_forget`, receipt issuance/consumption, registration epochs, active-use coordination, immediate logical removal, and human CLI cleanup through one application service without registration provenance/classes.
- Make `RepoAddInput` exactly absolute `path` plus caller-supplied `cleanup_receipt`; use only the path for identity, derive deterministic display labels, and disambiguate presentation collisions with stable short IDs.
- Implement Git common-directory/worktree discovery without collapsing sibling roots.
- Implement one repository-boundary service that classifies gitlinks and independent nested Git markers, produces bounded status/remediation summaries, enforces deepest-worktree resolution, and supplies non-overridable exclusions to every indexing/freshness/search path.
- Implement reusable clean commit generations plus workspace overlays.
- Implement private immutable content-addressed chunk-text artifacts, generation manifests, and model-aware embedding reuse.
- Enforce the fixed `text-embedding-3-small` contract at embedding, cache, generation, vector-store, and query boundaries.
- Implement compatible-base selection and Git-diff-derived generation construction.
- Assign stable random reference-target IDs during staging and immutable publication IDs at commit; serialize workspace/publication/target identity without a search-time write.
- Implement exact-workspace, non-blocking `repo_sync` with current/no-op detection, target-fingerprint deduplication, and internally selected minimal correctness-preserving plans.
- Implement debounced continuous watching plus the cheap pre-search drift check.
- Implement bounded pre-search catch-up and structured stale-search metadata.
- Implement non-blocking operation submission plus exact-ID immediate `operation_status`, non-extending 30-day terminal summaries, and reachability-independent compaction.
- Keep first-index staging inaccessible to all readers and atomically publish only a complete generation; expose durable phase/counter progress without speculative ETAs.
- Implement the stage/vector-verify/SQLite-pointer-swap publication protocol and its crash-reconciliation matrix; make snapshot-keyed cache invalidation idempotent.
- Surface branch, commit, dirty state, last successful index, pending drift, embedding model, and failure state.
- Surface generation origin plus actual parsed/reused file, chunk, cache-hit, cache-miss, and submitted-token counters.
- Add agent-oriented remediation and next actions.
- Persist approvable aggregate preflights and one-shot scope approvals; implement the interactive `dolphin repo approve-scope --preflight-id` flow and atomic operation requeue through the shared service layer.
- Implement missing-workspace detection, full-window reactivation, policy-versioned protection/reclaim tiers, deterministic victim ordering, and crash-safe mark/recheck/delete/finalize GC across SQLite, LanceDB, and artifact state.
- Implement one versioned eligibility engine shared by initial indexing, delta sync, watcher events, preflight estimates, and diagnostics.
- Implement the bounded no-follow `.dolphin/config.toml` loader, strict schema/version validation, Git-wildmatch pattern normalization, precedence rules, canonical digest, and read-only diagnostics.
- Make policy changes update file membership incrementally and atomically while reusing unchanged chunks and exact embedding inputs.

### 10.4 Language intelligence

- Replace configurable/internal language aliases with the canonical public registry in Section 5.14 while preserving precise internal parser metadata.
- Standardize the existing Python, JavaScript/TypeScript, Svelte, SQL, and Markdown chunkers on the shared chunk/result contract.
- Add an embedded parser-based Rust chunker and conservative relationship metadata without introducing a runtime Rust toolchain dependency; build Rust graph edges only as part of the D-040 candidate and delete them if the gate fails.
- Make parser identity, grammar/package version, chunker version, and degraded fallback mode explicit in pipeline/cache keys and diagnostics.
- Add first-class-language fixture corpora and outcome-oriented retrieval scenarios, including a representative multi-crate Rust workspace.
- Fail the release for a material correctness regression in any promised first-class language; do not hide parser failures behind successful generic indexing counts.

### 10.5 Search and retrieval UX

- Replace the existing search schema with the task-level contract in Section 7.7 and reject low-level retrieval knobs.
- Generate Section 7.7's nested strict-compatible query/continue `anyOf` from one Python model/schema source; verify OpenAI strict ingestion and identical MCP/Codex/Claude schema rather than maintaining client-specific forms.
- Add a strict no-follow loader for human-owned `StorageLayout.config_file`, keep repository policy separate, and permit candidate TOMLs only behind explicit development/evaluation entry points with isolated storage.
- Add only the create-only `config init` plus observational `config validate`/`config show` human CLI adapters over the shared typed loader/summary; give each only the serialization-only `--json` option.
- Implement cheap per-search fingerprinting, stable bounded reads, immutable call-pinned policies, durable semantic last-known-good snapshots, compare-and-set multi-runtime acceptance/deactivation, and side-effect-free status/doctor inspection.
- Implement one versioned TOML-backed adaptive output-budget policy that resolves omitted result/context budgets from published scope statistics, exposes the applied profile/digest, and validates explicit requests against effective caps without clamping.
- Implement `IntentClassifier` as a narrow internal boundary and ship only deterministic `rules-v1`: fixed normalization, finite ordered phrase groups, closed fallback, no model/source/config access, and no effect outside output-budget promotion.
- Implement a versioned adaptive retrieval policy optimized by the agent-value evaluation suite.
- Replace agent-visible scores with stable one-based global rank and `high`/`medium`/`exploratory`; implement the tiny pure-Python monotonic calibrator, exact mode/policy profiles, independently gated bands, validation/distribution identity, conservative unsupported fallback, and immediate raw-score disposal.
- Require a pinned SQLite `PublishedSnapshot` for every FTS5 and vector branch, prohibit unscoped LanceDB queries, and keep reader leases alive through fusion and result materialization.
- Return structured content rather than JSON embedded inside Markdown text where MCP supports it.
- Make citations stable and directly followable.
- Emit `dolphin://ref/<stable-id>` from the versioned opaque codec while keeping readable paths/ranges as separate structured fields; resolve only retained exact membership.
- Include validated absolute paths by default so agents can use native file tools without another Dolphin round trip.
- Implement current-only `open_ref` with issued-reference validation, stable no-follow reads, exact alignment, typed drift/errors, and no mode or generic file-read parameters.
- Calibrate size/intent-band result and snippet defaults/caps for task correctness first and context efficiency second; retain 8/4,000 only as the initial experimental baseline.
- Implement adaptive snippet selection over one aggregate token budget, using indexed-generation content and diversity-aware allocation.
- Bundle and verify the fixed `cl100k_base-v1` accounting asset; count exact final snippet strings without registry download/fallback; expose per-snippet and aggregate counts; and reject any post-allocation/serialization mismatch or overrun.
- Implement `hybrid-v1` as the fixed seed-then-greedy complete-window allocator with overlap-based seed deduplication, closed action tiers/reasons, stable tie-breaking, null-snippet behavior, and no public/configurable weights or strategy.
- Implement per-page search budgeting over one pinned deduplicated target sequence; revalidate every continuation binding before materialization, expose page index/next cursor, and give each successful page the same result ceiling plus a fresh identical snippet ceiling.
- Implement source-free SQLite continuation sessions, digest-only 256-bit cursor positions, deterministic domain-separated successor derivation, idempotent page replay, exact non-extending 30-minute logical expiry, cross-runtime resume, and matching publication/target/artifact reachability.
- Materialize at most 500 unique ranked target/focus pointers on the first page, expose retained/horizon-hit metadata, and make every continuation structurally unable to invoke query embedding or retrieval/ranking expansion.
- Add total `available`/`exhausted`/`unavailable` continuation metadata and one bounded optional-state transaction; preserve complete pages on persistence failure, disclose only proven cursors, and give safe built-in/reference/fresh-query remediation without rerunning work automatically.
- Materialize every snippet through snapshot-authorized verified chunk artifacts; never substitute a current worktree read for missing indexed text.
- Make freshness and incomplete-coverage states unmissable but concise.
- Gate search on complete-generation coverage, return typed `INDEX_BUILDING` instead of partial/empty hits, and reject incomplete multi-workspace coverage without silently dropping a workspace.
- Keep committed search and `open_ref` available under disk pressure while skipping optional cache/log writes; never run large synchronous GC from a read path.
- Add exact query-embedding cache lookup, centralized provider failure classification, bounded interactive retries, and lexical/structural fallback only for transient failures.
- Expose orthogonal freshness and execution-mode metadata; bind cursors to retrieval mode and invalidate continuation across mode changes.
- Keep cross-encoder code outside the production dependency path until its pre-registered agent-task ablation; then either delete it fully or make one fixed reranker part of the standard versioned ranking policy.
- Remove redundant retrieval tools.
- Keep cross-file graph construction/storage/enrichment outside the standard policy until its pre-registered agent-task ablation; then either remove the subsystem and graph-only dependencies completely or freeze one standard graph schema/extractor/retrieval policy.

### 10.6 Evaluation and local diagnostics

- Convert golden scenarios into reproducible agent-level control/treatment trials.
- Store run configuration and traces as build artifacts, not committed reports.
- Keep one redacted Python structured logger and a closed, low-cardinality in-process metrics registry for latency, indexing, failure, cache, watcher/lock, and retrieval-mode diagnostics.
- Record safe query-embedding cache-hit, live-call, transient-fallback, credential-failure, provider-category, retry, and retrieval-mode counts without raw queries, source, paths, provider payloads, or user-controlled labels.
- Permit source-free raw ranking features/scores only in explicit bounded development/evaluation artifacts; assert they never enter production results, state, caches, logs, metrics, or diagnostics.
- Implement the frozen task-utility rubric, canonical pinned target-view builder, blinded judgment records, closed audit reasons, unique query-target enforcement, and immutable held-out validation manifests entirely inside the isolated evaluation path.
- Implement the one-reviewer pilot/hidden-repeat harness with opaque IDs, independent deterministic shuffles, seven-day timestamp enforcement, stratified non-adjacent repeat placement, dependency-free exact agreement/quadratic-weighted kappa, conservative grade finalization, and no model-judge authority.
- Implement D-094's closed marginal-cell derivation/evaluation, separate high/medium passing-cell manifests, bounded diagnostic cross-tabs, and exact parity between evaluation keys and runtime `CalibrationContext` construction.
- Implement D-095's repository/task-family grouping validator, three-way disjoint manifest, held-out access boundary, domain-separated label-blind one-per-query population sampler, contamination failure, and diagnostic-only correlated-hit reporting.
- Implement D-096's real-repository/human-task authority manifests, pinned-origin/commit/tree/license validation, diagnostic-only synthetic/generated schema, isolated bounded-retention workspace, and distributable/Git/release leakage guard.
- Implement D-097's exact SPDX allowlist/expression-leaf validator, root/nested license-metadata inventory, pre-task subtree exclusion, canonical coverage manifest/digest, and fail-closed revalidation without executing repository code.
- Implement D-098's per-run retention record, seven/90-day deadlines, release-triggered 30-day shortening, pre-read logical expiry, contained CI/local reclamation, explicit earlier development cleanup, and source-free-manifest preservation without product/daemon exposure.
- Expose compact process/window snapshots through `status` and `doctor`; do not expose or export a time series.
- Report `application_encryption = none`, private-permission validity, and best-effort FileVault `on`/`off`/`unknown` through setup/`doctor` without privilege, mutation, or startup gating.
- Report pressure-policy version, safe volume/free/protected/reclaimable aggregates, paused operations, last bounded GC outcome, and deterministic human remediation without source paths or payloads.
- Implement private bounded log segmentation/retention under `StorageLayout` with concurrency, containment, and failure tests.
- Remove the Prometheus/OpenTelemetry/Grafana/Loki/Docker stack and prevent any production telemetry export, listener, or dashboard path from returning.
- Keep profiling and detailed traces explicit, development-only, and stored as uncommitted CI/build artifacts.
- Add release comparison output for baseline versus candidate.

### 10.7 Agent-integration generation

- Define one immutable Python `ToolSpec` registry containing exactly D-074's ordered eight tools, consumed by runtime registration, schema export, documentation generation, adapter generation, and contract tests.
- Define one typed agent-guidance specification whose blocks have stable IDs, ordering, criticality, examples, and applicable tool/error references.
- Generate MCP initialization instructions, Codex artifacts, Claude Code artifacts, shared documentation fragments, and integration fixtures deterministically.
- Keep client renderers thin and prohibit client-specific workflow or tool semantics outside the canonical contract.
- Commit distributable generated artifacts with a source digest and enforce `uv run python -m kb.integrations.generate --check` in CI.
- Parse generated artifacts back into normalized contracts and assert semantic parity, tool/schema parity, environment-variable parity, and release-version parity.
- Implement client-specific plan/apply/verify adapters behind `dolphin setup codex` and `dolphin setup claude-code`, preferring client-native configuration mechanisms.
- Implement `--dry-run`, `--json`, existing-entry ownership/conflict handling, optimistic concurrency, restricted rollback, manual fallback generation, and managed removal.
- Default setup/removal/diagnostics to user scope; support explicit exact-worktree project scope and diagnose client-specific global/project shadowing.
- Extend `dolphin doctor` with target-client configuration, absolute executable, adapter digest/version, environment-name forwarding, and MCP startup checks.
- Maintain shared client smoke scenarios with adapter-specific drivers and require clean native Apple Silicon macOS 14+ RC runs through both Codex and Claude Code on every supported major.

### 10.8 Unified release engineering

- Use Python project metadata as the canonical version source and validate plugin/skill metadata against it.
- Replace independent Python/npm publishing with one Python 0.3.0 release workflow plus coordinated plugin/skill metadata from the same commit.
- Require release builds and complete tests before any publish job receives authorization.
- Publish from the protected `main` release commit only.
- Publish one Python distribution containing Dolphin core, CLI, and MCP, with plugin/skill metadata from the same release commit.
- Generate checksums/provenance where supported.
- Exercise a clean-machine native Apple Silicon installation smoke test on the latest patch of every supported macOS major before publishing.

## 11. Step-by-step implementation checklist

### Phase 0 — settle design and establish baselines

- [x] Resolve all open decisions in Section 13.
- [ ] Validate `uv tool install --python 3.13 pb-dolphin`, automatic managed-Python download when 3.13 is absent, the installed `dolphin mcp` launch path, explicit `uv tool upgrade pb-dolphin`, and exact-version `uvx --python 3.13` trial behavior on clean native Apple Silicon accounts running the latest patch of every supported macOS major.
- [ ] Validate current supported configuration/install/inspection commands and formats for Codex and Claude Code; record version gates and safe manual fallbacks.
- [ ] Capture current install time, first-index time, search latency, and evaluation baseline.
- [ ] Measure SQLite/WAL, LanceDB build/index, chunk-text, embedding-cache, staging, crash-recovery, and multi-worktree peak disk amplification on representative small, large, and very large repositories; validate D-054's fixed constants before implementation freeze and treat any proposed change as a new recorded product decision.
- [ ] Select the exact LanceDB release only after native Apple Silicon macOS 14+ CPython 3.13 wheel, correctness/recall, concurrent read, serialized write, crash/reopen, index, license/vulnerability, disk-use, and uninstall qualification on every supported major; treat the current lockfile version only as a baseline candidate.
- [ ] Define 0.3.0 release thresholds for agent value and reliability.
- [ ] Pre-register the cross-encoder material-correctness threshold, non-regression rules, matched-trial design, lighter-tuning budget, install/runtime guardrails, and RC decision deadline.
- [ ] Pre-register the knowledge-graph material-correctness threshold, false/stale/cross-boundary edge rules, matched-trial design, non-graph tuning budget, resource guardrails, and RC decision deadline.
- [ ] Pre-register D-081's `rules-v1` correctness/follow-up threshold, critical-category non-regression bound, context-cost guardrail, matched scope-only ablation, trial count, uncertainty rule, and clean-removal deadline.
- [ ] Pre-register D-090's required stability strata, operational out-of-distribution rule, fit/held-out split, immutable artifact digests, and fresh-data rule before fitting or viewing candidate gate results; copy D-091's fixed per-band Wilson/support constants verbatim rather than choosing them from the baseline.
- [ ] Freeze D-092's grade/reason rubric, difficult positive/negative/redundancy examples for every first-class language, canonical target/earlier-evidence view builder, information-blinding boundary, and rubric/view-builder digests before splitting or grading calibration data.
- [ ] Pre-register D-093's pilot corpus, two shuffle seeds, seven-day interval, kappa/agreement implementation and gates, held-out repeat seed/stratification/non-adjacency algorithm, lower-utility finalization, invalidation/fresh-evidence rule, and prohibition on model-judge authority.
- [ ] Freeze D-094's five dimensions/cells, source-free runtime derivation, marginal-only authority, separate per-band support sets, cross-product diagnostic boundary, and canonical cell-key ordering/digest before held-out sampling.
- [ ] Freeze D-095's repository-family and semantic task/template-family identities, derivative inheritance, pilot/fit/held-out assignments, multi-repository rule, 256-bit population-sampling seed, domain/codec, and held-out access boundary before tuning.
- [ ] Freeze D-096's corpus authority/provenance schema, permissive-license validation policy, public-origin/commit/tree identity, original-human-task rule, diagnostic-only source classes, private workspace, retention boundary, and source-free release-manifest fields.
- [ ] Freeze D-097's six SPDX identifiers, all-leaves/no-exception expression rule, root/nested discovery inputs, independent-subtree coverage/exclusion behavior, canonical digest, and no-prose-inference/no-override boundary.
- [ ] Freeze D-098's terminal outcome/timestamps, exact deadline formula, compare-and-set release shortening, logical-read denial, CI teardown/local admission/explicit cleanup triggers, containment proof, and retained source-free manifest boundary.
- [x] Designate task correctness as the primary statistical comparison and efficiency metrics as regression guardrails.
- [ ] Inventory public surfaces and explicitly mark each keep, replace, or remove.
- [x] Confirm feature branches target `develop` and `develop` reaches protected `main` only through a release PR.

### Phase 1 — clean break and contract foundation

- [ ] Remove tracked backups, reports, and generated artifacts.
- [ ] Remove obsolete compatibility code and aliases.
- [ ] Delete `dolphin index`, `kb ingest`/`kb.ingest.cli`, every `dolphin repo add`/`import` spelling, their package entry points, completions, docs, and command tests; add a public-surface snapshot proving no equivalent enrollment alias remains.
- [ ] Choose and implement a single version source for all artifacts.
- [ ] Set `requires-python = ">=3.13,<3.14"`, retain only the CPython 3.13 packaging classifier, pin developer tooling to 3.13, regenerate the release lock for that runtime, and remove claims/tests for other Python versions.
- [ ] Define repository, operation, status, search-result, reference, and error schemas.
- [ ] Define `CleanupAuthority`, `RepoForgetInput`, `RepoForgetResult`, registration-epoch/receipt-digest records, the fixed 30-day cleanup-replay tombstone and co-expiring identity anchor with one non-extending deadline, and constant-shape `CLEANUP_NOT_AUTHORIZED` plus retryable `WORKSPACE_IN_USE` errors from Sections 5.34 and 7.27.
- [ ] Define `cleanup-intent-v1` with fixed 30-second TTL, five-second renewal, five-second drain budget, random intent/call ownership, operation-scoped cancellation IDs, compare-and-set transitions, logical expiry, and a schema that cannot store the raw receipt.
- [ ] Define `cleanup_pending` as an effective-state overlay, `CleanupPendingSummary`, `WorkspaceInUseDetails`, and `ReadLifecycle`; keep underlying registration state intact and make every blocked result typed, bounded, receipt/owner-free, and retryable.
- [ ] Define one compare-and-set `cleanup_abandoned_recovery` marker per workspace/epoch, its claim/clear transitions, deduplication key, watcher-baseline handshake, and new-operation linkage without any transition from cancelled back to queued.
- [ ] Freeze `RepoForgetInput` at exactly `workspace_id` plus opaque `cleanup_receipt`; reject every extra cleanup/cancellation/GC/source/worktree/timing/configuration field and remove any cleanup-specific physical-operation handle from results.
- [ ] Define `FilesystemObjectIdentity`, `WorktreeIdentityFacts`, and `ForgottenWorktreeIdentityAnchor`; normalize macOS device/inode/birth-time facts from no-follow descriptors and make exact repository-family/common-dir/worktree-gitdir equality the only restoration proof.
- [ ] Define `OpenRefResult`, exact-file/unchanged-range/relocated/unresolved alignment, issued-reference membership, current-only source labeling, fixed excerpt bounds, and all typed reference failures from Sections 5.29 and 7.22.
- [ ] Freeze `RepoSyncInput` at exactly `workspace_id` and define the `up_to_date`/`operation_created`/`operation_reused` result invariants from Section 7.29; reject every wait/full/force/strategy/provider/concurrency/tuning field.
- [ ] Define the Section 7.30 `StatusInput`, `StatusResult`, `RepoListInput`, and `RepoListResult` contracts; fix the page size at 25, forbid all listing knobs other than the opaque cursor, and add typed `CURSOR_INVALID`/`CURSOR_EXPIRED` outcomes.
- [ ] Define Section 7.31's exact `OperationStatusInput`/bounded `OperationStatusResult`, closed operation kinds/states/phases/pause reasons, 250–5,000 ms polling guidance, non-extending 30-day terminal deadline, forgotten-workspace redaction, and constant-shape `OPERATION_MISSING`; reject wait/stream/list/history/cancel/resume/retry/pagination fields.
- [ ] Define random workspace/publication/reference-target IDs, the versioned `dolphin://ref/<stable-id>` codec, strict parser limits, checksum semantics, membership resolution, expiration, and no-search-write contract from Sections 5.30 and 7.23.
- [ ] Remove caller-supplied repository/workspace names and name-conflict errors from MCP, service, persistence, examples, and tests; reject retired `name` input explicitly.
- [ ] Keep one registration schema with no creator/owner, human/agent, temporary/persistent, promotion, or transfer fields; model cleanup authority as a separate epoch-bound capability record only.
- [ ] Define canonical typed `ToolSpec`, agent-guidance, example, client-target, and generated-artifact models in Python.
- [ ] Encode `PUBLIC_MCP_TOOL_NAMES` and one canonical registry digest for exactly the ordered D-074 set; fail on missing/extra/duplicate/misordered specs or handlers and prohibit callable aliases/resources/prompts in the installed server.
- [ ] Freeze Section 7.7's exact required `request` envelope and nested closed `query`/`continue` `anyOf`; require every declared field, explicit null/empty-array query optionals, `additionalProperties: false` at every object, nullable budgets, absolute 50/20,000 ceilings, typed `SEARCH_BUDGET_EXCEEDED`, and typed `SearchBudget` metadata; implement Section 7.33's complete four-profile models/selector, canonical digest rules, and D-076 authority/precedence.
- [ ] Define Section 7.36's `cl100k_base-v1` asset/digest, exact independent-string accounting, complete-line window rules, per-snippet/aggregate metadata, final serialization assertion, and cache/cursor compatibility boundary.
- [ ] Define `hybrid-v1` window-candidate invariants, same-publication/path overlap rule, three-seed rank walk, action tiers, stable tie-breakers, closed reasons, allocation-version identity, and null-snippet semantics.
- [ ] Define Section 7.37's finite ranked-sequence digest, page index/offset, exact pinned publications/scope/modes/versions/budgets/relevance calibration, per-page accounting, next-cursor/exhaustion semantics, duplicate prohibition, and all-or-nothing continuation validation.
- [ ] Define D-086's source-free session/pointer/position schema, rank/band-only pointers, cursor prefix/entropy/digests/hash-chain derivation, compare-and-set successor issuance, deterministic replay, fixed deadline, monotonic live-process bound, logical reachability expiry, compaction, and raw-query/result-echo/score removal.
- [ ] Define D-087's exact 500-target post-ranking/deduplication horizon, canonical contiguous one-based ranks/sequence digest, normalized pointer-row storage, retained/horizon-hit execution metadata, final-page narrowing guidance, and separation from every output-budget authority.
- [ ] Define D-088's strict `SearchContinuation` state combinations, four unavailable reasons, proven-cursor publication point, bounded write attempt, uncertain-commit/orphan behavior, quality-metadata independence, and first-page versus same-cursor retry guidance.
- [ ] Define D-089's `SearchHit.rank`/`relevance`, `SearchExecution` calibration identity, pure-Python monotonic profile contract, exact mode/policy binding, canonical artifact validation, unsupported-to-`exploratory` fallback, transient-score boundary, and development/evaluation-only score artifact schema.
- [ ] Define D-090's independently enabled bands, fit/held-out judgment manifests, validation/distribution digests, preregistered gate result, conservative fallthrough, version invalidation, and structural prohibition on production/online/user-specific fitting or cross-profile threshold reuse.
- [ ] Define D-091's cumulative medium population, unique final-pair counting, exact one-sided Wilson implementation/constants, full-precision comparison, global/stratum gate records, and no-pooling/weighting/rounding invariants.
- [ ] Define D-092's isolated held-out judgment record, closed grade/reason enums, optional redundant-target digest, rubric/view-builder identity, immutable finalization, success mapping, and structural exclusion from every production schema/store/artifact.
- [ ] Define D-093's pilot-pass, opaque-presentation, hidden-repeat linkage, repeatability-result, conservative-finalization, invalid-run, and optional model-diagnostic artifact schemas without allowing duplicate support counts or production ingestion.
- [ ] Define D-094's typed `CalibrationContext`, closed cell-key codec, per-band supported-cell artifact, applicability/fallthrough algorithm, and evaluator/runtime parity contract without accepting calibration context from MCP or TOML.
- [ ] Define D-095's split/member/population/candidate/selection manifests, domain-separated hash framing, at-most-one-target-per-query invariant, authority-versus-diagnostic marker, contamination result, and immutable digest chain.
- [ ] Define D-096's strict repository/task/diagnostic manifests and isolation types so generated/synthetic/model-derived material cannot inhabit an authority-bearing partition or reach fit/gate APIs.
- [ ] Define D-097's strict normalized-expression/symbol/exception result, license-file and nested-coverage manifests, eligibility exclusion linkage, and typed authority-rejection reasons using an evaluation-only standards-conforming SPDX parser.
- [ ] Define D-098's private run-retention record and contained cleanup-plan/result schemas; keep them structurally absent from production state, public CLI, MCP, and release payloads.
- [ ] Define the Section 7.33 synchronous `IntentClassifier` boundary, exact `rules-v1` normalization/phrase precedence/fallback, classifier-version metadata, and proof that intent can influence only one-step output-budget promotion.
- [ ] Define Section 7.34's config file fingerprint, immutable effective policy, durable semantic last-known-good record/generation, `valid_user`/`absent_using_shipped`/invalid-fallback states, safe error codes, stable-read retry, acceptance/deactivation compare-and-set transitions, and non-mutating inspection result.
- [ ] Define Section 7.35's closed `ConfigCommandResult`, bounded safe validation detail, exact CLI grammar/exit outcomes, text/JSON parity, fixed path, private atomic no-replace installation contract, and side-effect boundaries.
- [ ] Implement deterministic adapter generation plus source digests and a no-diff `--check` mode.
- [ ] Define typed client setup plan/result/conflict/validation schemas without fields that can carry credential values.
- [ ] Define repository-family, workspace, clean-generation, workspace-overlay, artifact-cache, embedding-cache, writer-lock, and maintenance-lease schemas.
- [ ] Define runtime-owner, operation-lease, normalized checkpoint/completed-manifest, pause reason, resume count, and compare-and-set transition schemas.
- [ ] Define backend-neutral `MetadataStore`, `KeywordStore`, `VectorStore`, and `GenerationCoordinator` protocols plus published-snapshot/read-lease, staging/readiness, and verified-vector-commit types; make SQLite the only visibility authority.
- [ ] Define the chunk-text artifact envelope/ID, SQLite chunk-instance membership, verified generation-manifest, corruption error, aggregate accounting, retention/reachability, and snapshot-authorized materialization contracts from Sections 5.28 and 7.21.
- [ ] Define missing-workspace tombstones, retention policy, generation reachability, and GC audit records.
- [ ] Define the versioned pressure policy, protected/time-protected/reclaim tiers, authoritative measurements, peak-write estimates, GC plan/tombstones, deterministic ordering, `DISK_PRESSURE`/`STORAGE_MEASUREMENT_FAILED`, and disk-pressure checkpoint/remediation schemas from Sections 5.32 and 7.25.
- [ ] Define typed aggregate-fuse observations, preflight/approval records, `awaiting_approval` operation state, `SCOPE_FUSE_TRIPPED` response, expiry, one-shot claim, and bounded audit retention.
- [ ] Define versioned built-in noise exclusions, non-overridable security exclusions, binary/text detection, and skipped-file reason codes.
- [ ] Define the frozen repository-policy model, canonical pattern/digest rules, typed validation errors, and exact eligibility precedence from Section 5.24.
- [ ] Freeze the canonical first-class language names, extension mappings, parser identities, chunker contracts, and generic-fallback metadata from Section 5.14.
- [ ] Implement the typed macOS `StorageLayout`; route the optional human `config.toml` plus database, vector, artifact, lock, log, and temporary paths through it; remove global `~/.dolphin/` path resolution and never create/overwrite the config implicitly.
- [ ] Define the private-mode/owner/type/link contract, `STORAGE_PERMISSIONS_UNSAFE`, safe mode-tightening transaction, backend-descendant audit, `StorageProtectionStatus`, and closed best-effort FileVault adapter from Sections 5.31 and 7.24.
- [ ] Add containment, symlink, permission, spaces-in-path, unwritable-root, low-disk, and concurrent-initialization tests for the Application Support layout.
- [ ] Add one shared native-platform preflight used by setup, MCP, CLI, foreground operations, and preflight-only `doctor`; test numeric versions around 14.0, every supported major, future majors, malformed/overflowing versions, native `arm64`, Intel, Rosetta, Linux, unknown/contradictory state, and zero side effects on failure.
- [ ] Add one shared interpreter preflight before storage/worker/credential initialization; test standard CPython 3.13 plus Python 3.12, 3.14+, PyPy/other implementations, free-threaded builds, and debug builds with typed `UNSUPPORTED_PYTHON` remediation.
- [ ] Add schema contract tests in Python and the MCP layer.
- [ ] Update the metadata schema freely for 0.3.0 and test clean initialization plus interrupted-operation recovery.
- [ ] Configure SQLite foreign keys, WAL, bounded busy timeouts, selected durability, FTS5, quick/integrity checks, and the transactional published-snapshot pointer swap.
- [ ] Pin the qualified LanceDB release, confine its imports and backend objects to `kb/store/`, open only the validated local vector path, and reject cloud/object-store URIs, embedding registries/functions, and caller-supplied backend settings.
- [ ] Extract domain workflows from FastAPI handlers into application services shared by MCP and CLI.
- [ ] Replace endpoint tests with service-level and MCP-level outcome tests.
- [ ] Remove `kb/api/`, `kb-api`, `dolphin serve`, REST clients, server configuration, and dependencies used only by HTTP.
- [ ] Remove legacy broad config templates/merge/inheritance and implement separate authority types for Application Support search output budgets versus worktree indexing include/exclude policy; reject every retired credential, embedding, retrieval/ranking, storage, runtime, telemetry, and unrelated limit key.
- [ ] Remove `observability/`, Prometheus/Grafana/Loki/Promtail/Docker workflows, OpenTelemetry and `prometheus-client` dependencies, telemetry configuration, metrics endpoints, stack tests, and obsolete profiling/deployment documentation.
- [ ] Simplify `StructuredLogger` to the local versioned redacted event schema and remove OpenTelemetry trace-context behavior.
- [ ] Consolidate retained CLI behavior behind one command registry and prove setup, startup, `doctor`, list/audit, evaluation helpers, and maintenance cannot create or reactivate a registration or synthesize a first-index operation.

### Phase 2 — one-product runtime

Implementation status (2026-08-09): the Python stdio process now records one capability-bearing runtime owner with PID plus process-start identity, renews a bounded heartbeat, and marks itself stopped on normal connection shutdown. Startup or heartbeat ownership failure leaves the diagnostic read surface available but blocks readiness, and a failed heartbeat immediately makes the runtime unusable for further operation work. The shared SQLite authority now provides exclusive expiring operation leases, atomic oldest-compatible queued/paused claims, monotonic source-free phase/counter checkpoints, persisted executor pipeline compatibility keys, PID-reuse/expiry reconciliation, immediate graceful handoff, and lease-checked terminal completion. The clean-generation publication foundation now adds strict backend-neutral staging, verified-vector, manifest, published-snapshot, and reader-lease contracts plus a SQLite coordinator. Staging and independently ready components remain invisible; publication requires a live compatible operation lease, the persisted target HEAD, the fixed OpenAI embedding contract, and a compare-and-set pointer swap in one transaction. The current clean target contract is deliberately named `git-head-v1`; final filesystem worktree/common-Git identity revalidation remains an executor responsibility before this path is enabled. Each publication records the generation it replaced so lost-response retries remain idempotent while still rejecting a different predecessor precondition. Authority and expiry decisions use the coordinator's internal UTC clock rather than caller timestamps, write-lock acquisition has a short bounded contention retry, and reader acquisition prunes a bounded batch of abandoned expired leases. Published snapshots carry immutable backend verification data, and bounded reader leases keep an older generation addressable while the current pointer advances. Reader rows now bind workspace, generation, and publication identity, but this API remains unavailable to search until pending GC work treats every unexpired reader lease as a physical metadata/vector/artifact reachability root. The immutable chunk-text foundation now preserves exact decoded Unicode and newline sequences in a fixed network-order, versioned domain-separated envelope beneath a held no-follow Application Support descriptor chain. Private same-shard temporary writes use one validated UTF-8 encoding and are synchronized and atomically installed without replacement; each newly created directory entry is parent-synchronized, exclusive writer and shared reader locks make the temporary hard-link state unobservable and keep bounded cleanup non-interfering while it immediately reclaims validated two-link crash remnants and age-gates unlinked temporary files, and unlock failures never replace a primary verification/install error. A concurrent read that initially sees no private installer directory performs one unlocked verification; any unavailable/corrupt result rechecks for newly appeared coordination and serializes behind that writer before retrying. Existing/racing winners are fully reverified, immutable reads reject type/link/mode/header/length/digest/UTF-8 instability, canonical physical artifact sets can be verified without claiming generation authority, and embedding cache identities bind the exact provider/model/dimension/contract/text tuple. Tests cover concurrent deduplication, first-install/read races, fresh crash-link recovery, install failure and abandoned cleanup, containment substitution, unsafe modes, envelope/payload corruption, exact text fidelity, bounded input, artifact-set verification, and model-key isolation. Durable SQLite chunk membership, generation-manifest binding, and snapshot-authorized materialization remain pending, so physical artifact existence alone still grants no search visibility. `status` reports aggregate active-process and operation-executor counts, while `operation_status` projects real checkpoint phase/counters and distinguishes a compatible live executor from `runtime_absent`. The packaged MCP process deliberately registers as non-executing until the indexing adapter is connected, so `repo_add` remains unavailable and no queued operation is advertised as making progress. Physical chunk membership/FTS5 and LanceDB adapters, overlays, GC reachability, the concrete indexing executor, store-wide maintenance/watcher leases, signal-specific drain tests, complete crash injection, and foreground CLI execution remain pending.

Native Apple Silicon storage qualification now instruments Application Support initialization and immutable artifact installation through real macOS filesystem syscalls, asserting successful directory-descriptor syncs on the supported hardware. Directory durability fails closed when the filesystem rejects it. Repeated artifact puts verify the existing immutable envelope under the install lock before allocating or syncing temporary bytes; all blocking artifact lock acquisitions have a fixed deadline, while healthy reads take only a shared lock and invoke exclusive cleanup solely for the exact two-link crash-recovery path.

The generation-content foundation now persists strict canonical chunk-instance membership and one content-addressed manifest per staging generation under exact live operation-lease authority. Readiness and publication recompute the complete membership/descriptor/artifact-set binding and physically verify every immutable artifact before taking the SQLite writer lock; the visibility transaction rechecks the captured file identities and all metadata authority before committing. Materialization requires an unexpired reader lease, resolves every canonical snapshot field server-side, requires the generation's current content revision to match the revision validated by the visibility transaction, and still verifies the requested membership and artifact bytes on every access. SQLite triggers advance the content revision on every membership insertion, update, or deletion, so coherent metadata damage fails closed while healthy reads remain bounded independently of generation size and unrelated runtime writes.

Generation staging now also derives one exact FTS5 keyword document from each verified artifact in the same transaction as membership and manifest persistence. A domain-separated keyword commit binds the generation, content manifest, artifact identity, path, language, and item count. Readiness independently rebuilds the staged generation through the same pinned FTS5 tokenizer and freezes a commitment for each canonical term's generation-scoped postings only when the complete production index matches; publication trusts that immutable ready revision without a global index scan. Binding-field triggers invalidate the validated revision if any stored commit field changes later. Lexical retrieval accepts only bounded literal terms plus an unexpired reader-lease ID, normalizes those terms through the pinned tokenizer, resolves the published generation entirely from SQLite, and verifies only the queried terms' postings before ranking directly from that same bounded set. A fixed internal 100,000-posting ceiling fails an over-broad query with explicit narrowing guidance before ranking, so response limits also bound candidate and verification work. Post-publication keyword-document, commit, or result-affecting FTS mutation fails closed without involving unrelated terms or generations. Staging and ready keyword rows remain invisible.

Generation vector storage now pins LanceDB 0.27.0 and exposes a separate strict adapter over the fixed local Application Support vector directory. Every staged row is float32-canonical, finite, nonzero, fixed at 1,536 dimensions, and bound to the exact generation chunk identity plus embedding-cache key already persisted in SQLite. One immutable table per opaque generation makes an unscoped or cross-generation backend query structurally unavailable; a domain-separated complete-row digest plus exact Lance table/version token forms the verified commit. One bounded interprocess shared/exclusive lock serializes table creation and crash reconciliation while holding committed tables stable through short SQLite visibility transitions and searches. The SQLite coordinator fully verifies that commit before recording vector readiness and again outside the write lock before readiness/publication, then performs a cheap version/schema/count stability check while holding the shared backend guard through the visibility transaction. Retrieval accepts only a live SQLite reader-lease ID, validates the exact published commit and content revision, executes fixed cosine search against that generation's table, and reauthorizes every returned chunk/cache identity through the same SQLite snapshot before returning bounded internal candidates. Exact commit verification is cached only by immutable token plus digest, while every search still rechecks backend version and live reader authority; missing, mutated, malformed, expired, or cross-scoped state fails closed. Hybrid fusion, query-embedding integration, public search wiring, vector GC/reachability, and large-corpus policy qualification remain pending.

- [ ] Add the Python MCP SDK dependency and `dolphin mcp` entry point.
- [ ] Implement the environment-only `DOLPHIN_OPENAI_API_KEY` resolver and exhaustive secret-redaction tests.
- [ ] Add cleanup-receipt prefix redaction to every structured log, diagnostic, exception, tracing, and test-capture path without classifying the receipt as a global credential or persisting its raw value.
- [ ] Port MCP server instructions, tool annotations, schemas, structured results, errors, and payload limits to Python.
- [ ] Generate MCP `instructions` from the canonical agent contract, keep the first 512 characters self-contained, and test the exact critical guidance and ordering.
- [ ] Register exactly the frozen eight runtime tools from canonical `ToolSpec` data, with identical discovery output in every credential/storage/repository/component state and typed call failures instead of conditional exposure.
- [ ] Route MCP tools to transport-independent application services. Share only applicable setup/diagnostic/operation/approval/cleanup/maintenance services with the human CLI; do not register an enrollment/index creation command there.
- [ ] Implement store locking and process ownership records.
- [ ] Create every directory/file with explicit private modes, safely verify existing descriptors before backend access, re-audit SQLite WAL/SHM and LanceDB/log/backup/temp descendants after creation, and refuse unsafe ownership/type/link state.
- [ ] Allow concurrent snapshot readers while serializing mutating operations with bounded interprocess writer locks.
- [ ] Implement renewable per-workspace maintenance leases, heartbeat expiry, takeover, and drift reconciliation.
- [ ] Implement renewable operation execution leases, PID-plus-start-identity stale-owner proof, queued/paused discovery, compatible active-peer handoff, and next-launch auto-resume.
- [ ] Implement bounded in-process initialization and readiness.
- [ ] Implement normalized checkpoints for each long phase and idempotent artifact/embedding units; never treat uncommitted in-flight provider work as complete.
- [ ] Implement the five-second EOF/`SIGINT`/`SIGTERM` drain: stop scheduling, checkpoint, release leases, close watchers/workers/stores, and preserve protocol-only stdout.
- [ ] Implement crash reconciliation around checkpoint, embedding-cache, staging-store, and atomic-publication boundaries.
- [ ] Implement volume/state-class measurement, overflow-safe peak reservation before provider work, bounded automatic GC under one maintenance lease, `ENOSPC` classification, durable `disk_pressure` pause, and next-launch/foreground resume.
- [ ] Implement `dolphin operation run <operation-id>` as a scoped foreground runner with identical credentials, compatibility checks, checkpoints, locks, leases, and outcomes.
- [ ] Reject incompatible persisted operations with `OPERATION_INCOMPATIBLE` while retaining the prior complete generation and safe replan remediation.
- [ ] Add packaging/setup/uninstall assertions that Dolphin never invokes `launchctl`, writes a plist/login item, daemonizes, detaches, opens a runtime listener, or leaves a child process alive.
- [ ] Implement interactive-TTY-only `dolphin repo approve-scope --preflight-id`, exact confirmation text, full pre-prompt recomputation, short locked claim/requeue transaction, and restart reconciliation.
- [ ] Implement interrupted-operation reconciliation and ownership-aware graceful shutdown.
- [ ] Make the `forgotten` transition callable only through the explicit cleanup application service; prove EOF, every shutdown signal, crash recovery, timeout, cancellation, lease expiry, root change, and session teardown preserve registration epoch, receipt digest, and retention state.
- [ ] Ensure all MCP stdout remains protocol-only.
- [ ] Implement the closed low-cardinality in-process metrics registry and latest-only per-process diagnostic snapshot in runtime ownership records.
- [ ] Implement per-process JSONL log segments plus private, containment-checked, globally bounded retention under `StorageLayout.logs`.
- [ ] Add unit tests for every state transition and failure class.
- [ ] Add integration tests for concurrent starts/searches, writer contention, stale locks/leases, active-peer takeover, last-runtime pause, PID reuse, incompatible stores/operations, interrupted operations, crashes, every shutdown phase/signal/deadline, offline drift, next-launch/foreground resume, concurrent log segments, retention, diagnostic-snapshot expiry, and degraded diagnostic sinks.
- [ ] Make `dolphin doctor --json` report the resolved Application Support root, writability, free space, schema state, aggregate state-class sizes, and clearly windowed active-process diagnostics with no source or credential leakage.
- [ ] Expose the pressure-policy version and safe measured/free/protected/reclaimable/required-reserve aggregates, last GC result, pause details, and ready-to-use `gc --dry-run`/free-space remediation through `status`, `doctor`, and `operation_status`.
- [ ] Make setup and `doctor` report application encryption as `none`, permission validity, and FileVault `on`/`off`/`unknown`; test a fixed no-shell/no-privilege probe with strict timeout/output/parsing and advisory-only failure behavior.
- [ ] Port every retained TypeScript behavior test before deleting its implementation.
- [ ] Remove the TypeScript/Bun bridge, shared package, npm metadata, lockfile entries, and npm publish workflow.
- [ ] Add clean native Apple Silicon macOS 14+ install-and-start smoke tests on every supported major that assert wheel-only dependency resolution, compatible Mach-O deployment targets, and no compiler invocation.

### Phase 3 — safe autonomous repository lifecycle

Implementation status (2026-08-09): the lifecycle read foundation now provides descriptor-validated observational storage inspection, real mutually exclusive registry counts and exact-root resolution in `status`, explicit availability for all eight tools, fixed 25-item HMAC-protected revision-bound `repo_list` cursors, and exact-ID `operation_status` with durable attempts, live checkpoint projections, and non-extending terminal expiry. Git enrollment discovery now captures the common Git directory and concrete worktree Git directory in one Git snapshot, binds both to no-follow filesystem identities, revalidates the complete snapshot before registration commits, gives linked worktrees distinct workspace identities within one repository family, rejects path reuse by a replacement Git worktree, and preserves registration plus operation identity across a same-volume move when the prior root has disappeared. The shared repository-boundary foundation now parses authoritative gitlinks directly from bounded NUL-delimited index output, classifies initialized/uninitialized/missing/conflicted submodules without recursive submodule commands, performs a bounded no-follow descendant-marker walk that stops at malformed boundaries, validates reciprocal linked-worktree gitfiles, masks both submodule and independent nested-repository subtrees in sequential and parallel parent scans, revalidates the boundary snapshot after scanning, persists typed summaries, and returns at most eight summaries per read projection without rescanning during `status` or `repo_list`. The transport-independent current-workspace resolver now supports explicit ID, bounded client-root snapshots, connection-local, and probed process-CWD precedence; chooses the deepest registered worktree or persisted child boundary; refuses to collapse a newly created nested worktree into its registered parent; dynamically links separately registered children in boundary summaries; and returns typed ambiguity, missing-scope, uninitialized-submodule, invalid-boundary, and probe-unavailable remediation. The packaged MCP 2026-07-28 stdio transport owns isolated session state but does not yet supply client roots because that protocol version exposes no client-roots request surface; transport wiring therefore remains pending. Public mutation and search handlers remain unavailable, and the stdio runtime remains explicitly non-executing until the indexing adapter exists. Unsupported missing, cleanup-pending, and forgotten aggregates are deliberately omitted rather than reported as fabricated zeros until their durable states exist. The broad items below remain unchecked until their boundary/policy/freshness detail, forgotten/cleanup overlays, complete publication checkpoints, and full matrix tests are implemented.

- [ ] Implement observational empty-input `status`: bounded runtime/credential/storage diagnostics, mutually exclusive effective-state counts, aggregate-only forgotten accounting, and at most one deterministically resolved current workspace with no provider, scan, reconciliation, operation, GC, or enrollment side effect.
- [ ] Implement cursor-only `repo_list` with fixed 25-item pages, deterministic family/workspace ordering, one actionable-list revision, bounded integrity-protected cursor decoding, all-or-nothing invalidation, and no forgotten entries or expansion/filter/sort/page-size controls.
- [ ] Exclude forgotten epochs from every MCP list/resolution/ambiguity/boundary surface; add aggregate-only forgotten/tombstone accounting to `status` and a bounded human `dolphin repo list --include-forgotten` audit view with automatic disappearance at replay-tombstone compaction.
- [ ] Implement canonical worktree-root plus Git-common-directory detection and idempotent `repo_add`, with the Python MCP adapter as the sole packaged public caller of registration creation.
- [ ] Require the caller to generate and retain a 256-bit versioned cleanup receipt before `repo_add`; bind only its domain-separated digest inside the winning new-registration transaction, re-echo authority only to matching retries with `expires_at = null`, and prove repeat/concurrent calls with different receipts receive no authority.
- [ ] Implement MCP `repo_forget` and human `dolphin repo forget <workspace-id>` on one lifecycle service with registration-epoch validation, a durable cancellation request plus `cleanup-intent-v1`, atomic queued/paused cancellation, the shared five-second running-work drain, foreign/non-draining `WORKSPACE_IN_USE`, receipt consumption only after safe drain, immediate resolution/publication removal, session-scope invalidation, and no source/Git mutation.
- [ ] Linearize reader-lease and cleanup-intent admission in SQLite; allow pre-intent readers to serialize with lifecycle-change metadata, reject all post-intent workspace reads/mutations before provider/backend/file work, and preserve reader reachability through concurrent logical forget and GC.
- [ ] On abandoned-intent expiry, let one live compatible runtime—or next startup—claim recovery, perform cheap drift/policy/boundary reconciliation, restore a race-safe watcher baseline, and enqueue at most one new initial/incremental operation only when needed with normal preflights and reuse.
- [ ] Make explicit forget bypass missing-workspace grace only for now-unreachable workspace-derived state, preserve every shared/reusable/leased artifact, and schedule physical reclamation exclusively through bounded ordinary GC.
- [ ] Discover submodules from validated gitlink entries, exclude their complete subtrees from the parent pipeline, and report initialized/uninitialized/missing/conflicted/invalid states without mutation or network access.
- [ ] Discover descendant `.git` directory/file markers through a bounded metadata-only pass, stop traversal at every marker, and classify valid independent worktrees without following symlinks, running hooks, or making network calls.
- [ ] Generalize submodule/nested-repository reporting into one typed boundary model while retaining submodule-only gitlink metadata.
- [ ] Make path resolution choose the deepest enclosing registered/enrollable worktree and return typed remediation when a gitlink has no usable checkout or a nested marker is invalid/unregistered.
- [ ] Implement deterministic repository-family/workspace display-label derivation, stable short-ID disambiguation, and ID-only resolution across branch/root metadata changes.
- [ ] Implement stable repository-family and workspace identities independent of branch names.
- [ ] Implement identity-safe post-forget `repo_add`: prove one retained repository-family/concrete-worktree match before preserving a workspace ID, always create a fresh registration epoch/receipt and first-index/adoption operation, allocate a new ID for different/ambiguous/insufficient forgotten evidence, and retain normal active/missing idempotency rules.
- [ ] Capture Git common-directory and concrete-worktree-gitdir filesystem identities before/after bounded local discovery; reject missing/changed/type-unsafe facts, allow same-volume renames when object identities persist, and never invoke hooks, repository code, or network access for identity.
- [ ] Implement explicit, MCP-root, session-local, and process-CWD workspace-resolution precedence.
- [ ] Implement immutable clean commit generations and workspace-specific dirty/untracked overlays.
- [ ] Implement compatible generation lookup and Git-diff-based derivation for new worktrees and branch switches.
- [ ] Run a conservative storage/peak-write preflight before every growth phase and before document embedding calls; checkpoint measured versus estimated bytes and stop further provider submissions immediately on unsafe reserve.
- [ ] Implement content-addressed chunk artifacts and exact model-aware embedding-cache keys.
- [ ] Implement exact decoded-text preservation, domain-separated IDs, private atomic no-replace artifact writes, racing-writer verification, immutable reads, and verified per-generation artifact manifests.
- [ ] Standardize the existing Python, JavaScript/TypeScript, Svelte, SQL, and Markdown chunkers on the versioned language contract.
- [ ] Add the Rust parser dependency, `.rs` detection, parser-based structural chunker, conservative relationship metadata, graph-candidate extraction, and bounded error-region fallback.
- [ ] Attach Rust doc comments/attributes correctly and preserve impl/type/trait context for method chunks, local metadata, and any graph candidate.
- [ ] Verify a clean native Apple Silicon macOS 14+ wheel installation can index Rust on every supported major without `rustc`, Cargo, repository builds, or network access beyond OpenAI embedding calls.
- [ ] Reject mixed model/dimension state and test fixed-model enforcement on document and query embeddings.
- [ ] Return actual reuse and embedding counters in repository operations.
- [ ] Implement asynchronous operation persistence and exact-ID `operation_status`: immediate committed snapshots, nonterminal recovery retention, atomic terminal timestamps/deadlines, logical-expiry-before-serialization, and idempotent detail compaction with no derived-data reachability.
- [ ] Implement isolated staging generations and one atomic publication boundary for files, chunks, vectors, keyword state, manifests, references, and graph state if D-040 promotes it.
- [ ] Assign reference-target IDs as immutable staged membership, create one publication ID in the visibility transaction, and preserve both through retained-generation recovery, adoption, and GC.
- [ ] Implement generation-tagged vector staging, immutable artifact keys, verified LanceDB commit tokens/digests, matching SQLite FTS5 staging, readiness verification, and the single SQLite visibility transition.
- [ ] Require every staged chunk membership to resolve to a verified artifact and include its manifest digest in publication readiness; make partially written/orphaned artifacts invisible and safely reconcilable.
- [ ] Implement and test the complete cross-store crash matrix: before/after vector commit, before/after SQLite readiness, during pointer swap, during cache invalidation, on reopen, and during reclamation.
- [ ] Persist first-index phase, processed/known-total counters, and last-progress time without fabricating completion estimates.
- [ ] Implement exact-workspace `repo_sync` and branch-change handling through the shared reconciliation planner: no-op when current, compare-and-set reuse/creation for the observed target, non-blocking return, and an internal rebuild only when correctness makes delta/adoption unsafe.
- [ ] Implement continuous debounced watching and cheap pre-search fingerprint checks.
- [ ] Implement bounded catch-up followed by successful stale-marked search when the bound expires.
- [ ] Add source-disclosure, estimated scope, and catastrophic safety-fuse diagnostics.
- [ ] Calibrate the default fuse above legitimate large-monorepo fixtures and test each runaway condition independently.
- [ ] Separate approvable stable aggregate file/byte/token excess from unapprovable containment, traversal, boundary, configuration, type, arithmetic, snapshot-stability, and integrity failures.
- [ ] Build the versioned exact preflight fingerprint from workspace/Git state, dirty/untracked membership, policy/boundary inputs, measurements, and triggered thresholds without persisting source content.
- [ ] Make a fused operation durable and idempotently `awaiting_approval`; ensure `repo_add`, `search`, and `operation_status` expose one consistent human remediation and built-in-tool path.
- [ ] Implement bounded no-follow loading of root-only `.dolphin/config.toml`, strict TOML/schema/pattern validation, safe diagnostics, and the shared effective-policy digest.
- [ ] Enforce tracked-plus-nonignored Git candidacy before repository includes; enforce hard boundaries/security/text/size rules before every repository pattern result.
- [ ] Implement incremental policy-change planning so newly eligible/excluded membership changes atomically and unaffected chunks/embeddings remain reusable.
- [ ] Ensure every path and file operation uses containment validation.
- [ ] Test symlinks, linked worktrees, submodules, nested paths, duplicate names, large repositories, missing credentials, cancellation, crash recovery, concurrent operations, branch switches, detached HEADs, dirty overlays, untracked files, edit bursts, watcher overflow, and stale-reference drift.
- [ ] Test `repo_sync` schema rejection for every forbidden control; exact workspace isolation; up-to-date zero-operation/zero-provider behavior; repeated/concurrent operation reuse; racing edits; internal rebuild selection; crash/restart; and parity with watcher and pre-search reconciliation.
- [ ] Test `status` and `repo_list` with zero/one/many repositories and sibling worktrees; every current-workspace resolution state; all effective lifecycle states; 24/25/26-item boundaries; deterministic ordering; malformed/remixed/cross-store/wrong-version/stale cursors; concurrent add/forget/rename/reactivation; restart; complete redaction; and proof of zero network, repository scan, mutation, operation, GC, or retention side effects.
- [ ] Test `operation_status` for every nonterminal/terminal state and phase; exact 250/5,000 ms guidance bounds; malformed/guessed/cross-store/expired IDs; one instant before/at/after 30 days; repeated polling without deadline extension; crashes around terminal commit/compaction; forgotten-workspace redaction; bounded failures/counters; and proof that inspection cannot wait, list, cancel, resume, call a provider, or retain derived state.
- [ ] Implement the shared stable-descriptor current-file reader and test edit/rename/delete/recreate/symlink races, input/output bounds, encoding failures, current policy/security/boundary changes, and zero returned bytes on blocked or torn reads.
- [ ] Test parent/child double-index prevention for both submodules and independent nested repositories across initial scan, delta derivation, dirty overlays, watcher events, drift checks, graph extraction if retained, reference resolution, recovery, and GC.
- [ ] Test initialized, uninitialized, missing, deinitialized, dirty, commit-mismatched, conflicted, nested, malicious-path, escaping, and cyclic submodule metadata; assert no `git submodule` mutation or remote access occurs.
- [ ] Test explicit submodule registration, deepest-root resolution, safe generation reuse, independent watcher/freshness state, and deliberate parent-plus-submodule multi-workspace search.
- [ ] Test unrelated nested repositories, nested linked worktrees, same-name/remotes, dirty and ignored children, spaces/Unicode, invalid/escaping `.git` files, symlinks, permission failures, marker creation/removal, and duplicate gitlink-marker classification.
- [ ] Assert a newly discovered nested boundary is immediately masked from parent search/`open_ref`, while removal remains hidden until a fresh complete parent generation publishes.
- [ ] Assert parent embedding requests, chunks, references, and graph edges never include nested-repository content; assert child enrollment and parent-plus-child search remain explicit.
- [ ] Assert zero embedding calls for a compatible same-commit worktree, a no-change branch creation, and returning to an indexed generation.
- [ ] Assert that divergent worktrees return only their own versions of files, chunks, paths, references, and graph context if retained.
- [ ] Assert that changed-branch/worktree operations embed only cache-missing changed chunk inputs.
- [ ] Test root changes, nested roots, multiple roots, stale session defaults, explicit overrides, missing worktrees, and ready-to-use ambiguity remediation.
- [ ] Test identical basenames, duplicate remote basenames, linked worktrees with identical branch labels, detached HEADs, primary-checkout disappearance, display-label changes, and rejection of caller-supplied names.
- [ ] Test 30-day missing-workspace recovery, moved/re-registered worktrees, protected generations, shared artifacts, GC dry runs, interrupted GC, and idempotent GC retries.
- [ ] Test cleanup receipt creation races, loss, malformed/guessed/swapped values, log redaction, indefinite unused validity across large forward/backward clock jumps, inactivity, restart and compatible upgrade, epoch supersession, replay one instant before/at/after the exact 30-day consumed-receipt deadline, non-extension under repeated replay, tombstone compaction, same-root re-registration during/after the window, missing worktrees, queued/paused/running operations, exact five-second drain boundaries, provider calls already submitted versus not yet scheduled, active local/foreign leases, intent acquisition/attachment/renewal one instant before/at/after five- and 30-second boundaries, repeated authorized retries, abandoned-call maximum blocking, stale-row cleanup, publication/reader/GC races, receipt preservation on `WORKSPACE_IN_USE`, and crash recovery at every forget transition.
- [ ] Test every tool immediately before/at/after cleanup-intent admission/expiry/forget; single/multi-workspace all-or-nothing blocking; zero provider/cache/vector/FTS/file activity after rejection; pre-admitted read completion and lifecycle warnings; continuation suppression; reference expiry guidance; `cleanup_pending` list/status redaction; and underlying-state restoration.
- [ ] Test abandoned recovery with no/one/many runtimes, no drift/every drift class, no complete generation, duplicate observers, watcher races, renewed cleanup, process loss at each marker/operation transition, next-startup claim, zero-call reuse, and proof that cancelled operations never resume.
- [ ] Prove forgotten registrations never appear in MCP `repo_list`, resolution candidates, repository-boundary registration fields, or per-entry status; test aggregate redaction and bounded CLI `--include-forgotten` text/JSON at, before, and after compaction without creating reachability.
- [ ] Test workspace-ID preservation only on one proven identity match before the shared deadline; fresh epoch/receipt under same ID; new ID for same-path replacement, different family/worktree, multiple candidates, insufficient evidence, and one instant at/after identity-anchor expiry; non-extension by every read/replay path; delayed/crashed pair compaction; active/missing conflicts; concurrent winners; moved roots; and non-resurrection of every old reference, operation, lease, approval, cache, publication, and receipt.
- [ ] Test exact device/inode/birth-time matching for primary and linked worktrees; common-dir/gitdir aliasing; same-volume rename; cross-volume move/copy; inode reuse with different birth time; birth-time absence/precision/overflow; symlink/type swaps; before/after races; Git-admin repair/replacement; and path/branch/HEAD/remote matches that must not prove identity.
- [ ] Assert an agent cannot forget a workspace that existed before its `repo_add`, cannot target a sibling worktree/repository family, cannot force reclamation, and cannot alter or remove any source file, `.git` state, branch, commit, or physical Git worktree.
- [ ] Prove GC cannot traverse outside Dolphin's data directory or delete artifacts reachable from active workspaces/operations.
- [ ] Test tracked tests/docs/config, eligible untracked files, repository/info/global Git ignores, ordinary include/exclude overrides, exclude-over-include precedence, hard security exclusions, `.env.example`, binaries, minified/generated files, oversized single files, and skipped-file summaries.
- [ ] Test absent, valid, malformed, oversized, symlinked, wrong-version, unknown-key, duplicate-key, traversal-pattern, excessive-pattern, Unicode, and concurrently changed repository policies with zero provider calls on invalid first registration.
- [ ] Test divergent branch/worktree policies, invalid-after-valid stale behavior, watcher/pre-search policy drift, atomic policy publication, and actual parse/reuse/embedding counters for include/exclude deltas.
- [ ] Test every first-class extension, public language filter, parser-error fallback, version-driven invalidation, and generic `chunking_mode` metadata.
- [ ] Test Rust nested modules, imports/re-exports, structs/enums/traits, inherent and trait impls, methods, generics/lifetimes, async/unsafe/extern items, macros, tests, Unicode, incomplete edits, and multi-crate workspaces.
- [ ] Prove staged first-index data is invisible during normal progress, cancellation, provider failure, process crash, publication failure, and concurrent search.
- [ ] Prove readers pinned before publication finish on the old generation while new readers see only the new complete generation; retain read leases through fusion/materialization and reclaim neither side early.
- [ ] Fault corrupt/missing vector commit tokens, rows, dimensions, indexes, SQLite metadata/FTS5 rows, and snapshot pointers; require explicit integrity failures, safe reconciliation, and no mixed-generation response.
- [ ] Fault missing/truncated/corrupt chunk envelopes, text/digest/length mismatches, invalid UTF-8, swapped membership, symlink/path escapes, write races, and crashes on each side of artifact installation/publication; require typed failure with no current-disk substitution or payload leakage.
- [ ] Verify exact Unicode and newline preservation, deduplication across repositories without scope leakage, stale snippets after edits/branch switches/worktree removal, artifact reachability under reader leases, and GC disk/accounting behavior.
- [ ] Exercise concurrent readers and serialized writers in separately spawned processes, including reopen/takeover, and assert exact generation scope, reuse counters, and embedding call counts.
- [ ] Test every protection/reclaim tier and D-054 boundary; deterministic LRU/order; active/paused operations and approvals; live/expired readers; full 30-day missing-workspace retention/reactivation; shared reachability; GC/publisher races; and proof that no protected item is ever planned or deleted.
- [ ] Inject wrong/overflowing measurements and `ENOSPC` at artifact, SQLite/WAL, LanceDB, vector-index, manifest, and publication phases; require zero further provider calls, invisible partial state, retained committed search, idempotent cleanup, durable pause, and safe resume after space returns.
- [ ] Test aggregate approval at, below, and above every threshold; every unapprovable failure; non-TTY, pipe, env, repo-config, MCP, guessed-ID, wrong-workspace, expired, changed-fingerprint, repeated, and concurrent bypass attempts.
- [ ] Test exact confirmation, 24-hour expiry, one-shot atomic claim, crash on both sides of claim, restart/resume, missing credentials after approval, full snapshot revalidation, zero pre-claim document embeddings, and isolation from every other workspace/operation.

### Phase 4 — agent retrieval experience

- [ ] Add concise MCP server instructions for repository enrollment and tool choice.
- [ ] Teach agents to call compact `status` for runtime/current-workspace readiness and cursor through `repo_list` only when they need repository inventory; never suggest filters, page-size controls, forgotten enumeration, or treating either read as reconciliation.
- [ ] Teach agents to poll exact `operation_status(operation_id)` only when task progress depends on it, follow returned polling/remediation guidance, and never expect a wait, listing, cancellation, or operation-control mode.
- [ ] Teach agents that automatic freshness is normal and `repo_sync(workspace_id)` is reserved for an explicit correctness-critical freshness request; never teach waiting, forcing, or selecting an indexing strategy.
- [ ] Teach agents to generate and retain a fresh cleanup receipt before `repo_add`, retry a lost response with that exact receipt, call `repo_forget` explicitly only when that exact registration is genuinely no longer needed, treat `cleanup = null` as no removal authority, and never treat disconnect/session end/process exit as disposal or introduce agent/human or temporary/persistent registration classes.
- [ ] Teach agents that `SCOPE_FUSE_TRIPPED` requires a human to run the supplied CLI command, is not agent-retryable, and should trigger safe built-in discovery while awaiting approval; never teach an agent to execute the approval itself.
- [ ] Replace hand-maintained Codex/Claude guidance and metadata with generated thin adapters from the canonical contract.
- [ ] Generate equivalent Codex and Claude Code install/configuration examples without embedding `DOLPHIN_OPENAI_API_KEY` values.
- [ ] Add normalized cross-client parity tests for guidance blocks, tool names/schemas/annotations, example IDs, error/remediation language, environment-variable names, and versions.
- [ ] Add CI checks that fail on hand-edited or stale generated integration artifacts.
- [ ] Implement idempotent `dolphin setup codex` and `dolphin setup claude-code` plan/apply/verify flows using canonical absolute executable paths.
- [ ] Implement dry-run and JSON output, same-name conflict refusal, managed-entry upgrades/removal, concurrent-edit detection, private rollback, post-apply validation, and no-partial-edit manual fallback.
- [ ] Add redaction tests proving setup argv, output, errors, logs, generated files, and backup reports never contain an OpenAI key value.
- [ ] Extend `dolphin doctor` to diagnose each supported client's executable, config scope, managed entry, adapter digest/version, environment forwarding, startup, and credential presence separately.
- [ ] Test user-scope defaults, explicit project scope in primary and linked worktrees, tracked/untracked project config reporting, global/project precedence, shadowed stale entries, and scope-specific removal for both clients.
- [ ] Freeze and snapshot the exact eight task-oriented tool names, order, descriptions, schemas, annotations, handler bindings, and registry digest; reject every removed 0.2.x alias and any client-specific addition.
- [ ] Ensure generated instructions and both client adapters teach MCP `repo_add(path, cleanup_receipt)` as the sole enrollment path, including secure local receipt generation and lost-response reuse, never suggest a CLI enrollment alternative, and use returned stable workspace IDs for explicit scope.
- [ ] Teach agents that submodules and independent nested repositories require separate enrollment only when task scope needs them, and surface ready-to-use child `repo_add` plus explicit multi-workspace search examples.
- [ ] Implement deterministic current-workspace resolution and session-local scope without global mutable defaults.
- [ ] Implement the frozen strict-compatible `search.request` union with query-only first page and cursor-only continuation, nullable result/context overrides, and native structured results; reject mixed/missing/extra mode fields, unknown engine knobs, and explicit budgets over the resolved effective cap before query embedding or retrieval.
- [ ] Implement D-076's bounded strict Application Support config loader and canonical digest, with no-follow/private-owner checks and no parent/repository/environment discovery; keep the production loader structurally unable to accept a development/evaluation override path.
- [ ] Implement D-078 hot reload at MCP startup and first-page search: cheap unchanged reuse, one-retry stable read on change, atomic semantic snapshot acceptance, durable last-known-good fallback, explicit absence deactivation, immutable per-call pinning, and cursor expiry only on effective digest change.
- [ ] Make `status`/`doctor` inspect the current TOML without applying/deactivating it; report active/pending validity, source/digest/accepted time, invalid fallback state, and bounded remediation with no arbitrary values, and mark `status.readiness = degraded` only for invalid fallback.
- [ ] Add explicit evaluation-only candidate-TOML loading that requires isolated storage, records the path/digest/invocation, and is absent from installed MCP/setup/doctor/foreground-resume code paths.
- [ ] Implement exactly `dolphin config init|validate|show [--json]`; make initialization install the complete shipped matrix only when absent, and make validation/show use inspection plus read-only snapshot access without accepting/deactivating policy.
- [ ] Implement deterministic adaptive-budget selection from published scope statistics and closed query-intent classes; run `rules-v1` locally from the raw query only; emit profile/policy/classifier version/digest/default/cap/applied/source metadata; and bind all of it into cache/cursor validation.
- [ ] Test omitted versus explicit/zero budgets; every schema/effective-cap boundary; no-clamp `SEARCH_BUDGET_EXCEEDED` with zero provider/retrieval work; all inclusive threshold edges; required/missing/extra profiles; ordered/unordered/unbounded thresholds; defaults-versus-caps invariants; every closed intent; classifier normalization, phrase precedence, multi-match, and unmatched fallback; zero classifier provider/source/repository/config access; zero/one/two promotion reasons with at most one step; exact filtered single/multi-workspace counts; classifier/config/policy changes between cursor pages; metadata redaction; and identical results under semantically identical TOML formatting.
- [ ] Test absent/valid/malformed/oversized/symlinked/wrong-owner/wrong-mode/wrong-version/unknown-key global config; repository/parent/sibling/client/environment attempts to set budgets; production attempts to load evaluation files; isolated evaluation overrides; unchanged semantic digests across formatting; and absolute-ceiling enforcement under every authority.
- [ ] Test hot reload with unchanged metadata, in-place/atomic-replace edits, equal timestamp/size but changed inode/ctime, before/during/after read races, repeated instability, canonical-equivalent edits, valid-to-valid and valid-to-invalid transitions, no-prior invalid fallback, deletion/deactivation, invalid recreation after deletion, restart persistence, two/many runtime acceptance races, in-flight pinning, cursor continuation, and proof that status/doctor never mutates acceptance.
- [ ] Test every config CLI command in text/JSON; absent/existing/symlink/directory/special/wrong-owner/raced destinations; permissive umask; concurrent creators; crash/fault at every temporary/write/fsync/install step; no-overwrite/no-chmod/no-backup/no-delete guarantees; validation exit codes/details; active/candidate/fallback display; forbidden flags/subcommands/paths; and proof that no command accepts policy or invokes MCP/provider/repository work.
- [ ] Return `SCOPE_FUSE_TRIPPED` when any required workspace awaits approval; otherwise return `INDEX_BUILDING` with typed operation progress and built-in-tool next actions when coverage is incomplete. Make no query-embedding call on either path.
- [ ] Under disk pressure, keep prior complete snapshots searchable/stale as appropriate, skip optional cache/log writes, make first-generation `INDEX_BUILDING` include `pause_reason = disk_pressure`, and prove read paths neither invoke large GC nor mutate retention state.
- [ ] Return `WORKSPACE_IN_USE` before query embedding when any requested workspace is cleanup-pending; return no partial multi-workspace results, and teach agents to use supplied retry timing or built-in filesystem tools.
- [ ] Test no-generation single-workspace, exact-generation adoption, dirty-overlay catch-up, incomplete multi-workspace scope, retry after publication, and stale complete-generation behavior.
- [ ] Implement compatible exact query-embedding reuse before any provider call and reject corrupt/mismatched cached vectors.
- [ ] Route vector retrieval exclusively through `VectorStore.search(PublishedSnapshot, ...)` and keyword retrieval through the same snapshot's FTS5 membership; prohibit raw or unscoped LanceDB access outside the storage adapter.
- [ ] Implement centralized missing, rejected, transient, permanent, and contract-violation OpenAI failure categories with bounded retry/timeout policy.
- [ ] Implement mode-specific relevance calibration for lexical/structural fallback after transient failures only, with prominent execution metadata, omitted-vector indication, and retry/built-in next actions.
- [ ] Remove raw score from `SearchHit`; assign immutable one-based global rank after final deduplication/ranking, label through the exact verified calibration profile, persist/cache only rank and band, and expose the calibration version/digest in execution metadata.
- [ ] Test missing/empty/rejected credentials, cache hit during outage, timeout, connection failure, throttling, retryable service failure, permanent request failure, wrong dimensions, fallback-store failure, stale-plus-degraded composition, and cursor invalidation after mode recovery.
- [ ] Remove MCP inputs for vector/BM25 weights, ANN probes, MMR, reranking, graph toggles, score cutoffs, model choice, and concurrency.
- [ ] Add schema tests proving unknown low-level knobs fail clearly and task-level filters resolve identically across worktrees.
- [ ] Implement the opaque reference codec/resolver plus current-only `open_ref` resolution, exact alignment, fixed current excerpt policy, drift metadata, next actions, and typed invalid/missing/expired/blocked/unstable-read outcomes.
- [ ] Prove `open_ref` has no path, line-range, artifact, generation, or indexed/current-mode input and never serializes retained historical text.
- [ ] Prove repeated reference serialization is deterministic and read-only; tokens contain no path/source metadata; sibling worktrees/publications differ; malformed, guessed, remixed, mismatched, concurrently collected, and expired tokens fail with bounded constant-shape errors and no fallback.
- [ ] Include canonical absolute paths, relative paths, line ranges, repository identity, and fingerprints in every hit.
- [ ] Add containment and symlink-escape tests for both search serialization and reference resolution.
- [ ] Remove redundant 0.2.x MCP tools.
- [ ] Run a reproducible TOML matrix over scope-size/intent bands, defaults, and effective caps; choose the RC policy by task correctness first, then context efficiency, and commit its signed version/digest rather than hard-coding the initial 8/4,000 baseline.
- [ ] Materialize snippets only from snapshot-authorized verified chunk artifacts and keep the reader lease until result serialization completes.
- [ ] Test exact snippet budget accounting at zero/one-below/exact/one-above boundaries; independent-versus-concatenated encoding; bundled-asset offline load and digest failure; special-token-looking source text; complete-line shrinking and an overlong single line; Unicode/newline fidelity; per-snippet/aggregate/serialized equality; stale generations after current-file mutation/deletion; artifact corruption; redundancy suppression; zero-budget output; and deterministic selection.
- [ ] Test `hybrid-v1` with fewer/equal/more than three seed candidates; unaffordable high-rank candidates; overlapping same-file versus identical cross-file/workspace targets; every action tier and tie-break; exact-fit/remainder-too-small cases; greedy regeneration; null snippets; unordered input hardening; allocation-version cursor/cache changes; and deterministic byte-identical output.
- [ ] Test search pagination with zero/one/exact/multiple pages; fresh equal budgets and page-local counts; final partial page; target deduplication across every page; offset/page-index tampering and replay; changed budgets/scope/workspace publication/retrieval mode/ranking/relevance calibration/policy/tokenizer/allocator/sequence; lifecycle transitions; exhaustion; no partial error payload; and deterministic page concatenation equal to the pinned ranked sequence.
- [ ] Test cursor creation/replay/successor races across threads/processes/restarts; exact prefix and 256-bit entropy; malformed/guessed/remixed/cross-store handles; digest-only persistence; deterministic hash-chain successor; same page/next cursor on retry; no deadline/reachability refresh; one instant before/at/after 30 minutes; forward/backward clock changes; logical expiry before compaction; target/artifact GC pins; state corruption; zero raw query/source/snippet/embedding/provider payload in continuation state/results/logs/diagnostics/metrics; and raw cursor presence only in the intended `next_cursor` result/input, never persistence or observability.
- [ ] Test ranked plans with 0/1/499/500/501+ eligible targets; post-dedup horizon application; contiguous one-based global rank/digest/order and stable bands across every page; horizon metadata on every page; final narrowing guidance; pointer-state size; TOML/page-budget independence; and proof that continuation performs zero query-provider, vector, FTS, fusion, reranker, graph, classifier, calibrator, config-reload, or candidate-expansion work.
- [ ] Test calibration artifact digest/schema/order/finite/monotonic/threshold/validation-manifest checks; exact hybrid and lexical/structural profile selection; independently enabled bands; every D-094 language/base-size/workspace/filter/rank boundary and evaluator/runtime cell-key parity; failed `high` cell fallthrough to independently validated cumulative `medium`; underpowered/unsupported/distribution-mismatched-to-`exploratory`; exact Wilson results and one-below/at/above every D-091 support/bound; duplicate-pair rejection; no pooling/weighting/decision rounding/cross-product authority; deterministic boundary labels; cache/cursor invalidation on identity change; unchanged ordering/snippet allocation; no runtime fitting; and zero raw component/fused/normalized/calibrated scalar scores in production result/state/cache/log/metric/diagnostic/terminal-summary boundaries.
- [ ] Test continuation persistence success, exhaustion, disk reserve denial, immediate/timeout writer contention, definite storage failure, and crash/connection loss before/during/after commit; assert exact state/nullable-field invariants, no unproven cursor, complete identical page/hits/snippets/accounting, unchanged freshness/execution degradation, no provider/retrieval/GC retry, correct first-page/same-cursor remediation, and logical expiry of every undisclosed orphan.
- [ ] Snapshot the exact Section 7.7 JSON Schema and test runtime/client/docs parity, nested `anyOf`, discriminant constants, all-required fields, explicit null/empty arrays, extras forbidden at every level, query/continue success, every mixed/missing combination, OpenAI strict-schema acceptance, and absence of a non-strict/client-specific fallback.
- [ ] Update the bundled agent skill and examples to teach autonomous enrollment.
- [ ] Add mirrored Codex/Claude examples for secure receipt generation, worktree enrollment, lost-response retry, delta reuse, receipt-authorized cleanup, `WORKSPACE_IN_USE` retry, and refusal when `cleanup = null`; assert the receipt never appears as a fixed literal example value and no example labels registrations by human/agent ownership or temporary/persistent class.
- [ ] Keep cleanup guidance to the canonical flow and prove generated clients expose no cleanup choice or argument beyond generating/retaining the opaque receipt, passing it to `repo_add`, and later passing its workspace ID/receipt to `repo_forget`.
- [ ] Add contract tests that inspect tool descriptions, annotations, schemas, and examples.
- [ ] Add cross-state discovery tests proving `tools/list` is byte-for-byte semantically identical with missing credentials, zero/many repositories, cleanup pending, disk pressure, incompatible state, and either binary retrieval-component decision; assert no callable MCP resource/prompt proxies an operation.

### Phase 5 — prove value

- [ ] Implement fixed control/treatment evaluation harnesses.
- [ ] Add representative tasks from every category in Section 9.
- [ ] Sweep adaptive search output-budget TOMLs across small/medium/large/massive single- and multi-workspace scopes plus closed query-intent classes; ablate `rules-v1` against scope-only selection and compare correctness, missing-evidence regressions, irrelevant context, follow-up calls, total context, and variance against fixed 8/4,000 and explicit-budget baselines.
- [ ] Apply D-081 without discretion after viewing results: either freeze the passing classifier/version and intent promotion into the signed RC policy, or remove all classifier code/interface, intent metadata/identity, promotion behavior, tests/docs, and flags before the RC branch is cut.
- [ ] Compare `hybrid-v1` with top-hit-depth and breadth-only snippet baselines under identical rankings/budgets; retain or revise it by task correctness first, with missing evidence, irrelevant context, null-snippet rate, follow-up reads, and determinism as guardrails.
- [ ] Evaluate agents following and declining `next_cursor`; verify pagination adds useful non-duplicated evidence only on an explicit call and that per-page allowances do not encourage unnecessary continuation or hide the first page's quality.
- [ ] Freeze the simplest RC profile thresholds/defaults/caps whose repeated task-correctness result wins without a critical-category regression; sign its version/digest and retain the full experiment matrix only as a bounded build artifact.
- [ ] Evaluate receipt-scoped cleanup end to end: the caller supplies and later uses its receipt, a matching lost-response retry recovers authority, a call without that receipt cannot remove the registration, cleanup leaves Git/source untouched, and later re-enrollment reuses safe shared artifacts without accepting the old receipt or introducing registration provenance/classes.
- [ ] Evaluate an agent encountering `cleanup_pending`: it does not force/bypass, does not assume omitted multi-workspace coverage, uses built-in tools or retries appropriately, and treats a pre-admitted result's lifecycle warning as authoritative.
- [ ] Evaluate abandoned-cleanup recovery without manual `repo_sync`: watcher/reconciliation returns automatically, unchanged content triggers zero embedding calls, and the agent sees one coherent operation/state transition.
- [ ] Verify re-enrollment correctness with stable-ID restoration on a proven same-worktree case and new-ID isolation on same-path replacement, while both cases reuse only independently compatible content-addressed artifacts.
- [ ] Add and independently score structural-discovery tasks for every first-class language, with Rust trait/impl, module/re-export, and analogous-pattern cases.
- [ ] Run the paired lightweight-versus-cross-encoder ablation with identical candidates, budgets, agent conditions, and blinded outcome grading.
- [ ] Record the binary reranker decision. If `removed`, delete all runtime code/dependencies/config/docs before RC; if `standard`, lock weights/provenance and pass clean provisioning, integrity, offline restart, memory, latency, upgrade, and uninstall gates.
- [ ] Run the paired non-graph-versus-graph ablation with identical non-graph candidates, budgets, agent conditions, and blinded outcome grading; audit false, stale, cross-workspace, cross-submodule, and cross-independent-nested-repository relationships.
- [ ] Record the binary graph decision. If `removed`, delete graph stores/schemas/resolvers/enrichment/dependencies/config/docs before RC; if `standard`, lock schema/extractor/policy versions and pass atomicity, isolation, incremental correctness, storage, memory, latency, and failure-degradation gates.
- [ ] Build canonical pinned target views and establish human-curated relevance judgments under D-092, including hard lexical false friends, direct implementations, indispensable evidence, supporting call/test/config context, misleading matches, and redundant earlier evidence across every first-class language.
- [ ] Pass D-093's two-pass non-held-out pilot before generating held-out presentations; then complete the blinded hidden-repeat run, verify kappa/agreement before precision reveal, finalize repeats conservatively once, and discard the complete run on repeatability failure.
- [ ] Validate zero repository/task-family overlap, freeze every D-095 population, select one target per query before labels, generate hidden repeats only from the authority-bearing union, and prove diagnostic correlated hits/repeat copies never increase any D-091 count.
- [ ] Assemble authority-bearing fit/held-out corpora only from license-validated real public pinned repositories and original human revision-grounded tasks; keep Dolphin, generated/paraphrased prompts, synthetic/copied fixtures, and contrived cases diagnostic-only and verify they cannot reach fitting or gate counts.
- [ ] Test every allowed identifier and allowed-only `AND`/`OR` expression; mixed copyleft/source-available/custom/deprecated/unknown leaves; `LicenseRef`/`WITH`; missing/malformed/conflicting/changed files; nested allowed/disallowed/ambiguous subtrees; exclusion-before-task semantics; zero hook/build/network execution during frozen runs; and manifest revalidation at fit/gate admission.
- [ ] Test invalid/failed seven-day and successful 90-day deadlines; release-before/after finalization and 30-day shortening; one instant before/at/after expiry; access non-refresh; clock movement; CI teardown; local next-run cleanup; explicit early cleanup; crash/retry/idempotency; symlink/path-swap/broad-target refusal; original-repository/production-state preservation; and retained source-free manifests.
- [ ] Fit and evaluate separate monotonic relevance profiles for every exact shipped retrieval-mode/ranking-policy pair; report per-band precision/coverage, ordering consistency, stability across repository/query-size strata, out-of-distribution behavior, and whether agents use the bands correctly, while retaining raw source-free scores only in bounded build artifacts.
- [ ] Apply D-090/D-091/D-094 mechanically: enable each `high` or `medium` claim only when its untouched held-out result clears the exact global and all five applicable marginal Wilson/support gates; disable inconclusive/underpowered/failing cells, generate separate per-band cell manifests plus diagnostic-only cross-tabs, and rerun production-boundary tests against the exact resulting artifact.
- [ ] Run repeated trials and report variance.
- [ ] Run explicit `uv run` profiling/evaluation commands and retain their bounded outputs only as CI/build artifacts.
- [ ] Diagnose cases where Dolphin is ignored, misused, or inferior to built-in tools.
- [ ] Improve tool guidance, retrieval, and response shaping based on evidence.
- [ ] Run the same client-smoke scenario IDs through Codex and Claude Code harnesses and compare semantic outcomes, including autonomous `repo_add` and exact-search deferral.
- [ ] Measure agent correctness under cached-semantic, transient-degraded, and credential-failure scenarios; verify degraded results never imply semantic coverage.
- [ ] Meet the agreed 0.3.0 value thresholds.

### Phase 6 — documentation and release candidate

- [ ] Update the README quickstart to the persistent `uv tool install --python 3.13 pb-dolphin` path, automatic CPython provisioning, installed `dolphin mcp` executable, explicit upgrade/uninstall commands, and clearly secondary exact-version `uvx --python 3.13` trial path.
- [ ] Document MCP `repo_add` as the only enrollment/first-index workflow; remove every `dolphin index`, `kb ingest`, `dolphin repo add`/`import`, implicit-current-directory, and setup-driven enrollment example from README, architecture, testing, operational guidance, generated agent artifacts, and shell completions.
- [ ] State the native Apple Silicon-only platform boundary before installation, document `UNSUPPORTED_PLATFORM`, and explicitly exclude Intel, Rosetta, Linux/Windows, universal binaries, and native source-build troubleshooting from the 0.3.0 support promise.
- [ ] State the macOS 14.0 minimum and non-patch-gated runtime rule; document supported/unqualified/unsupported diagnostics and recommend current security patches without a network update check.
- [ ] Document `uv tool update-shell` plus an absolute-executable-path fallback for GUI-launched MCP clients.
- [ ] Document `DOLPHIN_OPENAI_API_KEY` for shell and GUI-launched MCP clients, including `.zshrc`, MCP `env`, CI, and optional 1Password `op run` examples.
- [ ] Document that GUI applications may not source `.zshrc` and provide an executable verification step for the actual MCP launch context.
- [ ] Document `~/Library/Application Support/Dolphin/`, its contents and permissions, disk-use diagnostics, safe GC, and the intentional absence of `~/.dolphin/` migration.
- [ ] Document receipt-authorized MCP `repo_forget` and human CLI cleanup without describing distinct repository kinds, including the unused receipt's epoch lifetime and `expires_at = null`, receipt scope/loss/redaction, the non-extending 30-day consumed-receipt replay window, post-compaction behavior, exact logical-versus-physical effects, active-use retries, shared-state retention, same-root re-registration, and the guarantee that Dolphin never deletes a Git worktree or source file.
- [ ] Document `cleanup-intent-v1`'s fixed 30-second TTL, five-second renewal/drain, maximum abandoned blocking, retry behavior, logical-expiry semantics, and absence of configuration or retention side effects.
- [ ] Document cleanup-pending read/mutation admission, allowed diagnostic tools, all-or-nothing multi-workspace behavior, retry/built-in guidance, pre-admitted lifecycle warnings, and post-expiry underlying-state restoration.
- [ ] Document automatic abandoned-intent recovery and the frozen four-step/two-input cleanup UX; state that all cleanup constants are internal, non-configurable defaults and that logical success does not wait for physical GC.
- [ ] Document that normal MCP listings omit forgotten registrations, `status` exposes aggregates only, and human `repo list --include-forgotten` provides bounded read-only audit detail only during the replay window.
- [ ] Document post-forget workspace-ID restoration proof, the shared non-extending 30-day identity-anchor deadline, post-window new-ID behavior, mandatory epoch/receipt rotation, safe outcome reasons, old-reference non-resurrection, and independence of identity from artifact reuse.
- [ ] Document the exact macOS filesystem identity tuple, same-volume move behavior, conservative new-ID outcomes for copy/replacement/unsupported metadata, and the fact that identity discovery executes no hooks or network operations.
- [ ] Document `storage-pressure-v1`'s exact D-054 watermarks, hysteresis, reservation formula, batch/overshoot semantics, protected/time-protected/reclaim order, 30-day guarantee, `DISK_PRESSURE` behavior, no quota/force knob, `gc --dry-run`/apply parity, and safe ways to free space or resume.
- [ ] Document the no-application-encryption boundary, plaintext native store formats, exact `0700`/`0600` policy, FileVault recommendation/status semantics, threat-model exclusions, and absence of a storage key, unlock flow, SQLCipher, Keychain, or 1Password storage integration.
- [ ] Disclose that private content-addressed chunk artifacts retain derived local source text and may collectively cover most eligible files; document permissions, aggregate disk reporting, retention/GC, uninstall persistence, corruption remediation, and the absence of an MCP artifact-dump/reset tool.
- [ ] Document that `open_ref` returns bounded current-worktree text only, explain every alignment/error state, and direct agents to exact search snippets or sync/native file tools instead of a historical mode.
- [ ] Document opaque-reference stability and expiration, separate path/line fields, non-authorization semantics, and the fact that returning a reference does not indefinitely retain its originating generation.
- [ ] Document the split-store architecture, SQLite visibility authority, local-only exact LanceDB pin, diagnostics/recovery behavior, and the absence of user-facing backend or vector tuning.
- [ ] Document the complete `.dolphin/config.toml` schema, pattern semantics/precedence, Git-ignore boundary, examples, validation remediation, read-only guarantee, and settings deliberately unavailable to repositories.
- [ ] Document catastrophic-fuse intent, approvable versus unapprovable failures, the interactive exact-fingerprint approval flow, expiry/one-shot behavior, resume semantics, and the absence of a global/MCP/config bypass.
- [ ] Document process-bound lifetime, what pauses when clients close, automatic next-launch resume, `dolphin operation run`, offline watcher reconciliation, the five-second shutdown budget, explicit-only `repo_forget`, and the absence of both implicit session-end cleanup and LaunchAgent/daemon installation.
- [ ] Document automatic freshness as the default and the exact one-field, non-blocking `repo_sync` escape hatch; state that it cannot wait, force, select a rebuild, or bypass safety and that a current workspace performs zero provider work.
- [ ] Document the bounded `status`/`repo_list` split, all current-workspace resolution states, fixed 25-item cursor pages, restart-on-cursor-change behavior, aggregate-only forgotten accounting, and the guarantee that both tools are observational local reads.
- [ ] Document exact-ID immediate `operation_status`, every state/phase/pause/failure field, polling guidance, the non-extending 30-day terminal-summary window, `OPERATION_MISSING`, forgotten-workspace redaction, no reachability pin, and the absence of MCP wait/list/cancel/resume/retry controls.
- [ ] Document nullable search budgets, the complete four-profile TOML with clearly labeled experimental seed values, inclusive threshold and one-step promotion semantics, selection metadata, explicit override validation without clamping, the 50/20,000 protocol ceilings, cursor invalidation on policy change, D-076 authority/path/precedence, and reproducible evaluation overrides.
- [ ] Document intent's budget-only role, the deterministic local `rules-v1` behavior and fallback, classifier-version metadata, zero provider/source/config access, and the absence of an agent/config/plugin classifier selector.
- [ ] Document exact snippet-only `max_context_tokens` accounting, the bundled `cl100k_base-v1` version, excluded-but-bounded metadata, complete-line/null-snippet behavior, per-snippet/aggregate counts, offline failure semantics, and cursor invalidation on accounting-version change.
- [ ] Document `hybrid-v1` at the agent-relevant level: up to three initial distinct snippets, deterministic breadth/depth allocation, closed reasons/version, possible null snippets, and the absence of allocation knobs or guaranteed snippet-per-hit behavior.
- [ ] Document per-page result/context budgets, fresh continuation allowances, pinned values/versions/scope, page index and exhaustion, no duplicate targets, all-or-nothing expiry, and the guarantee that additional context requires another explicit search call.
- [ ] Document opaque cursor-only continuation, deterministic safe retry, fixed non-extending 30-minute lifetime, restart/concurrent-runtime support, expiry remediation, no raw-query echo/state, source-free private persistence, and automatic post-expiry compaction.
- [ ] Document the fixed 500-target ranked horizon, retained/horizon-hit metadata, local-only continuation work, absence of progressive reretrieval, final-page narrow-query guidance, and intentional lack of MCP/TOML horizon control.
- [ ] Document all three continuation states, closed unavailable reasons, the guarantee that correct pages survive optional cursor-write failure, lack of an unproven cursor or automatic rerun/GC, and safe reference/built-in/fresh-query recovery.
- [ ] Document one-based global rank and the `high`/`medium`/`exploratory` meanings, their non-probabilistic guidance, D-092's task-utility rubric, D-093's one-reviewer repeatability safeguards, D-094's five marginal runtime strata/all-cells rule, D-095's repository/task-family separation and query-weighted sampling, independently held-out-gated mode-specific calibration version/digest, D-091's exact Wilson/support gates/cumulative-medium rule, stable continuation behavior, conservative unsupported/underpowered fallback, and the absence of raw scores, online fitting, model-judge authority, or MCP/TOML calibration controls.
- [ ] Document D-096's real permissively licensed repository/original human task authority, pinned revision and source-free provenance, diagnostic-only generated/synthetic material, private corpus retention, and guarantee that source-bearing evaluation data is neither distributed nor stored in production.
- [ ] Document D-097's exact license allowlist, strict expression/nested-subtree rules, conservative exclusion/rejection behavior, provenance fields, and evaluation-policy-not-legal-advice scope.
- [ ] Document D-098's private seven/90/30-day retention rules, non-extending logical expiry, CI/local/development-only cleanup triggers, original-repository safety, and retained source-free provenance.
- [ ] Document the one `search.request` envelope with complete strict query and cursor-only continuation examples; explain explicit null/empty-array values, reject mixed modes, and keep generated Codex/Claude examples semantically identical.
- [ ] Document startup/per-search atomic hot reload, stable semantic digests, in-flight pinning, durable last-known-good behavior, first-invalid shipped fallback, deletion reset, invalid/degraded metadata, status/doctor inspection semantics, multi-runtime behavior, and typo recovery without restart.
- [ ] Document only `dolphin config init|validate|show [--json]`, their exact fixed-path/create-only/observational behavior and exit outcomes, manual editing workflow, and the intentional absence of editor/set/unset/reload/watch/overwrite/reset/import/export or MCP configuration writes.
- [ ] Document local log location/retention, redaction guarantees, compact `status`/`doctor` diagnostic semantics, and explicit development profiling commands; remove every dashboard, telemetry-export, and Docker-monitoring instruction.
- [ ] Update `docs/ARCHITECTURE.md`, `docs/TESTING.md`, and `docs/PUBLISH.md` to the implemented 0.3.0 design.
- [ ] Update Python, MCP, and plugin changelogs and metadata to 0.3.0.
- [ ] Ensure all examples use current tool names and schemas.
- [ ] Publish the exact eight-tool registry table and state that server instructions are guidance rather than another capability; remove provisional-name language, aliases, dynamic-tool documentation, and low-level MCP resource/file/index controls.
- [ ] Verify generated Codex and Claude Code artifacts are semantically mirrored, source-digest clean, and derived from the 0.3.0 runtime tool registry.
- [ ] Document automatic setup, dry-run/JSON usage, conflict handling, manual fallback, verification, managed removal, and recovery from interrupted client configuration.
- [ ] Run Python unit, integration, E2E, MCP/client, storage, watcher/process, and uninstall suites on standard CPython 3.13 on the latest patch of every supported native Apple Silicon macOS major; assert CI and publishing contain no other interpreter/architecture matrix entries.
- [ ] Run Python MCP/core unit, contract, integration, and E2E suites, lint, type checks, audit, and build.
- [ ] Run interrupted-index, branch-switch, watcher, and runtime-lifecycle soak tests.
- [ ] Run storage-pressure soaks with large shared worktree histories, repeated branch churn, concurrent reads/publication/GC, exact-boundary transitions, wrong estimates, full-disk injection, crash/restart, and deterministic low-water convergence without provider work after pause.
- [ ] Verify repeated client close/reopen cycles checkpoint, pause, reconcile offline changes, and resume without full re-embedding, partial publication, or orphan processes.
- [ ] On a permissive-umask clean account, audit every created state class and backend descendant for containment, owner, type, `0700`/`0600` modes, redaction, and zero application-encryption/key artifacts; exercise FileVault advisory states without changing the host.
- [ ] Run clean-user-directory installation and uninstallation tests.
- [ ] Assert the built wheel has no optional/environment-dependent reranking behavior and matches the recorded `removed` or `standard` decision exactly.
- [ ] Assert the built wheel and initialized schema contain either the complete standard graph policy or no graph subsystem/dependencies at all, matching the signed decision.
- [ ] Assert the built wheel and lockfile contain no Prometheus/OpenTelemetry dependency, telemetry exporter, metrics server, bundled dashboard, or Docker observability asset.
- [ ] Assert the built wheel contains the exact qualified LanceDB pin, every native dependency is `arm64` with deployment target no newer than 14.0, and local create/index/publish/reopen/search/recovery/uninstall passes on every supported macOS major without cloud access or a source build.
- [ ] Produce the 0.3.0 agent-value evaluation report as a CI/release artifact.
- [ ] Inspect Git, wheel, plugin/skill, build staging, and public release artifacts for zero source-bearing corpus/task/view/judgment/score material; retain only the bounded D-096 source-free provenance and decision manifests, then apply the private evaluation-workspace retention policy.
- [ ] Open the release PR from `develop` to protected `main`.

### Phase 7 — coordinated release

- [ ] Verify the release commit is the exact tested commit.
- [ ] Publish all coordinated artifacts from the protected release commit.
- [ ] Verify package metadata, versions, provenance, and installation commands.
- [ ] Verify the Python distribution, Codex integration, Claude Code integration, and generated guidance all report the same 0.3.0 version and source commit.
- [ ] Verify runtime discovery plus both installed client integrations expose exactly the canonical eight-tool registry and matching digest, with no additional MCP operation surface.
- [ ] Run post-publish installation and first-repository smoke tests on clean native Apple Silicon environments for every supported macOS major; prove the worktree remains unregistered after install/setup/doctor and becomes registered only after the agent's MCP `repo_add` call.
- [ ] Confirm agent startup, autonomous `repo_add`, indexing, search, reference follow-up, sync, receipt-authorized `repo_forget`, and recovery.
- [ ] Publish release notes with breaking-change language focused on the new canonical workflow rather than migration support.

## 12. Definition of done

Dolphin 0.3.0 is done when a developer on a clean native Apple Silicon macOS 14-or-newer account can install and configure one MCP entry, start an agent, and have that agent:

1. understand when Dolphin is appropriate;
2. use compact `status` to discover that the current repository is not registered, without triggering enrollment or indexing, and use `repo_list` only when broader inventory is needed;
3. explicitly register it through MCP `repo_add`, with no CLI or setup enrollment alternative;
4. observe indexing through exact-ID immediate operation snapshots without blocking, listing, or acquiring operation-control authority;
5. use Dolphin as a meaningful part of a real code task with observable adaptive result/context budgets chosen from the indexed scope and tunable through the documented TOML policy rather than hidden constants;
6. follow citations into relevant implementation context;
7. rely on automatic freshness ordinarily and use the one-field non-blocking `repo_sync` when task correctness requires an explicit current-snapshot request, without selecting or forcing an indexing strategy; and
8. recover from ordinary runtime and interrupted-operation failures without human debugging; and
9. register and search two divergent worktrees concurrently without cross-contamination or redundant embedding of their unchanged base; and
10. close every client during indexing and later resume from durable progress without an installed daemon, partial search state, or implicit workspace cleanup; and
11. survive an injected interruption at every cross-store publication boundary without exposing a partial or mixed generation; and
12. return an exact published snippet after the underlying worktree changes, or fail explicitly if its private chunk artifact cannot be verified; and
13. follow an opaque Dolphin-issued reference into bounded current code with unambiguous drift/alignment metadata and no historical/current mode choice; and
14. keep every local state path privately owned/mode-restricted, accurately report that Dolphin adds no application encryption, and remain fully usable regardless of advisory FileVault status; and
15. reclaim only twice-verified unprotected derived state under disk pressure, keep committed reads available, and durably pause/resume indexing without another provider call after reserve becomes unsafe; and
16. pass the same native CPython 3.13 wheel and end-to-end behavior on the latest patch of every supported Apple Silicon macOS major from 14 through the RC-current stable release; and
17. release the exact workspace-registration epoch bound to its supplied receipt through the two-field cleanup contract, while being unable to release an epoch for which it has no matching receipt and leaving the Git worktree, source files, and shared derived artifacts untouched; and
18. recover automatically from an abandoned cleanup attempt by restoring reconciliation/watching and at most one needed index operation without manual `repo_sync`, duplicate work, or resurrection of a cancelled operation; and
19. discover exactly the same frozen eight-tool registry in every supported client and runtime state, with no alias, dynamic disappearance, or alternate MCP operation surface.

The coordinated artifacts must all report 0.3.0, pass the complete release gates, and originate from the same protected release commit.

## 13. Open design questions

None. The implementation team should treat Sections 3–12 as the frozen 0.3.0 plan. An implementation-discovered ambiguity that would change public behavior, safety authority, release gates, or data retention requires a new explicit decision in Section 3; ordinary internal details should use the simplest design satisfying the existing invariants.

## 14. Risks to track

| Risk                                                                                             | Consequence                                                                                                                     | Planned mitigation                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python MCP rewrite accidentally loses useful bridge behavior                                     | Search or tool-contract regressions                                                                                             | Port outcome-focused contract tests before deleting TypeScript code                                                                                                                                                                                            |
| Autonomous indexing causes unexpected API cost or disclosure                                     | Loss of trust                                                                                                                   | Explicit `repo_add`, clear descriptions, scope estimates, hard bounds                                                                                                                                                                                          |
| A hidden or retained CLI enrollment path diverges from MCP semantics                             | Registrations bypass canonical guidance, cleanup-receipt issuance, or worktree rules                                            | One MCP-only public creation adapter, command/entry-point/help/completion snapshots, no enrollment side effects in setup or diagnostics, end-to-end negative tests                                                                                             |
| Explicit, watcher, and pre-search sync paths schedule the same work more than once               | Duplicate parsing, OpenAI calls, or competing publication                                                                       | One reconciliation planner, exact target fingerprints, compare-and-set operation submission, idempotent units, concurrency and zero-provider no-op tests                                                                                                       |
| Health or inventory reads grow unbounded or change state                                         | Agent context floods, listing pages skip workspaces, or a diagnostic unexpectedly triggers cost                                 | Empty observational status, fixed cursor-only pages, actionable-list revision binding, all-or-nothing cursor expiry, side-effect/network assertions                                                                                                            |
| Operation polling becomes control authority or retained history pins expensive state             | Agents accidentally cancel/resume work, forgotten identities leak, or derived data never reclaims                               | Exact-ID immediate snapshots, no control/list modes, source-free 30-day terminal summary, logical expiry, independent reachability, constant-shape missing errors                                                                                              |
| Runtime or client tool discovery drifts from the intended product                                | Agents learn inconsistent workflows or a hidden low-level capability bypasses safety                                            | Frozen ordered eight-tool tuple, one registry digest, startup/generator failure on mismatch, cross-state/client discovery snapshots, no callable resource/prompt proxy                                                                                         |
| Adaptive output budgets are opaque, unstable, or controlled by repository content                | Results become irreproducible, context floods, or a checkout steers agent behavior                                              | Versioned TOML policy and digest, source-free deterministic inputs, applied-budget metadata, cursor binding, human-owned authority, fixed protocol ceilings, task-level matrix evaluation                                                                      |
| Adaptive-budget TOML changes race searches or a typo disables discovery                          | Mixed-policy pages, inconsistent clients, or avoidable loss of agent workflow                                                   | Cheap per-search fingerprint, immutable pinned snapshot, atomic durable last-known-good, explicit invalid/degraded metadata, shipped fallback only when no valid snapshot exists, cursor expiry                                                                |
| Configuration helpers grow into a second administration surface                                  | Human commands overwrite policy, MCP gains writes, or setup changes behavior implicitly                                         | Exactly three fixed-path subcommands, create-only no-replace init, observational validate/show, one serialization flag, command/help/side-effect snapshots                                                                                                     |
| Intent rules overfit wording or become an unreviewed policy engine                               | Broad questions receive too little evidence, simple questions waste context, or later implementations change behavior invisibly | Tiny closed ruleset, budget-only effect, versioned metadata/identity, source/provider/config isolation, task-level ablation, future release gate                                                                                                               |
| Snippet token accounting drifts or metadata becomes a budget bypass                              | Responses exceed the agent's intended context, evaluations cannot reproduce settings, or arbitrary prose escapes the ceiling    | Bundled digest-verified tokenizer, exact final-string assertion, per-snippet/aggregate counts, closed bounded metadata, cursor/version binding, boundary/adversarial tests                                                                                     |
| Hybrid snippet allocation is unstable or favors one giant result                                 | Agents miss distinct evidence, repeated searches vary, or tuning grows into a public engine surface                             | Three-seed pass, fixed whole-action tiers, stable tie-breaks, closed reasons/version, final hard accounting, matched task-level ablation                                                                                                                       |
| Search pagination changes budgets/order or repeats evidence                                      | Agents over-consume context, miss candidates, or trust a page assembled from incompatible state                                 | Per-page pinned budgets, finite deduplicated sequence, integrity-bound offset/index/versions, full pre-read validation, page-concatenation and tamper tests                                                                                                    |
| A clever search union is rejected or interpreted differently by agent clients                    | Search calls fall back to best effort, agents send mixed modes, or generated adapters drift                                     | One nested strict-compatible `anyOf`, all-required/nullable fields, extras forbidden, OpenAI strict-ingestion test, canonical cross-client schema digest                                                                                                       |
| Search cursors leak query/source or pin state indefinitely                                       | Private code/search intent persists, GC cannot reclaim artifacts, or retries behave inconsistently                              | Source-free pointer state, digest-only immutable handles, deterministic replay/successors, exact non-extending 30-minute reachability, expiry/compaction/leakage tests                                                                                         |
| A large continuation horizon reruns expensive search or becomes configurable                     | Later pages incur provider/engine cost, ranking shifts, or repository settings steer retrieval depth                            | Fixed 500-pointer first-page plan, source-free state, continuation no-retrieval boundary, explicit horizon metadata, 501+ and zero-call tests                                                                                                                  |
| Optional cursor persistence failure discards correct search evidence                             | A local write problem turns a useful read into failure or causes costly automatic reruns                                        | Total continuation state, proven-cursor boundary, complete-page preservation, no provider/retrieval/GC retry, fault-boundary and orphan-expiry tests                                                                                                           |
| Relevance bands imply false confidence or drift across ranking modes                             | Agents over-trust weak evidence, labels change across pages, or a fallback inherits invalid thresholds                          | Non-probabilistic guidance, exact mode/policy profiles, preregistered disjoint held-out gates per band, fail-closed support/uncertainty/stability rules, version/digest and cursor/cache binding, conservative `exploratory` fallback, raw-score leakage tests |
| Relevance judgments reward similarity instead of task utility or leak candidate labels           | Calibration certifies plausible-looking but unhelpful hits, duplicate evidence, or the evaluator's own policy                   | Frozen direct/supporting/not-useful rubric, canonical pinned views, earlier-target redundancy context only, reviewer blinding, closed reasons, immutable rubric/view digests, adversarial examples                                                             |
| One reviewer's judgments are inconsistent or an AI judge creates false consensus                 | Precision gates reflect mood/recall/model bias rather than stable task utility                                                  | Seven-day two-pass pilot, hidden stratified held-out repeats, exact-agreement and quadratic-kappa gates, conservative disagreement, fresh evidence after failure, diagnostic-only model output                                                                 |
| Global calibration hides failures for a language, large scope, filters, or deep ranks            | A generally passing band overstates weak evidence in a specific agent workflow                                                  | Five closed marginal runtime strata, per-band all-cells support, deterministic evaluator/runtime keys, affected-hit fallthrough, diagnostic-only cross-products, boundary tests                                                                                |
| Calibration leaks repositories/tasks or lets one query manufacture support                       | Held-out precision measures memorization or correlated result volume rather than transfer                                       | Repository- and task-family-disjoint partitions, derivative inheritance, frozen held-out access, label-blind one-per-query sampling, immutable manifests, contamination failure                                                                                |
| Synthetic benchmarks certify confidence or evaluation source leaks into release artifacts        | Relevance bands fail on real work, licensing/trust is harmed, or third-party code is redistributed unintentionally              | Real permissively licensed pinned repos and original human tasks for authority, diagnostic-only generated/fixture material, private bounded-retention workspace, source-free provenance, artifact leakage gates                                                |
| Corpus licensing is ambiguous or a nested subtree has different terms                            | Evaluation admits material outside the intended policy or requires subjective legal analysis                                    | Six-ID SPDX allowlist, all-leaves/no-exception parser rule, license/nested-coverage digests, pre-task subtree exclusion, fail-closed ambiguity, no prose inference or override                                                                                 |
| Private evaluation source persists indefinitely or cleanup reaches original work                 | Third-party code/raw judgments accumulate or developer repositories are damaged                                                 | Fixed seven/90/30-day non-extending deadlines, pre-read expiry, exact run-root manifests, contained idempotent cleanup, no daemon/product surface, original-repository preservation tests                                                                      |
| More lifecycle tools increase destructive capability                                             | Agent can damage useful index state                                                                                             | One receipt-scoped logical-release tool; no arbitrary target, source deletion, force, or direct GC; active-use and reachability checks                                                                                                                         |
| A cleanup receipt leaks or is applied to the wrong lifecycle                                     | An unrelated or newly re-registered workspace becomes unavailable                                                               | 256-bit capability, epoch/domain binding, digest-only persistence, constant-time validation, prefix redaction, one-shot consumption, bounded replay tombstone, adversarial concurrency tests                                                                   |
| An abandoned cleanup intent freezes an otherwise usable workspace                                | Agents cannot sync/index after a failed cleanup attempt                                                                         | Fixed 30-second TTL, active-call-only five-second renewal, immediate logical expiry, operation-scoped cancellation, safe new-operation recovery tests                                                                                                          |
| A new read slips in after cleanup intent or a pre-admitted result hides lifecycle change         | An agent acts on a workspace being released or receives misleading multi-workspace coverage                                     | Atomic admission ordering, reader leases, all-or-nothing rejection, serialization recheck, typed lifecycle warning, zero-work boundary tests                                                                                                                   |
| Abandoned-cleanup recovery duplicates work or revives cancellation                               | Unwanted provider cost, watcher races, or stale publication                                                                     | One epoch-scoped recovery marker, lease/CAS claim, cheap reconciliation, new deduplicated operation only, normal reuse/preflight, crash matrix                                                                                                                 |
| Cleanup UX exposes internal policy knobs                                                         | Agents make unsafe or inconsistent lifecycle decisions                                                                          | Frozen two-field schema, four-step guidance, unknown-field rejection, no cleanup modes/force/GC/timing controls, contract snapshots                                                                                                                            |
| A forgotten epoch leaks into MCP listing or resolution                                           | An agent searches or acts on a workspace the user intentionally released                                                        | One centralized actionable-workspace predicate across list/resolution/boundaries, aggregate-only status, no MCP include flag, contract and race tests                                                                                                          |
| Post-forget identity matching merges a reused path with the wrong worktree                       | Old authority/state contaminates a new checkout or references revive incorrectly                                                | Unique strong family/worktree proof, fresh epoch/receipt/publication, new ID on doubt, separate artifact verification, adversarial path-reuse and concurrency tests                                                                                            |
| Search adds context without improving outcomes                                                   | More cost and slower agents                                                                                                     | Control/treatment task evaluations and strict response budgets                                                                                                                                                                                                 |
| Background watchers or abandoned MCP runtimes leak resources                                     | Poor laptop experience                                                                                                          | Ownership locks, bounded lifecycle, crash and soak tests                                                                                                                                                                                                       |
| Last-client exit loses progress, leaves partial state, or implicitly forgets a workspace         | Repeated work, redundant OpenAI calls, lost registration, or incorrect search                                                   | Bounded phase checkpoints, exact embedding-cache commits, isolated staging, five-second drain, lease expiry, explicit-only forgotten transition, next-launch resume tests                                                                                      |
| A hidden worker survives upgrade or uninstall                                                    | Ghost CPU/network/filesystem activity and version conflicts                                                                     | No launchd/login registration or detach path, process-owned children only, packaging/uninstall and orphan-process assertions                                                                                                                                   |
| Two live runtimes race to resume the same operation                                              | Duplicate writes, embeddings, or publication                                                                                    | Renewable execution lease, short compare-and-set claims, idempotent work units, one atomic publisher                                                                                                                                                           |
| SQLite and LanceDB disagree after an interrupted publication                                     | Partial, missing, or mixed-generation search results                                                                            | SQLite-only visibility pointer, generation-scoped staging IDs, verified vector commit tokens, explicit reconciliation, and failure injection at every boundary                                                                                                 |
| A vector query is issued without a published snapshot scope                                      | Another worktree's or generation's chunks can leak into results                                                                 | Snapshot-required `VectorStore` API, no raw backend access outside `kb/store/`, exact-scope assertions, and reader leases through materialization                                                                                                              |
| A LanceDB upgrade changes storage, indexing, or concurrency behavior                             | Reopen failures, recall regression, corruption, or packaging breakage                                                           | Exact qualified pin, narrow adapter, clean-install/reopen/concurrency/crash/recall gates, and deliberate upgrade qualification                                                                                                                                 |
| Reusable vector projections accumulate across branches and worktrees                             | Disk use grows despite embedding reuse                                                                                          | Content-addressed reuse, generation reachability, protected reader leases, measured retention, safe GC, and multi-worktree disk benchmarks                                                                                                                     |
| GC reachability is stale or wrong for shared worktree artifacts                                  | Current snippets/vectors disappear or a published generation corrupts                                                           | SQLite-authoritative plan snapshot, protection tiers, maintenance lease, immediate pre-delete recheck, adapter idempotency, publication/GC race tests                                                                                                          |
| Pressure thresholds are too tight and churn reusable generations                                 | Repeated parsing/embedding cost and slower branch/worktree adoption                                                             | Large calibrated soft cap, low-water hysteresis, deterministic cost-aware LRU tiers, measured call-count/latency/disk soaks before freeze                                                                                                                      |
| Disk fills after preflight but before cross-store publication                                    | Partial native writes, failed operations, or provider spend with no usable generation                                           | Conservative peak/crash reserve, phase remeasurement, `ENOSPC` classification, stop provider work, old pointer retention, resumable reconciliation                                                                                                             |
| Retained chunk artifacts surprise a developer or outlive the executable                          | Unexpected local source retention or disk use                                                                                   | Up-front accurate disclosure, private permissions, content-only names, aggregate diagnostics, documented reachability/GC, explicit uninstall semantics                                                                                                         |
| A corrupt or wrongly scoped chunk artifact is materialized as a snippet                          | Incorrect or cross-workspace source context undermines task correctness                                                         | Snapshot-authorized SQLite membership, immutable digest/length verification, reader leases, fail-closed typed errors, adversarial corruption/scope tests                                                                                                       |
| `open_ref` returns stale text as current or follows a raced/unsafe path                          | Agent edits the wrong code or reads newly ineligible content                                                                    | Current-only typed contract, issued-reference membership, secure stable-descriptor reread, exact-only alignment, prominent drift, boundary/policy race tests                                                                                                   |
| An opaque reference is trusted without authoritative membership proof                            | Guessed/remixed tokens expose another workspace or bypass retention                                                             | High-entropy scoped components, exact workspace-publication-target lookup, current safety validation, constant-shape invalid/expired failures, no fallback                                                                                                     |
| Private local state is mistaken for an encrypted vault                                           | Developers retain sensitive derived source under a stronger threat-model assumption than Dolphin provides                       | Explicit pre-enrollment/plaintext disclosure, exact private modes/ownership, FileVault advice, `application_encryption = none`, documented same-user/admin/unlocked-session exclusions                                                                         |
| Backend or crash-created files bypass private modes                                              | Source, vectors, logs, or configuration backups become readable to another local account                                        | Descriptor-based creation/audit, backend adapter verification, permissive-umask tests, fail-before-open on unfixable state                                                                                                                                     |
| An unsupported Intel, Rosetta, pre-macOS-14, or non-macOS runtime proceeds partway through setup | Confusing native-dependency failures or a partially initialized store                                                           | Explicit Apple Silicon macOS 14+ statement, shared preflight before mutation, typed `UNSUPPORTED_PLATFORM`, negative boundary tests                                                                                                                            |
| A native dependency works on the newest macOS but not the 14.0 deployment floor                  | Install/import/runtime failure on a promised supported major                                                                    | Exact wheel/Mach-O inspection, no source builds, latest-patch native arm64 matrix, full backend/parser/watch/process smoke suite per major                                                                                                                     |
| An unqualified Python interpreter reaches native storage or parser code                          | ABI failures, inconsistent indexes, or an installation that passes setup but fails on first use                                 | CPython 3.13-only metadata and commands, shared early `UNSUPPORTED_PYTHON` preflight, one CI/runtime matrix, native-wheel qualification                                                                                                                        |
| Worktrees share Git history but diverge in files                                                 | An agent receives another agent's branch or dirty state                                                                         | First-class workspace IDs, isolated overlays/namespaces, scoped references, cross-contamination tests                                                                                                                                                          |
| New worktrees redundantly embed their unchanged base                                             | Slow parallel-agent startup and needless API use                                                                                | Reusable commit generations, Git-diff derivation, content-addressed artifacts, zero-call acceptance tests                                                                                                                                                      |
| Missing worktrees and reusable generations accumulate                                            | Unbounded disk growth                                                                                                           | Grace-period tombstones, storage-pressure LRU, reachability GC, dry-run and safety tests                                                                                                                                                                       |
| Rust parsing appears supported but fails on real projects or requires a local toolchain          | Incorrect results or broken clean installation                                                                                  | Embedded parser dependency, no build-script execution, diverse Rust fixtures, multi-crate agent-value gates, clean macOS wheel smoke test                                                                                                                      |
| Runtime paths are reconstructed inconsistently or mishandle `Application Support`                | Corruption, split state, unsafe cleanup, or failed GUI launch                                                                   | One injected typed layout, canonical containment checks, spaces/symlink/permission tests, doctor visibility                                                                                                                                                    |
| Codex and Claude adapters drift despite sharing one MCP server                                   | Agents enroll/search differently or receive stale commands                                                                      | Canonical typed guidance/tool specs, generated thin adapters, source digests, normalized parity tests, shared smoke scenarios                                                                                                                                  |
| Automated client setup overwrites user configuration or leaks credentials                        | Broken agent setup or secret exposure                                                                                           | Explicit client target, dry-run, native APIs, ownership markers, digest preconditions, atomic rollback, value-free environment forwarding, redaction tests                                                                                                     |
| Global and project client entries shadow one another                                             | A stale or wrong Dolphin command runs in one worktree                                                                           | User-scope default, explicit project override, effective-entry diagnostics, digest/version checks, scope-specific mutation/removal                                                                                                                             |
| A partially built first index looks complete to an agent                                         | False-negative search results undermine task correctness                                                                        | Unpublished staging generations, atomic publication, typed `INDEX_BUILDING`, strict multi-workspace coverage, crash/failure visibility tests                                                                                                                   |
| Lexical fallback silently masquerades as normal semantic retrieval                               | Agent trusts incomplete retrieval or treats fallback relevance as equivalent to hybrid retrieval                                | Strict failure taxonomy, cache-first ladder, explicit execution mode, separately calibrated bands, cursor binding, degraded-path evaluations                                                                                                                   |
| Parent indexing crosses a submodule boundary                                                     | Duplicate embeddings, mixed identities, or unintended external-repository disclosure                                            | Gitlink exclusions shared by every pipeline path, explicit child enrollment, deepest-root resolution, no submodule mutation/network calls                                                                                                                      |
| Parent indexing crosses an independent nested-repository boundary                                | Unintended disclosure, duplicate embeddings, mixed Git identities, or stale child code returned as parent content               | Metadata-first marker discovery, stop-before-descent exclusion, immediate search masking, explicit child enrollment, deepest-root tests                                                                                                                        |
| An invalid or fixture `.git` marker masks useful parent content                                  | False-negative search until the boundary is understood                                                                          | Report the exact blocked boundary and state, provide safe remediation, test common fixture layouts, and prefer omission over crossing an ambiguous repository boundary                                                                                         |
| A checked-out repository policy widens disclosure or changes runtime behavior                    | A repository can expose ignored local files, weaken safety, or create inconsistent installs                                     | Closed include/exclude-only schema, Git candidacy before includes, immutable hard denials, no inheritance/interpolation, unknown-key failure, Dolphin never writes the file                                                                                    |
| Policy changes unnecessarily rebuild a worktree                                                  | Slow branch switching and redundant OpenAI cost                                                                                 | Canonical policy digests, eligibility deltas, content-addressed chunk reuse, exact embedding-cache reuse, call-count tests                                                                                                                                     |
| A fuse approval becomes a standing or cross-repository bypass                                    | Runaway traversal or unintended disclosure after the reviewed scope changes                                                     | Exact versioned fingerprint, one operation/workspace, TTY confirmation, no automation/global setting, short expiry, atomic one-shot claim, full snapshot revalidation                                                                                          |
| Human approval holds a writer lock or races another runtime                                      | Search/index stalls or multiple operations consume one authority                                                                | Full preflight and prompt outside locks, short compare-and-set transaction, durable state machine, one claimant, crash/race tests                                                                                                                              |
| Heavy reranking survives as an unproven optional path                                            | Multi-gigabyte installs, inconsistent results, and maintenance burden without task value                                        | Pre-registered agent-task ablation, binary remove-or-standard decision, fixed weights/provenance, no MCP selector                                                                                                                                              |
| Knowledge-graph complexity survives without task value                                           | Stale/false context, larger stores, slower indexing, and heavy dependencies                                                     | Pre-registered graph ablation, false-edge audit, binary remove-or-standard decision, no graph knob                                                                                                                                                             |
| Local diagnostics either leak code/secrets or grow without bound                                 | Loss of trust, disk pressure, or noisy agent output                                                                             | Closed redacted schemas, no raw queries/source/provider payloads, fixed cardinality, private capped logs, compact windowed snapshots, adversarial tests                                                                                                        |
| Removing the external monitoring stack leaves failures opaque                                    | Solo developers cannot recover without deep debugging                                                                           | Actionable structured failure codes, current-process `status`, active-process `doctor` snapshots, persisted operation counters, explicit profiling workflows                                                                                                   |
| Aggressive cleanup removes useful behavior                                                       | Regression during clean break                                                                                                   | Inventory behaviors, retain outcome tests, remove contracts intentionally                                                                                                                                                                                      |
| Unified publishing partially succeeds                                                            | Mismatched components                                                                                                           | Test once, publish from one immutable commit, coordinated verification                                                                                                                                                                                         |
