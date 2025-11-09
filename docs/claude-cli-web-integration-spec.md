# Claude CLI to Web Interface Integration Specification

## Overview

This specification describes the integration of Anthropic's Claude API (via CLI or SDK) with Dolphin's web interface, enabling Claude to use MCP tools through a native Anthropic tool calling format.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     VSCode Extension                     │
│  ┌────────────────┐         ┌─────────────────────────┐ │
│  │ Webview (UI)   │◄───────►│  Agent Bridge           │ │
│  │ - Svelte       │  Events │  - Spawns agent-core    │ │
│  │ - Chat UI      │         │  - JSON-RPC over stdio  │ │
│  └────────────────┘         └───────────┬─────────────┘ │
└──────────────────────────────────────────┼───────────────┘
                                           │
                         JSON-RPC          │
                         (stdio)           ▼
┌─────────────────────────────────────────────────────────┐
│                      Agent Core                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │ Claude       │  │ MCP Client   │  │ Tool Format   │ │
│  │ Client       │  │              │  │ Converter     │ │
│  │ - Streaming  │  │ - Tool calls │  │ MCP ↔ Claude  │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘ │
│         │                 │                             │
│         │                 │ JSON-RPC                    │
│         │                 ▼                             │
│         │         ┌──────────────┐                      │
│         │         │ MCP Bridge   │                      │
│         │         │ - tools/list │                      │
│         │         │ - tools/call │                      │
│         │         └──────┬───────┘                      │
│         │                │                              │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
          │ Messages API   │ HTTP
          ▼                ▼
  ┌──────────────┐  ┌──────────────┐
  │ Anthropic    │  │ Dolphin KB   │
  │ API          │  │ REST Server  │
  └──────────────┘  └──────────────┘
```

## Component Specifications

### 1. Tool Format Converter

**Purpose**: Convert between MCP tool schema and Anthropic tool schema

**Location**: `agent-core/src/llm/tool-converter.ts`

#### MCP Tool Format (Input)
```typescript
interface MCPTool {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, MCPProperty>;
    required?: string[];
  };
}

interface MCPProperty {
  type: string;
  description?: string;
  enum?: any[];
  items?: any;
}
```

#### Anthropic Tool Format (Output)
```typescript
interface AnthropicTool {
  name: string;
  description: string;
  input_schema: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
  };
}
```

#### Conversion Logic
```typescript
class ToolFormatConverter {
  /**
   * Convert MCP tools to Anthropic format
   */
  static mcpToAnthropic(mcpTools: MCPTool[]): AnthropicTool[] {
    return mcpTools.map(tool => ({
      name: tool.name,
      description: tool.description,
      input_schema: tool.inputSchema
    }));
  }

  /**
   * Extract tool calls from Anthropic content blocks
   */
  static extractToolCalls(content: ContentBlock[]): ToolCall[] {
    return content
      .filter(block => block.type === 'tool_use')
      .map(block => ({
        id: block.id,
        name: block.name,
        input: block.input
      }));
  }

  /**
   * Create tool result content block for Anthropic
   */
  static createToolResult(
    toolUseId: string,
    result: MCPToolResult
  ): ToolResultBlock {
    return {
      type: 'tool_result',
      tool_use_id: toolUseId,
      content: this.formatMCPResult(result)
    };
  }

  /**
   * Format MCP result for Anthropic consumption
   */
  private static formatMCPResult(result: MCPToolResult): string {
    // MCP returns content blocks array
    if (Array.isArray(result.content)) {
      return result.content
        .filter(block => block.type === 'text')
        .map(block => block.text)
        .join('\n\n');
    }

    // Fallback to string representation
    return JSON.stringify(result, null, 2);
  }
}
```

### 2. Claude Tool Executor

**Purpose**: Orchestrate tool calling loop with Claude and MCP

**Location**: `agent-core/src/llm/claude-tool-executor.ts`

```typescript
interface ToolExecutorConfig {
  claudeClient: ClaudeClient;
  mcpClient: MCPClient;
  maxToolRounds: number;      // Prevent infinite loops
  onEvent: (event: AgentEvent) => void;
}

class ClaudeToolExecutor {
  private config: ToolExecutorConfig;
  private availableTools: AnthropicTool[] = [];
  private toolIdCounter = 0;

  constructor(config: ToolExecutorConfig) {
    this.config = config;
  }

