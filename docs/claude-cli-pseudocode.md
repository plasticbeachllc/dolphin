# Claude CLI Integration - Detailed Pseudocode

## 1. Tool Format Converter (`agent-core/src/llm/tool-converter.ts`)

```typescript
/**
 * Converts between MCP tool schema and Anthropic tool schema
 */

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface MCPTool {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, {
      type: string;
      description?: string;
      enum?: any[];
      items?: any;
    }>;
    required?: string[];
  };
}

interface AnthropicTool {
  name: string;
  description: string;
  input_schema: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
  };
}

interface ToolUseBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, any>;
}

interface ToolResultBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string | ContentBlock[];
  is_error?: boolean;
}

// ============================================================================
// CONVERTER CLASS
// ============================================================================

class ToolFormatConverter {

  // --------------------------------------------------------------------------
  // MCP → Anthropic Tool Schema Conversion
  // --------------------------------------------------------------------------

  static mcpToAnthropic(mcpTools: MCPTool[]): AnthropicTool[] {
    PSEUDOCODE:
      INITIALIZE result as empty array

      FOR EACH mcpTool in mcpTools:
        CREATE anthropicTool with:
          name = mcpTool.name
          description = mcpTool.description
          input_schema = mcpTool.inputSchema  // Direct mapping (schemas are compatible)

        APPEND anthropicTool to result

      RETURN result

    IMPLEMENTATION:
      return mcpTools.map(tool => ({
        name: tool.name,
        description: tool.description,
        input_schema: tool.inputSchema
      }));
  }

  // --------------------------------------------------------------------------
  // Extract Tool Calls from Claude Response
  // --------------------------------------------------------------------------

  static extractToolCalls(content: ContentBlock[]): ToolCall[] {
    PSEUDOCODE:
      INITIALIZE toolCalls as empty array

      FOR EACH block in content:
        IF block.type === 'tool_use':
          CREATE toolCall with:
            id = block.id
            name = block.name
            input = block.input

          APPEND toolCall to toolCalls

      RETURN toolCalls

    IMPLEMENTATION:
      return content
        .filter(block => block.type === 'tool_use')
        .map(block => ({
          id: block.id,
          name: block.name,
          input: block.input
        }));
  }

  // --------------------------------------------------------------------------
  // Create Tool Result for Claude
  // --------------------------------------------------------------------------

  static createToolResult(
    toolUseId: string,
    mcpResult: MCPToolResult,
    isError: boolean = false
  ): ToolResultBlock {
    PSEUDOCODE:
      // MCP results have format: { content: [{ type: "text", text: "..." }], ... }

      INITIALIZE formattedContent

      IF mcpResult.content is Array:
        // Extract text from content blocks
        INITIALIZE textParts as empty array

        FOR EACH block in mcpResult.content:
          IF block.type === 'text':
            APPEND block.text to textParts

        formattedContent = JOIN textParts with '\n\n'

      ELSE IF mcpResult.content is String:
        formattedContent = mcpResult.content

      ELSE:
        // Fallback to JSON
        formattedContent = JSON.stringify(mcpResult, null, 2)

      CREATE toolResultBlock with:
        type = 'tool_result'
        tool_use_id = toolUseId
        content = formattedContent
        is_error = isError  // Only include if true

      RETURN toolResultBlock

    IMPLEMENTATION:
      let formattedContent: string;

      if (Array.isArray(mcpResult.content)) {
        formattedContent = mcpResult.content
          .filter(block => block.type === 'text')
          .map(block => block.text)
          .join('\n\n');
      } else if (typeof mcpResult.content === 'string') {
        formattedContent = mcpResult.content;
      } else {
        formattedContent = JSON.stringify(mcpResult, null, 2);
      }

      const result: ToolResultBlock = {
        type: 'tool_result',
        tool_use_id: toolUseId,
        content: formattedContent
      };

      if (isError) {
        result.is_error = true;
      }

      return result;
  }

  // --------------------------------------------------------------------------
  // Create Error Tool Result
  // --------------------------------------------------------------------------

  static createErrorResult(
    toolUseId: string,
    error: Error
  ): ToolResultBlock {
    PSEUDOCODE:
      CREATE errorMessage with:
        "Error executing tool: {error.message}"

      IF error.stack exists:
        APPEND "\n\nStack trace:\n{error.stack}" to errorMessage

      RETURN createToolResult(toolUseId, { content: errorMessage }, true)

    IMPLEMENTATION:
      const errorMessage = `Error executing tool: ${error.message}` +
        (error.stack ? `\n\nStack trace:\n${error.stack}` : '');

      return this.createToolResult(
        toolUseId,
        { content: errorMessage },
        true
      );
  }
}

// ============================================================================
// EXPORTS
// ============================================================================

export { ToolFormatConverter };
export type { MCPTool, AnthropicTool, ToolUseBlock, ToolResultBlock };
```

