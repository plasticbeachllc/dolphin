# Dolphin VSCode Extension — Focused Improvement Plan

Version: 0.1
Status: Proposal
Date: 2025-11-09

Scope: Non‑KB improvements to the VSCode extension, webview UI, and Agent Bridge. Excludes Knowledge Bank lifecycle/sync work already covered in docs/kb-index.

---

## Goals

- Improve startup, stability, and security of the extension.
- Add ergonomic editor integrations and commands.
- Make configuration/auth seamless and safe.
- Strengthen IPC, error handling, and test coverage.
- Enhance the chat UI for clarity and productivity.

---

## Out of Scope

- KB indexing, file watching, and status UX (tracked in docs/kb-index/).

---

## Changes by Area

### 1) Activation & Lifecycle

- Targeted activation (avoid global startup):
  - Replace `onStartupFinished` with `onView:dolphin.chatView`, `onCommand:dolphin.*`.
  - File: `vscode-extension/package.json:14`.
- Agent auto‑recover with backoff:
  - When Agent Core exits non‑zero, show notification to retry and attempt 3 progressive restarts (1s/3s/10s). Surface status in Output.
  - Files: `vscode-extension/src/agent/bridge.ts:85` (exit handler), `:77` (error handler).
- Cross‑platform Bun detection:
  - On Windows, try `where bun` before falling back to known paths.
  - File: `vscode-extension/src/agent/bridge.ts:111`.

Acceptance
- Extension does not activate until user opens the view or runs a command.
- Crash of Agent Core triggers a restart prompt and logs; recoveries limited and visible to the user.

---

### 2) Commands & UX Basics

- New Conversation (wire through):
  - Extension sends JSON‑RPC `clear_conversation`; webview state resets.
  - Files: `vscode-extension/src/extension.ts:77`, `agent-core/src/main.ts:145` (already supports `clear_conversation`).
- Focus Input (actual focus):
  - Provider posts `{type:'focus_input'}` to webview; ChatInput focuses textarea.
  - Files: `vscode-extension/src/extension.ts:66`, `vscode-extension/src/views/provider.ts:71` (message handling), webview ChatInput handler.
- Contextual commands:
  - Editor: “Ask about selection”, “Refactor selection”. Explorer: “Ask about this file/folder”. Prefill chat input with context.
  - Files: `vscode-extension/package.json` (contributes.commands/menus), `vscode-extension/src/extension.ts` (handlers).

Acceptance
- Running “New Conversation” clears assistant/user messages in the UI and agent history.
- Running “Focus Input” places caret in the webview input without a toast.
- Context menu commands appear in the editor and explorer and seed the chat input.

---

### 3) Webview Security & Link Handling

- Tighten CSP (remove `unsafe-inline`):
  - Use nonces for scripts/styles or ensure Vite emits external scripts; inject nonce into the CSP meta.
  - File: `vscode-extension/src/views/provider.ts:209`.
- External/open‑file links:
  - Intercept anchor clicks in webview; for `http(s)` and `vscode://file/...`, post a message and use `vscode.env.openExternal` from the extension. Prevent default navigation.
  - Files: webview `App.svelte`, `lib/api/vscode.ts`, provider onDidReceiveMessage.

Acceptance
- Webview loads with strict CSP and functions correctly.
- Clicking a link opens externally (browser or VS Code file), never navigates the webview frame.

---

### 4) Configuration & Secrets

- Contribute configuration schema:
  - `dolphin.model`, `dolphin.maxTokens`, `dolphin.temperature`, `dolphin.preferCLI`, `dolphin.useTools`, `dolphin.enableTelemetry` (default false), keybinding override.
  - File: `vscode-extension/package.json` (contributes.configuration).
- API key management:
  - Add “Dolphin: Set API Key” command; store in `SecretStorage`. Pass to Agent Core via env on spawn.
  - Files: `vscode-extension/src/extension.ts`, `AgentBridge.start()`.

Acceptance
- Settings appear in VS Code Settings UI with descriptions and defaults.
- Secret is stored/retrieved via VS Code secrets and not logged.

---

### 5) Conversation Persistence & Sessions

- Persist chat history in webview state:
  - Save messages via `setState` and restore on mount.
  - Files: `vscode-extension/webview/src/lib/api/vscode.ts:57,66`, `webview/src/App.svelte` (onMount/teardown).
- Multi‑session support (optional, phase 2):
  - Add a `TreeView` for “Conversations” with create/rename/pin/delete. Store in `globalState`.

Acceptance
- Reloading the view/window preserves the current conversation.
- Users can create and switch between named sessions.

---

### 6) Editor Integration

- Apply diffs from the assistant:
  - When tool results include a patch, show a VS Code diff and allow “Apply” via `WorkspaceEdit`. Reuse webview DiffViewer for preview.
  - Files: `vscode-extension/webview/src/lib/components/DiffViewer.svelte:1`, add extension handlers to apply edits.
- Code Actions (quick fixes):
  - Provide code actions like “Explain selection”, “Refactor selection”, “Add tests”, “Document function” to seed prompts.
  - Files: new provider in `vscode-extension/src/` and package.json contributions.
- Inline completions (experimental):
  - Provide minimal `InlineCompletionItemProvider` gated by a setting. Start with deterministic prompts (no tool use).

