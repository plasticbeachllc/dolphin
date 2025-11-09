// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { DolphinViewProvider } from "./views/provider";

let agentBridge: AgentBridge | null = null;
let outputChannel: vscode.OutputChannel;

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

    // Listen for agent events
    agentBridge.onEvent((event) => {
      outputChannel.appendLine(`[Extension] Agent event: ${event.type}`);
    });

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

export function deactivate() {
  agentBridge?.shutdown();
  agentBridge = null;
}