## 2. Claude Tool Executor (`agent-core/src/llm/claude-tool-executor.ts`)

```typescript
/**
 * Orchestrates Claude API calls with MCP tool execution
 */

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface ToolExecutorConfig {
  claudeClient: ClaudeClient;
  mcpClient: MCPClient;
  maxToolRounds: number;      // Default: 10
  onEvent: (event: AgentEvent) => void;
}

interface ExecutionResult {
  messages: Message[];
  stopReason: string | undefined;
  toolRounds: number;
  usage: {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens?: number;
    cacheWriteTokens?: number;
  };
}

interface Message {
  role: 'user' | 'assistant';
  content: string | ContentBlock[];
}

interface ContentBlock {
  type: 'text' | 'tool_use' | 'tool_result';
  // ... type-specific fields
}

// ============================================================================
// EXECUTOR CLASS
// ============================================================================

class ClaudeToolExecutor {
  private config: ToolExecutorConfig;
  private availableTools: AnthropicTool[] = [];
  private totalUsage = {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0
  };

  constructor(config: ToolExecutorConfig) {
    this.config = config;
  }

  // --------------------------------------------------------------------------
  // Initialization
  // --------------------------------------------------------------------------

  async initialize(): Promise<void> {
    PSEUDOCODE:
      LOG "[ToolExecutor] Initializing..."

      // Fetch available tools from MCP
      mcpTools = AWAIT this.config.mcpClient.listTools()

      LOG "Received {mcpTools.length} tools from MCP"

      // Convert to Anthropic format
      this.availableTools = ToolFormatConverter.mcpToAnthropic(mcpTools)

      LOG "Available tools:"
      FOR EACH tool in this.availableTools:
        LOG "  - {tool.name}: {tool.description}"

      LOG "[ToolExecutor] Ready"

    IMPLEMENTATION:
      console.log('[ToolExecutor] Initializing...');

      const mcpTools = await this.config.mcpClient.listTools();
      console.log(`[ToolExecutor] Received ${mcpTools.length} tools from MCP`);

      this.availableTools = ToolFormatConverter.mcpToAnthropic(mcpTools);

      console.log('[ToolExecutor] Available tools:');
      this.availableTools.forEach(tool => {
        console.log(`  - ${tool.name}: ${tool.description}`);
      });

      console.log('[ToolExecutor] Ready');
  }

  // --------------------------------------------------------------------------
  // Main Execution Loop
  // --------------------------------------------------------------------------

  async executeWithTools(
    userMessage: string,
    conversationHistory: Message[] = []
  ): Promise<ExecutionResult> {
    PSEUDOCODE:
      // Initialize conversation with history + new user message
      messages = [...conversationHistory, { role: 'user', content: userMessage }]

      toolRound = 0
      stopReason = undefined
      totalUsage = { inputTokens: 0, outputTokens: 0, ... }

      WHILE toolRound < this.config.maxToolRounds:
        LOG "[ToolExecutor] Round {toolRound + 1}"

        // Call Claude with tools
        response = AWAIT this.callClaudeWithTools(messages)

        // Accumulate usage
        totalUsage.inputTokens += response.usage.input_tokens
        totalUsage.outputTokens += response.usage.output_tokens
        // ... cache tokens

        stopReason = response.stop_reason

        // Extract tool calls from response
        toolCalls = ToolFormatConverter.extractToolCalls(response.content)

        IF toolCalls.length === 0:
          LOG "[ToolExecutor] No tools called, ending loop"
          BREAK

        LOG "[ToolExecutor] Claude requested {toolCalls.length} tool(s)"

        // Add Claude's response to conversation
        messages.push({
          role: 'assistant',
          content: response.content
        })

        // Execute tools in parallel
        toolResults = AWAIT this.executeToolCalls(toolCalls)

        // Add tool results as user message
        messages.push({
          role: 'user',
          content: toolResults
        })

        toolRound++

      IF toolRound >= this.config.maxToolRounds:
        LOG "[ToolExecutor] WARNING: Max tool rounds reached"

      RETURN {
        messages: messages,
        stopReason: stopReason,
        toolRounds: toolRound,
        usage: totalUsage
      }

    IMPLEMENTATION:
      const messages: Message[] = [
        ...conversationHistory,
        { role: 'user', content: userMessage }
      ];

      let toolRound = 0;
      let stopReason: string | undefined;
      const totalUsage = {
        inputTokens: 0,
        outputTokens: 0,
        cacheReadTokens: 0,
        cacheWriteTokens: 0
      };

      while (toolRound < this.config.maxToolRounds) {
        console.log(`[ToolExecutor] Round ${toolRound + 1}`);

        const response = await this.callClaudeWithTools(messages);

        totalUsage.inputTokens += response.usage.input_tokens;
        totalUsage.outputTokens += response.usage.output_tokens;
        if (response.usage.cache_read_input_tokens) {
          totalUsage.cacheReadTokens += response.usage.cache_read_input_tokens;
        }
        if (response.usage.cache_creation_input_tokens) {
          totalUsage.cacheWriteTokens += response.usage.cache_creation_input_tokens;
        }

        stopReason = response.stop_reason;

        const toolCalls = ToolFormatConverter.extractToolCalls(response.content);

        if (toolCalls.length === 0) {
          console.log('[ToolExecutor] No tools called, ending loop');
          break;
        }

        console.log(`[ToolExecutor] Claude requested ${toolCalls.length} tool(s)`);

        messages.push({
          role: 'assistant',
          content: response.content
        });

        const toolResults = await this.executeToolCalls(toolCalls);

        messages.push({
          role: 'user',
          content: toolResults
        });

        toolRound++;
      }

      if (toolRound >= this.config.maxToolRounds) {
        console.warn('[ToolExecutor] WARNING: Max tool rounds reached');
      }

      return {
        messages,
        stopReason,
        toolRounds: toolRound,
        usage: totalUsage
      };
  }

  // --------------------------------------------------------------------------
  // Call Claude with Streaming
  // --------------------------------------------------------------------------

  private async callClaudeWithTools(
    messages: Message[]
  ): Promise<ClaudeResponse> {
    PSEUDOCODE:
      LOG "[ToolExecutor] Calling Claude API..."

      // Create streaming request
      stream = this.config.claudeClient.messages.stream({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        tools: this.availableTools,
        messages: messages,
        stream: true
      })

      // Accumulators
      fullContent = []
      currentTextBlock = ''
      currentToolUse = null

      // Process stream events
      FOR AWAIT event in stream:
        SWITCH event.type:

          CASE 'content_block_start':
            IF event.content_block.type === 'text':
              // Start new text block
              currentTextBlock = ''

            ELSE IF event.content_block.type === 'tool_use':
              // Start new tool use block
              currentToolUse = {
                type: 'tool_use',
                id: event.content_block.id,
                name: event.content_block.name,
                input: '',  // Will accumulate as JSON
                inputJson: ''  // Raw JSON accumulator
              }

          CASE 'content_block_delta':
            IF event.delta.type === 'text_delta':
              // Stream text to UI
              currentTextBlock += event.delta.text

              // Emit to UI immediately
              this.config.onEvent({
                type: 'content_delta',
                delta: event.delta.text
              })

            ELSE IF event.delta.type === 'input_json_delta':
              // Accumulate tool input JSON
              currentToolUse.inputJson += event.delta.partial_json

          CASE 'content_block_stop':
            IF currentTextBlock !== '':
              // Finalize text block
              fullContent.push({
                type: 'text',
                text: currentTextBlock
              })
              currentTextBlock = ''

            ELSE IF currentToolUse !== null:
              // Finalize tool use block
              TRY:
                currentToolUse.input = JSON.parse(currentToolUse.inputJson)
              CATCH error:
                LOG "ERROR: Failed to parse tool input JSON"
                currentToolUse.input = {}

              DELETE currentToolUse.inputJson

              fullContent.push(currentToolUse)

              // Emit tool call started event
              this.config.onEvent({
                type: 'tool_call_started',
                toolId: currentToolUse.id,
                tool: currentToolUse.name,
                input: currentToolUse.input
              })

              currentToolUse = null

          CASE 'message_stop':
            // End of stream
            BREAK

      // Get final message metadata
      finalMessage = AWAIT stream.finalMessage()

      RETURN {
        content: fullContent,
        stop_reason: finalMessage.stop_reason,
        usage: finalMessage.usage
      }

    IMPLEMENTATION:
      console.log('[ToolExecutor] Calling Claude API...');

      const stream = this.config.claudeClient.messages.stream({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        tools: this.availableTools,
        messages: messages
      });

      const fullContent: ContentBlock[] = [];
      let currentTextBlock = '';
      let currentToolUse: any = null;

      for await (const event of stream) {
        switch (event.type) {
          case 'content_block_start':
            if (event.content_block.type === 'text') {
              currentTextBlock = '';
            } else if (event.content_block.type === 'tool_use') {
              currentToolUse = {
                type: 'tool_use',
                id: event.content_block.id,
                name: event.content_block.name,
                inputJson: ''
              };
            }
            break;

          case 'content_block_delta':
            if (event.delta.type === 'text_delta') {
              currentTextBlock += event.delta.text;
              this.config.onEvent({
                type: 'content_delta',
                delta: event.delta.text
              });
            } else if (event.delta.type === 'input_json_delta') {
              currentToolUse.inputJson += event.delta.partial_json;
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
              try {
                currentToolUse.input = JSON.parse(currentToolUse.inputJson);
              } catch (error) {
                console.error('[ToolExecutor] Failed to parse tool input JSON:', error);
                currentToolUse.input = {};
              }

              delete currentToolUse.inputJson;
              fullContent.push(currentToolUse);

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

  // --------------------------------------------------------------------------
  // Execute Tool Calls
  // --------------------------------------------------------------------------

  private async executeToolCalls(
    toolCalls: ToolCall[]
  ): Promise<ToolResultBlock[]> {
    PSEUDOCODE:
      LOG "[ToolExecutor] Executing {toolCalls.length} tool(s) in parallel"

      // Execute all tools in parallel
      results = AWAIT Promise.all(
        FOR EACH toolCall in toolCalls:
          ASYNC FUNCTION:
            startTime = Date.now()

            TRY:
              LOG "Calling MCP tool: {toolCall.name}"

              // Call MCP
              mcpResult = AWAIT this.config.mcpClient.callTool(
                toolCall.name,
                toolCall.input
              )

              executionTime = Date.now() - startTime

              LOG "Tool {toolCall.name} completed in {executionTime}ms"

              // Emit success event
              this.config.onEvent({
                type: 'tool_call_completed',
                toolId: toolCall.id,
                result: mcpResult,
                executionTime: executionTime
              })

              // Convert to Anthropic format
              RETURN ToolFormatConverter.createToolResult(
                toolCall.id,
                mcpResult,
                false  // not an error
              )

            CATCH error:
              executionTime = Date.now() - startTime

              LOG "ERROR: Tool {toolCall.name} failed: {error.message}"

              // Emit error event
              this.config.onEvent({
                type: 'tool_call_completed',
                toolId: toolCall.id,
                result: null,
                error: error.message,
                executionTime: executionTime
              })

              // Return error result
              RETURN ToolFormatConverter.createErrorResult(
                toolCall.id,
                error
              )
      )

      RETURN results

    IMPLEMENTATION:
      console.log(`[ToolExecutor] Executing ${toolCalls.length} tool(s) in parallel`);

      const results = await Promise.all(
        toolCalls.map(async (toolCall) => {
          const startTime = Date.now();

          try {
            console.log(`[ToolExecutor] Calling MCP tool: ${toolCall.name}`);

            const mcpResult = await this.config.mcpClient.callTool(
              toolCall.name,
              toolCall.input
            );

            const executionTime = Date.now() - startTime;

            console.log(`[ToolExecutor] Tool ${toolCall.name} completed in ${executionTime}ms`);

            this.config.onEvent({
              type: 'tool_call_completed',
              toolId: toolCall.id,
              result: mcpResult,
              executionTime
            });

            return ToolFormatConverter.createToolResult(
              toolCall.id,
              mcpResult,
              false
            );
          } catch (error) {
            const executionTime = Date.now() - startTime;

            console.error(`[ToolExecutor] Tool ${toolCall.name} failed:`, error.message);

            this.config.onEvent({
              type: 'tool_call_completed',
              toolId: toolCall.id,
              result: null,
              error: error.message,
              executionTime
            });

            return ToolFormatConverter.createErrorResult(
              toolCall.id,
              error
            );
          }
        })
      );

      return results;
  }

  // --------------------------------------------------------------------------
  // Get Usage Statistics
  // --------------------------------------------------------------------------

  getUsage() {
    return { ...this.totalUsage };
  }
}

// ============================================================================
// EXPORTS
// ============================================================================

export { ClaudeToolExecutor };
export type { ToolExecutorConfig, ExecutionResult };
```

