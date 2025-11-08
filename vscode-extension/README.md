# Dolphin VS Code Extension

VS Code AI coding assistant with semantic code search.

## Development

```bash
# Install dependencies
npm install

# Compile TypeScript
npm run compile

# Watch mode
npm run watch

# Debug: Press F5 in VS Code
```

## Structure

- `src/extension.ts` - Entry point
- `src/agent/` - AgentBridge (stdio/RPC to Agent Core)
- `src/views/` - Webview provider
- `webview/` - Svelte UI