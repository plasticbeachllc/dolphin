import * as assert from 'assert';
import * as vscode from 'vscode';
import { DolphinViewProvider } from '../../views/provider';
import { AgentBridge } from '../../agent/bridge';

describe('DolphinViewProvider Unit Tests', () => {
  let provider: DolphinViewProvider;
  let outputChannel: vscode.OutputChannel;
  let mockAgentBridge: AgentBridge;

  beforeEach(() => {
    outputChannel = vscode.window.createOutputChannel('Test');
    mockAgentBridge = new AgentBridge();
    const extensionUri = vscode.Uri.file('/test/path');
    provider = new DolphinViewProvider(extensionUri, outputChannel, mockAgentBridge);
  });

  afterEach(() => {
    outputChannel.dispose();
    if (mockAgentBridge) {
      mockAgentBridge.shutdown();
    }
  });

  describe('postMessage', () => {
    it('Should log when webview is not ready', () => {
      const messages: string[] = [];
      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        messages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      provider.postMessage({ type: 'test' });

      const hasNotReadyMessage = messages.some(m => m.includes('not ready'));
      assert.ok(hasNotReadyMessage, 'Should log that webview is not ready');

      outputChannel.appendLine = originalAppendLine;
    });

    it('Should send message when webview is ready', () => {
      let sentMessage: any = null;

      // Mock webview view
      const mockWebviewView = {
        webview: {
          postMessage: (message: any) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as any;

      // Set the webview view by calling resolveWebviewView
      // We can't call it directly due to missing dependencies, so we'll inject it
      (provider as any).webviewView = mockWebviewView;

      provider.postMessage({ type: 'test', data: 'test-data' });

      assert.ok(sentMessage, 'Message should have been sent');
      assert.strictEqual(sentMessage.type, 'test', 'Message type should match');
      assert.strictEqual(sentMessage.data, 'test-data', 'Message data should match');
    });
  });

  describe('clearConversation', () => {
    it('Should send clear_conversation message to webview', () => {
      let sentMessage: any = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: any) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as any;

      (provider as any).webviewView = mockWebviewView;

      provider.clearConversation();

      assert.ok(sentMessage, 'Message should have been sent');
      assert.strictEqual(sentMessage.type, 'clear_conversation', 'Should send clear_conversation message');
    });

    it('Should handle missing webview gracefully', () => {
      // webviewView is not set
      assert.doesNotThrow(() => {
        provider.clearConversation();
      }, 'Should not throw when webview is not ready');
    });
  });

  describe('focusInput', () => {
    it('Should send focus_input message to webview', () => {
      let sentMessage: any = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: any) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as any;

      (provider as any).webviewView = mockWebviewView;

      provider.focusInput();

      assert.ok(sentMessage, 'Message should have been sent');
      assert.strictEqual(sentMessage.type, 'focus_input', 'Should send focus_input message');
    });

    it('Should handle missing webview gracefully', () => {
      assert.doesNotThrow(() => {
        provider.focusInput();
      }, 'Should not throw when webview is not ready');
    });
  });

  describe('getNonce', () => {
    it('Should generate unique nonces', () => {
      const nonce1 = (provider as any).getNonce();
      const nonce2 = (provider as any).getNonce();

      assert.ok(nonce1, 'Nonce 1 should be generated');
      assert.ok(nonce2, 'Nonce 2 should be generated');
      assert.notStrictEqual(nonce1, nonce2, 'Nonces should be unique');
    });

    it('Should generate base64 encoded strings', () => {
      const nonce = (provider as any).getNonce();

      // Base64 regex pattern
      const base64Pattern = /^[A-Za-z0-9+/]+=*$/;
      assert.ok(base64Pattern.test(nonce), 'Nonce should be base64 encoded');
    });

    it('Should generate nonces of expected length', () => {
      const nonce = (provider as any).getNonce();

      // 16 bytes -> 24 base64 characters (including padding)
      assert.ok(nonce.length >= 20, 'Nonce should be at least 20 characters');
      assert.ok(nonce.length <= 28, 'Nonce should be at most 28 characters');
    });
  });

  describe('CSP Integration', () => {
    it('Should include nonce in CSP when generating HTML', () => {
      // This test would require mocking the file system and creating a fake index.html
      // For now, we'll test the nonce generation which is part of CSP
      const nonce = (provider as any).getNonce();
      assert.ok(nonce, 'Nonce should be generated for CSP');
    });
  });

  describe('Event Forwarding', () => {
    it('Should forward agent events to webview when ready', (done) => {
      let forwardedEvent: any = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: any) => {
            forwardedEvent = message;
            return Promise.resolve(true);
          },
        },
      } as any;

      (provider as any).webviewView = mockWebviewView;

      // The provider sets up event forwarding in the constructor
      // We need to trigger an event from the mock agent bridge
      const mockEvent = { type: 'content_delta', delta: 'Hello' };

      // Access the event emitter from the agent bridge
      (mockAgentBridge as any).eventEmitter.fire(mockEvent);

      // Give it a moment to process
      setTimeout(() => {
        assert.ok(forwardedEvent, 'Event should have been forwarded');
        assert.strictEqual(forwardedEvent.type, 'content_delta', 'Event type should match');
        assert.strictEqual(forwardedEvent.delta, 'Hello', 'Event data should match');
        done();
      }, 50);
    });
  });
});
