# Provider Selection UX - Project Plan

## Overview
This document outlines the implementation of a comprehensive provider selection UX for the Dolphin VS Code extension, allowing users to easily switch between AI providers (Anthropic, OpenAI) and models directly from the chat interface.

## Goals
- Enable users to select and switch between AI providers (Anthropic, OpenAI) from the UI
- Support provider-specific model selection
- Validate API key presence and prompt for configuration when missing
- Provide a seamless UX that updates VS Code settings automatically

## Architecture

### Backend (Extension)
The backend handles provider settings management, configuration updates, and API key validation.

#### Components
1. **Configuration Layer** (`vscode-extension/src/config/`)
   - `provider-settings.ts`: Resolves current provider/model from VS Code config
   - `provider-options.ts`: Defines available providers and models

2. **Message Protocol** (`vscode-extension/src/shared/messages.ts`)
   - `GetProviderSettingsCommand`: Request current settings
   - `ProviderSettingsMessage`: Response with current + available options
   - `SaveProviderSettingsCommand`: Update provider/model selection

3. **View Provider** (`vscode-extension/src/views/provider.ts`)
   - Handles provider settings requests from webview
   - Updates VS Code configuration on save
   - Validates API key presence and triggers setup flow

### Frontend (Webview)
> **Status**: Not yet implemented. Backend is complete and ready for frontend integration.

The frontend will consume the backend API to render UI components for provider selection.

#### Proposed Components
1. **Provider Selector Dropdown**: Select between Anthropic/OpenAI
2. **Model Selector Dropdown**: Display models for selected provider
3. **Status Indicator**: Show if API key is configured
4. **Setup Flow**: Prompt for API key when missing

## Implementation Status

### ✅ Completed (Backend)
- [x] Configuration logic with `getCurrentProviderSettings()`
- [x] Exported `PROVIDER_OPTIONS` for UI consumption
- [x] Message protocol for provider settings communication
- [x] View provider handlers for get/save operations
- [x] API key validation and prompting
- [x] Integration tests for provider settings messages

### ⏳ Pending (Frontend)
- [ ] UI components for provider/model selection
- [ ] Integration with webview message protocol
- [ ] User flow for switching providers
- [ ] Visual indicators for API key status

## API Reference

### Extension → Webview Messages

#### `ProviderSettingsMessage`
Sent in response to `GetProviderSettingsCommand` or after `SaveProviderSettingsCommand`.

```typescript
{
  type: "provider_settings",
  currentProvider: "anthropic" | "openai",
  currentModel: string,
  availableProviders: Array<{
    id: "anthropic" | "openai",
    label: string,
    description: string,
    models: Array<{
      id: string,
      label: string,
      description: string,
      default?: boolean
    }>
  }>
}
```

### Webview → Extension Messages

#### `GetProviderSettingsCommand`
Request current provider settings.

```typescript
{
  type: "get_provider_settings"
}
```

#### `SaveProviderSettingsCommand`
Update provider and model selection.

```typescript
{
  type: "save_provider_settings",
  provider: "anthropic" | "openai",
  model: string
}
```

## User Flow

1. **User opens Dolphin chat**
   - Webview sends `get_provider_settings`
   - Extension responds with current provider/model + available options
   - UI renders current selection

2. **User changes provider**
   - User selects new provider from dropdown
   - UI updates model dropdown to show provider-specific models
   - Webview sends `save_provider_settings`
   - Extension updates VS Code configuration
   - Extension checks for API key

3. **API key validation**
   - If key exists: Update succeeds, UI refreshed
   - If key missing: Extension triggers VS Code command to prompt for key
   - On success: Settings updated, confirmation shown

## Testing

### Backend Tests
- **Location**: `vscode-extension/src/test/suite/integration/ui/provider.test.ts`
- **Coverage**: 
  - `get_provider_settings` message handling
  - `save_provider_settings` message handling
  - Configuration updates
  - Message payload validation

### Frontend Tests (Pending)
- User interaction with provider selector
- Model dropdown updates on provider change
- API key validation flow
- Settings persistence

## Configuration

### VS Code Settings
```json
{
  "dolphin.llm.provider": "anthropic" | "openai",
  "dolphin.llm.model.anthropic": "claude-sonnet-4-5-20250929" | "claude-sonnet-4-5" | "claude-haiku-4-5",
  "dolphin.llm.model.openai": "gpt-5.1" | "gpt-5.1-codex" | "gpt-5.1-codex-mini"
}
```

### Secret Storage
API keys are stored securely in VS Code's SecretStorage:
- `dolphin.anthropicApiKey`
- `dolphin.openaiApiKey`

## Next Steps

1. **Frontend Implementation**
   - Create React components for provider selection UI
   - Integrate with webview message protocol
   - Implement user flow and validation

2. **UX Enhancements**
   - Add provider logos/icons
   - Improve API key setup flow
   - Add tooltips and help text

3. **Documentation**
   - Update user-facing documentation
   - Add screenshots of UI
   - Document provider setup process

## Files Modified

### Configuration
- `vscode-extension/src/config/provider-settings.ts` - Added `getCurrentProviderSettings()`
- `vscode-extension/src/config/provider-options.ts` - Exported `PROVIDER_OPTIONS`

### Message Protocol
- `vscode-extension/src/shared/messages.ts` - Added provider settings messages

### View Provider
- `vscode-extension/src/views/provider.ts` - Added message handlers

### Tests
- `vscode-extension/src/test/suite/integration/ui/provider.test.ts` - Added integration tests

## References
- [Provider Settings Implementation](file:///Users/tdc/worktable/dolphin/vscode-extension/src/config/provider-settings.ts)
- [Provider Options](file:///Users/tdc/worktable/dolphin/vscode-extension/src/config/provider-options.ts)
- [Message Protocol](file:///Users/tdc/worktable/dolphin/vscode-extension/src/shared/messages.ts)
- [View Provider](file:///Users/tdc/worktable/dolphin/vscode-extension/src/views/provider.ts)
