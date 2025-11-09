# Claude Code Integration Summary

## Investigation Results

After reviewing the Kilocode implementation and official Claude Code documentation, here's what I found:

## Key Findings

### 1. **Claude Code Uses the `claude` CLI Binary**

Kilocode does NOT use session tokens or a local API server. Instead, it:

1. **Spawns the `claude` CLI process** as a subprocess
2. **Communicates via stdin/stdout** using JSON-RPC
3. **Passes messages and system prompts** as command-line arguments or files
4. **Receives streaming JSON responses** from stdout

### 2. **Authentication is Handled by the CLI Itself**

The `claude` CLI binary handles authentication internally:
- When you run `claude` interactively, it authenticates with your Claude subscription
- When spawned programmatically, it uses the **same authentication session**
- No API keys or session tokens needed in your code

### 3. **Implementation Details from Kilocode**

**File: [`/Users/tdc/worktable/kilocode/src/integrations/claude-code/run.ts`](file:///Users/tdc/worktable/kilocode/src/integrations/claude-code/run.ts:221)**

```typescript
const child = execa(claudePath, args, {
  stdin: "pipe",
  stdout: "pipe",
  stderr: "pipe",
  env: {
    ...process.env,
    CLAUDE_CODE_MAX_OUTPUT_TOKENS: maxOutputTokens?.toString() || "16000"
  },
  cwd,
  maxBuffer: 1024 * 1024 * 1000,
  timeout: 600000, // 10 minutes
});

// Write messages to stdin
child.stdin.write(JSON.stringify(messages), "utf8");
child.stdin.end();
```

**Arguments passed to `claude` CLI:**

```typescript
const args = [
  "-p",                           // Programmatic mode
  "--system-prompt", systemPrompt, // Or --system-prompt-file for large prompts
  "--verbose",
  "--output-format", "stream-json",
  "--disallowedTools", claudeCodeTools,
  "--max-turns", "1",
  "--model", modelId
];
```

### 4. **Response Format**

The CLI returns **streaming JSON** on stdout. Each line is a JSON object:

**Init Message** (indicates auth status):
```typescript
{
  type: "system",
  subtype: "init",
  session_id: "...",
  tools: [...],
  mcp_servers: [...],
  apiKeySource: "none" | "/login managed key" | string
}
```

- `apiKeySource: "none"` = Using Claude subscription (free for subscriber)
- `apiKeySource: "/login managed key"` = Using API key from environment

**Assistant Message** (contains response):
```typescript
{
  type: "assistant",
  message: {
    content: [...],
    usage: {
      input_tokens: number,
      output_tokens: number,
      cache_read_input_tokens?: number,
      cache_creation_input_tokens?: number
    },
    stop_reason: string
  },
  session_id: "..."
}
```

**Result Message** (final summary):
```typescript
{
  type: "result",
  subtype: "success",
  total_cost_usd: number,  // 0 for subscription usage
  is_error: boolean,
  duration_ms: number,
  num_turns: number,
  result: string,
  session_id: "..."
}
```

### 5. **Authentication Detection**

From [`/Users/tdc/worktable/kilocode/src/api/providers/claude-code.ts`](file:///Users/tdc/worktable/kilocode/src/api/providers/claude-code.ts:65-68):

```typescript
if (chunk.type === "system" && chunk.subtype === "init") {
  // Subscription usage sets the `apiKeySource` to "none"
  isPaidUsage = chunk.apiKeySource !== "none";
  continue;
}
```

**This means:**
- If `apiKeySource === "none"` → Using subscription (no API costs)
- If `apiKeySource !== "none"` → Using API key (charges apply)

### 6. **No Environment Variables Needed**

The `claude` CLI handles authentication automatically:
- If you've run `claude` interactively and authenticated, it stores session credentials
- When spawned programmatically, it reuses those credentials
- No need to set `ANTHROPIC_API_KEY` unless you want to override subscription with API key

## Implementation Plan for Dolphin

### What We Need to Do

1. **Revert the `isAuthenticated()` simplification**
   - Don't check for `ANTHROPIC_API_KEY`
   - Instead, check if `claude` CLI is installed and working

2. **Implement subprocess spawning (like Kilocode)**
   - Use `execa` or similar to spawn `claude` process
   - Pass messages via stdin
   - Read JSON responses from stdout
   - Handle errors from stderr

3. **Parse streaming JSON responses**
   - Read line-by-line from stdout
   - Parse each line as JSON
   - Handle partial chunks (may span multiple lines)
   - Extract `apiKeySource` to determine if using subscription

4. **Update ClaudeClient to use subprocess**
   - Remove Anthropic SDK usage for CLI mode
   - Implement subprocess communication
   - Parse responses and return in standard format

## Files to Update

1. **[`agent-core/src/llm/claude-cli-detector.ts`](agent-core/src/llm/claude-cli-detector.ts:93)** - Fix `isAuthenticated()`
2. **[`agent-core/src/llm/claude-cli-process.ts`](agent-core/src/llm/claude-cli-process.ts:1)** - Implement subprocess spawning
3. **[`agent-core/src/llm/claude-client.ts`](agent-core/src/llm/claude-client.ts:1)** - Update to use subprocess for CLI mode

## Next Steps

1. Read the Kilocode implementation more carefully
2. Implement subprocess-based Claude Code execution
3. Test with real Claude CLI installation
4. Update documentation to reflect correct implementation

## References

- **Kilocode Implementation:** `/Users/tdc/worktable/kilocode/src/integrations/claude-code/`
- **Claude Code CLI Docs:** https://docs.anthropic.com/en/docs/claude-code/overview
- **Context7 Documentation:** Retrieved via MCP (shows `ANTHROPIC_API_KEY` is for CLI but optional)

## Key Takeaway

**Claude Code authentication is NOT about API keys or session tokens.** It's about:

1. Having the `claude` CLI binary installed
2. Authenticating once interactively (`claude` command)
3. The CLI stores session credentials automatically
4. Spawning the CLI programmatically reuses those credentials
5. Detecting `apiKeySource` in responses to know if using subscription vs API key

This is much simpler than we thought - no custom authentication logic needed!