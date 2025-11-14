# E2E Test Disposal Order Fix

## Problem

The e2e tests were showing DisposableStore warnings because of improper disposal order and async operations:

1. **Root Cause**:
   - `beforeEach()` creates `AgentBridge` and `DolphinViewProvider`
   - These objects register event listeners and disposables with VSCode's internal systems
   - `afterEach()` called `shutdown()` but disposal happened AFTER VSCode's test framework disposed its internal DisposableStore
   - Meanwhile, async operations (timeouts from crash recovery, event forwarding) tried to register more listeners after disposal

2. **Specific Issues**:
   - Output channel was disposed before `AgentBridge.shutdown()` completed
   - Event listeners continued firing after resources were disposed
   - Restart timers from crash recovery weren't cancelled on shutdown
   - Event emitter wasn't disposed, allowing new listeners after shutdown

## Solution

### 1. Fixed Disposal Order in Tests

**File**: `vscode-extension/src/test/suite/agent-bridge.test.ts`

- **Before**: Output channel disposed first, then AgentBridge shutdown
- **After**: AgentBridge shutdown first, THEN output channel disposal
- This prevents async operations from trying to log to a disposed channel

**File**: `vscode-extension/src/test/suite/provider.test.ts`

- **Before**: AgentBridge shutdown, then output channel disposal
- **After**: Provider disposal → AgentBridge shutdown → output channel disposal
- This stops event forwarding before shutting down the event source

### 2. Added Shutdown Guards in AgentBridge

**File**: `vscode-extension/src/agent/bridge.ts`

- Track restart timers in `restartTimers[]` array
- Cancel all restart timers in `shutdown()` to prevent async operations after disposal
- Add `isShuttingDown` checks in `handleCrash()` to prevent operations after shutdown
- Add `isShuttingDown` checks in `waitForReady()` to reject promises during shutdown
- Dispose `eventEmitter` in `shutdown()` to prevent new event listeners
- Wrap output channel logging in try-catch since it may be disposed

### 3. Added Disposal Guards in DolphinViewProvider

**File**: `vscode-extension/src/views/provider.ts`

- Add `isDisposed` flag to track disposal state
- Add `eventListenerDisposable` to track the event subscription
- Check `isDisposed` in event handler before processing events
- Wrap all output channel and webview operations in try-catch
- Add `dispose()` method that:
  1. Sets `isDisposed = true`
  2. Disposes event listener (stops receiving events)
  3. Disposes workspace change listener
  4. Clears webview reference

## Disposal Order Summary

Correct disposal order for tests:

```typescript
afterEach(() => {
  // 1. Stop event listeners (DolphinViewProvider)
  if (provider) {
    provider.dispose();
  }

  // 2. Shutdown agent and cancel async operations
  if (agentBridge) {
    agentBridge.shutdown();
  }

  // 3. Finally dispose output channel
  if (outputChannel) {
    outputChannel.dispose();
  }
});
```

## Why This Matters

VSCode's DisposableStore warnings indicate that we're trying to register disposables after the store has been disposed. This can lead to:

- Memory leaks (disposables not properly cleaned up)
- Race conditions (async operations accessing disposed resources)
- Flaky tests (timing-dependent failures)
- Resource exhaustion (timers/listeners not cancelled)

By ensuring proper disposal order and adding early-exit checks, we prevent these issues and make tests more reliable.

## Testing

To verify the fix works:

1. Close all VSCode instances
2. Run: `cd vscode-extension && npm test`
3. Look for absence of DisposableStore warnings in output
4. All tests should pass without disposal errors

## Related Files

- `vscode-extension/src/agent/bridge.ts` - AgentBridge shutdown logic
- `vscode-extension/src/views/provider.ts` - DolphinViewProvider disposal
- `vscode-extension/src/test/suite/agent-bridge.test.ts` - Test disposal order
- `vscode-extension/src/test/suite/provider.test.ts` - Test disposal order
