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
    // For UI testing, we'll skip Agent Core initialization
    // Uncomment the lines below when you have the Knowledge Bank installed
    
    /*
    // Initialize AgentBridge
    agentBridge = new AgentBridge();

    const agentCorePath = context.asAbsolutePath(
      path.join("..", "agent-core", "src", "main.ts")
    );

    await agentBridge.start(agentCorePath);

    // Set context for keybindings
    await vscode.commands.executeCommand(
      "setContext",
      "dolphin.agentReady",
      true
    );

    // Listen for agent events
    agentBridge.onEvent((event) => {
      console.log("[Extension] Agent event:", event.type);

      if (event.type === "content_delta") {
        vscode.window.showInformationMessage(
          `Agent: ${event.delta.slice(0, 50)}...`
        );
      } else if (event.type === "error") {
        vscode.window.showErrorMessage(`Agent error: ${event.error.message}`);
      }
    });
    */

    // Register webview provider (without AgentBridge for UI testing)
    outputChannel.appendLine("[Dolphin] Creating DolphinViewProvider...");
    const provider = new DolphinViewProvider(context.extensionUri, outputChannel);
    outputChannel.appendLine("[Dolphin] Registering webview view provider for 'dolphin.chatView'...");
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider("dolphin.chatView", provider, {
        webviewOptions: {
          retainContextWhenHidden: true
        }
      })
    );
    outputChannel.appendLine("[Dolphin] Provider registered successfully");

    vscode.window.showInformationMessage("Dolphin activated! 🐬 (UI-only mode)");
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