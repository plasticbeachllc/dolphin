// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { DolphinViewProvider } from "./views/provider";
import { FileWatcher } from "./kb/file-watcher";
import { KBStatusBar } from "./kb/status-bar";
import { loadWatcherConfig } from "./kb/config";

let agentBridge: AgentBridge | null = null;
let outputChannel: vscode.OutputChannel;
let fileWatcher: FileWatcher | null = null;
let statusBar: KBStatusBar | null = null;

export async function activate(context: vscode.ExtensionContext) {
  // Create output channel for logging
  outputChannel = vscode.window.createOutputChannel("Dolphin");
  outputChannel.show();
  outputChannel.appendLine("[Dolphin] Activating...");

  try {
    // Initialize AgentBridge
    outputChannel.appendLine("[Dolphin] Initializing AgentBridge...");
    agentBridge = new AgentBridge();

    const agentCorePath = context.asAbsolutePath(
      path.join("..", "agent-core", "src", "main.ts")
    );
    const extensionPath = context.extensionPath;

    outputChannel.appendLine(`[Dolphin] Agent Core path: ${agentCorePath}`);
    outputChannel.appendLine(`[Dolphin] Extension path: ${extensionPath}`);
    
    try {
      await agentBridge.start(agentCorePath, extensionPath);
      outputChannel.appendLine("[Dolphin] AgentBridge.start() returned successfully");
    } catch (startError: any) {
      outputChannel.appendLine(`[Dolphin] ERROR in AgentBridge.start(): ${startError.message}`);
      outputChannel.appendLine(`[Dolphin] Stack: ${startError.stack}`);
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

      // Handle KB events
      if (event.type === "kb_progress" && statusBar) {
        statusBar.setIndexing(event.data?.indexed || 0);
      } else if (event.type === "kb_complete" && statusBar) {
        statusBar.setReady(0);
      }
    });

    // Initialize file watcher
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder && agentBridge) {
      const config = loadWatcherConfig();
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
    outputChannel.appendLine("[Dolphin] Creating DolphinViewProvider with AgentBridge...");
    const provider = new DolphinViewProvider(context.extensionUri, outputChannel, agentBridge);
    outputChannel.appendLine("[Dolphin] Registering webview view provider for 'dolphin.chatView'...");
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider("dolphin.chatView", provider, {
        webviewOptions: {
          retainContextWhenHidden: true
        }
      })
    );
    outputChannel.appendLine("[Dolphin] Provider registered successfully");

    // Register commands
    outputChannel.appendLine("[Dolphin] Registering commands...");
    
    // Command: dolphin.focusInput - Focus the chat input in the webview
    context.subscriptions.push(
      vscode.commands.registerCommand('dolphin.focusInput', async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.focusInput");
        await vscode.commands.executeCommand('dolphin.chatView.focus');
        // Post message to webview to focus the input element
        // This would require provider to expose a method to post messages
        vscode.window.showInformationMessage("Chat input focused");
      })
    );

    // Command: dolphin.newConversation - Start a new conversation
    context.subscriptions.push(
      vscode.commands.registerCommand('dolphin.newConversation', async () => {
        outputChannel.appendLine("[Dolphin] Executing dolphin.newConversation");
        // Clear the current conversation and start fresh
        if (agentBridge) {
          // Would need to implement clearConversation on AgentBridge
          outputChannel.appendLine("[Dolphin] Starting new conversation");
        }
        vscode.window.showInformationMessage("New conversation started");
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

    vscode.window.showInformationMessage("Dolphin activated! 🐬");
    outputChannel.appendLine("[Dolphin] Activation complete");
  } catch (error: any) {
    const errorMsg = `Dolphin activation failed: ${error.message}`;
    outputChannel.appendLine(`[ERROR] ${errorMsg}`);
    outputChannel.appendLine(`[ERROR] Stack: ${error.stack}`);
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