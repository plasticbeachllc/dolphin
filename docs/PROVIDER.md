# Provider Integration Specification

This document is the canonical specification for expanding Dolphin's inference layer to support multiple providers while keeping the user experience provider-agnostic. It replaces the earlier OpenAI-only proposal and now formalizes: OpenAI (GPT 5.1 family), Anthropic (Claude 4.5 family), and user-provided OpenAI-compatible endpoints.

## 1. Objectives

1. **Unify Provider Selection** – All call sites (Agent Core, MCP Bridge, VS Code, CLI) reference a single provider registry and invocation contract.
2. **Encode Capabilities** – Capture each provider's authentication methods, supported models, modalities, limits, and quirks.
3. **Enable Extensibility** – Adding a provider requires only registry data plus optional thin client code.
4. **Support Custom Endpoints** – Users can point Dolphin at any OpenAI-compatible inference URL without new code.
5. **Ship-Tested Spec** – Provide function headers, pseudocode, and QA requirements to guide implementation across TypeScript and Python surfaces.

## 2. Provider Matrix

| Provider ID         | Models (Initial)                                                                                     | Authentication                         | Modalities                                          | Notes                                                                                                                                                                                                |
| ------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `openai`            | `gpt-5.1`, `gpt-5.1-codex`, `gpt-5.1-codex-mini`, `text-embedding-3-large`, `text-embedding-3-small` | API key only (`OPENAI_API_KEY`)        | Chat, tool calling, JSON, vision, audio, embeddings | Default OpenAI cloud endpoint; GPT models serve chat/tool flows while the `text-embedding-3-*` family remains available for the existing KB pipeline but is **not** modified as part of this effort. |
| `openai-compatible` | User-provided model IDs (OpenAI spec-compliant)                                                      | API key in header plus custom base URL | Mirrors OpenAI compatibility surface                | Covers Azure OpenAI, self-hosted servers, etc.; embeddings supported when the endpoint exposes `text-embedding-3-large`, `text-embedding-3-small`, or future embedding IDs declared in the manifest. |
| `anthropic`         | `claude-4.5-sonnet`, `claude-4.5-haiku`                                                              | Subscription token **or** API key      | Chat, tool use, JSON (beta)                         | Requires dual-auth support toggled per deployment; no embedding surface yet.                                                                                                                         |

### Capability Snapshot

| Capability                                                       | gpt-5.1                     | gpt-5.1-codex               | gpt-5.1-codex-mini          | claude-4.5-sonnet | claude-4.5-haiku |
| ---------------------------------------------------------------- | --------------------------- | --------------------------- | --------------------------- | ----------------- | ---------------- |
| Context tokens                                                   | 200K                        | 200K                        | 100K                        | 200K              | 100K             |
| Tool/function calls                                              | ✅                          | ✅                          | ✅                          | ✅ (Claude tools) | ✅               |
| Streaming                                                        | ✅                          | ✅                          | ✅                          | ✅                | ✅               |
| JSON strict mode                                                 | ✅                          | ✅                          | ✅                          | ⚠️ (beta)         | ⚠️               |
| Code interpreter                                                 | ❌                          | ⚠️ (beta)                   | ❌                          | ❌                | ❌               |
| Audio input/output                                               | ✅                          | ✅                          | ✅                          | ❌                | ❌               |
| Vision                                                           | ✅                          | ✅                          | ✅                          | ✅                | ✅               |
| Embeddings (`text-embedding-3-large` / `text-embedding-3-small`) | ✅ (via dedicated endpoint) | ✅ (via dedicated endpoint) | ✅ (via dedicated endpoint) | ❌                | ❌               |

## 3. Architecture Overview

```
┌─────────────────────────┐
│ Provider Registry (TS/py│
│   provider_config.toml  │
└────────────┬────────────┘
             │
   ┌─────────▼──────────┐
   │ Client Factory     │
   │ (per surface)      │
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │ Invocation Layer   │
   │ (invoke_model)     │
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │ Call Sites         │
   │ Agent Core / MCP   │
   └────────────────────┘
```

- **Provider Registry** – Source of truth for provider metadata, auth schema, default models, throttling, and capability tags.
- **Client Factory** – Produces typed HTTP clients with shared middleware (retry, logging, PII scrubbing).
- **Invocation Layer** – Normalizes request/response payloads and surfaces streaming callbacks. Auto-failover between providers is explicitly **not** supported in the first release; callers must pick a provider per request.

## 4. Configuration Specification

### Environment Variables

