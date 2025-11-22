# Provider Selection UX - V2 Project Plan

## Objectives

- Deliver the end-to-end provider/model selection experience in the VS Code webview so users can switch providers with immediate feedback.
- Close current backend gaps (secret checks and warning surfacing) and expose richer status signals to the UI.
- Ship a tested flow that gracefully handles missing credentials and invalid settings while keeping the UX responsive.

## Current State (as of V1)

- **Configuration helpers exist** to normalize provider/model choices and emit warnings when inputs are unknown or invalid, but the warnings are not surfaced to the UI payloads. 【F:vscode-extension/src/config/provider-settings.ts†L13-L45】
- **Provider metadata and model lists** are defined and exported for UI consumption, including secret commands and descriptions. 【F:vscode-extension/src/config/provider-options.ts†L4-L70】【F:vscode-extension/src/config/provider-options.ts†L90-L106】
- **Message protocol** includes `get_provider_settings` / `save_provider_settings` and the `provider_settings` response shape but does not carry warning data. 【F:vscode-extension/src/shared/messages.ts†L34-L68】
- **View provider wiring** handles get/save settings and secret command dispatch, yet the credential existence check is stubbed (`checkSecretExists` returns `true`). 【F:vscode-extension/src/views/provider.ts†L1-L95】【F:vscode-extension/src/views/provider.ts†L113-L141】
- **Frontend webview is absent**; provider selection UI described in V1 remains unimplemented. 【F:docs/provider-selection-ux.md†L43-L58】

## Detailed Spec (V2)

### Backend contract

1. **Provider settings payload**
   - Extend `ProviderSettingsMessage` to include `warnings: string[]` and an `authStatus` per provider. Populate warnings via `resolveProviderSettings` so the UI can show normalization feedback.
   - Add `secretStatuses` array of `{ provider, ok, message? }` derived from SecretStorage checks.
2. **Secret validation**
   - Implement `checkSecretExists(secretId: string, secrets: vscode.SecretStorage)` and inject `ExtensionContext.secrets` into `DolphinViewProvider`.
   - On `save_provider_settings`, block saving if the target provider is missing a secret; reply with `settings.error { code: "missingSecret" }` and keep previous provider/model in the response.
3. **Configuration updates**
   - When saving, write both `dolphin.llm.provider` and the provider-specific model key. Return the normalized settings (after applying defaults) in a refreshed `provider_settings` message.
4. **Event routing**
   - Send `provider_settings` automatically on webview load and after any settings change.

### Frontend webview spec

1. **UI components**
   - Provider dropdown backed by `availableProviders`; model dropdown filtered by `currentProvider`.
   - Status pill per provider with states: `authenticated`, `missing-secret`, `error`.
   - Inline warning banner that lists any `warnings` returned by the backend.
2. **Flows**
   - **Initial load**: request `get_provider_settings`; render selections, status pills, and warnings.
   - **Provider change**: update model list; if selected provider lacks a secret, render a blocking prompt with CTA to "Add key" (send `{ type: "setSecret", provider }`).
   - **Save**: submit `save_provider_settings` only when secret exists; optimistic disable save button until response received.
   - **Error handling**: display `settings.error` with retry affordance; preserve previous selection on error.
3. **Accessibility and UX**
   - Keyboard navigation for both dropdowns; focus management after modal prompts.
   - Toast confirmations on successful save and secret addition.

### Message shapes (examples)

```typescript
// Extension -> Webview
{
  type: "provider_settings",
  currentProvider: "anthropic",
  currentModel: "claude-sonnet-4-5-20250929",
  warnings: ["Unknown provider \"anthropicx\". Falling back to Anthropic."],
  secretStatuses: [
    { provider: "anthropic", ok: true },
    { provider: "openai", ok: false, message: "OpenAI key not set" }
  ],
  availableProviders: [
    {
      id: "anthropic",
      label: "Anthropic (Claude 4.5)",
      description: "Use Claude Sonnet/Haiku for Dolphin workflows.",
      models: [ { id: "claude-sonnet-4-5", label: "Claude Sonnet 4.5" }, ... ]
    },
    ...
  ]
}
```

```typescript
// Webview -> Extension
{ type: "get_provider_settings" }
{ type: "save_provider_settings", provider: "openai", model: "gpt-5.1-codex" }
{ type: "setSecret", provider: "openai" }
```

## Implementation Pathways

### Backend

- Refactor `DolphinViewProvider` constructor to accept `secrets: vscode.SecretStorage`; use it in a real `checkSecretExists` implementation. 【F:vscode-extension/src/views/provider.ts†L113-L141】
- Extend `ProviderSettingsMessage` and `getCurrentProviderSettings` response construction to include warnings and secret status.
- When handling `save_provider_settings`, validate secret presence before writing settings; if missing, emit `settings.error` and resend the current `provider_settings` snapshot.
- Add telemetry logs on provider changes and failed saves to aid debugging.

### Frontend (new webview module)

- Build Svelte components for provider/model selectors and a credential status bar (reuse provider labels and descriptions from `PROVIDER_OPTIONS`). 【F:vscode-extension/src/config/provider-options.ts†L4-L70】
- Implement a controller that manages message subscription, updates local state on `provider_settings` / `settings.saved` / `settings.error`, and dispatches `get_provider_settings` on mount.
- Gate the Save action behind positive `secretStatuses` for the target provider; trigger `setSecret` otherwise and re-fetch settings after the secret flow completes.
- Render warning banners using the `warnings` array and allow dismissal per session.

### Testing Strategy

- **Backend integration tests** (`vscode-extension/src/test/suite/integration/ui/provider.test.ts`):
  - Validate secret check gating: saving without a secret yields `settings.error` and preserves previous settings.
  - Ensure warnings propagate when an unknown provider/model is supplied.
  - Confirm `provider_settings` sends per-provider `secretStatuses`.
- **Frontend unit tests** (`vscode-extension/webview/tests/`):
  - Dropdown renders correct options and model filtering.
  - Save button disabled when secret missing; re-enabled after `secretStatus { ok: true }`.
  - Warning banner displays messages from `provider_settings` and hides after dismissal.
- **E2E (Playwright)**:
  - Simulate changing providers, adding secrets via command, and verifying persisted settings and success toasts.

## Risks & Mitigations

- **SecretStorage access requires context**: Passing `ExtensionContext.secrets` into the view provider is a small constructor change; add unit tests to prevent regressions.
- **Race conditions during save**: Use optimistic UI disable and refresh state after `settings.saved` to avoid stale dropdown selections.
- **Unsupported models in user settings**: Normalization warnings surfaced to UI ensure users understand fallback behavior and can pick supported models explicitly. 【F:vscode-extension/src/config/provider-settings.ts†L22-L45】
- **Backend/webview protocol drift**: Co-locate TypeScript types for messages in `shared/messages.ts` and import them in the webview bundle to enforce compile-time alignment. 【F:vscode-extension/src/shared/messages.ts†L34-L68】

## Milestones

1. **Backend hardening**: implement secret checks, warning propagation, and richer `provider_settings` payload.
2. **Webview UX**: ship provider/model selectors with status + warning surfaces; add accessibility polish.
3. **Test & documentation**: finalize integration + webview tests; update screenshots and user docs after UI lands.
