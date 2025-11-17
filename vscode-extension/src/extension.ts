// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { AgentBridgeAdapter } from "./agent/types";
import { TestAgentBridge } from "./agent/test-agent-bridge";
import { DolphinViewProvider } from "./views/provider";
import { FileWatcher } from "./kb/file-watcher";
import { KBStatusBar } from "./kb/status-bar";
import { loadWatcherConfig } from "./kb/config";
import { Logger } from "./utils/logger";
import { DolphinCodeActionProvider } from "./editor/code-actions";
import { DiffHandler, DiffChange } from "./editor/diff-handler";
import { AutoSyncManager } from "./kb/auto-sync-manager";
import { DriftDetector } from "./kb/drift-detector";
import { resolveProviderSettings } from "./config/provider-settings";
import type { ProviderSettingsResult } from "./config/provider-settings";

const FALLBACK_KB_BASE_URL = "http://127.0.0.1:7777";
let isTestEnv = false;
let defaultKbBaseUrl = FALLBACK_KB_BASE_URL;
const KB_API_KEY_SECRET_ID = "dolphin.kbApiKey";
const CLAUDE_SECRET_ID = "dolphin.anthropicApiKey";
const OPENAI_SECRET_ID = "dolphin.openaiApiKey";
const LEGACY_CLAUDE_SECRET_ID = "dolphin.apiKey";
let defaultKbApiKey: string | undefined;

function resolveKbBaseUrl(): string {
  try {
    return vscode.workspace
      .getConfiguration("dolphin.kb")
      .get<string>("apiBaseUrl", FALLBACK_KB_BASE_URL);
  } catch (error) {
    console.warn("[Extension] Failed to resolve KB base URL, using fallback", error);
    return FALLBACK_KB_BASE_URL;
  }
}

function getKbApiKey(): string | undefined {
  return (
    defaultKbApiKey || process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY || undefined
  );
}

function setKbApiKeyValue(value: string | undefined, source: "env" | "secret" | "command") {
  defaultKbApiKey = value;

  if (value) {
    process.env.DOLPHIN_API_KEY = value;
    process.env.DOLPHIN_KB_API_KEY = value;
    try {
      logger?.info?.(
        `[Extension] KB API key loaded from ${
          source === "env" ? "environment" : source === "secret" ? "secret storage" : "command"
        }`
      );
    } catch {
      // Logger may not be ready during activation bootstrap
    }
  }
}

async function initializeKbApiKey(context: vscode.ExtensionContext): Promise<void> {
  const envKey = process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY;
  if (envKey) {
    setKbApiKeyValue(envKey, "env");
    return;
  }

  const storedKey = await context.secrets.get(KB_API_KEY_SECRET_ID);
  if (storedKey) {
    setKbApiKeyValue(storedKey, "secret");
  } else {
    try {
      logger?.warn?.(
        "[Extension] KB API key not configured; secured KB endpoints will reject requests."
      );
    } catch {
      // Logger may not be ready yet
    }
  }
}

async function migrateLegacyAnthropicSecret(context: vscode.ExtensionContext): Promise<void> {
  const legacyValue = await context.secrets.get(LEGACY_CLAUDE_SECRET_ID);
  const modernValue = await context.secrets.get(CLAUDE_SECRET_ID);

  if (legacyValue && !modernValue) {
    await context.secrets.store(CLAUDE_SECRET_ID, legacyValue);
    await context.secrets.delete(LEGACY_CLAUDE_SECRET_ID);
    try {
      logger?.info?.("[Extension] Migrated legacy Anthropic API key secret to new namespace");
    } catch {
      // Logger may not be initialized yet
    }
  }
}

function buildProviderEnvDefaults(selection: ProviderSettingsResult): Record<string, string> {
  return {
    DOLPHIN_LLM_PROVIDER: selection.provider,
    DOLPHIN_LLM_MODEL: selection.model,
    DOLPHIN_PROVIDER: selection.provider,
    DOLPHIN_MODEL: selection.model,
  };
}

