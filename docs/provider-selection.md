# Provider Selection and Multi-Model Strategy

This document proposes an initial framework for expanding Dolphin's supported inference providers beyond the existing Vlaude subscription and Anthropic API key setups. It focuses on adding OpenAI endpoints while defining reusable abstractions so that future providers (Azure OpenAI, Google, etc.) can be added with minimal effort.

## Goals

1. **Flexible Provider Registry** – Allow runtime selection of a model provider, decoupled from call sites.
2. **Unified Capability Matrix** – Capture what each provider supports (chat completions, tool use, streaming, vision, JSON modes, etc.).
3. **Consistent Configuration** – Normalize environment variables, secrets, and rate-limit safety.
4. **Provider-Agnostic UX** – Keep CLI, MCP bridge, and Agent Core workflows identical regardless of the backend.
5. **Extensible Testing** – Ensure new providers have smoke tests, replay fixtures, and guardrails for cost/regressions.

## Terminology

| Term       | Definition                                                                        |
| ---------- | --------------------------------------------------------------------------------- |
| Provider   | Logical API backend (Anthropic, OpenAI, Vlaude, etc.).                            |
| Plan       | Billing plan or account type (Vlaude subscription, pay-as-you-go API).            |
| Model      | Specific deployable model (claude-3.5-sonnet, gpt-4o, etc.).                      |
| Capability | Feature supported by a provider/model (function calling, streaming, image input). |

## Current State Snapshot

| Surface Area          | Current Behavior                                                                               |
| --------------------- | ---------------------------------------------------------------------------------------------- |
| **Agent Core**        | Hard-coded Anthropic + Vlaude flows. Env vars: `ANTHROPIC_API_KEY`, Vlaude subscription token. |
| **MCP Bridge**        | Same as Agent Core. Provider logic lives inside handler modules, not abstracted.               |
| **VS Code Extension** | Assumes back-end providers exist but does not expose selection UI.                             |
| **Docs/Onboarding**   | Mentions only Anthropic/Vlaude flows.                                                          |

## High-Level Architecture Changes

1. **Provider Registry Module**
   - Central map: `provider_id -> ProviderConfig`.
   - Responsible for validation, capability lookup, default models.
   - Lives in shared package (likely `shared/providers/`).

2. **Client Factory Layer**
   - Returns typed client (Anthropic SDK, OpenAI SDK, custom HTTP).
   - Handles retries, telemetry tagging, PII scrubbing.

3. **Call Site Refactor**
   - Replace direct Anthropic/Vlaude references with provider-agnostic `invoke_model(request)` calls.
   - Ensure MCP bridge and Agent Core share the same invocation contract.

4. **Configuration Surface**
   - Add `DOLPHIN_PROVIDER=openai|anthropic|vlaude|auto` with overrides (per-scenario, per-agent).
   - Support env-var namespace per provider (e.g., `OPENAI_API_KEY`, `OPENAI_BASE_URL`).

5. **Observability**
   - Provider-specific metrics (latency, cost, retries) for dashboards.
   - Structured logs include `provider_id`, `model`, and response metadata.

## OpenAI Provider Requirements

### Supported Endpoints

| Endpoint                    | Purpose                     | Notes                                                                     |
| --------------------------- | --------------------------- | ------------------------------------------------------------------------- |
| `POST /v1/chat/completions` | Chat + tool-calling         | Support `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `o1`, `gpt-4o-audio-preview`. |
| `POST /v1/responses`        | Unified reasoning interface | Needed for o1-style models.                                               |
| `POST /v1/embeddings`       | Embeddings                  | Map to Dolphin KB embedding pipeline.                                     |

### Configuration

| Variable               | Example                     | Description                                |
| ---------------------- | --------------------------- | ------------------------------------------ |
| `OPENAI_API_KEY`       | `sk-...`                    | Required for all OpenAI calls.             |
| `OPENAI_BASE_URL`      | `https://api.openai.com/v1` | Optional for Azure/on-prem proxies.        |
| `OPENAI_ORG_ID`        | `org_...`                   | Optional header when needed.               |
| `OPENAI_PROJECT_ID`    | `proj_...`                  | Optional; some enterprise orgs require it. |
| `OPENAI_DEFAULT_MODEL` | `gpt-4o-mini`               | Fallback if agent config does not specify. |

