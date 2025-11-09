# Streaming Response Handling Guide

## Overview

This guide details how to handle streaming responses from Claude API in the Dolphin web interface, including text streaming, tool use detection, and progressive UI updates.

## Anthropic Streaming Events

### Event Types

```typescript
// Anthropic SDK streaming events
type StreamEvent =
  | MessageStartEvent
  | ContentBlockStartEvent
  | ContentBlockDeltaEvent
  | ContentBlockStopEvent
  | MessageDeltaEvent
  | MessageStopEvent

interface MessageStartEvent {
  type: 'message_start';
  message: {
    id: string;
    type: 'message';
    role: 'assistant';
    content: [];
    model: string;
    usage: { input_tokens: number };
  };
}

interface ContentBlockStartEvent {
  type: 'content_block_start';
  index: number;
  content_block: TextBlock | ToolUseBlock;
}

interface ContentBlockDeltaEvent {
  type: 'content_block_delta';
  index: number;
  delta: TextDelta | InputJsonDelta;
}

interface ContentBlockStopEvent {
  type: 'content_block_stop';
  index: number;
}

interface MessageStopEvent {
  type: 'message_stop';
}
```

## Streaming Patterns

### 1. Simple Text Streaming

**Scenario**: Claude responds with only text, no tools

```
Event Sequence:
─────────────────────────────────────────────────────
1. message_start
   → Initialize message metadata

2. content_block_start (index: 0)
   → content_block: { type: 'text', text: '' }

3. content_block_delta (index: 0)
   → delta: { type: 'text_delta', text: 'I' }

4. content_block_delta (index: 0)
   → delta: { type: 'text_delta', text: ' can help' }

5. content_block_delta (index: 0)
   → delta: { type: 'text_delta', text: ' you with that.' }

6. content_block_stop (index: 0)

7. message_stop
```

**Handler Implementation**:

```typescript
let currentText = '';

for await (const event of stream) {
  switch (event.type) {
    case 'content_block_start':
      if (event.content_block.type === 'text') {
        currentText = '';
      }
      break;

    case 'content_block_delta':
      if (event.delta.type === 'text_delta') {
        // Stream to UI immediately
        currentText += event.delta.text;

        emitToUI({
          type: 'content_delta',
          delta: event.delta.text
        });
      }
      break;

    case 'content_block_stop':
      // Text block complete
      console.log('Final text:', currentText);
      break;
  }
}
```

### 2. Text + Tool Use Streaming

**Scenario**: Claude responds with thinking text, then uses a tool

```
Event Sequence:
─────────────────────────────────────────────────────
1. message_start

2. content_block_start (index: 0)
   → content_block: { type: 'text', text: '' }

3. content_block_delta (index: 0) × N
   → delta: { type: 'text_delta', text: '...' }
   "Let me search for that information."

4. content_block_stop (index: 0)

5. content_block_start (index: 1)
   → content_block: {
       type: 'tool_use',
       id: 'toolu_01A2B3C4',
       name: 'search_knowledge'
     }

6. content_block_delta (index: 1) × N
   → delta: {
       type: 'input_json_delta',
       partial_json: '{"qu'
     }
   → delta: {
       type: 'input_json_delta',
       partial_json: 'ery":"auth'
     }
   → delta: {
       type: 'input_json_delta',
       partial_json: 'entication"}'
     }

7. content_block_stop (index: 1)

8. message_stop
```

**Handler Implementation**:

