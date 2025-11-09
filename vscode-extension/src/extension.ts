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