## 3. Agent Core Integration (`agent-core/src/main.ts`)

```typescript
/**
 * Modified AgentCore class with Claude integration
 */

PSEUDOCODE FOR main.ts MODIFICATIONS:

// --------------------------------------------------------------------------
// Class Fields (add to existing)
// --------------------------------------------------------------------------

class AgentCore {
  // Existing fields
  private mcpClient: MCPClient;
  private kbManager: KBManager;

  // NEW: Add Claude integration
  private claudeClient: ClaudeClient;
  private toolExecutor: ClaudeToolExecutor;
  private conversationHistory: Message[] = [];

  // --------------------------------------------------------------------------
  // Startup (modify existing start() method)
  // --------------------------------------------------------------------------

  async start() {
    LOG "[Agent Core] Starting..."

    // Existing startup
    AWAIT this.kbManager.start(this.workspaceRoot)

    mcpBridgePath = path.join(__dirname, "../../mcp-bridge/src/index.ts")
    AWAIT this.mcpClient.start(mcpBridgePath)

    // NEW: Initialize Claude client
    this.claudeClient = NEW ClaudeClient({
      model: 'claude-sonnet-4-20250514',
      maxTokens: 4096,
      authMode: 'auto',  // Auto-detect CLI vs API
      temperature: 1.0
    })

    // Check auth status
    authStatus = AWAIT this.claudeClient.getAuthStatus()
    LOG "[Agent Core] Claude auth:", authStatus.mode
    LOG "[Agent Core] Using subscription:", authStatus.willUseSubscription

    // NEW: Initialize tool executor
    this.toolExecutor = NEW ClaudeToolExecutor({
      claudeClient: this.claudeClient,
      mcpClient: this.mcpClient,
      maxToolRounds: 10,
      onEvent: (event) => this.sendEvent(event)
    })

    AWAIT this.toolExecutor.initialize()

    // Rest of existing startup
    this.setupStdio()

    this.sendEvent({
      type: "agent_ready",
      version: this.version,
      capabilities: ["claude_streaming", "kb_search", "file_operations"]
    })
  }

  // --------------------------------------------------------------------------
  // Message Handling (replace existing handleSendMessage)
  // --------------------------------------------------------------------------

  private async handleSendMessage(request: ExtensionRequest) {
    IF request.type !== "send_message":
      RETURN

    TRY:
      LOG "[Agent Core] Processing message:", request.content

      // Execute with Claude + tools
      result = AWAIT this.toolExecutor.executeWithTools(
        request.content,
        this.conversationHistory
      )

      // Update conversation history
      this.conversationHistory = result.messages

      // Log usage
      LOG "[Agent Core] Completed in {result.toolRounds} tool rounds"
      LOG "[Agent Core] Tokens:", result.usage

      // Send completion event
      this.sendEvent({
        type: "task_completed",
        success: true,
        result: {
          toolRounds: result.toolRounds,
          stopReason: result.stopReason,
          usage: result.usage
        }
      })

    CATCH error:
      LOG "ERROR:", error.message

      this.sendEvent({
        type: "error",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: error.message,
          suggestions: [
            "Check Claude authentication (run: claude)",
            "Check ANTHROPIC_API_KEY environment variable",
            "Ensure MCP bridge is running"
          ],
          recoverable: true
        }
      })

  // --------------------------------------------------------------------------
  // Conversation Management (NEW)
  // --------------------------------------------------------------------------

  private async handleClearConversation() {
    this.conversationHistory = []

    this.sendEvent({
      type: "conversation_cleared"
    })

    LOG "[Agent Core] Conversation cleared"
  }

  private async handleGetConversationHistory() {
    this.sendEvent({
      type: "conversation_history",
      messages: this.conversationHistory
    })
  }
}
```

