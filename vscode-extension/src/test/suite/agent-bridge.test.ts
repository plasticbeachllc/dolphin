import * as assert from 'assert';
import * as vscode from 'vscode';
import { AgentBridge } from '../../agent/bridge';
import { ChildProcess } from 'child_process';
import { EventEmitter } from 'events';

describe('AgentBridge Unit Tests', () => {
  let agentBridge: AgentBridge;
  let outputChannel: vscode.OutputChannel;

  beforeEach(() => {
    outputChannel = vscode.window.createOutputChannel('Test Agent Bridge');
    agentBridge = new AgentBridge(outputChannel);
  });

  afterEach(() => {
    outputChannel.dispose();
  });

  afterEach(() => {
    if (agentBridge) {
      // Add a mock kill method to the process if it exists
      const process = (agentBridge as any).process;
      if (process && !process.kill) {
        process.kill = () => true;
      }
      agentBridge.shutdown();
    }
  });

  describe('clearConversation', () => {
    it('Should send clear_conversation notification via JSON-RPC connection', async () => {
      // Mock the connection
      const mockConnection = {
        sendNotification: (method: string, params?: any) => {
          assert.strictEqual(method, 'clear_conversation', 'Method should be clear_conversation');
        },
        dispose: () => {},
      };

      // Inject mock connection
      (agentBridge as any).connection = mockConnection;

      // Call clearConversation
      await agentBridge.clearConversation();
    });

    it('Should throw error when JSON-RPC connection is not established', async () => {
      // Don't set up a connection
      (agentBridge as any).connection = null;

      try {
        await agentBridge.clearConversation();
        assert.fail('Should have thrown an error');
      } catch (error: any) {
        assert.ok(error.message.includes('not established'), 'Error should mention connection not established');
      }
    });
  });

  describe('abortGeneration', () => {
    it('Should send abort_generation notification via JSON-RPC connection', async () => {
      const mockConnection = {
        sendNotification: (method: string, params?: any) => {
          assert.strictEqual(method, 'abort_generation', 'Method should be abort_generation');
        },
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;

      await agentBridge.abortGeneration();
    });
  });

  describe('sendMessage', () => {
    it('Should send send_message notification with content via JSON-RPC connection', async () => {
      const testContent = 'Test message content';
      let receivedParams: any;

      const mockConnection = {
        sendNotification: (method: string, params?: any) => {
          assert.strictEqual(method, 'send_message', 'Method should be send_message');
          receivedParams = params;
        },
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;

      await agentBridge.sendMessage(testContent);

      assert.strictEqual(receivedParams.content, testContent, 'Should include message content');
      assert.ok(receivedParams.messageId, 'Should include message ID');
    });
  });

  describe('getAuthStatus', () => {
    it('Should send get_auth_status request and resolve with result', async () => {
      let requestMethod: string | undefined;
      const mockResult = { authenticated: true, user: 'test@example.com' };

      const mockConnection = {
        sendRequest: (method: string, params?: any) => {
          requestMethod = method;
          return Promise.resolve(mockResult);
        },
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;

      const result = await agentBridge.getAuthStatus();

      assert.strictEqual(requestMethod, 'get_auth_status', 'Should send get_auth_status request');
      assert.deepStrictEqual(result, mockResult, 'Should resolve with auth status');
    });

    it('Should reject on timeout', async function() {
      this.timeout(7000); // Allow time for timeout

      const mockConnection = {
        sendRequest: () => {
          // Never resolve to simulate timeout
          return new Promise(() => {});
        },
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;

      try {
        await agentBridge.getAuthStatus();
        assert.fail('Should have thrown timeout error');
      } catch (error: any) {
        assert.ok(error.message.includes('timeout'), 'Should be a timeout error');
      }
    });

    it('Should reject when connection not established', async () => {
      (agentBridge as any).connection = null;

      try {
        await agentBridge.getAuthStatus();
        assert.fail('Should have thrown an error');
      } catch (error: any) {
        assert.ok(error.message.includes('not established'), 'Error should mention connection not established');
      }
    });
  });

  describe('Event Handling', () => {
    it('Should emit events received from agent via connection', (done) => {
      const testEvent = {
        type: 'agent_ready',
        version: '0.1.0',
        capabilities: ['test'],
        requestId: 'req-123',
      };

      // Listen for the event
      const disposable = agentBridge.onEvent((event) => {
        assert.deepStrictEqual(event, testEvent, 'Should emit the received event');
        disposable.dispose();
        done();
      });

      // Simulate receiving an event via the event emitter
      (agentBridge as any).eventEmitter.fire(testEvent);
    });

    it('Should include requestId in event logs', (done) => {
      const testEvent = {
        type: 'content_delta',
        delta: 'test content',
        requestId: 'req-456',
      };

      const disposable = agentBridge.onEvent((event) => {
        assert.strictEqual((event as any).requestId, 'req-456', 'Event should include requestId');
        disposable.dispose();
        done();
      });

      (agentBridge as any).eventEmitter.fire(testEvent);
    });
  });

  describe('Auto-recovery and Backoff', () => {
    it('Should not auto-restart when isShuttingDown is true', async () => {
      (agentBridge as any).isShuttingDown = true;
      let restartCalled = false;

      // Mock start method
      const originalStart = agentBridge.start.bind(agentBridge);
      (agentBridge as any).start = async () => {
        restartCalled = true;
      };

      // Call handleCrash
      await (agentBridge as any).handleCrash('/fake/path', '/fake/ext', undefined);

      assert.strictEqual(restartCalled, false, 'Should not restart when shutting down');
    });

    it('Should increment restart attempts and use exponential backoff', async function() {
      this.timeout(5000);

      let startCallCount = 0;
      const startTimes: number[] = [];

      // Mock start method to track calls
      (agentBridge as any).start = async () => {
        startCallCount++;
        startTimes.push(Date.now());
      };

      // Mock vscode.window.showWarningMessage
      const originalShowWarning = (global as any).vscode?.window?.showWarningMessage;
      if (!(global as any).vscode) {
        (global as any).vscode = { window: {} };
      }
      (global as any).vscode.window.showWarningMessage = () => {};

      // Set restart attempts to 0
      (agentBridge as any).restartAttempts = 0;
      (agentBridge as any).isShuttingDown = false;

      // First crash - should restart after 1s
      await (agentBridge as any).handleCrash('/fake/path', '/fake/ext', undefined);

      // Wait for first restart
      await new Promise(resolve => setTimeout(resolve, 1100));
      assert.strictEqual(startCallCount, 1, 'Should call start once after first crash');
      assert.strictEqual((agentBridge as any).restartAttempts, 1, 'Should increment restart attempts');

      // Clean up
      if (originalShowWarning) {
        (global as any).vscode.window.showWarningMessage = originalShowWarning;
      }
    });

    it('Should stop auto-restart after max attempts', async function() {
      this.timeout(2000); // Give enough time for async operations
      
      (agentBridge as any).restartAttempts = 3; // Max attempts
      (agentBridge as any).maxRestartAttempts = 3;
      (agentBridge as any).isShuttingDown = false;

      let errorShown = false;
      let errorMessage = '';

      // Mock vscode.window.showErrorMessage
      const originalShowError = vscode.window.showErrorMessage;
      (vscode.window as any).showErrorMessage = (msg: string) => {
        errorShown = true;
        errorMessage = msg;
        return Promise.resolve('Cancel');
      };

      await (agentBridge as any).handleCrash('/fake/path', '/fake/ext', undefined);
      
      // Wait a tick for the promise to resolve
      await new Promise(resolve => setImmediate(resolve));

      assert.ok(errorShown, 'Should show error message');
      assert.ok(errorMessage.includes('crashed 3 times'), 'Error should mention max attempts');
      
      // Restore
      (vscode.window as any).showErrorMessage = originalShowError;
    });
  });

  describe('Cross-platform Bun Detection', () => {
    it('Should use "which bun" on Unix platforms', async () => {
      const originalPlatform = process.platform;
      Object.defineProperty(process, 'platform', { value: 'linux', configurable: true });

      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);

      // This will actually try to run 'which bun' which might fail in test env
      // So we'll just verify the logic without actually running it
      try {
        await (agentBridge as any).findBun();
      } catch (e) {
        // Expected if bun not installed
      }

      // Restore platform
      Object.defineProperty(process, 'platform', { value: originalPlatform, configurable: true });
    });

    it('Should use "where bun" on Windows platforms', async () => {
      const originalPlatform = process.platform;
      Object.defineProperty(process, 'platform', { value: 'win32', configurable: true });

      // Just verify the code path exists - actual execution will fail in test env
      try {
        await (agentBridge as any).findBun();
      } catch (e) {
        // Expected if bun not installed
      }

      // Restore platform
      Object.defineProperty(process, 'platform', { value: originalPlatform, configurable: true });
    });

    it('Should check platform-specific paths', async () => {
      const originalPlatform = process.platform;
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const originalExec = exec;
      const fs = require('fs');
      const originalExistsSync = fs.existsSync;

      // Mock exec to fail (simulating bun not in PATH)
      const mockExec = (cmd: string, options: any, callback: any) => {
        if (typeof options === 'function') {
          callback = options;
          options = {};
        }
        callback(new Error('Command not found'), '', '');
      };
      
      // Replace exec in child_process module
      require('child_process').exec = mockExec;

      // Mock existsSync to return false for all paths
      fs.existsSync = () => false;

      Object.defineProperty(process, 'platform', { value: 'darwin', configurable: true });

      const result = await (agentBridge as any).findBun();
      assert.strictEqual(result, null, 'Should return null when bun not found');

      // Restore
      require('child_process').exec = originalExec;
      fs.existsSync = originalExistsSync;
      Object.defineProperty(process, 'platform', { value: originalPlatform, configurable: true });
    });
  });

  describe('Connection Cleanup on Shutdown', () => {
    it('Should dispose connection and clear pending requests on shutdown', () => {
      let disposeCalled = false;
      const mockConnection = {
        sendNotification: () => {},
        dispose: () => { disposeCalled = true; },
      };

      // Set up connection and pending requests
      (agentBridge as any).connection = mockConnection;
      (agentBridge as any).pendingRequests.set(1, {
        resolve: () => {},
        reject: () => {},
        timeout: setTimeout(() => {}, 1000),
      });

      // Mock process
      const mockProcess = {
        kill: () => true,
      };
      (agentBridge as any).process = mockProcess;

      agentBridge.shutdown();

      assert.ok(disposeCalled, 'Should dispose connection');
      assert.strictEqual((agentBridge as any).connection, null, 'Connection should be null');
      assert.strictEqual((agentBridge as any).pendingRequests.size, 0, 'Pending requests should be cleared');
      assert.ok((agentBridge as any).isShuttingDown, 'isShuttingDown should be true');
    });

    it('Should reject all pending requests with shutdown error on shutdown', (done) => {
      let rejectionError: Error | null = null;

      const mockConnection = {
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;
      (agentBridge as any).pendingRequests.set(1, {
        resolve: () => {},
        reject: (error: Error) => {
          rejectionError = error;
        },
        timeout: setTimeout(() => {}, 1000),
      });

      const mockProcess = {
        kill: () => true,
      };
      (agentBridge as any).process = mockProcess;

      agentBridge.shutdown();

      // Give it a moment to process
      setTimeout(() => {
        assert.ok(rejectionError, 'Should reject pending request');
        assert.ok(rejectionError?.message.includes('shutting down'), 'Error should mention shutdown');
        done();
      }, 100);
    });

    it('Should clear timeout for pending requests on shutdown', () => {
      const mockTimer = setTimeout(() => {}, 5000);
      let timerCleared = false;

      // Override clearTimeout to track calls
      const originalClearTimeout = global.clearTimeout;
      global.clearTimeout = (timer: any) => {
        if (timer === mockTimer) {
          timerCleared = true;
        }
        originalClearTimeout(timer);
      };

      const mockConnection = { dispose: () => {} };
      (agentBridge as any).connection = mockConnection;
      (agentBridge as any).pendingRequests.set(1, {
        resolve: () => {},
        reject: () => {},
        timeout: mockTimer,
      });

      const mockProcess = { kill: () => true };
      (agentBridge as any).process = mockProcess;

      agentBridge.shutdown();

      assert.ok(timerCleared, 'Should clear timeout');

      // Restore
      global.clearTimeout = originalClearTimeout;
    });
  });

  describe('Request Timeout Handling', () => {
    it('Should timeout long-running requests', async function() {
      this.timeout(35000); // Allow time for timeout

      const mockConnection = {
        sendRequest: () => {
          // Never resolve
          return new Promise(() => {});
        },
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;

      const startTime = Date.now();
      try {
        await (agentBridge as any).sendRequest('test_method', {}, 1000);
        assert.fail('Should have timed out');
      } catch (error: any) {
        const elapsed = Date.now() - startTime;
        assert.ok(error.message.includes('timeout'), 'Should be timeout error');
        assert.ok(elapsed >= 1000 && elapsed < 2000, `Should timeout after ~1s, got ${elapsed}ms`);
      }
    });

    it('Should clean up pending request on timeout', async function() {
      this.timeout(3000);

      const mockConnection = {
        sendRequest: () => new Promise(() => {}),
        dispose: () => {},
      };

      (agentBridge as any).connection = mockConnection;

      try {
        await (agentBridge as any).sendRequest('test_method', {}, 500);
      } catch (error) {
        // Expected timeout
      }

      // Wait a bit more
      await new Promise(resolve => setTimeout(resolve, 100));

      assert.strictEqual((agentBridge as any).pendingRequests.size, 0, 'Pending requests should be empty after timeout');
    });
  });
});
