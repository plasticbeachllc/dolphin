import * as assert from 'assert';
import { AgentBridge } from '../../agent/bridge';
import { ChildProcess } from 'child_process';
import { EventEmitter } from 'events';

describe('AgentBridge Unit Tests', () => {
  let agentBridge: AgentBridge;

  beforeEach(() => {
    agentBridge = new AgentBridge();
  });

  afterEach(() => {
    if (agentBridge) {
      agentBridge.shutdown();
    }
  });

  describe('clearConversation', () => {
    it('Should send clear_conversation JSON-RPC message', async () => {
      // Mock the process
      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = {
        write: (data: string) => {
          const message = JSON.parse(data);
          assert.strictEqual(message.jsonrpc, '2.0', 'Should be JSON-RPC 2.0');
          assert.strictEqual(message.method, 'clear_conversation', 'Method should be clear_conversation');
          assert.ok(message.id !== undefined, 'Should have an ID');
          assert.deepStrictEqual(message.params, {}, 'Params should be empty object');
          return true;
        },
      };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      // Inject mock process
      (agentBridge as any).process = mockProcess;

      // Call clearConversation
      await agentBridge.clearConversation();
    });

    it('Should throw error when agent process is not running', async () => {
      // Don't set up a process
      (agentBridge as any).process = null;

      try {
        await agentBridge.clearConversation();
        assert.fail('Should have thrown an error');
      } catch (error: any) {
        assert.ok(error.message.includes('not running'), 'Error should mention process not running');
      }
    });

    it('Should throw error when agent process has exited', async () => {
      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = { write: () => true };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = 1; // Process has exited

      (agentBridge as any).process = mockProcess;

      try {
        await agentBridge.clearConversation();
        assert.fail('Should have thrown an error');
      } catch (error: any) {
        assert.ok(error.message.includes('not running'), 'Error should mention process not running');
      }
    });
  });

  describe('abortGeneration', () => {
    it('Should send abort_generation JSON-RPC message', async () => {
      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = {
        write: (data: string) => {
          const message = JSON.parse(data);
          assert.strictEqual(message.jsonrpc, '2.0', 'Should be JSON-RPC 2.0');
          assert.strictEqual(message.method, 'abort_generation', 'Method should be abort_generation');
          assert.ok(message.id !== undefined, 'Should have an ID');
          return true;
        },
      };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      (agentBridge as any).process = mockProcess;

      await agentBridge.abortGeneration();
    });
  });

  describe('sendMessage', () => {
    it('Should send send_message JSON-RPC with content', async () => {
      const testContent = 'Test message content';
      let sentMessage: any;

      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = {
        write: (data: string) => {
          sentMessage = JSON.parse(data);
          return true;
        },
      };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      (agentBridge as any).process = mockProcess;

      await agentBridge.sendMessage(testContent);

      assert.strictEqual(sentMessage.jsonrpc, '2.0', 'Should be JSON-RPC 2.0');
      assert.strictEqual(sentMessage.method, 'send_message', 'Method should be send_message');
      assert.strictEqual(sentMessage.params.content, testContent, 'Should include message content');
      assert.ok(sentMessage.params.messageId, 'Should include message ID');
    });
  });

  describe('getAuthStatus', () => {
    it('Should send get_auth_status JSON-RPC and handle response', async () => {
      const mockResponse = {
        mode: 'auto',
        cliInstalled: true,
        cliAuthenticated: true,
        apiKeySet: false,
        willUseSubscription: true,
      };

      const mockProcess = new EventEmitter() as any;
      let requestId: number;

      mockProcess.stdin = {
        write: (data: string) => {
          const message = JSON.parse(data);
          requestId = message.id;

          // Simulate response from agent
          setTimeout(() => {
            mockProcess.stdout.emit('data', JSON.stringify({
              jsonrpc: '2.0',
              id: requestId,
              result: mockResponse,
            }) + '\n');
          }, 10);

          return true;
        },
      };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      (agentBridge as any).process = mockProcess;

      const result = await agentBridge.getAuthStatus();

      assert.deepStrictEqual(result, mockResponse, 'Should return auth status response');
    });

    it('Should timeout if no response received', async function () {
      this.timeout(6000);

      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = {
        write: () => true,
      };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      (agentBridge as any).process = mockProcess;

      try {
        await agentBridge.getAuthStatus();
        assert.fail('Should have thrown a timeout error');
      } catch (error: any) {
        assert.ok(error.message.includes('timeout'), 'Error should mention timeout');
      }
    });
  });

  describe('Event Handling', () => {
    it('Should fire events when receiving notifications', (done) => {
      const mockEvent = {
        type: 'agent_ready',
        version: '0.1.0',
      };

      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = { write: () => true };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      (agentBridge as any).process = mockProcess;

      // Listen for events
      agentBridge.onEvent((event) => {
        assert.strictEqual(event.type, 'agent_ready', 'Event type should match');
        assert.strictEqual((event as any).version, '0.1.0', 'Version should match');
        done();
      });

      // Simulate notification from agent
      mockProcess.stdout.emit('data', JSON.stringify({
        jsonrpc: '2.0',
        method: 'notify',
        params: mockEvent,
      }) + '\n');
    });

    it('Should handle multiple events', (done) => {
      const mockProcess = new EventEmitter() as any;
      mockProcess.stdin = { write: () => true };
      mockProcess.stdout = new EventEmitter();
      mockProcess.stderr = new EventEmitter();
      mockProcess.exitCode = null;

      (agentBridge as any).process = mockProcess;

      const receivedEvents: any[] = [];

      agentBridge.onEvent((event) => {
        receivedEvents.push(event);

        if (receivedEvents.length === 2) {
          assert.strictEqual(receivedEvents[0].type, 'agent_ready');
          assert.strictEqual(receivedEvents[1].type, 'content_delta');
          done();
        }
      });

      // Send multiple events
      mockProcess.stdout.emit('data', JSON.stringify({
        jsonrpc: '2.0',
        method: 'notify',
        params: { type: 'agent_ready' },
      }) + '\n');

      mockProcess.stdout.emit('data', JSON.stringify({
        jsonrpc: '2.0',
        method: 'notify',
        params: { type: 'content_delta', delta: 'Hello' },
      }) + '\n');
    });
  });
});
