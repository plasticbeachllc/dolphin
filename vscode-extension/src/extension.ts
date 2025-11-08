// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { DolphinViewProvider } from "./views/provider";

let agentBridge: AgentBridge | null = null;

export async function activate(context: vscode.ExtensionContext) {
  console.log("[Dolphin] Activating...");

  try {
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

    // Register webview provider (placeholder for now)
    const provider = new DolphinViewProvider(context.extensionUri);
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider("dolphin.chatView", provider)
    );

    // Register test command
    const testCmd = vscode.commands.registerCommand(
      "dolphin.test",
      async () => {
        try {
          await agentBridge?.sendMessage("Hello from VS Code!");
        } catch (error: any) {
          vscode.window.showErrorMessage(
            `Failed to send message: ${error.message}`
          );
        }
      }
    );

    context.subscriptions.push(testCmd);

    vscode.window.showInformationMessage("Dolphin activated! 🐬");
  } catch (error: any) {
    vscode.window.showErrorMessage(
      `Dolphin activation failed: ${error.message}`
    );
    throw error;
  }
}

export function deactivate() {
  agentBridge?.shutdown();
  agentBridge = null;
}