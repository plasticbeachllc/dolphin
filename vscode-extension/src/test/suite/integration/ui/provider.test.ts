import * as assert from "assert";
import * as vscode from "vscode";
import { DolphinViewProvider } from "../../../../views/provider";
import { AgentBridge } from "../../../../agent/bridge";
import { createMockOutputChannel } from "../../../helpers/mock-output-channel";

describe("DolphinViewProvider Unit Tests", () => {
  let provider: DolphinViewProvider;
  let outputChannel: vscode.OutputChannel;
  let mockAgentBridge: AgentBridge;

  beforeEach(() => {
    outputChannel = createMockOutputChannel("Test");
    mockAgentBridge = new AgentBridge(outputChannel);
    const extensionUri = vscode.Uri.file("/test/path");
    provider = new DolphinViewProvider(extensionUri, outputChannel, mockAgentBridge);
  });

  afterEach(async () => {
    // CRITICAL: Dispose provider FIRST to stop event forwarding
    if (provider) {
      provider.dispose();
    }

    // Then shutdown agent bridge to stop async operations
    if (mockAgentBridge) {
      const process = (mockAgentBridge as unknown as Record<string, unknown>).process as
        | Record<string, unknown>
        | undefined;
      if (process && !process.kill) {
        process.kill = () => true;
      }
      await mockAgentBridge.shutdown();
    }

    // Wait for shutdown to complete before disposing output channel
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Finally dispose output channel
    if (outputChannel) {
      outputChannel.dispose();
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

      provider.postMessage({ type: "focus_input" });

      const hasNotReadyMessage = messages.some((m) => m.includes("not ready"));
      assert.ok(hasNotReadyMessage, "Should log that webview is not ready");

      outputChannel.appendLine = originalAppendLine;
    });

    it("Should send message when webview is ready", () => {
      let sentMessage: unknown = null;

      // Mock webview view
      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      // Set the webview view by calling resolveWebviewView
      // We can't call it directly due to missing dependencies, so we'll inject it
      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      provider.postMessage({
        type: "workspace_changed",
        hasWorkspace: true,
        capabilities: ["kb_search"],
        workspaceName: "demo",
        workspacePath: "/tmp/demo",
      });

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(messageRecord.type, "workspace_changed", "Message type should match");
      assert.strictEqual(messageRecord.hasWorkspace, true, "Should propagate payload fields");
    });
  });

  describe("clearConversation", () => {
    it("Should send clear_conversation message to webview", () => {
      let sentMessage: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      provider.clearConversation();

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(
        messageRecord.type,
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
      let sentMessage: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      provider.focusInput();

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(messageRecord.type, "focus_input", "Should send focus_input message");
    });

    it("Should handle missing webview gracefully", () => {
      assert.doesNotThrow(() => {
        provider.focusInput();
      }, "Should not throw when webview is not ready");
    });
  });

  describe("prefillInput (Phase 2)", () => {
    it("Should send prefill_input message with text to webview", () => {
      let sentMessage: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      const testText = "Can you explain this code?";
      provider.prefillInput(testText);

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(messageRecord.type, "prefill_input", "Should send prefill_input message");
      assert.strictEqual(messageRecord.text, testText, "Should include the text in the message");
    });

    it("Should handle empty string", () => {
      let sentMessage: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      provider.prefillInput("");

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(messageRecord.text, "", "Should handle empty string");
    });

    it("Should handle multi-line text with code blocks", () => {
      let sentMessage: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      const multiLineText = "Explain this code:\n\n```typescript\nconst x = 1;\n```";
      provider.prefillInput(multiLineText);

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(messageRecord.text, multiLineText, "Should preserve multi-line text");
    });

    it("Should handle special characters", () => {
      let sentMessage: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            sentMessage = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      const specialText = "Text with \"quotes\" and 'apostrophes' and <html> & more";
      provider.prefillInput(specialText);

      assert.ok(sentMessage, "Message should have been sent");
      const messageRecord = sentMessage as Record<string, unknown>;
      assert.strictEqual(messageRecord.text, specialText, "Should preserve special characters");
    });

    it("Should handle missing webview gracefully", () => {
      assert.doesNotThrow(() => {
        provider.prefillInput("test text");
      }, "Should not throw when webview is not ready");
    });
  });

  describe("getNonce", () => {
    it("Should generate unique nonces", () => {
      type ProviderWithGetNonce = {
        getNonce: () => string;
      };
      const nonce1 = (provider as unknown as ProviderWithGetNonce).getNonce();
      const nonce2 = (provider as unknown as ProviderWithGetNonce).getNonce();

      assert.ok(nonce1, "Nonce 1 should be generated");
      assert.ok(nonce2, "Nonce 2 should be generated");
      assert.notStrictEqual(nonce1, nonce2, "Nonces should be unique");
    });

    it("Should generate base64 encoded strings", () => {
      type ProviderWithGetNonce = {
        getNonce: () => string;
      };
      const nonce = (provider as unknown as ProviderWithGetNonce).getNonce();

      // Base64 regex pattern
      const base64Pattern = /^[A-Za-z0-9+/]+=*$/;
      assert.ok(base64Pattern.test(nonce), "Nonce should be base64 encoded");
    });

    it("Should generate nonces of expected length", () => {
      type ProviderWithGetNonce = {
        getNonce: () => string;
      };
      const nonce = (provider as unknown as ProviderWithGetNonce).getNonce();

      // 16 bytes -> 24 base64 characters (including padding)
      assert.ok(nonce.length >= 20, "Nonce should be at least 20 characters");
      assert.ok(nonce.length <= 28, "Nonce should be at most 28 characters");
    });
  });

  describe("CSP Integration", () => {
    it("Should include nonce in CSP when generating HTML", () => {
      // This test would require mocking the file system and creating a fake index.html
      // For now, we'll test the nonce generation which is part of CSP
      type ProviderWithGetNonce = {
        getNonce: () => string;
      };
      const nonce = (provider as unknown as ProviderWithGetNonce).getNonce();
      assert.ok(nonce, "Nonce should be generated for CSP");
    });
  });

  describe("Event Forwarding", () => {
    it("Should forward agent events to webview when ready", (done) => {
      let forwardedEvent: unknown = null;

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            forwardedEvent = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      // The provider sets up event forwarding in the constructor
      // We need to trigger an event from the mock agent bridge
      const mockEvent = { type: "content_delta", delta: "Hello" };

      // Access the event emitter from the agent bridge
      type AgentBridgeWithEmitter = {
        eventEmitter: { fire: (event: Record<string, unknown>) => void };
      };
      (mockAgentBridge as unknown as AgentBridgeWithEmitter).eventEmitter.fire(mockEvent);

      // Give it a moment to process
      setTimeout(() => {
        assert.ok(forwardedEvent, "Event should have been forwarded");
        const eventRecord = forwardedEvent as Record<string, unknown>;
        assert.strictEqual(eventRecord.type, "content_delta", "Event type should match");
        assert.strictEqual(eventRecord.delta, "Hello", "Event data should match");
        done();
      }, 50);
    });

    it("Should forward events with requestId for correlation", (done) => {
      let forwardedEvent: unknown = null;
      const loggedMessages: string[] = [];

      // Capture log messages
      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        loggedMessages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            forwardedEvent = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      const mockEvent = {
        type: "tool_call_started",
        toolId: "tool-1",
        tool: "test_tool",
        input: {},
        requestId: "req-1234567890-1",
      };

      type AgentBridgeWithEmitter = {
        eventEmitter: { fire: (event: Record<string, unknown>) => void };
      };
      (mockAgentBridge as unknown as AgentBridgeWithEmitter).eventEmitter.fire(mockEvent);

      setTimeout(() => {
        assert.ok(forwardedEvent, "Event should have been forwarded");
        const eventRecord = forwardedEvent as Record<string, unknown>;
        assert.strictEqual(
          eventRecord.requestId,
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
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      const mockEvent = {
        type: "agent_ready",
        version: "0.1.0",
        capabilities: [],
        requestId: "req-9999-42",
      };

      type AgentBridgeWithEmitter = {
        eventEmitter: { fire: (event: Record<string, unknown>) => void };
      };
      (mockAgentBridge as unknown as AgentBridgeWithEmitter).eventEmitter.fire(mockEvent);

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
      let forwardedEvent: unknown = null;
      const loggedMessages: string[] = [];

      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        loggedMessages.push(message);
        return originalAppendLine.call(outputChannel, message);
      };

      const mockWebviewView = {
        webview: {
          postMessage: (message: unknown) => {
            forwardedEvent = message;
            return Promise.resolve(true);
          },
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as Record<string, unknown>).webviewView = mockWebviewView;

      // Event without requestId
      const mockEvent = {
        type: "content_delta",
        delta: "test",
      };

      type AgentBridgeWithEmitter = {
        eventEmitter: { fire: (event: Record<string, unknown>) => void };
      };
      (mockAgentBridge as unknown as AgentBridgeWithEmitter).eventEmitter.fire(mockEvent);

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

  describe("auth status requests", () => {
    it("forwards provider-aware payloads to the webview", async () => {
      const posted: unknown[] = [];
      let messageHandler: ((message: unknown) => Thenable<void> | void) | undefined;

      const mockWebviewView = {
        webview: {
          options: {},
          postMessage: (message: unknown) => {
            posted.push(message);
            return Promise.resolve(true);
          },
          onDidReceiveMessage: (callback: (message: unknown) => Thenable<void> | void) => {
            messageHandler = callback;
            return { dispose: () => {} };
          },
          asWebviewUri: (resource: vscode.Uri) => resource,
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as { getHtml: () => string }).getHtml = () =>
        "<!doctype html><html></html>";
      (provider as unknown as { sendTheme: () => void }).sendTheme = () => {};
      provider.resolveWebviewView(mockWebviewView);

      const expected = {
        providers: [{ provider: "anthropic", authenticated: true, mode: "subscription" }],
      };
      (mockAgentBridge as unknown as { getAuthStatus: () => Promise<unknown> }).getAuthStatus =
        async () => expected;

      await (messageHandler as (message: unknown) => Promise<void>)({ type: "get_auth_status" });

      assert.strictEqual(posted.length, 1, "Should emit one auth_status message");
      const payload = posted[0] as { type: string; status: unknown };
      assert.strictEqual(payload.type, "auth_status", "Should forward auth_status type");
      assert.deepStrictEqual(payload.status, expected, "Should forward provider payload");
    });
  });

  describe("secret command bridging", () => {
    let originalExecuteCommand: typeof vscode.commands.executeCommand;

    before(() => {
      originalExecuteCommand = vscode.commands.executeCommand;
    });

    afterEach(() => {
      vscode.commands.executeCommand = originalExecuteCommand;
    });

    it("invokes provider-specific command and emits success status", async () => {
      const posted: unknown[] = [];
      let messageHandler: ((message: unknown) => Thenable<void> | void) | undefined;

      const mockWebviewView = {
        webview: {
          options: {},
          postMessage: (message: unknown) => {
            posted.push(message);
            return Promise.resolve(true);
          },
          onDidReceiveMessage: (callback: (message: unknown) => Thenable<void> | void) => {
            messageHandler = callback;
            return { dispose: () => {} };
          },
          asWebviewUri: (resource: vscode.Uri) => resource,
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as { getHtml: () => string }).getHtml = () =>
        "<!doctype html><html></html>";
      (provider as unknown as { sendTheme: () => void }).sendTheme = () => {};
      provider.resolveWebviewView(mockWebviewView);

      let invokedCommand: string | undefined;
      vscode.commands.executeCommand = (async (command: string) => {
        invokedCommand = command;
        return undefined;
      }) as typeof vscode.commands.executeCommand;

      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "setSecret",
        provider: "anthropic",
      });

      assert.strictEqual(invokedCommand, "dolphin.setClaudeApiKey");
      const payload = posted[posted.length - 1] as { type: string; provider: string; ok: boolean };
      assert.deepStrictEqual(payload, {
        type: "secretStatus",
        provider: "anthropic",
        ok: true,
      });
    });

    it("returns failure metadata when the command throws", async () => {
      const posted: unknown[] = [];
      let messageHandler: ((message: unknown) => Thenable<void> | void) | undefined;

      const mockWebviewView = {
        webview: {
          options: {},
          postMessage: (message: unknown) => {
            posted.push(message);
            return Promise.resolve(true);
          },
          onDidReceiveMessage: (callback: (message: unknown) => Thenable<void> | void) => {
            messageHandler = callback;
            return { dispose: () => {} };
          },
          asWebviewUri: (resource: vscode.Uri) => resource,
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as { getHtml: () => string }).getHtml = () =>
        "<!doctype html><html></html>";
      (provider as unknown as { sendTheme: () => void }).sendTheme = () => {};
      provider.resolveWebviewView(mockWebviewView);

      vscode.commands.executeCommand = (async () => {
        throw new Error("Command failed");
      }) as typeof vscode.commands.executeCommand;

      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "setSecret",
        provider: "openai",
      });

      const payload = posted[posted.length - 1] as {
        type: string;
        provider: string;
        ok: boolean;
        message?: string;
      };
      assert.strictEqual(payload.type, "secretStatus");
      assert.strictEqual(payload.provider, "openai");
      assert.strictEqual(payload.ok, false);
      assert.ok(payload.message?.includes("Command failed"));
    });
  });

  describe("provider settings messages", () => {
    it("handles get_provider_settings request", async () => {
      const posted: unknown[] = [];
      let messageHandler: ((message: unknown) => Thenable<void> | void) | undefined;

      const mockWebviewView = {
        webview: {
          options: {},
          postMessage: (message: unknown) => {
            posted.push(message);
            return Promise.resolve(true);
          },
          onDidReceiveMessage: (callback: (message: unknown) => Thenable<void> | void) => {
            messageHandler = callback;
            return { dispose: () => {} };
          },
          asWebviewUri: (resource: vscode.Uri) => resource,
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as { getHtml: () => string }).getHtml = () =>
        "<!doctype html><html></html>";
      (provider as unknown as { sendTheme: () => void }).sendTheme = () => {};
      provider.resolveWebviewView(mockWebviewView);

      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "get_provider_settings",
      });

      const payload = posted[posted.length - 1] as {
        type: string;
        currentProvider: string;
        availableProviders: unknown[];
      };
      assert.strictEqual(payload.type, "provider_settings");
      assert.ok(payload.currentProvider, "Should return current provider");
      assert.ok(payload.availableProviders.length > 0, "Should return available providers");
    });

    it("handles save_provider_settings request", async () => {
      const posted: unknown[] = [];
      let messageHandler: ((message: unknown) => Thenable<void> | void) | undefined;

      const mockWebviewView = {
        webview: {
          options: {},
          postMessage: (message: unknown) => {
            posted.push(message);
            return Promise.resolve(true);
          },
          onDidReceiveMessage: (callback: (message: unknown) => Thenable<void> | void) => {
            messageHandler = callback;
            return { dispose: () => {} };
          },
          asWebviewUri: (resource: vscode.Uri) => resource,
        },
      } as unknown as vscode.WebviewView;

      (provider as unknown as { getHtml: () => string }).getHtml = () =>
        "<!doctype html><html></html>";
      (provider as unknown as { sendTheme: () => void }).sendTheme = () => {};
      provider.resolveWebviewView(mockWebviewView);

      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "openai",
        model: "gpt-5.1",
      });

      const payload = posted[posted.length - 1] as {
        type: string;
        currentProvider: string;
        currentModel: string;
      };
      assert.strictEqual(payload.type, "provider_settings");
      assert.strictEqual(payload.currentProvider, "openai");
      assert.strictEqual(payload.currentModel, "gpt-5.1");
    });
  });
});