function surfaceProviderWarnings(warnings: string[]): void {
  if (!warnings.length) {
    return;
  }
  for (const warning of warnings) {
    logger?.warn?.(`[Extension] ${warning}`);
    void vscode.window.showWarningMessage(warning);
  }
}

async function promptForProviderSecret(
  context: vscode.ExtensionContext,
  options: {
    secretId: string;
    prompt: string;
    placeholder: string;
    successMessage: string;
    successLog?: string;
  }
): Promise<void> {
  const apiKey = await vscode.window.showInputBox({
    prompt: options.prompt,
    password: true,
    placeHolder: options.placeholder,
    ignoreFocusOut: true,
  });

  if (!apiKey) {
    await vscode.window.showErrorMessage("API key cannot be empty");
    return;
  }

  await context.secrets.store(options.secretId, apiKey.trim());
  outputChannel?.appendLine(
    `[Dolphin] ${options.successLog ?? options.successMessage}`
  );
  await vscode.window.showInformationMessage(options.successMessage);
}

function propagateKbApiKeyToConsumers(apiKey?: string): void {
  const key = apiKey ?? getKbApiKey();
  viewProvider?.updateKbApiKey(key);
  fileWatcher?.setApiKey?.(key);
  autoSyncManager?.updateApiKey?.(key);
  driftDetector?.updateApiKey?.(key);
}

let agentBridge: AgentBridgeAdapter | null = null;
let outputChannel: vscode.OutputChannel;
let fileWatcher: FileWatcher | null = null;
let statusBar: KBStatusBar | null = null;
let viewProvider: DolphinViewProvider | null = null;
let logger: Logger;
let autoSyncManager: AutoSyncManager | null = null;
let driftDetector: DriftDetector | null = null;

/**
 * Get the active agent bridge instance (for testing)
 */
export function getAgentBridge(): AgentBridgeAdapter | null {
  return agentBridge;
}