## 4. Webview UI Integration (Svelte)

```typescript
/**
 * Chat component event handling
 */

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

PSEUDOCODE FOR Chat.svelte:

// Component state
messages: ChatMessage[] = []
currentMessage: ChatMessage | null = null
toolCalls: Map<string, ToolCallDisplay> = NEW Map()
isWaiting: boolean = false

// --------------------------------------------------------------------------
// Message Submission
// --------------------------------------------------------------------------

function handleSendMessage(text: string) {
  // Add user message to UI
  userMsg = {
    id: generateId(),
    role: 'user',
    content: text,
    timestamp: NEW Date()
  }

  messages.push(userMsg)
  messages = messages  // Trigger reactivity

  // Send to extension
  vscode.postMessage({
    type: 'send_message',
    messageId: userMsg.id,
    content: text
  })

  isWaiting = true
}

// --------------------------------------------------------------------------
// Event Handlers
// --------------------------------------------------------------------------

function handleAgentEvent(event: AgentEvent) {
  SWITCH event.type:

    // --------------------------------------------------------------------
    // Content Streaming
    // --------------------------------------------------------------------

    CASE 'content_delta':
      // Create new assistant message if needed
      IF currentMessage === null:
        currentMessage = {
          id: generateId(),
          role: 'assistant',
          content: '',
          toolCalls: [],
          timestamp: NEW Date()
        }
        messages.push(currentMessage)

      // Append delta to current message
      currentMessage.content += event.delta

      // Trigger reactivity
      messages = messages

      // Auto-scroll to bottom
      scrollToBottom()

    // --------------------------------------------------------------------
    // Tool Execution
    // --------------------------------------------------------------------

    CASE 'tool_call_started':
      // Create tool call display object
      toolCall = {
        id: event.toolId,
        name: event.tool,
        input: event.input,
        status: 'running',
        startTime: NEW Date()
      }

      toolCalls.set(event.toolId, toolCall)

      // Attach to current message
      IF currentMessage:
        currentMessage.toolCalls = Array.from(toolCalls.values())
        messages = messages

    CASE 'tool_call_completed':
      // Update existing tool call
      existingCall = toolCalls.get(event.toolId)

      IF existingCall:
        existingCall.status = event.error ? 'error' : 'completed'
        existingCall.result = event.result
        existingCall.error = event.error
        existingCall.executionTime = event.executionTime
        existingCall.endTime = NEW Date()

        // Update UI
        IF currentMessage:
          currentMessage.toolCalls = Array.from(toolCalls.values())
          messages = messages

    // --------------------------------------------------------------------
    // Task Completion
    // --------------------------------------------------------------------

    CASE 'task_completed':
      // Finalize current message
      currentMessage = null
      toolCalls.clear()
      isWaiting = false

      // Show usage stats if available
      IF event.result?.usage:
        displayUsageStats(event.result.usage)

    // --------------------------------------------------------------------
    // Errors
    // --------------------------------------------------------------------

    CASE 'error':
      // Show error message
      errorMsg = {
        id: generateId(),
        role: 'system',
        content: `Error: ${event.error.message}`,
        error: event.error,
        timestamp: NEW Date()
      }

      messages.push(errorMsg)
      messages = messages

      currentMessage = null
      toolCalls.clear()
      isWaiting = false
}

// --------------------------------------------------------------------------
// Tool Call Display Component
// --------------------------------------------------------------------------

<ToolCallDisplay> COMPONENT:

  PROPS:
    toolCall: ToolCallDisplay

  RENDER:
    <div class="tool-call" class:running={toolCall.status === 'running'}
                           class:completed={toolCall.status === 'completed'}
                           class:error={toolCall.status === 'error'}>

      <div class="tool-header">
        <!-- Icon based on status -->
        IF toolCall.status === 'running':
          <Spinner />
        ELSE IF toolCall.status === 'completed':
          <CheckIcon />
        ELSE IF toolCall.status === 'error':
          <ErrorIcon />

        <!-- Tool name -->
        <span class="tool-name">{toolCall.name}</span>

        <!-- Execution time -->
        IF toolCall.executionTime:
          <span class="execution-time">{toolCall.executionTime}ms</span>
      </div>

      <!-- Tool input (collapsible) -->
      <details>
        <summary>Input</summary>
        <pre>{JSON.stringify(toolCall.input, null, 2)}</pre>
      </details>

      <!-- Tool result (collapsible) -->
      IF toolCall.result:
        <details>
          <summary>Result</summary>
          <div class="tool-result">
            {formatToolResult(toolCall.result)}
          </div>
        </details>

      <!-- Error message -->
      IF toolCall.error:
        <div class="tool-error">
          {toolCall.error}
        </div>
    </div>
```