  /**
   * Initialize: Load MCP tools and convert to Anthropic format
   */
  async initialize(): Promise<void> {
    // Get tools from MCP
    const mcpTools = await this.config.mcpClient.listTools();

    // Convert to Anthropic format
    this.availableTools = ToolFormatConverter.mcpToAnthropic(mcpTools);

    console.log(`[ToolExecutor] Loaded ${this.availableTools.length} tools`);
  }

  /**
   * Execute a user message with tool support
   */
  async executeWithTools(
    userMessage: string,
    conversationHistory: Message[] = []
  ): Promise<ExecutionResult> {
    const messages: Message[] = [
      ...conversationHistory,
      { role: 'user', content: userMessage }
    ];

    let toolRound = 0;
    let stopReason: string | undefined;

    while (toolRound < this.config.maxToolRounds) {
      // Call Claude with tools
      const response = await this.callClaudeWithTools(messages);

      stopReason = response.stop_reason;

      // Check if Claude wants to use tools
      const toolCalls = ToolFormatConverter.extractToolCalls(response.content);

      if (toolCalls.length === 0) {
        // No tools to call, we're done
        break;
      }

      // Execute tools in parallel
      const toolResults = await this.executeToolCalls(toolCalls);

      // Add assistant message with tool uses
      messages.push({
        role: 'assistant',
        content: response.content
      });

      // Add tool results as user message
      messages.push({
        role: 'user',
        content: toolResults
      });

      toolRound++;
    }

    return {
      messages,
      stopReason,
      toolRounds: toolRound
    };
  }

  /**
   * Call Claude with streaming + tools
   */
  private async callClaudeWithTools(
    messages: Message[]
  ): Promise<ClaudeResponse> {
    const stream = this.config.claudeClient.messages.stream({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 4096,
      tools: this.availableTools,
      messages: messages
    });

    let fullContent: ContentBlock[] = [];
    let currentTextBlock = '';
    let currentToolUse: any = null;

    for await (const event of stream) {
      switch (event.type) {
        case 'content_block_start':
          if (event.content_block.type === 'tool_use') {
            // New tool use block
            currentToolUse = {
              type: 'tool_use',
              id: event.content_block.id,
              name: event.content_block.name,
              input: {}
            };
          }
          break;

        case 'content_block_delta':
          if (event.delta.type === 'text_delta') {
            // Stream text to UI
            currentTextBlock += event.delta.text;
            this.config.onEvent({
              type: 'content_delta',
              delta: event.delta.text
            });
          } else if (event.delta.type === 'input_json_delta') {
            // Accumulate tool input (streamed as JSON)
            currentToolUse.input_json =
              (currentToolUse.input_json || '') + event.delta.partial_json;
          }
          break;

        case 'content_block_stop':
          if (currentTextBlock) {
            fullContent.push({
              type: 'text',
              text: currentTextBlock
            });
            currentTextBlock = '';
          }

          if (currentToolUse) {
            // Parse accumulated JSON input
            currentToolUse.input = JSON.parse(currentToolUse.input_json);
            delete currentToolUse.input_json;

            fullContent.push(currentToolUse);

            // Notify UI of tool call
            this.config.onEvent({
              type: 'tool_call_started',
              toolId: currentToolUse.id,
              tool: currentToolUse.name,
              input: currentToolUse.input
            });

            currentToolUse = null;
          }
          break;
      }
    }

    const finalMessage = await stream.finalMessage();

    return {
      content: fullContent,
      stop_reason: finalMessage.stop_reason,
      usage: finalMessage.usage
    };
  }

  /**
   * Execute multiple tool calls in parallel
   */
  private async executeToolCalls(
    toolCalls: ToolCall[]
  ): Promise<ContentBlock[]> {
    const results = await Promise.all(
      toolCalls.map(async (toolCall) => {
        const startTime = Date.now();

        try {
          // Call MCP tool
          const mcpResult = await this.config.mcpClient.callTool(
            toolCall.name,
            toolCall.input
          );

          const executionTime = Date.now() - startTime;

          // Notify UI
          this.config.onEvent({
            type: 'tool_call_completed',
            toolId: toolCall.id,
            result: mcpResult,
            executionTime
          });

          // Convert to Anthropic format
          return ToolFormatConverter.createToolResult(
            toolCall.id,
            mcpResult
          );
        } catch (error) {
          // Handle tool errors
          this.config.onEvent({
            type: 'tool_call_completed',
            toolId: toolCall.id,
            result: null,
            error: error.message,
            executionTime: Date.now() - startTime
          });

          return {
            type: 'tool_result',
            tool_use_id: toolCall.id,
            content: `Error: ${error.message}`,
            is_error: true
          };
        }
      })
    );

    return results;
  }
}
```

### 3. Agent Core Integration

**Purpose**: Wire up ClaudeToolExecutor in main agent loop

**Location**: `agent-core/src/main.ts` (modifications)

```typescript
class AgentCore {
  private claudeClient: ClaudeClient;
  private toolExecutor: ClaudeToolExecutor;
  private conversationHistory: Message[] = [];