export async function activate(context: vscode.ExtensionContext) {
  // Create output channel for logging (shared by extension and agent bridge)
  outputChannel = vscode.window.createOutputChannel("Dolphin");
  outputChannel.show();
  context.subscriptions.push(outputChannel);

  // Create logger
  logger = new Logger(outputChannel, "Extension");
  logger.info("Activating Dolphin extension...");

  isTestEnv = context.extensionMode === vscode.ExtensionMode.Test;
  defaultKbBaseUrl = resolveKbBaseUrl();

  if (isTestEnv) {
    logger.info("Test environment detected: background KB services will be skipped.");
  }

  logger.debug(`Using KB base URL: ${defaultKbBaseUrl}`);

  await initializeKbApiKey(context);
  await migrateLegacyAnthropicSecret(context);

  try {
    // Initialize AgentBridge with shared output channel
    logger.info(
      isTestEnv ? "Initializing AgentBridge stub for tests..." : "Initializing AgentBridge..."
    );
    agentBridge = isTestEnv ? new TestAgentBridge(outputChannel) : new AgentBridge(outputChannel);

    const agentCorePath = context.asAbsolutePath(path.join("..", "agent-core", "src", "main.ts"));
    const extensionPath = context.extensionPath;

    logger.debug(`Agent Core path: ${agentCorePath}`);
    logger.debug(`Extension path: ${extensionPath}`);

    const llmConfig = vscode.workspace.getConfiguration("dolphin.llm");
    const providerSelection = resolveProviderSettings({
      provider: llmConfig.get<string>("provider"),
      anthropicModel: llmConfig.get<string>("model.anthropic"),
      openaiModel: llmConfig.get<string>("model.openai"),
    });
    surfaceProviderWarnings(providerSelection.warnings);

    const anthropicApiKey = await context.secrets.get(CLAUDE_SECRET_ID);
    const openaiApiKey = await context.secrets.get(OPENAI_SECRET_ID);

    if (anthropicApiKey) {
      logger.info("Anthropic API key found in SecretStorage");
    }
    if (openaiApiKey) {
      logger.info("OpenAI API key found in SecretStorage");
    }
    if (!anthropicApiKey && !openaiApiKey) {
      logger.info("No provider API keys found - relying on CLI or env vars");
    }

    try {
      await agentBridge.start(agentCorePath, extensionPath, {
        anthropicApiKey,
        openaiApiKey,
        kbApiKey: getKbApiKey(),
        env: { defaults: buildProviderEnvDefaults(providerSelection) },
      });
      logger.info("AgentBridge started successfully");
    } catch (startError: unknown) {
      const message = startError instanceof Error ? startError.message : String(startError);
      const stack = startError instanceof Error ? startError.stack : undefined;
      logger.error(`AgentBridge.start() failed: ${message}`);
      if (stack) {
        logger.debug(`Stack: ${stack}`);
      }
      throw startError;
    }

    // Set context for keybindings
    await vscode.commands.executeCommand("setContext", "dolphin.agentReady", true);

    // Initialize KB status bar
    if (!isTestEnv) {
      statusBar = new KBStatusBar();
      context.subscriptions.push(statusBar);
    } else {
      logger.debug("[TestMode] Skipping KB status bar initialization.");
    }

    // Listen for agent events
    const bridgeEventDisposable = agentBridge.onEvent((event) => {
      outputChannel.appendLine(`[Extension] Agent event: ${event.type}`);
    });
    context.subscriptions.push(bridgeEventDisposable);

    // Crash recovery (Phase 5)
    if (!isTestEnv) {
      await recoverFromCrash(context);
    } else {
      logger.debug("[TestMode] Skipping crash recovery checks.");
    }

    // Initialize file watcher
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder && agentBridge && !isTestEnv) {
      // Load config with fallback for test environments where config system may not be ready
      let config;
      try {
        config = loadWatcherConfig();
        // Add API integration for file sync (Phase 2)
        config.apiBaseUrl = defaultKbBaseUrl;
        config.repoName = path.basename(workspaceFolder.uri.fsPath);
        config.apiKey = getKbApiKey();
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        logger.warn(`Failed to load watcher config, using defaults: ${message}`);
        // Fallback to safe defaults if config system isn't ready (e.g., in tests)
        config = {
          debounceMs: 2000,
          batchIntervalMs: 5000,
          excludePatterns: [
            "**/node_modules/**",
            "**/dist/**",
            "**/build/**",
            "**/.git/**",
            "**/out/**",
            "**/*.min.js",
          ],
          apiBaseUrl: defaultKbBaseUrl,
          repoName: path.basename(workspaceFolder.uri.fsPath),
          apiKey: getKbApiKey(),
        };
      }
      fileWatcher = new FileWatcher(config, async (changes) => {
        outputChannel.appendLine(`[Extension] Received ${changes.length} file changes`);

        // Extract file paths relative to workspace
        const files = changes.map((c) => vscode.workspace.asRelativePath(c.uri));

        // Send to agent core via bridge
        try {
          await queueFilesForIndexing(files, 5);
          outputChannel.appendLine(`[Extension] Queued ${files.length} files for indexing`);
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          outputChannel.appendLine(`[Extension] Failed to queue files: ${message}`);
        }
      });

      await fileWatcher.startWatching(workspaceFolder);
      fileWatcher.setApiKey(getKbApiKey());
      context.subscriptions.push({
        dispose: () => fileWatcher?.dispose(),
      });

      outputChannel.appendLine("[Extension] File watcher initialized");

      // Initialize Auto-Sync Manager (Phase 4)
      const autoSyncConfig = {
        enabled: vscode.workspace
          .getConfiguration("dolphin.kb.autoSync")
          .get<boolean>("enabled", true),
        mode: vscode.workspace
          .getConfiguration("dolphin.kb.autoSync")
          .get<"off" | "manual" | "smart" | "aggressive">("mode", "smart"),
        idleTimeMs: vscode.workspace
          .getConfiguration("dolphin.kb.autoSync")
          .get<number>("idleTimeMs", 30000),
        maxBatchSize: vscode.workspace
          .getConfiguration("dolphin.kb.autoSync")
          .get<number>("maxBatchSize", 100),
        checkIntervalMs: vscode.workspace
          .getConfiguration("dolphin.kb.autoSync")
          .get<number>("checkIntervalMs", 30000),
      };

      autoSyncManager = new AutoSyncManager(
        autoSyncConfig,
        path.basename(workspaceFolder.uri.fsPath),
        defaultKbBaseUrl,
        outputChannel,
        vscode.workspace,
        getKbApiKey()
      );
      autoSyncManager.updateApiKey(getKbApiKey());
      await autoSyncManager.start();
      context.subscriptions.push({
        dispose: () => autoSyncManager?.dispose(),
      });

      outputChannel.appendLine("[Extension] Auto-sync manager initialized");

      // Initialize Drift Detector (Phase 5)
      driftDetector = new DriftDetector(
        path.basename(workspaceFolder.uri.fsPath),
        defaultKbBaseUrl,
        outputChannel,
        undefined,
        getKbApiKey()
      );
      driftDetector.updateApiKey(getKbApiKey());
      await driftDetector.start();
      context.subscriptions.push({
        dispose: () => driftDetector?.dispose(),
      });

      outputChannel.appendLine("[Extension] Drift detector initialized");
    } else if (isTestEnv) {
      logger.debug(
        "[TestMode] Skipping file watcher, auto-sync, and drift detector initialization."
      );
    }

    // Register webview provider with AgentBridge
    logger.info("Creating DolphinViewProvider with AgentBridge...");
    viewProvider = new DolphinViewProvider(
      context.extensionUri,
      outputChannel,
      agentBridge,
      getKbApiKey()
    );
    logger.debug("Registering webview view provider for 'dolphin.chatView'...");
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider("dolphin.chatView", viewProvider, {
        webviewOptions: {
          retainContextWhenHidden: true,
        },
      })
    );
    context.subscriptions.push({
      dispose: () => viewProvider?.dispose(),
    });
    logger.info("Webview provider registered successfully");

    // Register commands
    logger.info("Registering commands...");

    // Command: dolphin.focusInput - Focus the chat input in the webview
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.focusInput", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.focusInput");
        await vscode.commands.executeCommand("dolphin.chatView.focus");
        if (viewProvider) {
          viewProvider.focusInput();
        }
      })
    );

    // Command: dolphin.newConversation - Start a new conversation
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.newConversation", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.newConversation");
        if (agentBridge) {
          await agentBridge.clearConversation();
        }
        if (viewProvider) {
          viewProvider.clearConversation();
        }
        vscode.window.showInformationMessage("New conversation started");
      })
    );

    // Command: dolphin.setApiKey - legacy alias for Claude API key
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.setApiKey", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.setApiKey");
        await promptForProviderSecret(context, {
          secretId: CLAUDE_SECRET_ID,
          prompt: "Enter your Anthropic API Key",
          placeholder: "sk-ant-...",
          successMessage: "Anthropic API key stored securely",
          successLog: "API key stored in SecretStorage",
        });
      })
    );

    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.setClaudeApiKey", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.setClaudeApiKey");
        await promptForProviderSecret(context, {
          secretId: CLAUDE_SECRET_ID,
          prompt: "Enter your Anthropic (Claude) API Key",
          placeholder: "sk-ant-...",
          successMessage: "Claude API key stored securely",
          successLog: "Claude API key stored in SecretStorage",
        });
      })
    );

    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.setOpenAIApiKey", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.setOpenAIApiKey");
        await promptForProviderSecret(context, {
          secretId: OPENAI_SECRET_ID,
          prompt: "Enter your OpenAI API Key",
          placeholder: "sk-openai-...",
          successMessage: "OpenAI API key stored securely",
          successLog: "OpenAI API key stored in SecretStorage",
        });
      })
    );

    // Command: dolphin.kb.setApiKey - Set the KB API key for REST endpoints
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.kb.setApiKey", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.kb.setApiKey");
        const kbKey = await vscode.window.showInputBox({
          prompt: "Enter your Dolphin KB API Key",
          password: true,
          placeHolder: "kb-local-secret",
          ignoreFocusOut: true,
        });

        if (!kbKey) {
          outputChannel.appendLine("[Dolphin] KB API key input cancelled");
          return;
        }

        await context.secrets.store(KB_API_KEY_SECRET_ID, kbKey);
        setKbApiKeyValue(kbKey, "command");
        propagateKbApiKeyToConsumers(kbKey);
        outputChannel.appendLine("[Dolphin] KB API key stored securely");

        const choice = await vscode.window.showInformationMessage(
          "KB API key stored securely. Restart the Dolphin KB to apply it to the agent?",
          "Restart Now",
          "Later"
        );

        if (choice === "Restart Now") {
          await vscode.commands.executeCommand("dolphin.kb.restart");
        } else {
          vscode.window.showInformationMessage(
            "Run 'Dolphin: Restart Knowledge Base' later so the agent picks up the new key."
          );
        }
      })
    );

    // Command: dolphin.test - Test command for development/debugging
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.test", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.test");
        const info = {
          agentBridgeActive: !!agentBridge,
          commands: await vscode.commands
            .getCommands(true)
            .then((cmds) => cmds.filter((c) => c.startsWith("dolphin."))),
        };
        outputChannel.appendLine(`[Dolphin] Test info: ${JSON.stringify(info, null, 2)}`);
        vscode.window.showInformationMessage(
          `Dolphin test: ${info.commands.length} commands registered`
        );
      })
    );

    // Register KB management commands
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.kb.showStatus", async () => {
        if (!agentBridge) {
          vscode.window.showErrorMessage("Agent not ready");
          return;
        }

        try {
          const status = await getKBStatus();
          vscode.window.showInformationMessage(
            `KB Status:\n` +
              `Repository: ${status.repoName || "Unknown"}\n` +
              `Queue Depth: ${status.queueDepth}\n` +
              `Indexing: ${status.isIndexing ? "Yes" : "No"}`
          );
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          vscode.window.showErrorMessage(`Failed to get KB status: ${message}`);
        }
      }),

      vscode.commands.registerCommand("dolphin.kb.restart", async () => {
        if (!agentBridge) {
          vscode.window.showErrorMessage("Agent not initialized");
          return;
        }

        try {
          outputChannel.appendLine("[KB Restart] Shutting down agent and KB...");

          // Shutdown existing agent (this also shuts down KB)
          agentBridge.shutdown();

          // Wait a moment for cleanup
          await new Promise((resolve) => setTimeout(resolve, 1000));

          // Restart agent (which will restart KB)
          outputChannel.appendLine("[KB Restart] Restarting agent and KB...");
          agentBridge = isTestEnv
            ? new TestAgentBridge(outputChannel)
            : new AgentBridge(outputChannel);

          const agentCorePath = context.asAbsolutePath(
            path.join("..", "agent-core", "src", "main.ts")
          );
          const extensionPath = context.extensionPath;
          const refreshConfig = vscode.workspace.getConfiguration("dolphin.llm");
          const llmSelection = resolveProviderSettings({
            provider: refreshConfig.get<string>("provider"),
            anthropicModel: refreshConfig.get<string>("model.anthropic"),
            openaiModel: refreshConfig.get<string>("model.openai"),
          });
          surfaceProviderWarnings(llmSelection.warnings);

          const anthropicApiKey = await context.secrets.get(CLAUDE_SECRET_ID);
          const openaiApiKey = await context.secrets.get(OPENAI_SECRET_ID);

          await agentBridge.start(agentCorePath, extensionPath, {
            anthropicApiKey,
            openaiApiKey,
            kbApiKey: getKbApiKey(),
            env: { defaults: buildProviderEnvDefaults(llmSelection) },
          });

          // Update view provider with new bridge
          if (viewProvider) {
            // Create new view provider with updated bridge
            viewProvider = new DolphinViewProvider(
              context.extensionUri,
              outputChannel,
              agentBridge,
              getKbApiKey()
            );
          }

          propagateKbApiKeyToConsumers();

          outputChannel.appendLine("[KB Restart] Agent and KB restarted successfully");
          vscode.window.showInformationMessage("KB restarted successfully");
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          outputChannel.appendLine(`[KB Restart] Failed: ${message}`);
          vscode.window.showErrorMessage(`Failed to restart KB: ${message}`);
        }
      })
    );

    // Register contextual editor commands
    context.subscriptions.push(
      // Ask about selection - opens chat with selected code as context
      vscode.commands.registerCommand("dolphin.askAboutSelection", async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
          return;
        }

        const selection = editor.document.getText(editor.selection);
        const fileName = path.basename(editor.document.fileName);
        const language = editor.document.languageId;

        // Open the chat view first
        await vscode.commands.executeCommand("dolphin.chatView.focus");

        // Prefill the input with context
        if (viewProvider) {
          const prompt = `Can you explain this code from ${fileName}?\n\n\`\`\`${language}\n${selection}\n\`\`\``;
          viewProvider.prefillInput(prompt);
        }
      }),

      // Refactor selection - opens chat with refactoring request
      vscode.commands.registerCommand("dolphin.refactorSelection", async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
          return;
        }

        const selection = editor.document.getText(editor.selection);
        const fileName = path.basename(editor.document.fileName);
        const language = editor.document.languageId;

        // Open the chat view first
        await vscode.commands.executeCommand("dolphin.chatView.focus");

        // Prefill the input with refactoring request
        if (viewProvider) {
          const prompt = `Please refactor this code from ${fileName}:\n\n\`\`\`${language}\n${selection}\n\`\`\``;
          viewProvider.prefillInput(prompt);
        }
      }),

      // Ask about file - opens chat with file path as context
      vscode.commands.registerCommand("dolphin.askAboutFile", async (uri: vscode.Uri) => {
        const filePath = vscode.workspace.asRelativePath(uri);

        // Open the chat view first
        await vscode.commands.executeCommand("dolphin.chatView.focus");

        // Prefill the input with file context
        if (viewProvider) {
          const prompt = `Can you help me understand the file: ${filePath}`;
          viewProvider.prefillInput(prompt);
        }
      }),

      // Ask about folder - opens chat with folder path as context
      vscode.commands.registerCommand("dolphin.askAboutFolder", async (uri: vscode.Uri) => {
        const folderPath = vscode.workspace.asRelativePath(uri);

        // Open the chat view first
        await vscode.commands.executeCommand("dolphin.chatView.focus");

        // Prefill the input with folder context
        if (viewProvider) {
          const prompt = `Can you help me understand the folder: ${folderPath}`;
          viewProvider.prefillInput(prompt);
        }
      })
    );

    // Register code action commands
    context.subscriptions.push(
      // Explain code
      vscode.commands.registerCommand(
        "dolphin.explainCode",
        async (selection: string, fileName: string, language: string) => {
          await vscode.commands.executeCommand("dolphin.chatView.focus");
          if (viewProvider) {
            const prompt = `Can you explain this code from ${fileName}?\n\n\`\`\`${language}\n${selection}\n\`\`\``;
            viewProvider.prefillInput(prompt);
          }
        }
      ),

      // Refactor code
      vscode.commands.registerCommand(
        "dolphin.refactorCode",
        async (selection: string, fileName: string, language: string) => {
          await vscode.commands.executeCommand("dolphin.chatView.focus");
          if (viewProvider) {
            const prompt = `Please refactor this code from ${fileName}:\n\n\`\`\`${language}\n${selection}\n\`\`\``;
            viewProvider.prefillInput(prompt);
          }
        }
      ),

      // Add tests
      vscode.commands.registerCommand(
        "dolphin.addTests",
        async (selection: string, fileName: string, language: string) => {
          await vscode.commands.executeCommand("dolphin.chatView.focus");
          if (viewProvider) {
            const prompt = `Please write tests for this code from ${fileName}:\n\n\`\`\`${language}\n${selection}\n\`\`\``;
            viewProvider.prefillInput(prompt);
          }
        }
      ),

      // Document code
      vscode.commands.registerCommand(
        "dolphin.documentCode",
        async (selection: string, fileName: string, language: string) => {
          await vscode.commands.executeCommand("dolphin.chatView.focus");
          if (viewProvider) {
            const prompt = `Please add documentation to this code from ${fileName}:\n\n\`\`\`${language}\n${selection}\n\`\`\``;
            viewProvider.prefillInput(prompt);
          }
        }
      ),

      // Apply diff
      vscode.commands.registerCommand("dolphin.applyDiff", async (diff: DiffChange) => {
        outputChannel.appendLine(`[Dolphin] Applying diff for ${diff.filePath}`);
        try {
          const success = await DiffHandler.applyDiff(diff);
          if (success) {
            outputChannel.appendLine(`[Dolphin] Successfully applied diff to ${diff.filePath}`);
          } else {
            outputChannel.appendLine(
              `[Dolphin] User cancelled or failed to apply diff to ${diff.filePath}`
            );
          }
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          outputChannel.appendLine(`[Dolphin] Error applying diff: ${message}`);
          vscode.window.showErrorMessage(`Failed to apply diff: ${message}`);
        }
      })
    );

    // Register CodeActionProvider for all languages
    const codeActionProvider = new DolphinCodeActionProvider(viewProvider);
    context.subscriptions.push(
      vscode.languages.registerCodeActionsProvider({ scheme: "file" }, codeActionProvider, {
        providedCodeActionKinds: [
          vscode.CodeActionKind.QuickFix,
          vscode.CodeActionKind.RefactorRewrite,
        ],
      })
    );

    outputChannel.appendLine("[Dolphin] Commands registered successfully");
    logger.info("Commands registered successfully");

    if (!isTestEnv) {
      vscode.window.showInformationMessage("Dolphin activated! 🐬");
    } else {
      logger.debug("[TestMode] Activation complete (UI notifications suppressed).");
    }
    logger.info("Activation complete");

    propagateKbApiKeyToConsumers();

    // Return extension API for testing and integration
    return {
      getAgentBridge: () => agentBridge,
      getViewProvider: () => viewProvider,
      getFileWatcher: () => fileWatcher,
      getStatusBar: () => statusBar,
      getAutoSyncManager: () => autoSyncManager,
      getDriftDetector: () => driftDetector,
    };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    const stack = error instanceof Error ? error.stack : undefined;
    const errorMsg = `Dolphin activation failed: ${message}`;
    logger.error(errorMsg);
    if (stack) {
      logger.debug(`Stack: ${stack}`);
    }
    vscode.window.showErrorMessage(errorMsg);
    throw error;
  }
}