## 5. Error Handling & Edge Cases

```typescript
/**
 * Comprehensive error handling patterns
 */

// ============================================================================
// TOOL EXECUTION ERRORS
// ============================================================================

SCENARIO: MCP tool times out

  IN ClaudeToolExecutor.executeToolCalls():
    TRY:
      mcpResult = AWAIT this.config.mcpClient.callTool(
        toolCall.name,
        toolCall.input,
        30000  // 30s timeout
      )

    CATCH TimeoutError:
      // Return error result to Claude
      RETURN {
        type: 'tool_result',
        tool_use_id: toolCall.id,
        content: "Tool execution timed out after 30 seconds. The knowledge base may be unresponsive.",
        is_error: true
      }

  RESULT:
    - Claude receives error result
    - Claude can retry with different parameters or apologize to user
    - User sees error in tool call display

// ============================================================================
// CLAUDE API ERRORS
// ============================================================================

SCENARIO: Rate limit exceeded

  IN ClaudeToolExecutor.callClaudeWithTools():
    TRY:
      stream = this.config.claudeClient.messages.stream(...)

    CATCH RateLimitError as error:
      retryAfter = error.headers['retry-after']

      // Emit error event
      this.config.onEvent({
        type: 'error',
        error: {
          code: 'RATE_LIMIT_EXCEEDED',
          message: `Rate limit exceeded. Please wait ${retryAfter} seconds.`,
          suggestions: [
            'Wait before retrying',
            'Use Claude CLI with subscription for unlimited requests'
          ],
          recoverable: true,
          retryAfter: retryAfter
        }
      })

      THROW error

SCENARIO: Invalid API key

  IN ClaudeClient.detectAuthMode():
    TRY:
      // Test API key
      testResponse = AWAIT this.apiClient.messages.create({
        model: this.config.model,
        max_tokens: 1,
        messages: [{ role: 'user', content: 'test' }]
      })

    CATCH AuthenticationError:
      THROW NEW Error(
        "Invalid ANTHROPIC_API_KEY. Get your key from: https://console.anthropic.com/"
      )

// ============================================================================
// CONVERSATION MANAGEMENT
// ============================================================================

SCENARIO: Context window overflow

  IN ClaudeToolExecutor.executeWithTools():
    TRY:
      response = AWAIT this.callClaudeWithTools(messages)

    CATCH ContextLengthExceeded:
      // Truncate conversation history
      LOG "WARN: Context window exceeded, truncating history"

      // Keep system prompt + last N messages
      truncatedMessages = [
        messages[0],  // System
        ...messages.slice(-10)  // Last 10 messages
      ]

      // Retry with truncated history
      response = AWAIT this.callClaudeWithTools(truncatedMessages)

      // Update conversation history
      this.conversationHistory = truncatedMessages

// ============================================================================
// STREAMING ERRORS
// ============================================================================

SCENARIO: Stream interrupted mid-response

  IN ClaudeToolExecutor.callClaudeWithTools():
    TRY:
      FOR AWAIT event in stream:
        // Process events...

    CATCH StreamInterruptedError:
      // Emit partial content + error
      IF currentTextBlock !== '':
        this.config.onEvent({
          type: 'content_delta',
          delta: currentTextBlock
        })

      this.config.onEvent({
        type: 'error',
        error: {
          code: 'SERVICE_UNAVAILABLE',
          message: 'Stream was interrupted. Response may be incomplete.',
          suggestions: ['Try sending the message again'],
          recoverable: true
        }
      })

      THROW error
```

## Summary

This pseudocode provides:

1. **ToolFormatConverter**: Bidirectional conversion between MCP and Anthropic tool formats
2. **ClaudeToolExecutor**: Main orchestration loop for Claude API + MCP tools
3. **AgentCore Integration**: Wiring into existing agent architecture
4. **Webview UI**: Event-driven UI updates for streaming and tool execution
5. **Error Handling**: Comprehensive error scenarios and recovery strategies

The implementation follows Anthropic's native tool use format while maintaining compatibility with the existing MCP infrastructure.
