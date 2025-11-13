# Tool Executor Unit Test Fixes - Remaining Work

## Current Status
- **12/18 tests passing** (67%)
- **6 tests failing** - all related to mock infrastructure limitations

## Failing Tests & Root Causes

### 1. "should accumulate usage across rounds" (line ~257)
**Issue**: Test expects 200+ input tokens from 2 rounds, but only getting 100 tokens (1 round executing)
**Root Cause**: `setupStreamMock()` helper uses mock responses, but the test is only making 1 API call instead of 2
**Fix**: The test needs 3 responses (2 tool calls + 1 final) to accumulate properly. Already updated to provide 3 responses, but need to verify the stream mock is cycling through them correctly.

### 2. "should abort ongoing execution" (line ~359)
**Issue**: Abort doesn't interrupt the stream, test expects rejection but gets resolution
**Root Cause**: The mock stream doesn't check for abort signals during iteration
**Fix**: Mock stream needs to check `this.isAborted` flag in the async iterator and throw error if set

### 3. "should set isAborted flag" (line ~379)
**Issue**: Same as #2 - abort flag is set but stream completes normally
**Root Cause**: Stream mock doesn't respect abort state
**Fix**: Check abort flag before yielding events in mock stream

### 4. "should handle Claude API errors" (line ~393)
**Issue**: Test sets `stream = mock(() => { throw new Error() })` but error isn't propagated
**Root Cause**: Mock is replaced after test setup, so throw doesn't work
**Fix**: Need to set the mock *before* calling `executeWithTools`, or have stream throw during iteration

### 5. "should format successful tool results" (line ~502)
**Issue**: `mockMCPClient.callTool` is never called despite setting up tool use response
**Root Cause**: `setupStreamMock()` is called AFTER `mockMCPClient.callTool` is set, which might be resetting state
**Fix**: Verify call order - setup stream mock first, then override MCP mock

### 6. "should format error tool results" (line ~544)  
**Issue**: Same as #5 - MCP tool not being called
**Root Cause**: Same as #5
**Fix**: Same as #5

## Implementation Strategy

### Option A: Fix Individual Tests (Recommended)
Update each failing test with proper mock setup:

```typescript
// For abort tests - check abort flag in mock
mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
  return {
    async *[Symbol.asyncIterator]() {
      // Check abort before yielding
      if (executor['isAborted']) {  // need to expose or check differently
        throw new Error('Generation aborted by user')
      }
      // ... yield events
    },
    async finalMessage() { ... }
  }
})

// For error tests - throw during stream creation
mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
  throw new Error('API error')
})

// For tool formatting tests - ensure proper call order
mockMCPClient.callTool = mock(...)  // Set FIRST
setupStreamMock(...)  // Then setup stream
```

### Option B: Enhance `setupStreamMock` Helper
Add support for abort checking and error scenarios:

```typescript
function setupStreamMock(...responses: any[]) {
  let callIndex = 0
  mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
    const response = responses[callIndex] || responses[responses.length - 1]
    callIndex++
    return createMockStream(response, executor)  // Pass executor for abort check
  })
}

function createMockStream(mockResponse: any, executor?: any) {
  return {
    async *[Symbol.asyncIterator]() {
      const content = mockResponse.content || [...]
      
      for (const block of content) {
        // Check abort if executor provided
        if (executor?.['isAborted']) {
          throw new Error('Generation aborted by user')
        }
        // ... yield events
      }
    },
    async finalMessage() { return mockResponse }
  }
}
```

## Quick Fix Checklist
1. ✅ Tests 1-12 already passing
2. ⏳ Test "should accumulate usage" - verify 3 responses cycle correctly
3. ⏳ Test "should abort" - add abort check to mock stream
4. ⏳ Test "should set isAborted flag" - same as #3
5. ⏳ Test "should handle API errors" - make stream throw on creation
6. ⏳ Test "format successful results" - check mock call order
7. ⏳ Test "format error results" - check mock call order

## Files to Modify
- `agent-core/tests/tool-executor-unit.test.ts` - Lines 257, 359, 379, 393, 502, 544