// Helper function to queue files for indexing via agent bridge
async function queueFilesForIndexing(files: string[], priority = 5): Promise<void> {
  if (!agentBridge) {
    throw new Error("Agent bridge not initialized");
  }

  if (!(agentBridge instanceof AgentBridge)) {
    if (isTestEnv) {
      outputChannel.appendLine("[Extension] Test mode active - skipping queueFilesForIndexing");
      return;
    }
    throw new Error("Agent bridge process not available");
  }

  // Call agent core's queue_files method
  const id = Date.now();
  const message = {
    jsonrpc: "2.0" as const,
    id,
    method: "queue_files",
    params: { files, priority },
  };

  // Write to agent bridge stdin
  // Access private process via type assertion (internal bridge communication)
  const bridge = agentBridge as unknown as {
    process?: { stdin?: { write: (data: string) => void } };
  };
  if (bridge.process?.stdin) {
    bridge.process.stdin.write(JSON.stringify(message) + "\n");
  } else {
    throw new Error("Agent bridge process not available");
  }
}

// Helper function to get KB status via agent bridge
async function getKBStatus(): Promise<Record<string, unknown>> {
  if (!agentBridge) {
    throw new Error("Agent bridge not initialized");
  }

  if (isTestEnv || !(agentBridge instanceof AgentBridge)) {
    return {
      repoName: "test-repo",
      queueDepth: 0,
      isIndexing: false,
    };
  }

  const id = Date.now();
  const message = {
    jsonrpc: "2.0" as const,
    id,
    method: "get_kb_status",
    params: {},
  };

  return new Promise((resolve, reject) => {
    // Access private process and pendingRequests via type assertion
    const bridge = agentBridge as unknown as {
      process?: { stdin?: { write: (data: string) => void } };
      pendingRequests?: Map<
        number,
        { resolve: (value: unknown) => void; reject: (error: unknown) => void }
      >;
    };

    // Set up response handler
    const timeout = setTimeout(() => {
      reject(new Error("KB status request timeout"));
    }, 5000);

    // Create temporary listener for response
    const _handleResponse = (event: unknown) => {
      const evt = event as Record<string, unknown>;
      if (evt.type === "kb_status_response") {
        clearTimeout(timeout);
        resolve(evt.data as Record<string, unknown>);
      }
    };

    // Try to use agent bridge's pending requests if available
    if (bridge.pendingRequests) {
      bridge.pendingRequests.set(id, {
        resolve: (value: unknown) => {
          resolve(value as Record<string, unknown>);
        },
        reject: (error: unknown) => {
          clearTimeout(timeout);
          reject(error);
        },
      });
    }

    // Send request
    if (bridge.process?.stdin) {
      bridge.process.stdin.write(JSON.stringify(message) + "\n");
    } else {
      clearTimeout(timeout);
      reject(new Error("Agent bridge process not available"));
    }
  });
}

