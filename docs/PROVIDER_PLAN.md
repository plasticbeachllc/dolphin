# Provider Implementation Plan

## Scope
Implement the multi-provider architecture described in `docs/PROVIDER.md`, covering OpenAI GPT 5.1 family, Anthropic Claude 4.5 family (subscription + API auth), and user-defined OpenAI-compatible inference endpoints. Initial scope explicitly limits embeddings to the OpenAI family and standardizes on the `text-embedding-3-*` models (default `text-embedding-3-large`, optional `text-embedding-3-small`, ready for future IDs); there is still no auto-failover between vendors.

## Milestones

1. **Manifest + Types**
   - Define `provider_config.toml` manifest.
   - Generate shared TS/Python types and validators.
2. **Auth + Config Layer**
   - Implement auth resolution (API key, subscription token, custom endpoint base URL overrides).
   - Add env validation CLI: `uv run dolphin providers check`.
3. **Client Factories**
   - Build `createProviderClient` (TS) and `create_provider_client` (Python) with middleware hooks.
   - Implement OpenAI + OpenAI-compatible client wrapper.
   - Implement Anthropic client wrapper with dual-mode auth.
4. **Invocation Layer + KB Alignment**
   - Introduce shared `invoke_model` helper with streaming + chunk normalization.
   - Update Agent Core + MCP Bridge to consume helper, ensuring provider selection is explicit per request (no auto-failover shims).
   - Add a Python manifest loader consumed by `kb/embeddings/provider.py` so the KB ingestion stack validates embedding models against the TOML manifest (default + overrides) and reuses shared auth/base URL logic.
   - Remove the hard-coded embedding dimension map in the KB pipeline in favor of manifest-derived metadata; extend KB tests to cover manifest-driven selection.
5. **Custom Endpoint Support**
   - Parse optional `~/.dolphin/providers.d/*.json` overrides.
   - Document user workflow for specifying model IDs + base URL.
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
| User-provided endpoints deviating from spec | Allow per-endpoint schema overrides + extensive logging for debugging. |
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