  async start() {
    console.error("[Agent Core] Starting...");

    // Initialize KB
    await this.kbManager.start(this.workspaceRoot);

    // Start MCP Bridge
    const mcpBridgePath = path.join(__dirname, "../../mcp-bridge/src/index.ts");
    await this.mcpClient.start(mcpBridgePath);

    // Initialize Claude client
    this.claudeClient = new ClaudeClient({
      model: 'claude-sonnet-4-20250514',
      maxTokens: 4096,
      authMode: 'auto'
    });

    // Initialize tool executor
    this.toolExecutor = new ClaudeToolExecutor({
      claudeClient: this.claudeClient,
      mcpClient: this.mcpClient,
      maxToolRounds: 10,
      onEvent: (event) => this.sendEvent(event)
    });

    await this.toolExecutor.initialize();

    // Setup stdio communication
    this.setupStdio();

    // Send ready signal
    this.sendEvent({
      type: "agent_ready",
      version: this.version,
      capabilities: ["kb_search", "file_operations", "claude_streaming"]
    });
  }

  private async handleSendMessage(request: ExtensionRequest) {
    if (request.type === "send_message") {
      try {
        // Execute with Claude + tools
        const result = await this.toolExecutor.executeWithTools(
          request.content,
          this.conversationHistory
        );

        // Update conversation history
        this.conversationHistory = result.messages;

        // Send completion
        this.sendEvent({
          type: "task_completed",
          success: true,
          result: {
            toolRounds: result.toolRounds,
            stopReason: result.stopReason
          }
        });
      } catch (error) {
        this.sendEvent({
          type: "error",
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: error.message,
            suggestions: ["Check Claude authentication", "Check MCP bridge"],
            recoverable: true
          }
        });
      }
    }
  }
}
```

### 4. Web UI Updates

**Purpose**: Display streaming responses and tool calls in chat interface

**Location**: `vscode-extension/webview/src/lib/components/chat/` (existing Svelte components)

#### Message Format
```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallDisplay[];
  timestamp: Date;
}

interface ToolCallDisplay {
  id: string;
  name: string;
  input: any;
  result?: any;
  error?: string;
  executionTime?: number;
  status: 'pending' | 'running' | 'completed' | 'error';
}
```

#### Event Handlers (Pseudocode)
```typescript
// In main chat component
let currentMessage: ChatMessage | null = null;
let toolCalls: Map<string, ToolCallDisplay> = new Map();

function handleAgentEvent(event: AgentEvent) {
  switch (event.type) {
    case 'content_delta':
      // Append to current assistant message
      if (!currentMessage) {
        currentMessage = {
          id: generateId(),
          role: 'assistant',
          content: '',
          timestamp: new Date()
        };
        messages.push(currentMessage);
      }
      currentMessage.content += event.delta;
      messages = messages; // Trigger Svelte reactivity
      break;

    case 'tool_call_started':
      // Add tool call indicator
      const toolCall: ToolCallDisplay = {
        id: event.toolId,
        name: event.tool,
        input: event.input,
        status: 'running'
      };
      toolCalls.set(event.toolId, toolCall);

      if (currentMessage) {
        currentMessage.toolCalls = Array.from(toolCalls.values());
        messages = messages;
      }
      break;

    case 'tool_call_completed':
      // Update tool call with result
      const existingCall = toolCalls.get(event.toolId);
      if (existingCall) {
        existingCall.status = event.error ? 'error' : 'completed';
        existingCall.result = event.result;
        existingCall.error = event.error;
        existingCall.executionTime = event.executionTime;

        if (currentMessage) {
          currentMessage.toolCalls = Array.from(toolCalls.values());
          messages = messages;
        }
      }
      break;

    case 'task_completed':
      // Finalize message
      currentMessage = null;
      toolCalls.clear();
      break;
  }
}
```

## Message Flow Example

### User sends: "Search for authentication code"

```
1. User → Webview: Click send button
   {
     type: "send_message",
     content: "Search for authentication code"
   }