// Crash recovery function (Phase 5)
async function recoverFromCrash(_context: vscode.ExtensionContext): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    return;
  }

  try {
    outputChannel.appendLine("[CrashRecovery] Checking for incomplete indexing tasks...");

    const repoName = path.basename(workspaceFolder.uri.fsPath);
    const apiBaseUrl = defaultKbBaseUrl;

    // Check for pending changes that accumulated during offline period
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const kbApiKey = getKbApiKey();
    if (kbApiKey) {
      headers["X-API-Key"] = kbApiKey;
    }

    const response = await fetch(`${apiBaseUrl}/v1/repos/${repoName}/pending-changes?limit=10`, {
      method: "GET",
      headers,
    });

    if (!response.ok) {
      outputChannel.appendLine(
        "[CrashRecovery] Failed to check for pending changes (KB may not be running)"
      );
      return;
    }

    const data = (await response.json()) as { total?: number; changes?: unknown[] };
    const pendingCount = data.total || 0;

    if (pendingCount > 0) {
      outputChannel.appendLine(
        `[CrashRecovery] Found ${pendingCount} pending changes from previous session`
      );

      const choice = await vscode.window.showInformationMessage(
        `Found ${pendingCount} file change(s) from previous session. Sync now?`,
        "Sync",
        "Later"
      );

      if (choice === "Sync") {
        outputChannel.appendLine(
          "[CrashRecovery] User requested sync - will be handled by auto-sync manager"
        );
      }
    } else {
      outputChannel.appendLine("[CrashRecovery] No pending changes found");
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    outputChannel.appendLine(`[CrashRecovery] Error during crash recovery: ${message}`);
  }
}

export function deactivate() {
  fileWatcher?.dispose();
  statusBar?.dispose();
  autoSyncManager?.dispose();
  driftDetector?.dispose();
  viewProvider?.dispose();
  agentBridge?.shutdown();
  agentBridge = null;
  fileWatcher = null;
  statusBar = null;
  autoSyncManager = null;
  driftDetector = null;
  viewProvider = null;
  outputChannel?.dispose();
}
