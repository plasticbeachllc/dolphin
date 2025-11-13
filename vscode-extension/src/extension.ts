// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { DolphinViewProvider } from "./views/provider";
import { FileWatcher } from "./kb/file-watcher";
import { KBStatusBar } from "./kb/status-bar";
import { loadWatcherConfig } from "./kb/config";
import { Logger } from "./utils/logger";
import { DolphinCodeActionProvider } from "./editor/code-actions";
import { DiffHandler, DiffChange } from "./editor/diff-handler";
import { AutoSyncManager } from "./kb/auto-sync-manager";
import { DriftDetector } from "./kb/drift-detector";

let agentBridge: AgentBridge | null = null;
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
export function getAgentBridge(): AgentBridge | null {
  return agentBridge;
}

export async function activate(context: vscode.ExtensionContext) {
  // Create output channel for logging (shared by extension and agent bridge)
  outputChannel = vscode.window.createOutputChannel("Dolphin");
  outputChannel.show();

  // Create logger
  logger = new Logger(outputChannel, "Extension");
  logger.info("Activating Dolphin extension...");

  try {
    // Initialize AgentBridge with shared output channel
    logger.info("Initializing AgentBridge...");
    agentBridge = new AgentBridge(outputChannel);

    const agentCorePath = context.asAbsolutePath(path.join("..", "agent-core", "src", "main.ts"));
    const extensionPath = context.extensionPath;

    logger.debug(`Agent Core path: ${agentCorePath}`);
    logger.debug(`Extension path: ${extensionPath}`);

    // Retrieve API key from SecretStorage
    const apiKey = await context.secrets.get("dolphin.apiKey");
    if (apiKey) {
      logger.info("API key found in SecretStorage");
    } else {
      logger.info("No API key found in SecretStorage - will use CLI or env");
    }

    try {
      await agentBridge.start(agentCorePath, extensionPath, apiKey);
      logger.info("AgentBridge started successfully");
    } catch (startError: any) {
      logger.error(`AgentBridge.start() failed: ${startError.message}`);
      logger.debug(`Stack: ${startError.stack}`);
      throw startError;
    }

    // Set context for keybindings
    await vscode.commands.executeCommand("setContext", "dolphin.agentReady", true);

    // Initialize KB status bar
    statusBar = new KBStatusBar();
    context.subscriptions.push(statusBar);

    // Listen for agent events
    agentBridge.onEvent((event) => {
      outputChannel.appendLine(`[Extension] Agent event: ${event.type}`);

      // Note: KB events would be handled here if they were part of the event type definition
      // For now, we just log them
    });

    // Crash recovery (Phase 5)
    await recoverFromCrash(context);

    // Initialize file watcher
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder && agentBridge) {
      // Load config with fallback for test environments where config system may not be ready
      let config;
      try {
        config = loadWatcherConfig();
        // Add API integration for file sync (Phase 2)
        config.apiBaseUrl = "http://127.0.0.1:7777";
        config.repoName = path.basename(workspaceFolder.uri.fsPath);
      } catch (error: any) {
        logger.warn(`Failed to load watcher config, using defaults: ${error.message}`);
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
          apiBaseUrl: "http://localhost:8765",
          repoName: path.basename(workspaceFolder.uri.fsPath),
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
        } catch (error: any) {
          outputChannel.appendLine(`[Extension] Failed to queue files: ${error.message}`);
        }
      });

      await fileWatcher.startWatching(workspaceFolder);
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
        "http://127.0.0.1:7777",
        outputChannel
      );
      await autoSyncManager.start();
      context.subscriptions.push({
        dispose: () => autoSyncManager?.dispose(),
      });

      outputChannel.appendLine("[Extension] Auto-sync manager initialized");

      // Initialize Drift Detector (Phase 5)
      driftDetector = new DriftDetector(
        path.basename(workspaceFolder.uri.fsPath),
        "http://127.0.0.1:7777",
        outputChannel
      );
      await driftDetector.start();
      context.subscriptions.push({
        dispose: () => driftDetector?.dispose(),
      });

      outputChannel.appendLine("[Extension] Drift detector initialized");
    }

    // Register webview provider with AgentBridge
    logger.info("Creating DolphinViewProvider with AgentBridge...");
    viewProvider = new DolphinViewProvider(context.extensionUri, outputChannel, agentBridge);
    logger.debug("Registering webview view provider for 'dolphin.chatView'...");
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider("dolphin.chatView", viewProvider, {
        webviewOptions: {
          retainContextWhenHidden: true,
        },
      })
    );
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

    // Command: dolphin.setApiKey - Set the Anthropic API key
    context.subscriptions.push(
      vscode.commands.registerCommand("dolphin.setApiKey", async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.setApiKey");
        const apiKey = await vscode.window.showInputBox({
          prompt: "Enter your Anthropic API Key",
          password: true,
          placeHolder: "sk-ant-...",
          ignoreFocusOut: true,
        });

        if (apiKey) {
          await context.secrets.store("dolphin.apiKey", apiKey);
          vscode.window.showInformationMessage("API key stored securely");
          outputChannel.appendLine("[Dolphin] API key stored in SecretStorage");
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
        } catch (error: any) {
          vscode.window.showErrorMessage(`Failed to get KB status: ${error.message}`);
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
          agentBridge = new AgentBridge(outputChannel);

          const agentCorePath = context.asAbsolutePath(
            path.join("..", "agent-core", "src", "main.ts")
          );
          const extensionPath = context.extensionPath;
          const apiKey = await context.secrets.get("dolphin.apiKey");

          await agentBridge.start(agentCorePath, extensionPath, apiKey);

          // Update view provider with new bridge
          if (viewProvider) {
            (viewProvider as any).agentBridge = agentBridge;
          }

          outputChannel.appendLine("[KB Restart] Agent and KB restarted successfully");
          vscode.window.showInformationMessage("KB restarted successfully");
        } catch (error: any) {
          outputChannel.appendLine(`[KB Restart] Failed: ${error.message}`);
          vscode.window.showErrorMessage(`Failed to restart KB: ${error.message}`);
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
        } catch (error: any) {
          outputChannel.appendLine(`[Dolphin] Error applying diff: ${error.message}`);
          vscode.window.showErrorMessage(`Failed to apply diff: ${error.message}`);
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

    vscode.window.showInformationMessage("Dolphin activated! 🐬");
    logger.info("Activation complete");
  } catch (error: any) {
    const errorMsg = `Dolphin activation failed: ${error.message}`;
    logger.error(errorMsg);
    logger.debug(`Stack: ${error.stack}`);
    vscode.window.showErrorMessage(errorMsg);
    throw error;
  }
}

// Helper function to queue files for indexing via agent bridge
async function queueFilesForIndexing(files: string[], priority = 5): Promise<void> {
  if (!agentBridge) {
    throw new Error("Agent bridge not initialized");
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
  const bridge = agentBridge as any;
  if (bridge.process && bridge.process.stdin) {
    bridge.process.stdin.write(JSON.stringify(message) + "\n");
  } else {
    throw new Error("Agent bridge process not available");
  }
}

// Helper function to get KB status via agent bridge
async function getKBStatus(): Promise<any> {
  if (!agentBridge) {
    throw new Error("Agent bridge not initialized");
  }

  const id = Date.now();
  const message = {
    jsonrpc: "2.0" as const,
    id,
    method: "get_kb_status",
    params: {},
  };

  return new Promise((resolve, reject) => {
    const bridge = agentBridge as any;

    // Set up response handler
    const timeout = setTimeout(() => {
      reject(new Error("KB status request timeout"));
    }, 5000);

    // Create temporary listener for response
    const handleResponse = (event: any) => {
      if (event.type === "kb_status_response") {
        clearTimeout(timeout);
        resolve(event.data);
      }
    };

    // Try to use agent bridge's pending requests if available
    if (bridge.pendingRequests) {
      bridge.pendingRequests.set(id, {
        resolve,
        reject: (error: any) => {
          clearTimeout(timeout);
          reject(error);
        },
      });
    }

    // Send request
    if (bridge.process && bridge.process.stdin) {
      bridge.process.stdin.write(JSON.stringify(message) + "\n");
    } else {
      clearTimeout(timeout);
      reject(new Error("Agent bridge process not available"));
    }
  });
}

// Crash recovery function (Phase 5)
async function recoverFromCrash(context: vscode.ExtensionContext): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    return;
  }

  try {
    outputChannel.appendLine("[CrashRecovery] Checking for incomplete indexing tasks...");

    const repoName = path.basename(workspaceFolder.uri.fsPath);
    const apiBaseUrl = "http://127.0.0.1:7777";

    // Check for pending changes that accumulated during offline period
    const response = await fetch(`${apiBaseUrl}/v1/repos/${repoName}/pending-changes?limit=10`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      outputChannel.appendLine(
        "[CrashRecovery] Failed to check for pending changes (KB may not be running)"
      );
      return;
    }

    const data = (await response.json()) as { total?: number; changes?: any[] };
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
  } catch (error: any) {
    outputChannel.appendLine(`[CrashRecovery] Error during crash recovery: ${error.message}`);
  }
}

export function deactivate() {
  fileWatcher?.dispose();
  statusBar?.dispose();
  autoSyncManager?.dispose();
  driftDetector?.dispose();
  agentBridge?.shutdown();
  agentBridge = null;
  fileWatcher = null;
  statusBar = null;
  autoSyncManager = null;
  driftDetector = null;
}