| Variable                       | Description                                                    | Applies To                                  |
| ------------------------------ | -------------------------------------------------------------- | ------------------------------------------- |
| `DOLPHIN_PROVIDER`             | Default provider (`openai`, `anthropic`, `openai-compatible`). | All surfaces.                               |
| `OPENAI_API_KEY`               | API key for OpenAI models.                                     | `openai`, `openai-compatible`.              |
| `OPENAI_BASE_URL`              | Override base URL (e.g., `https://oai-proxy.company.com/v1`).  | `openai-compatible`; optional for `openai`. |
| `OPENAI_COMPAT_MODELS`         | Comma list of custom model IDs if discovery is manual.         | `openai-compatible`.                        |
| `ANTHROPIC_API_KEY`            | Claude API key auth.                                           | `anthropic`.                                |
| `ANTHROPIC_SUBSCRIPTION_TOKEN` | Subscription auth token.                                       | `anthropic`.                                |
| `ANTHROPIC_AUTH_MODE`          | `subscription` or `api-key`; default `api-key`.                | `anthropic`.                                |
| `PROVIDER_TIMEOUT_SECONDS`     | Default timeout per request.                                   | All.                                        |
| `PROVIDER_MAX_RETRIES`         | Default retry attempts.                                        | All.                                        |

### Configuration Rules

1. **Precedence**: CLI flag > per-agent config > environment default > registry default.
2. **Dual Anthropic Auth**: If both `ANTHROPIC_SUBSCRIPTION_TOKEN` and `ANTHROPIC_API_KEY` are present, prefer the mode specified by `ANTHROPIC_AUTH_MODE`.
3. **Custom OpenAI-Compatible**: Users may set `DOLPHIN_PROVIDER=openai-compatible` plus `OPENAI_BASE_URL` and `OPENAI_API_KEY`. Optional JSON config (see section 7) can extend metadata per endpoint.
4. **Embeddings**: Until additional vendor support lands, embedding creation routes must target the OpenAI family (native or compatible) and call a supported `text-embedding-3-*` model (default `text-embedding-3-large`, optional `text-embedding-3-small`). Anthropic requests should raise a configuration error and instruct operators to switch providers before re-attempting. The manifest may enumerate future OpenAI embedding IDs, and callers must respect the configured default to keep routing centralized.

## 5. Provider Registry Specification

Define a single TOML manifest (`provider_config.toml`) consumed by both TypeScript and Python via generated types.

```toml
[openai]
base_url = "https://api.openai.com/v1"
features = ["json_mode", "streaming"]

[openai.auth]
type = "api-key"
env = ["OPENAI_API_KEY"]

[openai.base_url_overrides]
env = ["OPENAI_BASE_URL"]

[openai.models.gpt-5_1]
default = true
modalities = ["text", "tool", "vision", "audio"]
max_tokens = 200000

[openai.models.gpt-5_1-codex]
modalities = ["text", "tool"]
optimized_for = "code"

[openai.models.gpt-5_1-codex-mini]
modalities = ["text", "tool"]
max_tokens = 100000

[openai.embeddings.text-embedding-3-large]
modalities = ["embedding"]
dimensions = 3072
default = true

[openai.embeddings.text-embedding-3-small]
modalities = ["embedding"]
dimensions = 1536
default = false

[openai.throttling]
rps = 60

[anthropic]
features = ["streaming"]

[anthropic.auth]
type = "multi"

[anthropic.auth.modes.api-key]
env = ["ANTHROPIC_API_KEY"]

[anthropic.auth.modes.subscription]
env = ["ANTHROPIC_SUBSCRIPTION_TOKEN"]

[anthropic.models.claude-4_5-sonnet]
default = true
modalities = ["text", "tool", "vision"]

[anthropic.models.claude-4_5-haiku]
modalities = ["text", "tool"]

[anthropic.throttling]
rps = 20
```

### Shared Type Definition (pseudo-TypeScript)

```ts
interface ProviderConfig {
  id: string;
  auth: ApiKeyAuth | MultiAuth;
  baseUrl: string;
  models: Record<string, ModelConfig>;
  features: FeatureTag[];
  throttling?: { rps: number; burst: number };
  embeddings_supported: boolean;
}
```

### Pricing Metadata & Dynamic Feed

The manifest intentionally omits static pricing to avoid staleness. A separate dynamic feed ingests provider-owned pricing files (e.g., OpenAI usage APIs, Anthropic CSV) at startup, persists them to `provider_pricing_cache.json`, and exposes accessors to the CLI/UI for cost estimation. The feed refreshes on a configurable TTL and falls back to cached values when offline. Implementation detail: `load_pricing_feed()` runs independently from manifest parsing and must handle provider-specific schemas.

## 6. Out-of-Scope: KB Embeddings

Provider work for this release is limited to LLM inference surfaces (Agent Core, MCP Bridge, CLI, and the VS Code extension). The existing knowledge-base (KB) embedding APIs, storage contracts, and auth flows remain unchanged; any future manifest alignment for embeddings will be revisited under a separate spec.

## 7. Client Factory Specification

### Function Headers (TypeScript)

