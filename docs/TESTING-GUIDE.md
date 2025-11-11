# Dolphin Testing Guide

This guide will help you test the Dolphin agent end-to-end with Claude CLI subscription auth.

## Prerequisites

### Option A: Claude CLI (Recommended - No API Costs)
1. **Install Claude CLI:**
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **Authenticate:**
   ```bash
   claude
   ```
   Then select: **"1. Claude account with subscription"**
   
   This will open a browser window to authenticate with your Claude Pro/Max/Team subscription.

### Option B: API Key (Fallback)
Set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Setup

### 1. Build the Webview
```bash
cd vscode-extension/webview
bun install
bun run build
```

### 2. Build the Extension
```bash
cd vscode-extension
npm install
npm run compile
```

### 3. Test in VSCode
1. Open the `vscode-extension` folder in VSCode
2. Press `F5` to launch Extension Development Host
3. Open the Dolphin sidebar (click the dolphin icon)

## Testing Auth Status UI

### In the Extension:

1. **Open Settings Tab:**
   - Click on "Settings" in the navigation
   - You should see the "Authentication Status" card at the top

2. **Verify Status Display:**
   - ✅ If CLI authenticated: Green badge "Using Claude Subscription"
   - 💳 If API key set: Blue badge "Using API Key"
   - ❌ If nothing configured: Red warning with setup instructions

### In the Gallery (UI Preview):

1. **Open Gallery Tab:**
   - Click on "Gallery" in the navigation
   - Scroll to "Settings Components" section
   - View the AuthStatus component preview

## Testing End-to-End Chat

### Simple "Hello World" Test:

1. **Go to Chat Tab:**
   - Click on the main chat view (home icon)

2. **Send Test Message:**
   ```
   Hello! Can you tell me about the Dolphin project?
   ```

3. **Expected Behavior:**
   - User message appears immediately
   - System searches Knowledge Bank (you'll see a tool call card)
   - If CLI authenticated:
     - Shows "🤔 Thinking..."
     - Then displays full response
   - If API authenticated:
     - Response streams character-by-character
   - Task completes with success

### Advanced Test - Code Search:

1. **Send:**
   ```
   Search for authentication-related code in this project
   ```

2. **Expected:**
   - KB search tool executes
   - Shows 3 relevant files
   - Claude analyzes results and provides summary

## Component Gallery Testing

Open the **Gallery** page to test all UI components:

- ✅ Chat components (messages, input)
- ✅ Tool call cards (running, success, error states)
- ✅ Diff viewer
- ✅ Plan timeline
- ✅ Error alerts
- ✅ Confirmation dialogs
- ✅ **NEW:** Auth Status panel

## Troubleshooting

### Issue: "No authentication configured"

**Solution:**
- Verify Claude CLI is installed: `which claude`
- Check if authenticated: `claude auth status`
- Or set API key: `export ANTHROPIC_API_KEY=sk-ant-...`

### Issue: "Agent bridge not connected"

**Solution:**
- The extension is in UI-only mode by default
- To enable full agent:
  1. Edit `vscode-extension/src/extension.ts`
  2. Uncomment lines 20-49 (AgentBridge initialization)
  3. Rebuild: `npm run compile`
  4. Restart extension (F5)

### Issue: Auth status shows "auto" mode

**Cause:** This is normal when no auth is configured.

**Fix:** Set up Claude CLI or API key (see Prerequisites above)

### Issue: KB search fails

**Cause:** Knowledge Bank API not running

**Solution (Development):**
```bash
# In dolphin directory:
uv run dolphin serve
```

**Note:** In future production releases, the KB server will auto-start with the extension (see [`KB-LIFECYCLE-MANAGEMENT.md`](KB-LIFECYCLE-MANAGEMENT.md) for implementation plan).

## Manual Testing Checklist

### Auth Detection:
- [ ] Detects Claude CLI installation
- [ ] Detects CLI authentication status
- [ ] Detects API key in environment
- [ ] Shows correct status in UI
- [ ] Refresh button works

### Chat Flow:
- [ ] User message sent
- [ ] KB search executes
- [ ] Claude response generated
- [ ] Streaming works (API mode)
- [ ] Batch response works (CLI mode)
- [ ] Task completes successfully

### UI Components:
- [ ] Message cards render
- [ ] Tool call cards show status
- [ ] Auth status panel displays
- [ ] Settings page loads
- [ ] Gallery page shows all components

## Performance Benchmarks

Expected timings:

| Operation | Time |
|-----------|------|
| Extension activation | < 2s |
| Webview load | < 1s |
| KB search | ~250ms |
| Claude response (CLI) | 2-5s |
| Claude response (API) | 1-3s |
| Auth status check | < 100ms |

## Debug Logs

### Enable Debug Logging:

1. **VSCode Output:**
   - View → Output
   - Select "Dolphin" from dropdown

2. **Browser DevTools (for webview):**
   - Help → Toggle Developer Tools
   - Look for webview logs

### Useful Log Patterns:

```
[Agent Core] Starting...
[Agent Core] Auth Detection:
  - CLI Installed: true
  - CLI Authenticated: true
  - API Key Set: false
  - Selected Mode: claude_cli

[ClaudeClient] Using Claude Code CLI (subscription mode)
✅ Using Claude subscription (no API costs)
```

## Next Steps After Testing

Once basic "Hello World" works:

1. **Test Complex Queries:**
   - Multi-file searches
   - Code refactoring requests
   - Architecture questions

2. **Test Error Handling:**
   - Invalid queries
   - Network failures
   - Auth expiry

3. **Performance Testing:**
   - Large responses
   - Multiple concurrent requests
   - Memory usage

4. **Edge Cases:**
   - Switch between CLI and API modes
   - Unset then reset authentication
   - Workspace changes

## Current Limitations (Development Phase)

- **Manual KB Startup Required:** You must manually start the KB server with `uv run dolphin serve` before using the extension
- **Planned Improvement:** Automatic KB lifecycle management (see [`KB-LIFECYCLE-MANAGEMENT.md`](KB-LIFECYCLE-MANAGEMENT.md))

## Getting Help

If you encounter issues:

1. Check the output logs (View → Output → Dolphin)
2. Verify all prerequisites are met
3. Ensure KB server is running (`uv run dolphin serve`)
4. Try the troubleshooting steps above
5. Check [`docs/day3-claude-integration-summary.md`](day3-claude-integration-summary.md) for implementation details

---

**Last Updated:** November 9, 2025  
**Tested With:** VSCode 1.85+, Bun 1.0.14+, Claude CLI 2.0.36+