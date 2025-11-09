// vscode-extension/src/extension.ts
import * as vscode from "vscode";
import * as path from "path";
import { AgentBridge } from "./agent/bridge";
import { DolphinViewProvider } from "./views/provider";
import { Logger } from "./utils/logger";

let agentBridge: AgentBridge | null = null;
let outputChannel: vscode.OutputChannel;
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

    // Listen for agent events
    agentBridge.onEvent((event) => {
      outputChannel.appendLine(`[Extension] Agent event: ${event.type}`);
    });

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

export function deactivate() {
  agentBridge?.shutdown();
  agentBridge = null;
}