2. Webview → Extension → Agent Core (stdio):
   {
     jsonrpc: "2.0",
     method: "send_message",
     params: {
       type: "send_message",
       messageId: "msg-1",
       content: "Search for authentication code"
     }
   }

3. Agent Core → Claude API (streaming):
   POST https://api.anthropic.com/v1/messages
   {
     model: "claude-sonnet-4-20250514",
     max_tokens: 4096,
     tools: [
       {
         name: "search_knowledge",
         description: "Search indexed code semantically",
         input_schema: {
           type: "object",
           properties: {
             query: { type: "string" },
             top_k: { type: "number" }
           },
           required: ["query"]
         }
       }
     ],
     messages: [
       {
         role: "user",
         content: "Search for authentication code"
       }
     ],
     stream: true
   }

4. Claude → Agent Core (stream events):

   a. content_block_start (text)
   b. content_block_delta (text): "I'll search for..."
      → Agent Core → Webview:
      {
        type: "content_delta",
        delta: "I'll search for..."
      }

   c. content_block_stop (text)

   d. content_block_start (tool_use)
      {
        type: "tool_use",
        id: "toolu_123",
        name: "search_knowledge"
      }

   e. content_block_delta (input_json)
      { partial_json: '{"query":"auth' }
      { partial_json: 'entication","top' }
      { partial_json: '_k":5}' }

   f. content_block_stop (tool_use)
      → Agent Core → Webview:
      {
        type: "tool_call_started",
        toolId: "toolu_123",
        tool: "search_knowledge",
        input: { query: "authentication", top_k: 5 }
      }

5. Agent Core → MCP Bridge:
   {
     jsonrpc: "2.0",
     id: 1,
     method: "tools/call",
     params: {
       name: "search_knowledge",
       arguments: { query: "authentication", top_k: 5 }
     }
   }

6. MCP Bridge → Dolphin KB:
   POST http://localhost:7777/search
   { query: "authentication", top_k: 5 }

7. Dolphin KB → MCP Bridge:
   {
     results: [
       { path: "src/auth.ts", score: 0.89, ... },
       ...
     ]
   }

8. MCP Bridge → Agent Core:
   {
     jsonrpc: "2.0",
     id: 1,
     result: {
       content: [
         {
           type: "text",
           text: "Found 5 results:\n1. src/auth.ts..."
         }
       ],
       _meta: { hits: [...] }
     }
   }

   → Agent Core → Webview:
   {
     type: "tool_call_completed",
     toolId: "toolu_123",
     result: { ... },
     executionTime: 247
   }

9. Agent Core → Claude API (continue conversation):
   {
     messages: [
       {
         role: "user",
         content: "Search for authentication code"
       },
       {
         role: "assistant",
         content: [
           { type: "text", text: "I'll search for..." },
           {
             type: "tool_use",
             id: "toolu_123",
             name: "search_knowledge",
             input: { query: "authentication", top_k: 5 }
           }
         ]
       },
       {
         role: "user",
         content: [
           {
             type: "tool_result",
             tool_use_id: "toolu_123",
             content: "Found 5 results:\n1. src/auth.ts..."
           }
         ]
       }
     ],
     tools: [...],
     stream: true
   }

10. Claude → Agent Core (final response):
    content_block_delta: "Based on the search results, the authentication..."

    → Agent Core → Webview:
    {
      type: "content_delta",
      delta: "Based on the search results, the authentication..."
    }

11. Agent Core → Webview:
    {
      type: "task_completed",
      success: true
    }
```

## Error Handling

### Tool Execution Errors
```typescript
// When MCP tool fails
{
  type: "tool_result",
  tool_use_id: "toolu_123",
  content: "Error: Connection timeout to KB server",
  is_error: true
}

