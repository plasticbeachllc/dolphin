# Provider Implementation Plan

_Last updated: 2025-02-14_

## Phase 1 (Agent Core) Alignment

The first implementation milestone focused on getting the Agent Core to boot with
both Anthropic and OpenAI models, mirroring the original Phase 1 charter for the
provider initiative. The following deliverables are covered by the current code
base:

| Deliverable                                      | Status | Notes |
| ------------------------------------------------ | :----: | ----- |
| Shared chat provider abstraction (`ChatProvider`) |  ✅   | Implemented in `agent-core/src/execution/chat-provider.ts` and adopted by the orchestrator/editor/architect workflows. |
| Anthropic + OpenAI client wrappers               |  ✅   | `AnthropicProvider` keeps the CLI + API dual-mode AuthManager, while `OpenAIProvider` uses the new OpenAI Responses adapter with streaming/tool support. |
| Tool execution engine with provider adapters     |  ✅   | `ToolExecutorEngine` powers both Anthropic and OpenAI adapters (`anthropic-tool-executor.ts`, `openai-tool-executor.ts`). |
| Provider selection knobs                         |  ✅   | `~/.dolphin/config` + `DOLPHIN_*` env vars select provider/model/temperature; a custom OpenAI-compatible base URL/API key are now supported via `provider.openai` overrides. |
| MCP workflow integration                         |  ✅   | Both providers use the same MCP tool loop and bubble up token usage to orchestrator telemetry. |

**Default models:** Phase 1 now ships with `claude-sonnet-4-5-20250929` for the Anthropic path. When the OpenAI provider is selected, the editor/coding workflow defaults to `gpt-5.1-codex` while the architect workflow defaults to `gpt-5.1`, keeping runtime behavior aligned with the plan's "Claude 4.5" / "GPT 5.1" targeting without extra configuration.

### Remaining Gaps vs. Original Plan

The broader provider roadmap in `docs/PROVIDER.md` still includes several items
that are **not** part of the Phase 1 Agent Core drop:

- Canonical `provider_config.toml` manifest + JSON Schema generation (still
  tracked, but the runtime currently consumes `~/.dolphin/config`).
- CLI `providers check` validation command.
- GUI workflow for collecting a custom OpenAI-compatible endpoint.
- Dynamic pricing feed and cost estimators.
- MCP Bridge / VS Code wiring (Agent Core only so far).

Those gaps are now explicitly noted here to avoid ambiguity between the plan and
the repository state. Subsequent phases should re-use the abstractions landed in
Phase 1 to flesh out the remaining milestones.

## Scope

Implement the multi-provider architecture described in `docs/PROVIDER.md`,
covering OpenAI GPT 5.1 family, Anthropic Claude 4.5 family (subscription + API
auth), and a user-provided OpenAI-compatible inference endpoint surfaced through
the GUI (re-using the OpenAI wrapper). The canonical `provider_config.toml`
ships read-only with every runtime (no user-editable manifest) and is backed by
a checked-in JSON Schema that drives every generated type. The scope is limited
to LLM inference clients (Agent Core, MCP Bridge, VS Code extension); the
existing KB embedding APIs stay untouched. Initial scope explicitly limits
embeddings to the OpenAI family and standardizes on the `text-embedding-3-*`
models (default `text-embedding-3-large`, optional `text-embedding-3-small`,
ready for future IDs); there is still no auto-failover between vendors.

### Non-Goals

- No changes to `kb/` ingestion, embedding selection, or LanceDB schemas.
- No new KB authentication or configuration settings tied to the provider
  manifest.
- No attempt to route KB embedding calls through the shared provider factory in
  this release.

## Milestones

1. **Manifest + Types**
   - Define the canonical `provider_config.toml` manifest plus sibling
     `docs/provider_config.schema.json` JSON Schema (source of truth for
     validation/type generation).
   - Bundle the manifest with every LLM inference surface (Agent Core, MCP
     Bridge, CLI helpers, VS Code extension) so they all consume the exact same
     baked-in file.
   - Generate shared TS/Python types and validators from the schema (e.g.,
     `json-schema-to-typescript`, `datamodel-code-generator`) and ensure
     manifest keys can include vendor dots by quoting TOML tables (e.g.,
     `[models."gpt-5.1"]`).
   - Capture embedding metadata (default/optional models, vector dimensions,
     OpenAI requirement flag) directly in the manifest for completeness even
     though the KB stack remains unchanged in this release.
2. **Auth + Config Layer**
   - Implement auth resolution (API key, subscription token, GUI-supplied
     OpenAI-compatible base URL + key) that reuses the manifest loaders.
   - Add env validation CLI: `uv run dolphin providers check`, powered by the
     same shared schema/validator packages used in runtime code to avoid
     duplicate logic.
3. **Client Factories**
   - Build `createProviderClient` (TS) and `create_provider_client` (Python) with
     middleware hooks.
   - Implement OpenAI + OpenAI-compatible client wrapper.
   - Implement Anthropic client wrapper with dual-mode auth.
4. **Invocation Layer Integration**
   - Introduce shared `invoke_model` helper with streaming + chunk
     normalization.
   - Update Agent Core + MCP Bridge to consume helper, ensuring provider
     selection is explicit per request (no auto-failover shims).
   - Ensure CLI + VS Code surfaces call the shared helper rather than
     maintaining bespoke OpenAI logic.
5. **Custom Endpoint Support**
   - Expose a GUI workflow for users to provide an OpenAI-compatible base URL +
     API key (no manifest overrides).
   - Persist GUI inputs via the existing OpenAI client wrapper so only the
     approved options—Claude (subscription/API key), OpenAI (API key), or
     OpenAI-compatible endpoint—are surfaced to end users.
6. **Dynamic Pricing Feed**
   - Build `load_pricing_feed` service pulling provider-owned pricing JSON/CSV
     and caching to disk/db.
   - Wire CLI/UI cost estimators to feed output instead of manifest data.
7. **Testing + QA**
   - Registry unit tests; HTTP contract tests (MSW/vcrpy).
   - Smoke scripts for OpenAI + Anthropic + compatibility endpoint.
   - Load testing of retry/backoff logic using mocked throttling.
   - Feed refresh tests covering offline fallback + TTL expiry.
8. **Docs & UX**
   - Update README, onboarding, VS Code settings copy.
   - Publish troubleshooting + migration guidance.

## Deliverables Checklist

- [ ] Manifest + type generation
- [ ] Auth/config utilities
- [ ] Provider clients (OpenAI, OpenAI-compatible, Anthropic)
- [ ] Shared invocation helper
- [ ] Integration into Agent Core + MCP Bridge
- [ ] Dynamic pricing feed + estimators
- [ ] Compatibility + smoke tests
- [ ] Documentation updates + migration guide
