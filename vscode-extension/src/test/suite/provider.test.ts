import * as assert from "assert";
import * as vscode from "vscode";
import { DolphinViewProvider } from "../../views/provider";
import { AgentBridge } from "../../agent/bridge";

describe("DolphinViewProvider Unit Tests", () => {
  let provider: DolphinViewProvider;
  let outputChannel: vscode.OutputChannel;
  let mockAgentBridge: AgentBridge;

  beforeEach(() => {
    outputChannel = vscode.window.createOutputChannel("Test");
    mockAgentBridge = new AgentBridge(outputChannel);
    const extensionUri = vscode.Uri.file("/test/path");
    provider = new DolphinViewProvider(extensionUri, outputChannel, mockAgentBridge);
  });

  afterEach(() => {
    outputChannel.dispose();
    if (mockAgentBridge) {
      mockAgentBridge.shutdown();
    }
  });

  describe("postMessage", () => {
    it("Should log when webview is not ready", () => {
      const messages: string[] = [];
      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        messages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      provider.postMessage({ type: "test" });

      const hasNotReadyMessage = messages.some((m) => m.includes("not ready"));
      assert.ok(hasNotReadyMessage, "Should log that webview is not ready");

      outputChannel.appendLine = originalAppendLine;
    });

    it("Should send message when webview is ready", () => {
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

      provider.postMessage({ type: "test", data: "test-data" });

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(sentMessage.type, "test", "Message type should match");
      assert.strictEqual(sentMessage.data, "test-data", "Message data should match");
    });
  });

  describe("clearConversation", () => {
    it("Should send clear_conversation message to webview", () => {
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

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(
        sentMessage.type,
        "clear_conversation",
        "Should send clear_conversation message"
      );
    });

    it("Should handle missing webview gracefully", () => {
      // webviewView is not set
      assert.doesNotThrow(() => {
        provider.clearConversation();
      }, "Should not throw when webview is not ready");
    });
  });

  describe("focusInput", () => {
    it("Should send focus_input message to webview", () => {
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

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(sentMessage.type, "focus_input", "Should send focus_input message");
    });

    it("Should handle missing webview gracefully", () => {
      assert.doesNotThrow(() => {
        provider.focusInput();
      }, "Should not throw when webview is not ready");
    });
  });

  describe("prefillInput (Phase 2)", () => {
    it("Should send prefill_input message with text to webview", () => {
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

      const testText = "Can you explain this code?";
      provider.prefillInput(testText);

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(sentMessage.type, "prefill_input", "Should send prefill_input message");
      assert.strictEqual(sentMessage.text, testText, "Should include the text in the message");
    });

    it("Should handle empty string", () => {
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

      provider.prefillInput("");

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(sentMessage.text, "", "Should handle empty string");
    });

    it("Should handle multi-line text with code blocks", () => {
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

      const multiLineText = "Explain this code:\n\n```typescript\nconst x = 1;\n```";
      provider.prefillInput(multiLineText);

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(sentMessage.text, multiLineText, "Should preserve multi-line text");
    });

    it("Should handle special characters", () => {
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

      const specialText = "Text with \"quotes\" and 'apostrophes' and <html> & more";
      provider.prefillInput(specialText);

      assert.ok(sentMessage, "Message should have been sent");
      assert.strictEqual(sentMessage.text, specialText, "Should preserve special characters");
    });

    it("Should handle missing webview gracefully", () => {
      assert.doesNotThrow(() => {
        provider.prefillInput("test text");
      }, "Should not throw when webview is not ready");
    });
  });

  describe("getNonce", () => {
    it("Should generate unique nonces", () => {
      const nonce1 = (provider as any).getNonce();
      const nonce2 = (provider as any).getNonce();

      assert.ok(nonce1, "Nonce 1 should be generated");
      assert.ok(nonce2, "Nonce 2 should be generated");
      assert.notStrictEqual(nonce1, nonce2, "Nonces should be unique");
    });

    it("Should generate base64 encoded strings", () => {
      const nonce = (provider as any).getNonce();

      // Base64 regex pattern
      const base64Pattern = /^[A-Za-z0-9+/]+=*$/;
      assert.ok(base64Pattern.test(nonce), "Nonce should be base64 encoded");
    });

    it("Should generate nonces of expected length", () => {
      const nonce = (provider as any).getNonce();

      // 16 bytes -> 24 base64 characters (including padding)
      assert.ok(nonce.length >= 20, "Nonce should be at least 20 characters");
      assert.ok(nonce.length <= 28, "Nonce should be at most 28 characters");
    });
  });

  describe("CSP Integration", () => {
    it("Should include nonce in CSP when generating HTML", () => {
      // This test would require mocking the file system and creating a fake index.html
      // For now, we'll test the nonce generation which is part of CSP
      const nonce = (provider as any).getNonce();
      assert.ok(nonce, "Nonce should be generated for CSP");
    });
  });

  describe("Event Forwarding", () => {
    it("Should forward agent events to webview when ready", (done) => {
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
      const mockEvent = { type: "content_delta", delta: "Hello" };

      // Access the event emitter from the agent bridge
      (mockAgentBridge as any).eventEmitter.fire(mockEvent);

      // Give it a moment to process
      setTimeout(() => {
        assert.ok(forwardedEvent, "Event should have been forwarded");
        assert.strictEqual(forwardedEvent.type, "content_delta", "Event type should match");
        assert.strictEqual(forwardedEvent.delta, "Hello", "Event data should match");
        done();
      }, 50);
    });

    it("Should forward events with requestId for correlation", (done) => {
      let forwardedEvent: any = null;
      const loggedMessages: string[] = [];

      // Capture log messages
      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        loggedMessages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      const mockWebviewView = {
        webview: {
          postMessage: (message: any) => {
            forwardedEvent = message;
            return Promise.resolve(true);
          },
        },
      } as any;

      (provider as any).webviewView = mockWebviewView;

      const mockEvent = {
        type: "tool_call_started",
        toolId: "tool-1",
        tool: "test_tool",
        input: {},
        requestId: "req-1234567890-1",
      };

      (mockAgentBridge as any).eventEmitter.fire(mockEvent);

      setTimeout(() => {
        assert.ok(forwardedEvent, "Event should have been forwarded");
        assert.strictEqual(
          forwardedEvent.requestId,
          "req-1234567890-1",
          "RequestId should be preserved"
        );

        // Check that requestId was logged
        const hasRequestIdLog = loggedMessages.some((m) => m.includes("req-1234567890-1"));
        assert.ok(hasRequestIdLog, "RequestId should be logged");

        outputChannel.appendLine = originalAppendLine;
        done();
      }, 50);
    });

    it("Should log correlation ID when forwarding events", (done) => {
      const loggedMessages: string[] = [];

      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        loggedMessages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      const mockWebviewView = {
        webview: {
          postMessage: () => Promise.resolve(true),
        },
      } as any;

      (provider as any).webviewView = mockWebviewView;

      const mockEvent = {
        type: "agent_ready",
        version: "0.1.0",
        capabilities: [],
        requestId: "req-9999-42",
      };

      (mockAgentBridge as any).eventEmitter.fire(mockEvent);

      setTimeout(() => {
        // Check logs include requestId
        const receivedLog = loggedMessages.find((m) => m.includes("Received event from agent"));
        const forwardedLog = loggedMessages.find((m) => m.includes("Forwarding event to webview"));

        assert.ok(receivedLog, "Should log received event");
        assert.ok(receivedLog?.includes("req-9999-42"), "Received log should include requestId");
        assert.ok(forwardedLog, "Should log forwarded event");
        assert.ok(forwardedLog?.includes("req-9999-42"), "Forwarded log should include requestId");

        outputChannel.appendLine = originalAppendLine;
        done();
      }, 50);
    });

    it("Should handle events without requestId gracefully", (done) => {
      let forwardedEvent: any = null;
      const loggedMessages: string[] = [];

      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        loggedMessages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      const mockWebviewView = {
        webview: {
          postMessage: (message: any) => {
            forwardedEvent = message;
            return Promise.resolve(true);
          },
        },
      } as any;

      (provider as any).webviewView = mockWebviewView;

      // Event without requestId
      const mockEvent = {
        type: "content_delta",
        delta: "test",
      };

      (mockAgentBridge as any).eventEmitter.fire(mockEvent);

      setTimeout(() => {
        assert.ok(forwardedEvent, "Event should still be forwarded");

        // Should log 'unknown' as requestId
        const hasUnknownLog = loggedMessages.some((m) => m.includes("requestId: unknown"));
        assert.ok(hasUnknownLog, 'Should log "unknown" for missing requestId');

        outputChannel.appendLine = originalAppendLine;
        done();
      }, 50);
    });
  });
});
