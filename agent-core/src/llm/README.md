# LLM Module

This module handles Claude AI integration with dual authentication support (CLI + API).

## Components

### [`claude-cli-detector.ts`](claude-cli-detector.ts)

Detects and reports Claude Code CLI installation and authentication status.

#### Features

- ✅ Detects Claude CLI installation (`which claude`)
- ✅ Gets CLI version (`claude --version`)
- ✅ Checks authentication status (API key or subscription)
- ✅ Warns when API key overrides subscription
- ✅ Provides complete status report with warnings

#### Usage

```typescript
import { ClaudeCLIDetector } from "./llm/claude-cli-detector";

const detector = new ClaudeCLIDetector();

// Check if CLI is installed
const installed = await detector.isInstalled();
console.log(`CLI installed: ${installed}`);

// Get complete status
const status = await detector.getStatus();
console.log(status);
/*
{
  cliInstalled: true,
  cliVersion: "2.0.36 (Claude Code)",
  cliAuthenticated: false,
  authMethod: "none",
  apiKeySet: false,
  willUseSubscription: false,
  warnings: [
    "Claude CLI not authenticated and no API key set.",
    "Authenticate with: claude (then select \"1. Claude account with subscription\")"
  ]
}
*/
```

#### Integration Example

See [`example-integration.ts`](example-integration.ts) for complete integration examples.

Quick integration into AgentCore:

```typescript
import { ClaudeCLIDetector } from "./llm/claude-cli-detector";

class AgentCore {
  private authDetector: ClaudeCLIDetector;
  
  constructor(workspaceRoot: string) {
    this.authDetector = new ClaudeCLIDetector();
    // ... rest of constructor
  }
  
  async start() {
    // Check auth status on startup
    const authStatus = await this.authDetector.getStatus();
    
    console.error("[Agent Core] Auth Status:", {
      mode: authStatus.authMethod,
      willUseSubscription: authStatus.willUseSubscription,
    });
    
    // Display warnings
    if (authStatus.warnings.length > 0) {
      authStatus.warnings.forEach(w => console.error(`[Auth] ${w}`));
    }
    
    // ... continue with rest of startup
  }
}
```

## Authentication Modes

### 1. **Subscription Mode** (Recommended)
- Uses Claude Pro/Max/Team subscription
- No API costs
- Fixed monthly price ($20-200/month)
- Requires Claude CLI installation and authentication

**Setup:**
```bash
# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Authenticate (opens browser)
claude
# Select: "1. Claude account with subscription"
```

### 2. **API Key Mode** (Fallback)
- Uses Anthropic API
- Pay-per-token billing
- Requires `ANTHROPIC_API_KEY` environment variable

**Setup:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. **Auto Mode** (Default)
- Automatically selects best available method
- Prefers subscription over API
- Falls back gracefully

## Warnings

The detector provides helpful warnings for common issues:

### Warning: API Key Overrides Subscription
```
⚠️  ANTHROPIC_API_KEY is set. CLI will use API billing instead of subscription.
⚠️  To use subscription: unset ANTHROPIC_API_KEY
```

**Fix:**
```bash
unset ANTHROPIC_API_KEY
```

### Warning: CLI Not Installed
```
⚠️  Claude Code CLI not installed. Using API mode only.
⚠️  Install with: npm install -g @anthropic-ai/claude-code
```

### Warning: Not Authenticated
```
⚠️  Claude CLI not authenticated and no API key set.
⚠️  Authenticate with: claude (then select "1. Claude account with subscription")
```

## Testing

Run tests with:

```bash
cd agent-core
bun test tests/llm/claude-cli-detector.test.ts
```

Expected output:
```
✅ Claude CLI is installed
✅ Claude CLI version: 2.0.36 (Claude Code)
ℹ️  Claude CLI not authenticated (expected if not set up)
✅ Auth method: none

📊 Complete Auth Status:
  CLI Installed: true
  CLI Version: 2.0.36 (Claude Code)
  CLI Authenticated: false
  Auth Method: none
  API Key Set: false
  Will Use Subscription: false
```

## Next Steps

After implementing ClaudeCLIDetector, the next components are:

1. **ClaudeCLIProcess** - Subprocess management for CLI execution
2. **ClaudeClient** - Unified interface supporting both CLI and API
3. **Integration** - Add to AgentCore main.ts

See [`docs/private/vscode-architecture/claude-cli/updated-implementation-roadmap.md`](../../../docs/private/vscode-architecture/claude-cli/updated-implementation-roadmap.md) for the complete implementation plan.

## References

- [Claude Code CLI Integration Spec](../../../docs/private/vscode-architecture/claude-cli/claude-code-cli-integration.md)
- [Agent Core v1 Specification](../../../docs/private/vscode-architecture/claude-cli/agent-core-v1-specification.md)
- [Implementation Roadmap](../../../docs/private/vscode-architecture/claude-cli/updated-implementation-roadmap.md)