```typescript
const contentBlocks: ContentBlock[] = [];
let currentBlock: any = null;

for await (const event of stream) {
  switch (event.type) {
    case 'content_block_start':
      if (event.content_block.type === 'text') {
        currentBlock = { type: 'text', text: '' };
      } else if (event.content_block.type === 'tool_use') {
        currentBlock = {
          type: 'tool_use',
          id: event.content_block.id,
          name: event.content_block.name,
          inputJson: ''
        };
      }
      break;

    case 'content_block_delta':
      if (event.delta.type === 'text_delta') {
        currentBlock.text += event.delta.text;

        // Stream to UI
        emitToUI({
          type: 'content_delta',
          delta: event.delta.text
        });
      } else if (event.delta.type === 'input_json_delta') {
        // Accumulate JSON (don't emit yet)
        currentBlock.inputJson += event.delta.partial_json;
      }
      break;

    case 'content_block_stop':
      // Finalize current block
      if (currentBlock.type === 'tool_use') {
        // Parse accumulated JSON
        currentBlock.input = JSON.parse(currentBlock.inputJson);
        delete currentBlock.inputJson;

        // Emit tool call event
        emitToUI({
          type: 'tool_call_started',
          toolId: currentBlock.id,
          tool: currentBlock.name,
          input: currentBlock.input
        });
      }

      contentBlocks.push(currentBlock);
      currentBlock = null;
      break;
  }
}
```

### 3. Multiple Tool Uses in Sequence

**Scenario**: Claude uses multiple tools in one response

```
Event Sequence:
─────────────────────────────────────────────────────
1. message_start

2. content_block_start (index: 0) - text
3. content_block_delta (index: 0) × N
4. content_block_stop (index: 0)

5. content_block_start (index: 1) - tool_use (search_knowledge)
6. content_block_delta (index: 1) × N - input_json_delta
7. content_block_stop (index: 1)

8. content_block_start (index: 2) - tool_use (fetch_chunk)
9. content_block_delta (index: 2) × N - input_json_delta
10. content_block_stop (index: 2)

11. message_stop
```

**Key Points**:
- Each tool use is a separate content block
- Tools are emitted sequentially in the stream
- All tools should be executed in parallel (after stream completes)

## UI Update Patterns

### Real-Time Text Updates

```typescript
// Svelte component state
let messages: ChatMessage[] = [];
let currentMessage: ChatMessage | null = null;

function handleContentDelta(delta: string) {
  // Create new message if needed
  if (!currentMessage) {
    currentMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: new Date()
    };
    messages = [...messages, currentMessage];
  }

  // Append delta
  currentMessage.content += delta;

  // Trigger Svelte reactivity
  messages = messages;

  // Auto-scroll to bottom
  requestAnimationFrame(() => {
    scrollToBottom();
  });
}
```

### Progressive Tool Display

```typescript
interface ToolCallDisplay {
  id: string;
  name: string;
  input: any;
  result?: any;
  status: 'pending' | 'running' | 'completed' | 'error';
  executionTime?: number;
}

let toolCalls = new Map<string, ToolCallDisplay>();

function handleToolCallStarted(event: ToolCallStartedEvent) {
  const toolCall: ToolCallDisplay = {
    id: event.toolId,
    name: event.tool,
    input: event.input,
    status: 'running'
  };

  toolCalls.set(event.toolId, toolCall);

  // Attach to current message
  if (currentMessage) {
    currentMessage.toolCalls = Array.from(toolCalls.values());
    messages = messages;
  }
}

function handleToolCallCompleted(event: ToolCallCompletedEvent) {
  const toolCall = toolCalls.get(event.toolId);

  if (toolCall) {
    toolCall.status = event.error ? 'error' : 'completed';
    toolCall.result = event.result;
    toolCall.executionTime = event.executionTime;

    if (currentMessage) {
      currentMessage.toolCalls = Array.from(toolCalls.values());
      messages = messages;
    }
  }
}
```

## Performance Optimization

### 1. Debounced UI Updates

For very fast streaming, debounce UI updates to reduce re-renders:

```typescript
let textBuffer = '';
let updateScheduled = false;

function handleContentDelta(delta: string) {
  textBuffer += delta;

  if (!updateScheduled) {
    updateScheduled = true;

    requestAnimationFrame(() => {
      // Flush buffer to UI
      if (currentMessage) {
        currentMessage.content += textBuffer;
        messages = messages;
      }

      textBuffer = '';
      updateScheduled = false;
    });
  }
}
```