// Claude will see the error and can respond appropriately
// or retry with different parameters
```

### Claude API Errors
```typescript
// Catch in executeWithTools
try {
  const response = await this.callClaudeWithTools(messages);
} catch (error) {
  // Send error event to UI
  this.config.onEvent({
    type: 'error',
    error: {
      code: 'SERVICE_UNAVAILABLE',
      message: error.message,
      suggestions: [
        'Check ANTHROPIC_API_KEY',
        'Authenticate Claude CLI with: claude'
      ],
      recoverable: true
    }
  });
}
```

### Rate Limiting
```typescript
// Detect rate limit from API
if (error.status === 429) {
  const retryAfter = error.headers['retry-after'];

  this.config.onEvent({
    type: 'error',
    error: {
      code: 'RATE_LIMIT_EXCEEDED',
      message: `Rate limit exceeded. Retry after ${retryAfter}s`,
      suggestions: [
        'Wait before retrying',
        'Use Claude CLI with subscription for unlimited requests'
      ],
      recoverable: true
    }
  });
}
```

## Configuration

### Environment Variables
```bash
# Anthropic API (optional if using CLI)
ANTHROPIC_API_KEY=sk-ant-...

# Claude Code CLI (preferred)
# Authenticate with: claude
# Then select subscription mode
```

### Agent Core Config
```typescript
interface AgentCoreConfig {
  claude: {
    model: string;           // 'claude-sonnet-4-20250514'
    maxTokens: number;       // 4096
    authMode: AuthMode;      // 'auto' | 'claude_cli' | 'api_key'
    maxToolRounds: number;   // 10 - prevent infinite loops
  };
  mcp: {
    bridgePath: string;
    timeout: number;         // 30000ms
  };
}
```

## Performance Considerations

### Streaming
- Text content streams in real-time to UI (character by character)
- Tool use blocks accumulate until complete, then fire as single event
- Multiple tools execute in parallel for efficiency

### Caching
- Conversation history grows with each turn
- Consider truncating after N messages to prevent context overflow
- Use Claude's prompt caching for repeated system prompts/tools

### Monitoring
```typescript
interface UsageMetrics {
  totalInputTokens: number;
  totalOutputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  toolCallCount: number;
  averageToolExecutionMs: number;
}

// Track and emit periodically
this.sendEvent({
  type: 'usage_metrics',
  metrics: this.usageTracker.getMetrics()
});
```

## Testing Strategy

### Unit Tests
```typescript
describe('ToolFormatConverter', () => {
  it('converts MCP tools to Anthropic format', () => {
    const mcpTools = [/* ... */];
    const anthropicTools = ToolFormatConverter.mcpToAnthropic(mcpTools);
    expect(anthropicTools[0].input_schema).toBeDefined();
  });
});
```

### Integration Tests
```typescript
describe('ClaudeToolExecutor', () => {
  it('executes tool calling loop', async () => {
    const mockClaudeClient = createMockClaudeClient();
    const mockMCPClient = createMockMCPClient();

    const executor = new ClaudeToolExecutor({
      claudeClient: mockClaudeClient,
      mcpClient: mockMCPClient,
      maxToolRounds: 5,
      onEvent: jest.fn()
    });

    await executor.initialize();
    const result = await executor.executeWithTools('search for auth');

    expect(result.toolRounds).toBeGreaterThan(0);
  });
});
```

### E2E Tests
```bash
# Start all services
$ dolphin serve &
$ bun run agent-core/src/main.ts &

# Send test message via stdio
$ echo '{"jsonrpc":"2.0","method":"send_message","params":{"type":"send_message","content":"test"}}' | bun run agent-core/src/main.ts

# Verify events emitted
```

## Migration Path

### Phase 1: Tool Converter (Week 1)
- Implement `ToolFormatConverter`
- Unit tests
- Verify MCP tools convert correctly

### Phase 2: Tool Executor (Week 2)
- Implement `ClaudeToolExecutor`
- Integration tests with mock clients
- Test streaming + tool use events

### Phase 3: Agent Core Integration (Week 3)
- Wire up in `main.ts`
- Test with real Claude API
- Test with real MCP bridge

### Phase 4: UI Updates (Week 4)
- Update Svelte components for tool displays
- Add loading states for tool execution
- Polish streaming UX

### Phase 5: Production Hardening (Week 5)
- Error handling
- Rate limiting
- Usage tracking
- Logging and monitoring

## Open Questions

1. **Context Management**: How to handle conversation history truncation?
   - Rolling window of N messages?
   - Summarization of old context?

2. **Tool Approval**: Should some tools require user confirmation?
   - File writes?
   - External API calls?

3. **Parallel vs Sequential**: Should tools always run in parallel?
   - Some tools may depend on others
   - Need dependency detection?

4. **Cost Tracking**: How to display API costs vs subscription usage?
   - Real-time cost estimates?
   - Usage dashboards?

## References

- [Anthropic Tool Use Documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- [Existing LLM Module](../agent-core/src/llm/README.md)