Acceptance
- Users can preview/apply patches generated by the agent.
- Code actions appear on selected ranges and open the chat with prefilled context.

---

### 7) IPC Robustness & Events

- Adopt `vscode-jsonrpc`:
  - Replace manual NDJSON parsing with the library’s message connection and cancellation wiring.
  - File: `vscode-extension/src/agent/bridge.ts:56,140` (stdout handler and request plumbing).
- Backpressure & timeouts:
  - Queue writes when `stdin.write` returns false; flush on `drain`. Keep per‑request timeouts.
  - File: `vscode-extension/src/agent/bridge.ts:195`.
- Correlation IDs:
  - Include `requestId` on notifications and log it in Output to correlate UI/tool events.
  - Files: `agent-core/src/main.ts:100` (notify), extension forwarder `provider.ts:17`.

Acceptance
- No message loss when agent stdout/stderr chunk boundaries change.
- Large outputs no longer stall the process; queued writes resume on `drain`.

---

### 8) UI Improvements

- Theme fidelity & a11y:
  - Use theme tokens everywhere; ensure controls have ARIA labels; verify keyboard navigation.
  - Files: `vscode-extension/src/views/provider.ts:242` (sendTheme), Svelte components (labels/buttons).
- Header badges & tool breadcrumb:
  - Show current model/temperature/tool‑mode; collapse/expand tool calls with durations and quick “Peek” actions.
  - Files: `webview/src/App.svelte`, `lib/components/tools/ToolCallCard.svelte`.

Acceptance
- UI reflects theme accurately and passes basic accessibility checks.
- Tool calls are readable, collapsible, and actionable.

---

### 9) Packaging & Assets

- Fix missing icon:
  - `icon` points to a non‑existent file; update to `resources/dolphin_vscode.png`.
  - File: `vscode-extension/package.json:7`.
- Bundle Agent Core for VSIX:
  - Prebuild a JS entry (no TS path) and spawn that in production. Keep TS path during dev.
  - Files: `vscode-extension/src/extension.ts:21`, build scripts.

Acceptance
- VSIX includes a working icon and launches Agent Core without relying on TS sources.

---

### 10) Logging & Optional Telemetry

- Log levels & categories:
  - `dolphin.logLevel` setting; categorize logs (Agent, KB, Webview, RPC). Filter by level.
  - File: `vscode-extension/src/extension.ts` and bridge/provider emitters.
- Anonymous telemetry (opt‑in):
  - Count command usage and feature toggles only; content‑free; off by default.

Acceptance
- Users can reduce log verbosity. Telemetry remains disabled unless explicitly enabled.

---

## Implementation Notes & Pointers

- Activation events: `vscode-extension/package.json:14`.
- Provider CSP and asset rewriting: `vscode-extension/src/views/provider.ts:189–218`.
- Bridge spawn and stdout parsing: `vscode-extension/src/agent/bridge.ts:49–70` and `:56–69`.
- Agent notifications: `agent-core/src/main.ts:100` (notify), message handling at `:136`.
- Webview load handshake: `webview/src/lib/api/vscode.ts` posts `webview_loaded` on init.
- Auth status UI: `webview/src/lib/components/AuthStatus.svelte`.

---

## Phased Plan & Estimates

Phase 1 — Hardening & Basics (1–2 days)
- Activation events, icon fix, CSP tightening with nonces, Focus Input wiring, New Conversation wiring, build‑missing UI, log levels.

Phase 2 — Editor Integration (2–3 days)
- Contextual commands, apply diffs/WorkspaceEdit, basic CodeActionProvider.

Phase 3 — IPC Robustness (1–2 days)
- `vscode-jsonrpc` adoption, backpressure queue, restart/backoff.

Phase 4 — UI Enhancements & Sessions (2 days)
- Persist chat state, header badges, tool breadcrumb, basic a11y pass.

Phase 5 — Optional (2+ days)
- Inline completions (gated), opt‑in telemetry.

---

## Risks & Mitigations

- CSP breakage after tightening → Develop with a CSP‑nonce dev flag and add a Webview test for asset rewrite + CSP injection.
- Windows Bun lookup → Use `process.platform === 'win32'` to try `where bun` first.
- Agent packaging paths → Detect dev vs. prod; use `context.asAbsolutePath` to select the right entry.

---

## Testing Strategy

- Extend E2E to cover:
  - Webview handshake (webview_loaded → agent_ready → get_auth_status).
  - Agent crash and restart prompt flow.
  - Asset rewrite + CSP injection sanity check.
  - Contextual commands presence and basic execution.
- Add unit tests for:
  - Bridge write queue/backpressure and response timeouts.
  - Link interception in webview.

---

## Quick Checklist

- [ ] Update activation events and icon path.
- [ ] Add “Set API Key” command using `SecretStorage`.
- [ ] Wire `clear_conversation` and `focus_input` messages.
- [ ] Tighten CSP with nonce; intercept links.
- [ ] Add contextual commands (editor/explorer) and code actions.
- [ ] Implement diff apply flow.
- [ ] Adopt `vscode-jsonrpc`; add write queue/backpressure.
- [ ] Persist chat state; add header badges and tool breadcrumb.
- [ ] Bundle Agent Core for VSIX; select entry at runtime.
- [ ] Expand tests to cover new flows.