```ts
// shared/providers/index.ts
export async function loadProviderConfig(id: ProviderId): Promise<ProviderConfig>;

export function createProviderClient(options: {
  providerId: ProviderId;
  surface: "agent-core" | "mcp" | "cli";
  authContext?: AuthOverride;
}): ProviderClient;

export interface ProviderClient {
  invokeModel(req: InvokeModelRequest): AsyncIterable<InvokeChunk>;
  listModels(): Promise<ModelSummary[]>;
}
```

### Function Headers (Python)

```py
# shared/providers/factory.py
from typing import AsyncIterator

async def load_provider_config(provider_id: str) -> ProviderConfig: ...

def create_provider_client(*, provider_id: str, surface: str, auth_override: dict | None = None) -> ProviderClient: ...

class ProviderClient(Protocol):
    async def invoke_model(self, request: InvokeModelRequest) -> AsyncIterator[InvokeChunk]: ...
    async def list_models(self) -> list[ModelSummary]: ...
    async def supports_embeddings(self) -> bool: ...
```

### Client Factory Pseudocode

```pseudo
function create_provider_client(provider_id, surface, auth_override):
    config = load_provider_config(provider_id)
    auth = resolve_auth(config.auth, auth_override)
    http = HttpClient(base_url=resolve_base_url(config), headers=build_headers(surface, auth))
    middleware = compose([trace_middleware(surface), retry_middleware(config), pii_scrubber])
    if provider_id in ['openai', 'openai-compatible']:
        return OpenAIClient(http, middleware)
    if provider_id == 'anthropic':
        return AnthropicClient(http, middleware)
    raise UnknownProviderError(provider_id)
```

## 8. Invocation Layer Specification

### Shared Request Schema

```ts
interface InvokeModelRequest {
  model: string;
  provider?: ProviderId;
  messages: Message[];
  tools?: ToolDefinition[];
  response_format?: "json" | "text";
  max_output_tokens?: number;
  temperature?: number;
  stream?: boolean;
}
```

### Pseudocode

```pseudo
async function invoke_model(request):
    provider = request.provider or env.DOLPHIN_PROVIDER or 'openai'
    client = create_provider_client(provider, surface=request.surface)
    if request.stream:
        async for chunk in client.invoke_model(request):
            yield normalize_chunk(chunk, provider)
    else:
        chunks = []
        async for chunk in client.invoke_model(request):
            chunks.append(chunk)
        return merge_chunks(chunks)
```

### OpenAI-Compatible Endpoint Support

- Users specify `DOLPHIN_PROVIDER=openai-compatible`.
- Required env vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL` (e.g., Azure, LM Studio, llama.cpp server following OpenAI schema).
- Optional per-endpoint config file (`~/.dolphin/providers.d/custom.json`) extends registry with custom throttling, model aliases, or TLS settings.
- Client implementation reuses OpenAI JSON wire format; only base URL / headers differ.

## 9. Authentication Workflows

### Anthropic

1. Determine mode via `ANTHROPIC_AUTH_MODE` or fallback order: `subscription` if subscription token exists, else `api-key`.
2. Subscription mode sets `X-Subscription-Token` header; API mode sets `x-api-key` header.
3. Telemetry includes `auth_mode` tag for debugging.

### OpenAI & Compatible

1. `Authorization: Bearer <OPENAI_API_KEY>` header always present.
2. Optional `OpenAI-Organization` and `OpenAI-Project` headers if env variables exist.
3. Base URL defaults to `https://api.openai.com/v1`; override allowed for compatibility endpoints.

## 10. Error Handling & Retries

| Error Type       | Strategy                                                                               |
| ---------------- | -------------------------------------------------------------------------------------- |
| 429 / Rate limit | Exponential backoff with jitter, respect provider `Retry-After`.                       |
| 5xx              | Retry up to `PROVIDER_MAX_RETRIES` with capped backoff.                                |
| Auth failures    | Fail fast with actionable error message (mention env var).                             |
| Schema mismatch  | Log provider response + request metadata (excluding PII) and surface structured error. |

## 11. Testing Requirements

1. **Unit Tests** – Provider registry parsing, auth resolution, base URL overrides.
2. **Integration Tests** – Mocked HTTP (vcrpy / MSW) verifying request payloads for each provider + auth mode.
3. **Smoke Tests** – Optional manual script `uv run dolphin providers smoke --provider openai` hitting live endpoints with environment credentials.
4. **Compatibility Tests** – JSON fixtures representing OpenAI-compatible responses to ensure normalization works for third-party servers.

## 12. Documentation & UX Updates

- Update README + onboarding to describe new providers and environment variables.
- Provide UI copy for VS Code settings: dropdown of providers plus custom endpoint fields.
- Document migration steps from legacy Vlaude/Anthropic-only stack.

## 13. Open Questions

1. Do we expose provider selection per tool type once additional embedding vendors are added?
2. What heuristics should gate the dynamic pricing feed refresh interval in offline environments?
3. When Anthropic ships embeddings, do we split the registry or extend the existing manifest schema?
