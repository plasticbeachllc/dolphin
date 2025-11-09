// vscode-extension/src/views/provider.ts
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { AgentBridge } from "../agent/bridge";

export class DolphinViewProvider implements vscode.WebviewViewProvider {
  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly outputChannel: vscode.OutputChannel,
    private readonly agentBridge?: AgentBridge
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.outputChannel.appendLine("[DolphinViewProvider] resolveWebviewView called!");
    
    try {
      webviewView.webview.options = {
        enableScripts: true,
        localResourceRoots: [
          vscode.Uri.joinPath(this.extensionUri, "webview", "build")
        ]
      };
      
      this.outputChannel.appendLine("[DolphinViewProvider] Webview options set, generating HTML...");

      webviewView.webview.html = this.getHtml(webviewView.webview);
      
      this.outputChannel.appendLine("[DolphinViewProvider] HTML set to webview");
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      this.outputChannel.appendLine(`[DolphinViewProvider] FATAL ERROR in resolveWebviewView: ${errorMsg}`);
      if (error instanceof Error && error.stack) {
        this.outputChannel.appendLine(`[DolphinViewProvider] Stack: ${error.stack}`);
      }
      
      // Set error HTML
      webviewView.webview.html = `<!DOCTYPE html>
      <html>
        <head>
          <meta charset="UTF-8">
          <title>Error</title>
        </head>
        <body>
          <h1>Dolphin Failed to Load</h1>
          <p><strong>Error:</strong> ${errorMsg}</p>
          <pre>${error instanceof Error && error.stack ? error.stack : 'No stack trace'}</pre>
        </body>
      </html>`;
    }

    // Handle messages from webview
    webviewView.webview.onDidReceiveMessage(async (message) => {
      this.outputChannel.appendLine(`[DolphinViewProvider] Received message from webview: ${JSON.stringify(message)}`);
      
      switch (message.type) {
        case "send_message":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing send_message: ${message.content}`);
          if (this.agentBridge) {
            await this.agentBridge.sendMessage(message.content);
          } else {
            this.outputChannel.appendLine(`[DolphinViewProvider] WARNING: agentBridge not available`);
            // Send mock response for testing
            webviewView.webview.postMessage({
              type: 'content_delta',
              delta: '<p>Agent bridge not connected. This is a test response.</p>'
            });
            webviewView.webview.postMessage({
              type: 'task_completed',
              success: true
            });
          }
          break;
        
        case "get_auth_status":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing get_auth_status request`);
          if (this.agentBridge) {
            try {
              // Request auth status from agent via JSON-RPC
              this.outputChannel.appendLine(`[DolphinViewProvider] Requesting auth status from agent`);
              
              // Use the new getAuthStatus method on AgentBridge
              const status = await this.agentBridge.getAuthStatus();
              
              this.outputChannel.appendLine(`[DolphinViewProvider] Received auth status: ${JSON.stringify(status)}`);
              
              // Send status to webview
              webviewView.webview.postMessage({
                type: 'auth_status',
                status: status
              });
            } catch (error: any) {
              this.outputChannel.appendLine(`[DolphinViewProvider] Error getting auth status: ${error.message}`);
              // Send error state
              webviewView.webview.postMessage({
                type: 'auth_status',
                status: {
                  mode: 'auto',
                  cliInstalled: false,
                  cliAuthenticated: false,
                  apiKeySet: false,
                  willUseSubscription: false
                }
              });
            }
          } else {
            // Mock auth status when agent not connected
            this.outputChannel.appendLine(`[DolphinViewProvider] Agent not connected, using mock data`);
            webviewView.webview.postMessage({
              type: 'auth_status',
              status: {
                mode: 'auto',
                cliInstalled: false,
                cliAuthenticated: false,
                apiKeySet: false,
                willUseSubscription: false
              }
            });
          }
          break;
        
        default:
          this.outputChannel.appendLine(`[DolphinViewProvider] Unknown message type: ${message.type}`);
      }
    });

    // Forward agent events to webview
    if (this.agentBridge) {
      this.agentBridge.onEvent((event) => {
        webviewView.webview.postMessage(event);
      });
    }

    // Send theme on load
    this.sendTheme(webviewView.webview);

    // Update theme on change
    vscode.window.onDidChangeActiveColorTheme(() => {
      this.sendTheme(webviewView.webview);
    });
  }

  private getHtml(webview: vscode.Webview): string {
    const buildPath = vscode.Uri.joinPath(this.extensionUri, "webview", "build");
    const indexPath = path.join(this.extensionUri.fsPath, "webview", "build", "index.html");
    
    this.outputChannel.appendLine(`[DolphinViewProvider] Loading HTML from: ${indexPath}`);
    this.outputChannel.appendLine(`[DolphinViewProvider] Build path: ${buildPath.fsPath}`);
    
    try {
      // Read the built index.html
      let htmlContent = fs.readFileSync(indexPath, "utf8");
      this.outputChannel.appendLine(`[DolphinViewProvider] Original HTML length: ${htmlContent.length}`);
      
      // Replace /assets/ paths (legacy Vite build) with webview URIs
      let replacementCount = 0;
      htmlContent = htmlContent.replace(
        /(href|src)="\/assets\/([^"]+)"/g,
        (match, attr, assetPath) => {
          const assetUri = webview.asWebviewUri(
            vscode.Uri.joinPath(buildPath, "assets", assetPath)
          );
          replacementCount++;
          this.outputChannel.appendLine(`[DolphinViewProvider] ${match} -> ${attr}="${assetUri}"`);
          return `${attr}="${assetUri}"`;
        }
      );
      
      this.outputChannel.appendLine(`[DolphinViewProvider] Made ${replacementCount} path replacements`);
      
      // Remove crossorigin attribute (not needed for webview URIs)
      htmlContent = htmlContent.replace(/\s+crossorigin/g, '');
      this.outputChannel.appendLine(`[DolphinViewProvider] Removed crossorigin attribute`);
      
      // Add CSP meta tag
      const cspTag = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src ${webview.cspSource} 'unsafe-inline'; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}; connect-src ${webview.cspSource};">`;
      htmlContent = htmlContent.replace(
        /<meta charset="UTF-8" \/>/,
        `<meta charset="UTF-8" />\n\t${cspTag}`
      );
      
      this.outputChannel.appendLine(`[DolphinViewProvider] CSP tag added: ${htmlContent.includes('Content-Security-Policy')}`);
      
      this.outputChannel.appendLine(`[DolphinViewProvider] Final HTML length: ${htmlContent.length}`);
      
      return htmlContent;
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      this.outputChannel.appendLine(`[DolphinViewProvider] ERROR loading HTML: ${errorMsg}`);
      if (error instanceof Error && error.stack) {
        this.outputChannel.appendLine(`[DolphinViewProvider] Stack: ${error.stack}`);
      }
      return `<!DOCTYPE html>
      <html>
        <head>
          <meta charset="UTF-8">
          <title>Error</title>
        </head>
        <body>
          <h1>Failed to load Dolphin UI</h1>
          <p>Error: ${errorMsg}</p>
          <p>Index path: ${indexPath}</p>
        </body>
      </html>`;
    }
  }

  private sendTheme(webview: vscode.Webview): void {
    const theme = vscode.window.activeColorTheme;
    webview.postMessage({
      type: "theme_update",
      theme: {
        kind: theme.kind === vscode.ColorThemeKind.Dark ? "dark" : "light",
        colors: {
          background: "#1e1e1e",
          foreground: "#d4d4d4",
          primary: "#007acc",
          border: "#454545"
        }
      }
    });
  }
}