# Provider Implementation Plan

## Scope
Implement the multi-provider architecture described in `docs/PROVIDER.md`, covering OpenAI GPT 5.1 family, Anthropic Claude 4.5 family (subscription + API auth), and a user-provided OpenAI-compatible inference endpoint surfaced through the GUI (re-using the OpenAI wrapper). The canonical `provider_config.toml` ships read-only with every runtime (no user-editable manifest) and is backed by a checked-in JSON Schema that drives every generated type. Initial scope explicitly limits embeddings to the OpenAI family and standardizes on the `text-embedding-3-*` models (default `text-embedding-3-large`, optional `text-embedding-3-small`, ready for future IDs); there is still no auto-failover between vendors.

## Milestones

1. **Manifest + Types**
   - Define the canonical `provider_config.toml` manifest plus sibling `docs/provider_config.schema.json` JSON Schema (source of truth for validation/type generation).
   - Bundle the manifest with every surface (Agent Core, MCP Bridge, KB, CLI, VS Code) so they all consume the exact same baked-in file.
   - Generate shared TS/Python types and validators from the schema (e.g., `json-schema-to-typescript`, `datamodel-code-generator`) and ensure manifest keys can include vendor dots by quoting TOML tables (e.g., `[models."gpt-5.1"]`).
   - Capture embedding metadata (default/optional models, vector dimensions, OpenAI requirement flag) directly in the manifest to unblock later KB alignment work.
2. **Auth + Config Layer**
   - Implement auth resolution (API key, subscription token, GUI-supplied OpenAI-compatible base URL + key) that reuses the manifest loaders.
   - Add env validation CLI: `uv run dolphin providers check`, powered by the same shared schema/validator packages used in runtime code to avoid duplicate logic.
3. **Client Factories**
   - Build `createProviderClient` (TS) and `create_provider_client` (Python) with middleware hooks.
   - Implement OpenAI + OpenAI-compatible client wrapper.
   - Implement Anthropic client wrapper with dual-mode auth.
4. **Invocation Layer + KB Alignment**
   - Introduce shared `invoke_model` helper with streaming + chunk normalization.
   - Update Agent Core + MCP Bridge to consume helper, ensuring provider selection is explicit per request (no auto-failover shims).
   - Add a Python manifest loader consumed by `kb/embeddings/provider.py` so the KB ingestion stack validates embedding models against the baked-in TOML manifest (plus any GUI-provided OpenAI-compatible endpoint settings) and reuses shared auth/base URL logic.
   - Remove the hard-coded embedding dimension map in the KB pipeline in favor of manifest-derived metadata; extend KB tests to cover manifest-driven selection.
5. **Custom Endpoint Support**
   - Expose a GUI workflow for users to provide an OpenAI-compatible base URL + API key (no manifest overrides).
   - Persist GUI inputs via the existing OpenAI client wrapper so only the approved options—Claude (subscription/API key), OpenAI (API key), or OpenAI-compatible endpoint—are surfaced to end users.
6. **Dynamic Pricing Feed**
   - Build `load_pricing_feed` service pulling provider-owned pricing JSON/CSV and caching to disk/db.
   - Wire CLI/UI cost estimators to feed output instead of manifest data.
7. **Testing + QA**
   - Registry unit tests; HTTP contract tests (MSW/vcrpy).
   - Smoke scripts for OpenAI + Anthropic + compatibility endpoint.
   - Load testing of retry/backoff logic using mocked throttling.
   - Feed refresh tests covering offline fallback + TTL expiry.
8. **Docs & UX**
   - Update README, onboarding, VS Code settings copy.
   - Publish troubleshooting + migration guidance.

## Risks & Mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Divergent payload schemas | Normalize request/response at invocation layer; add conformance tests. |
| Auth misconfiguration | Provide `providers check` command and detailed error surfaces. |
| Rate-limit instability | Central retry/backoff middleware with provider-specific caps. |
| User-provided endpoints deviating from spec | Constrain the GUI to OpenAI-compatible flows only and reuse the OpenAI client wrapper + schema validation before accepting custom URLs. |
| Bundled manifest drifting across surfaces | Version JSON Schema + manifest together and gate releases on regenerating shared TS/Python types + validator snapshots. |
| Pricing feed drift or downtime | Cache last-known-good feed locally and surface TTL/health metrics. |

## Deliverables Checklist

- [ ] Manifest + type generation
- [ ] Auth/config utilities
- [ ] Provider clients (OpenAI, OpenAI-compatible, Anthropic)
- [ ] Shared invocation helper
- [ ] Integration into Agent Core + MCP Bridge
- [ ] Dynamic pricing feed + estimators
- [ ] Compatibility + smoke tests
- [ ] Documentation updates + migration guide
