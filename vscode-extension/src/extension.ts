// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { DolphinViewProvider } from "./views/provider";
import { FileWatcher } from "./kb/file-watcher";
import { KBStatusBar } from "./kb/status-bar";
import { loadWatcherConfig } from "./kb/config";
import { Logger } from "./utils/logger";

let agentBridge: AgentBridge | null = null;
let outputChannel: vscode.OutputChannel;
let fileWatcher: FileWatcher | null = null;
let statusBar: KBStatusBar | null = null;
let viewProvider: DolphinViewProvider | null = null;
let logger: Logger;

export async function activate(context: vscode.ExtensionContext) {
  // Create output channel for logging
  outputChannel = vscode.window.createOutputChannel("Dolphin");
  outputChannel.show();

  // Create logger
  logger = new Logger(outputChannel, "Extension");
  logger.info("Activating Dolphin extension...");

  try {
    // Initialize AgentBridge
    logger.info("Initializing AgentBridge...");
    agentBridge = new AgentBridge();

    const agentCorePath = context.asAbsolutePath(
      path.join("..", "agent-core", "src", "main.ts")
    );
    const extensionPath = context.extensionPath;

    logger.debug(`Agent Core path: ${agentCorePath}`);
    logger.debug(`Extension path: ${extensionPath}`);

    // Retrieve API key from SecretStorage
    const apiKey = await context.secrets.get('dolphin.apiKey');
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
    await vscode.commands.executeCommand(
      "setContext",
      "dolphin.agentReady",
      true
    );

    // Initialize KB status bar
    statusBar = new KBStatusBar();
    context.subscriptions.push(statusBar);

    // Listen for agent events
    agentBridge.onEvent((event) => {
      outputChannel.appendLine(`[Extension] Agent event: ${event.type}`);

      // Note: KB events would be handled here if they were part of the event type definition
      // For now, we just log them
    });

    // Initialize file watcher
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder && agentBridge) {
      // Load config with fallback for test environments where config system may not be ready
      let config;
      try {
        config = loadWatcherConfig();
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
    }

    // Register webview provider with AgentBridge
    logger.info("Creating DolphinViewProvider with AgentBridge...");
    viewProvider = new DolphinViewProvider(context.extensionUri, outputChannel, agentBridge);
    logger.debug("Registering webview view provider for 'dolphin.chatView'...");
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider("dolphin.chatView", viewProvider, {
        webviewOptions: {
          retainContextWhenHidden: true
        }
      })
    );
    logger.info("Webview provider registered successfully");

    // Register commands
    logger.info("Registering commands...");
    
    // Command: dolphin.focusInput - Focus the chat input in the webview
    context.subscriptions.push(
      vscode.commands.registerCommand('dolphin.focusInput', async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.focusInput");
        await vscode.commands.executeCommand('dolphin.chatView.focus');
        if (viewProvider) {
          viewProvider.focusInput();
        }
      })
    );

    // Command: dolphin.newConversation - Start a new conversation
    context.subscriptions.push(
      vscode.commands.registerCommand('dolphin.newConversation', async () => {
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
      vscode.commands.registerCommand('dolphin.setApiKey', async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.setApiKey");
        const apiKey = await vscode.window.showInputBox({
          prompt: "Enter your Anthropic API Key",
          password: true,
          placeHolder: "sk-ant-...",
          ignoreFocusOut: true
        });

        if (apiKey) {
          await context.secrets.store('dolphin.apiKey', apiKey);
          vscode.window.showInformationMessage("API key stored securely");
          outputChannel.appendLine("[Dolphin] API key stored in SecretStorage");
        }
      })
    );

    // Command: dolphin.test - Test command for development/debugging
    context.subscriptions.push(
      vscode.commands.registerCommand('dolphin.test', async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.test");
        const info = {
          agentBridgeActive: !!agentBridge,
          commands: await vscode.commands.getCommands(true).then(cmds => 
            cmds.filter(c => c.startsWith('dolphin.'))
          )
        };
        outputChannel.appendLine(`[Dolphin] Test info: ${JSON.stringify(info, null, 2)}`);
        vscode.window.showInformationMessage(`Dolphin test: ${info.commands.length} commands registered`);
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
        vscode.window.showInformationMessage(
          "KB restart not yet implemented. Please restart VSCode to restart KB."
        );
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

export function deactivate() {
  fileWatcher?.dispose();
  statusBar?.dispose();
  agentBridge?.shutdown();
  agentBridge = null;
  fileWatcher = null;
  statusBar = null;
}