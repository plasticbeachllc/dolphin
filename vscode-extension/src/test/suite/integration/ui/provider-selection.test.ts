import * as assert from "assert";
import * as vscode from "vscode";
import { DolphinViewProvider } from "../../../../views/provider";
import { AgentBridge } from "../../../../agent/bridge";
import { createMockOutputChannel } from "../../../helpers/mock-output-channel";

describe("Provider Selection E2E Tests", () => {
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
    if (provider) {
      provider.dispose();
    }
    if (mockAgentBridge) {
      const process = (mockAgentBridge as unknown as Record<string, unknown>).process as
        | Record<string, unknown>
        | undefined;
      if (process && !process.kill) {
        process.kill = () => true;
      }
      await mockAgentBridge.shutdown();
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
    if (outputChannel) {
      outputChannel.dispose();
    }
  });

  describe("Provider Settings Workflow", () => {
    it("Should retrieve available providers and current selection", async () => {
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
        currentModel: string;
        availableProviders: Array<{
          id: string;
          label: string;
          description: string;
          models: Array<{ id: string; label: string; description: string }>;
        }>;
      };

      // Verify message structure
      assert.strictEqual(payload.type, "provider_settings", "Should send provider_settings message");
      assert.ok(payload.currentProvider, "Should include current provider");
      assert.ok(payload.currentModel, "Should include current model");
      assert.ok(Array.isArray(payload.availableProviders), "Should include available providers");
      assert.ok(payload.availableProviders.length > 0, "Should have at least one provider");

      // Verify provider structure
      const firstProvider = payload.availableProviders[0];
      assert.ok(firstProvider.id, "Provider should have ID");
      assert.ok(firstProvider.label, "Provider should have label");
      assert.ok(firstProvider.description, "Provider should have description");
      assert.ok(Array.isArray(firstProvider.models), "Provider should have models array");
      assert.ok(firstProvider.models.length > 0, "Provider should have at least one model");

      // Verify model structure
      const firstModel = firstProvider.models[0];
      assert.ok(firstModel.id, "Model should have ID");
      assert.ok(firstModel.label, "Model should have label");
      assert.ok(firstModel.description, "Model should have description");
    });

    it("Should update provider and model selection", async () => {
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

      // Save provider settings
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "openai",
        model: "gpt-5.1",
      });

      // Should receive confirmation message
      const confirmPayload = posted[posted.length - 1] as {
        type: string;
        currentProvider: string;
        currentModel: string;
      };

      assert.strictEqual(confirmPayload.type, "provider_settings", "Should send confirmation");
      assert.strictEqual(confirmPayload.currentProvider, "openai", "Should update to openai");
      assert.strictEqual(confirmPayload.currentModel, "gpt-5.1", "Should update to gpt-5.1");

      // Verify config was actually updated
      const config = vscode.workspace.getConfiguration("dolphin.llm");
      const savedProvider = config.get("provider");
      const savedModel = config.get("model.openai");

      assert.strictEqual(savedProvider, "openai", "Config should be updated for provider");
      assert.strictEqual(savedModel, "gpt-5.1", "Config should be updated for model");
    });

    it("Should switch between providers with model auto-selection", async () => {
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

      // Switch to Anthropic
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "anthropic",
        model: "claude-sonnet-4-5-20250929",
      });

      let payload = posted[posted.length - 1] as {
        type: string;
        currentProvider: string;
        currentModel: string;
      };

      assert.strictEqual(payload.currentProvider, "anthropic");
      assert.strictEqual(payload.currentModel, "claude-sonnet-4-5-20250929");

      // Switch to OpenAI
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "openai",
        model: "gpt-5.1-codex",
      });

      payload = posted[posted.length - 1] as {
        type: string;
        currentProvider: string;
        currentModel: string;
      };

      assert.strictEqual(payload.currentProvider, "openai");
      assert.strictEqual(payload.currentModel, "gpt-5.1-codex");
    });

    it("Should handle provider-specific model updates", async () => {
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

      // Set Anthropic model
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "anthropic",
        model: "claude-haiku-4-5",
      });

      const config = vscode.workspace.getConfiguration("dolphin.llm");
      const anthropicModel = config.get("model.anthropic");
      assert.strictEqual(anthropicModel, "claude-haiku-4-5", "Should set Anthropic model");

      // Set OpenAI model
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "openai",
        model: "gpt-5.1-codex-mini",
      });

      // Wait for settings to be fully saved
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Re-fetch config to ensure it's persisted
      const freshConfig = vscode.workspace.getConfiguration("dolphin.llm");
      const openaiModel = freshConfig.get("model.openai");
      assert.strictEqual(openaiModel, "gpt-5.1-codex-mini", "Should set OpenAI model");

      // Verify both settings persist
      assert.strictEqual(
        freshConfig.get("model.anthropic"),
        "claude-haiku-4-5",
        "Anthropic model should persist"
      );
      assert.strictEqual(
        freshConfig.get("model.openai"),
        "gpt-5.1-codex-mini",
        "OpenAI model should persist"
      );
    });
  });

  describe("Integration with Auth Status", () => {
    it("Should work with get_auth_status to provide complete provider info", async () => {
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

      // Mock auth status response
      (mockAgentBridge as unknown as { getAuthStatus: () => Promise<unknown> }).getAuthStatus =
        async () => ({
          providers: [
            { provider: "anthropic", authenticated: true, mode: "api_key" },
            { provider: "openai", authenticated: false, mode: "none" },
          ],
        });

      provider.resolveWebviewView(mockWebviewView);

      // Get provider settings
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "get_provider_settings",
      });

      const settingsPayload = posted[posted.length - 1] as {
        type: string;
        availableProviders: unknown[];
      };
      assert.strictEqual(settingsPayload.type, "provider_settings");
      assert.ok(settingsPayload.availableProviders.length >= 2);

      // Get auth status
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "get_auth_status",
      });

      const authPayload = posted[posted.length - 1] as {
        type: string;
        status: {
          providers: Array<{ provider: string; authenticated: boolean; mode: string }>;
        };
      };

      assert.strictEqual(authPayload.type, "auth_status");
      assert.ok(authPayload.status.providers);
      assert.strictEqual(authPayload.status.providers.length, 2);

      const anthropicAuth = authPayload.status.providers.find((p) => p.provider === "anthropic");
      const openaiAuth = authPayload.status.providers.find((p) => p.provider === "openai");

      assert.ok(anthropicAuth?.authenticated, "Anthropic should be authenticated");
      assert.ok(!openaiAuth?.authenticated, "OpenAI should not be authenticated");
    });
  });

  describe("Error Handling", () => {
    it("Should handle invalid provider gracefully", async () => {
      const posted: unknown[] = [];
      let messageHandler: ((message: unknown) => Thenable<void> | void) | undefined;
      const errors: string[] = [];

      const originalAppendLine = outputChannel.appendLine;
      outputChannel.appendLine = (message: string) => {
        if (message.includes("Error")) {
          errors.push(message);
        }
        return originalAppendLine.call(outputChannel, message);
      };

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

      // Try to set invalid provider - this should still work because backend
      // will save whatever is sent, but it won't match known providers
      await (messageHandler as (message: unknown) => Promise<void>)({
        type: "save_provider_settings",
        provider: "invalid_provider",
        model: "invalid_model",
      });

      // Should still send confirmation (backend doesn't validate provider names)
      const payload = posted[posted.length - 1] as { type: string };
      assert.strictEqual(payload.type, "provider_settings");

      outputChannel.appendLine = originalAppendLine;
    });

    it("Should handle concurrent provider switches", async () => {
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

      // Send multiple provider changes rapidly
      const promises = [
        (messageHandler as (message: unknown) => Promise<void>)({
          type: "save_provider_settings",
          provider: "anthropic",
          model: "claude-sonnet-4-5",
        }),
        (messageHandler as (message: unknown) => Promise<void>)({
          type: "save_provider_settings",
          provider: "openai",
          model: "gpt-5.1",
        }),
        (messageHandler as (message: unknown) => Promise<void>)({
          type: "save_provider_settings",
          provider: "anthropic",
          model: "claude-haiku-4-5",
        }),
      ];

      await Promise.all(promises);

      // Last one should win
      const finalPayload = posted[posted.length - 1] as {
        currentProvider: string;
        currentModel: string;
      };
      assert.strictEqual(finalPayload.currentProvider, "anthropic");
      assert.strictEqual(finalPayload.currentModel, "claude-haiku-4-5");
    });
  });
});