**Result**: Updates are batched per animation frame (~60fps) instead of every delta event (~100+ fps)

### 2. Virtual Scrolling for Long Responses

For very long responses, use virtual scrolling:

```svelte
<script>
  import { VirtualList } from 'svelte-virtual-list';

  let messages = [];
</script>

<VirtualList items={messages} let:item>
  <MessageComponent message={item} />
</VirtualList>
```

### 3. Lazy Rendering of Tool Results

Don't render large tool results by default:

```svelte
<details class="tool-result">
  <summary>
    Result ({formatBytes(result.length)})
  </summary>

  {#if expanded}
    <pre>{result}</pre>
  {/if}
</details>
```

## Error Handling During Streaming

### Stream Interruption

```typescript
try {
  for await (const event of stream) {
    // Process events...
  }
} catch (error) {
  if (error instanceof StreamInterruptedError) {
    // Show partial content + warning
    emitToUI({
      type: 'content_delta',
      delta: '\n\n⚠️ Stream was interrupted'
    });

    emitToUI({
      type: 'task_completed',
      success: false,
      error: 'Stream interrupted'
    });
  }
}
```

### Malformed JSON in Tool Input

```typescript
case 'content_block_stop':
  if (currentBlock.type === 'tool_use') {
    try {
      currentBlock.input = JSON.parse(currentBlock.inputJson);
    } catch (error) {
      console.error('Failed to parse tool input:', currentBlock.inputJson);

      // Emit error
      emitToUI({
        type: 'error',
        error: {
          code: 'INVALID_TOOL_INPUT',
          message: 'Claude generated invalid tool input JSON',
          recoverable: false
        }
      });

      // Use empty object as fallback
      currentBlock.input = {};
    }
  }
```

## Testing Streaming Behavior

### Mock Stream for Testing

```typescript
async function* mockStream(events: StreamEvent[]) {
  for (const event of events) {
    yield event;
    await sleep(10); // Simulate network delay
  }
}

// Test text streaming
const textEvents: StreamEvent[] = [
  { type: 'message_start', message: { /* ... */ } },
  { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } },
  { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: 'Hello' } },
  { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: ' world' } },
  { type: 'content_block_stop', index: 0 },
  { type: 'message_stop' }
];

const stream = mockStream(textEvents);
const result = await processStream(stream);
assert.equal(result.content, 'Hello world');
```

### Integration Test with Real API

```typescript
import Anthropic from '@anthropic-ai/sdk';

describe('Streaming Integration', () => {
  it('handles real Claude streaming', async () => {
    const client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY
    });

    const events: string[] = [];

    const stream = client.messages.stream({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 100,
      messages: [{ role: 'user', content: 'Say hello' }]
    });

    for await (const event of stream) {
      events.push(event.type);
    }

    expect(events).toContain('message_start');
    expect(events).toContain('content_block_start');
    expect(events).toContain('content_block_delta');
    expect(events).toContain('content_block_stop');
    expect(events).toContain('message_stop');
  }, 30000);
});
```

## Best Practices

### 1. Always Wait for `content_block_stop`

Don't process content blocks until they're complete:

```typescript
// ❌ BAD: Process immediately
case 'content_block_start':
  if (event.content_block.type === 'tool_use') {
    // DON'T emit tool call here - input not ready yet!
    emitToolCall(event.content_block);
  }

// ✅ GOOD: Wait for stop event
case 'content_block_stop':
  if (currentBlock.type === 'tool_use') {
    currentBlock.input = JSON.parse(currentBlock.inputJson);
    emitToolCall(currentBlock);
  }
```

### 2. Handle Out-of-Order Events

Stream events should be in order, but be defensive:

```typescript
const contentBlocks: Map<number, ContentBlock> = new Map();

case 'content_block_delta':
  // Get or create block at index
  let block = contentBlocks.get(event.index);

  if (!block) {
    console.warn('Delta for unknown block:', event.index);
    return;
  }

  // Process delta...
```

