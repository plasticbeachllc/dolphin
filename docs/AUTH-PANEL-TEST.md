# Auth Panel Smoke Test Guide

This guide walks you through testing the auth panel UI to ensure Claude Code authentication is working correctly.

## Prerequisites

1. Extension is built: `cd vscode-extension && npm run compile`
2. Webview is built: `cd vscode-extension/webview && bun run build`
3. Claude CLI installed: `npm install -g @anthropic-ai/claude` (if not already installed)
4. Claude CLI authenticated: Run `claude` once interactively to authenticate

## Test Steps

### 1. Launch Extension in Debug Mode

1. Open the Dolphin project in VSCode
2. Press `F5` or go to **Run > Start Debugging**
3. This opens a new VSCode window titled `[Extension Development Host]`

### 2. Open Dolphin Panel

1. In the Extension Development Host window, open any workspace folder
2. Open Dolphin panel:
   - Click the Dolphin icon (🐬) in the Activity Bar (left sidebar)
   - OR use Command Palette: `Cmd+Shift+P` → "Dolphin: Focus on Chat View"

### 3. Navigate to Settings Page

The auth panel is located on the Settings page:

1. In the Dolphin webview, click the **Settings** navigation item (gear icon in top nav)
2. The **Authentication Status** card should appear at the top

### 4. Verify Auth Panel Display

The auth panel should show:

**If Claude CLI is installed and authenticated:**
- ✅ Icon with green highlight
- Status: "Using Claude Subscription"
- Mode: `claude_cli` or `auto`
- CLI Installed: `Yes` (green badge)
- CLI Authenticated: `Yes` (green badge)
- API Key Set: `No` (gray badge)
- Green success message: "🎉 Using your Claude subscription - no API costs!"

**If Claude CLI is not installed:**
- ❌ Icon
- Status: "Not Configured"
- CLI Installed: `No`
- CLI Authenticated: `No`
- API Key Set: `No`
- Red error message: "❌ No authentication configured"
- Help text: "Install Claude CLI or set ANTHROPIC_API_KEY"

**If Claude CLI installed but not authenticated:**
- ⚠️ Icon with yellow highlight
- Status: "CLI Not Authenticated"
- CLI Installed: `Yes`
- CLI Authenticated: `No`
- API Key Set: `No`
- Yellow warning: "⚠️ Claude CLI installed but not authenticated"
- Help text: "Run: `claude` to authenticate"

### 5. Test Refresh Button

1. Click the "Refresh status" link at the bottom of the auth panel
2. The panel should show a loading spinner briefly
3. Status should reload and display current authentication state

### 6. Check Output Logs

Open the **Output** panel in the Extension Development Host window:

1. `Cmd+Shift+U` to open Output panel
2. Select "Dolphin Agent" from the dropdown
3. Look for log entries:
   ```
   [AgentBridge] Agent Core ready!
   📊 Claude Authentication Status:
     Mode: claude_cli
     CLI Installed: true
     CLI Authenticated: true
     API Key Set: false
     Will Use Subscription: true
   
   ✅ Using Claude subscription (no API costs)
   ```

### 7. Test Gallery Page (Optional)

The auth panel is also displayed in the Gallery page:

1. Navigate to **Gallery** in the top navigation
2. Scroll down to the "Settings Components" section
3. Verify the auth panel displays correctly there as well

## Expected Results

### Success Criteria ✅

- [ ] Auth panel loads without errors
- [ ] Status reflects actual Claude CLI installation and authentication state
- [ ] UI updates correctly when clicking "Refresh status"
- [ ] Appropriate icon (✅/⚠️/❌) displays based on auth state
- [ ] Help text provides clear guidance for each state
- [ ] No console errors in webview
- [ ] Agent Core logs show correct auth detection

### Known Issues

**"Checking authentication..." never completes:**
- Check Output > Dolphin Agent for errors
- Verify Agent Core started successfully
- Ensure `bun` is installed and accessible

**Auth panel shows "Not Configured" despite CLI being installed:**
- Run `which claude` to verify CLI is in PATH
- Check Agent Core logs for authentication check results
- Try running `claude` interactively to re-authenticate

**Webview doesn't load:**
- Verify webview was built: `ls -la vscode-extension/webview/build/`
- Check for build artifacts: `index.html`, `assets/main.*.js`, `assets/main.*.css`
- Rebuild if missing: `cd vscode-extension/webview && bun run build`

## Debugging

### Enable Verbose Logging

The extension already logs extensively to the Output panel. To see more:

1. Open **Developer Tools** for the webview:
   - In Extension Development Host, run: `Developer: Open Webview Developer Tools`
   - Check Console tab for any JavaScript errors

2. Check Agent Core stderr:
   - Output > Dolphin Agent shows all stderr from Agent Core
   - Look for authentication check results

### Manual Auth Status Check

Test the auth status endpoint directly:

```bash
# In a separate terminal
cd agent-core
bun run src/main.ts $(pwd)

# Send JSON-RPC request
echo '{"jsonrpc":"2.0","id":1,"method":"get_auth_status"}' | bun run src/main.ts $(pwd)
```

Expected output:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "mode": "claude_cli",
    "cliInstalled": true,
    "cliAuthenticated": true,
    "apiKeySet": false,
    "willUseSubscription": true
  }
}
```

## Next Steps

After successful smoke test:

1. Test sending a message to verify end-to-end Claude integration
2. Monitor usage costs (should show `isPaidUsage: false` for subscription mode)
3. Test fallback to API key mode by setting `ANTHROPIC_API_KEY`
4. Prepare extension for publication