**Secret Management**

- Mirror existing `.env` loading conventions (`env.example`, `shared/config`).
- Clarify precedence: CLI flags > per-agent config > `OPENAI_DEFAULT_MODEL`.
- Add validation CLI command (`uv run dolphin providers test openai`).

### Capability Matrix (Initial)

| Capability   | `gpt-4o` | `gpt-4o-mini` | `gpt-4.1` | `o1`                        |
| ------------ | -------- | ------------- | --------- | --------------------------- |
| Tool Calling | ✅       | ✅            | ✅        | ⚠️ (limited)                |
| Streaming    | ✅       | ✅            | ✅        | ⚠️ (currently no streaming) |
| JSON Mode    | ✅       | ✅            | ✅        | ❌                          |
| Vision       | ✅       | ✅            | ✅        | ⚠️ (text only)              |
| Audio Input  | ✅       | ✅            | ✅        | ❌                          |
| Audio Output | ✅       | ✅            | ✅        | ❌                          |

## Migration Steps

1. **Design**
   - Finalize provider registry schema (YAML/TS/py dataclasses?).
   - Decide canonical provider identifiers (e.g., `anthropic`, `openai`, `vlaude`).

2. **Shared Utilities**
   - Implement provider registry + capability lookup.
   - Provide typed request/response models for chat + embeddings.

3. **OpenAI Client**
   - Wrap OpenAI SDK (Node + Python) or use `fetch`/`httpx` manually for deterministic logging.
   - Ensure user-agent header identifies Dolphin build + surface (Agent Core vs MCP).

4. **Integration into Agent Core**
   - Extend orchestrator config schema with `provider` field.
   - Support per-task overrides (e.g., research uses `o1`, quick replies use `gpt-4o-mini`).

5. **Integration into MCP Bridge**
   - Mirror the provider selection logic; ensure tool-call payloads translate correctly.

6. **CLI / KB Updates**
   - Add `openai` option in KB embedding settings.
   - Provide migration script to map existing `ANTHROPIC_API_KEY` usage.

7. **Testing**
   - Mocked unit tests for provider registry.
   - Replay tests using recorded OpenAI responses (vcrpy / Polly).
   - Optional smoke test script (manual) to verify credentials.

8. **Docs and Onboarding**
   - Update README + docs/ARCHITECTURE with new provider narrative.
   - Add troubleshooting section (rate limits, 429 handling, network proxies).

## Security & Compliance

- **PII Controls**: Reuse existing redaction filters before payload logging.
- **Least Privilege**: Encourage dedicated OpenAI project per deployment; document RBAC steps.
- **Key Rotation**: Provide script/CLI to test and rotate keys safely.
- **Data Residency**: Document that OpenAI defaults to US; note options for Azure OpenAI in future.

## Telemetry & Cost Awareness

- Add provider tag to telemetry events (OpenTelemetry spans, metrics).
- Track per-provider token usage to support budgeting dashboards.
- Provide opt-in prompt/response sampling for debugging, respecting privacy settings.

## Open Questions

1. Should provider registry live in shared TypeScript + Python packages, or should we generate artifacts from a single source (e.g., YAML -> codegen)?
2. How do we unify tool schemas when providers enforce different shapes (Anthropic vs OpenAI function calling)?
3. Do we need feature flags to roll out OpenAI gradually? (e.g., `DOLPHIN_PROVIDER=openai` for canaries only.)
4. What SLA differences must we surface to users (latency, context window, cost multipliers)?

## Next Steps Checklist

- [ ] Confirm registry data model + storage location.
- [ ] Draft configuration examples for `.env`, CLI, and VS Code UI.
- [ ] Prototype OpenAI client wrapper with logging + retries.
- [ ] Integrate provider selection into Agent Core orchestrator.
- [ ] Add docs section covering provider selection UI/CLI flows.
- [ ] Plan QA and smoke testing for OpenAI rollout.