### 3. Clean Up on Completion

Always reset state when stream completes:

```typescript
case 'message_stop':
  // Emit final event
  emitToUI({ type: 'task_completed', success: true });

  // Clean up state
  currentMessage = null;
  contentBlocks.clear();
  toolCalls.clear();
```

### 4. Preserve Message History

Keep full content blocks for conversation history:

```typescript
// Store complete messages with content blocks
conversationHistory.push({
  role: 'assistant',
  content: [
    { type: 'text', text: 'Let me search for that.' },
    {
      type: 'tool_use',
      id: 'toolu_123',
      name: 'search_knowledge',
      input: { query: 'authentication' }
    }
  ]
});

// This is needed for the next API call in multi-turn conversations
```

## Streaming Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   Claude API Stream                      │
│                                                          │
│  message_start                                           │
│  ────────────────────────────────────────────────────▶   │
│                                                          │
│  content_block_start (text)                              │
│  ────────────────────────────────────────────────────▶   │
│                                                          │
│  content_block_delta × N (text chunks)                   │
│  ─────▶ ─────▶ ─────▶ ─────▶ ─────▶ ─────▶ ─────▶      │
│     "I"  " can"  " help" " you" " with" " that"          │
│                                                          │
│  content_block_stop                                      │
│  ────────────────────────────────────────────────────▶   │
│                                                          │
│  content_block_start (tool_use)                          │
│  ────────────────────────────────────────────────────▶   │
│                                                          │
│  content_block_delta × N (JSON chunks)                   │
│  ─────▶ ─────▶ ─────▶ ─────▶ ─────▶                     │
│   '{"q'  'uery'  '":"'  'auth'  '"}'                     │
│                                                          │
│  content_block_stop                                      │
│  ────────────────────────────────────────────────────▶   │
│                                                          │
│  message_stop                                            │
│  ────────────────────────────────────────────────────▶   │
└─────────────────────────────────────────────────────────┘
                        │
                        │ Event Stream
                        ▼
┌─────────────────────────────────────────────────────────┐
│               ClaudeToolExecutor                         │
│                                                          │
│  Text Delta Handler                                      │
│  ────────────────────────────────────────────────────▶   │
│    Accumulate text                                       │
│    Emit to UI immediately                                │
│                                                          │
│  Tool Use Handler                                        │
│  ────────────────────────────────────────────────────▶   │
│    Accumulate JSON                                       │
│    Parse on block_stop                                   │
│    Emit tool call event                                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        │
                        │ Agent Events
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  Agent Core (stdio)                      │
│                                                          │
│  { type: 'content_delta', delta: '...' }                 │
│  { type: 'tool_call_started', ... }                      │
│  { type: 'tool_call_completed', ... }                    │
│  { type: 'task_completed', ... }                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        │
                        │ JSON-RPC
                        ▼
┌─────────────────────────────────────────────────────────┐
│              VSCode Extension (Bridge)                   │
│                                                          │
│  Forward events to webview                               │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        │
                        │ postMessage
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  Webview (Svelte UI)                     │
│                                                          │
│  Update DOM incrementally                                │
│  ┌───────────────────────────────────┐                  │
│  │  Assistant: I can help you with   │                  │
│  │  that█                             │ ◀─ Text cursor  │
│  │                                    │                  │
│  │  🔧 search_knowledge               │                  │
│  │     Running... ⏳                  │ ◀─ Tool status   │
│  └───────────────────────────────────┘                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Summary

Key takeaways for streaming implementation:

1. **Text**: Stream character-by-character to UI for responsiveness
2. **Tool Use**: Buffer JSON until complete, then parse and emit
3. **UI Updates**: Use reactive patterns (Svelte stores, React state)
4. **Performance**: Debounce updates, virtual scroll for long content
5. **Error Handling**: Handle interruptions, malformed JSON gracefully
6. **Testing**: Mock streams for unit tests, real API for integration

This approach provides a smooth, real-time user experience while maintaining robustness and correctness.
