// vscode-extension/src/views/provider.ts
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { AgentBridge } from "../agent/bridge";

export class DolphinViewProvider implements vscode.WebviewViewProvider {
  private webviewView?: vscode.WebviewView;
  private workspaceChangeDisposable?: vscode.Disposable;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly outputChannel: vscode.OutputChannel,
    private readonly agentBridge?: AgentBridge
  ) {
    // Set up event forwarding immediately when AgentBridge is available
    if (this.agentBridge) {
      this.agentBridge.onEvent((event) => {
        // Phase 7: Extract and log correlation ID for event tracking
        const requestId = (event as any).requestId || 'unknown';
        this.outputChannel.appendLine(`[DolphinViewProvider] Received event from agent: ${event.type} (requestId: ${requestId})`);

        // Forward to webview if it's available
        if (this.webviewView) {
          this.outputChannel.appendLine(`[DolphinViewProvider] Forwarding event to webview: ${event.type} (requestId: ${requestId})`);
          this.webviewView.webview.postMessage(event);
        } else {
          this.outputChannel.appendLine(`[DolphinViewProvider] Webview not ready yet, event will be queued (requestId: ${requestId})`);
        }
      });
    }
  }
  
  /**
   * Handle workspace folder changes
   */
  private handleWorkspaceChange(): void {
    if (this.webviewView) {
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      const hasWorkspace = !!workspaceFolder;
      this.outputChannel.appendLine(`[DolphinViewProvider] Workspace changed, hasWorkspace: ${hasWorkspace}`);
      
      const capabilities = ['kb_search', 'file_operations', 'planning', 'claude_auth', 'agentic_tools'];
      if (hasWorkspace) {
        capabilities.push('conversation_persistence');
      }
      
      // Get workspace folder name for KB operations
      const workspaceName = workspaceFolder ? path.basename(workspaceFolder.uri.fsPath) : null;
      
      // Send updated workspace status to webview
      this.webviewView.webview.postMessage({
        type: 'workspace_changed',
        hasWorkspace,
        capabilities,
        workspaceName
      });
    }
  }

  /**
   * Post a message to the webview
   */
  public postMessage(message: any): void {
    if (this.webviewView) {
      this.webviewView.webview.postMessage(message);
    } else {
      this.outputChannel.appendLine(`[DolphinViewProvider] Cannot post message - webview not ready`);
    }
  }

  /**
   * Clear the conversation in the webview
   */
  public clearConversation(): void {
    this.postMessage({ type: 'clear_conversation' });
  }

  /**
   * Focus the chat input in the webview
   */
  public focusInput(): void {
    this.postMessage({ type: 'focus_input' });
  }

  /**
   * Prefill the chat input with text
   */
  public prefillInput(text: string): void {
    this.postMessage({ type: 'prefill_input', text });
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    // Store webview reference
    this.webviewView = webviewView;
    this.outputChannel.appendLine("[DolphinViewProvider] resolveWebviewView called!");
    
    // Set up workspace change listener now that webview exists
    this.workspaceChangeDisposable = vscode.workspace.onDidChangeWorkspaceFolders(() => {
      this.handleWorkspaceChange();
    });
    
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
        case "webview_loaded":
          // Webview JavaScript has loaded and is ready to receive messages
          this.outputChannel.appendLine(`[DolphinViewProvider] ✅ Webview confirmed loaded, sending agent_ready event`);
          if (this.agentBridge) {
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
            const hasWorkspace = !!workspaceFolder;
            const capabilities = ['kb_search', 'file_operations', 'planning', 'claude_auth', 'agentic_tools'];
            if (hasWorkspace) {
              capabilities.push('conversation_persistence');
            }
            
            // Get workspace folder name for KB operations
            const workspaceName = workspaceFolder ? path.basename(workspaceFolder.uri.fsPath) : null;
            
            webviewView.webview.postMessage({
              type: 'agent_ready',
              version: '0.1.0',
              capabilities,
              hasWorkspace,
              workspaceName
            });
          }
          break;
          
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
        
        case "abort_generation":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing abort_generation`);
          if (this.agentBridge) {
            await this.agentBridge.abortGeneration();
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
        
        case "apply_diff":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing apply_diff for ${message.diff?.filePath}`);
          if (message.diff) {
            try {
              await vscode.commands.executeCommand('dolphin.applyDiff', message.diff);
            } catch (error: any) {
              this.outputChannel.appendLine(`[DolphinViewProvider] Error applying diff: ${error.message}`);
            }
          }
          break;
        
        // Phase 5: Conversation Management
        case "list_conversations":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing list_conversations`);
          if (this.agentBridge) {
            try {
              const conversations = await this.agentBridge.listConversations();
              webviewView.webview.postMessage({
                type: 'conversations_listed',
                conversations: conversations
              });
            } catch (error: any) {
              this.outputChannel.appendLine(`[DolphinViewProvider] Error listing conversations: ${error.message}`);
              webviewView.webview.postMessage({
                type: 'error',
                error: { message: `Failed to list conversations: ${error.message}` }
              });
            }
          }
          break;

        case "load_conversation":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing load_conversation: ${message.conversationId}`);
          if (this.agentBridge) {
            try {
              const result = await this.agentBridge.loadConversation(message.conversationId);
              webviewView.webview.postMessage({
                type: 'conversation_loaded',
                conversation: result.conversation,
                branchInfo: result.branchInfo
              });
            } catch (error: any) {
              this.outputChannel.appendLine(`[DolphinViewProvider] Error loading conversation: ${error.message}`);
              webviewView.webview.postMessage({
                type: 'error',
                error: { message: `Failed to load conversation: ${error.message}` }
              });
            }
          }
          break;

        case "delete_conversation":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing delete_conversation: ${message.conversationId}`);
          if (this.agentBridge) {
            try {
              await this.agentBridge.deleteConversation(message.conversationId);
              webviewView.webview.postMessage({
                type: 'conversation_deleted',
                conversationId: message.conversationId
              });
            } catch (error: any) {
              this.outputChannel.appendLine(`[DolphinViewProvider] Error deleting conversation: ${error.message}`);
              webviewView.webview.postMessage({
                type: 'error',
                error: { message: `Failed to delete conversation: ${error.message}` }
              });
            }
          }
          break;

        case "rename_conversation":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing rename_conversation: ${message.conversationId} -> ${message.newTitle}`);
          if (this.agentBridge) {
            try {
              await this.agentBridge.renameConversation(message.conversationId, message.newTitle);
              webviewView.webview.postMessage({
                type: 'conversation_renamed',
                conversationId: message.conversationId,
                newTitle: message.newTitle
              });
            } catch (error: any) {
              this.outputChannel.appendLine(`[DolphinViewProvider] Error renaming conversation: ${error.message}`);
              webviewView.webview.postMessage({
                type: 'error',
                error: { message: `Failed to rename conversation: ${error.message}` }
              });
            }
          }
          break;

        default:
          this.outputChannel.appendLine(`[DolphinViewProvider] Unknown message type: ${message.type}`);
      }
    });

    // Webview will send "webview_loaded" message when ready
    // We'll respond with agent_ready event at that point

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

      // Generate a nonce for scripts and styles
      const nonce = this.getNonce();
      this.outputChannel.appendLine(`[DolphinViewProvider] Generated nonce: ${nonce}`);

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

      // Add nonce to script tags
      htmlContent = htmlContent.replace(
        /<script/g,
        `<script nonce="${nonce}"`
      );

      // Add nonce to inline style tags
      htmlContent = htmlContent.replace(
        /<style/g,
        `<style nonce="${nonce}"`
      );

      // Add CSP meta tag with nonce - allow connections to localhost KB API
      const cspTag = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'nonce-${nonce}'; script-src ${webview.cspSource} 'nonce-${nonce}'; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}; connect-src ${webview.cspSource} http://127.0.0.1:7777;">`;
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

    // Get actual VS Code theme colors
    const getColor = (key: string, fallback: string): string => {
      return new vscode.ThemeColor(key).toString() || fallback;
    };

    webview.postMessage({
      type: "theme_update",
      theme: {
        kind: theme.kind === vscode.ColorThemeKind.Dark ? "dark" : "light",
        colors: {
          background: getColor("editor.background", "#1e1e1e"),
          foreground: getColor("editor.foreground", "#d4d4d4"),
          primary: getColor("focusBorder", "#007acc"),
          border: getColor("panel.border", "#454545"),
          // Additional theme colors for better fidelity
          sidebarBackground: getColor("sideBar.background", "#252526"),
          inputBackground: getColor("input.background", "#3c3c3c"),
          buttonBackground: getColor("button.background", "#0e639c"),
          buttonForeground: getColor("button.foreground", "#ffffff")
        }
      }
    });
  }

  /**
   * Generate a cryptographically secure nonce for CSP
   */
  private getNonce(): string {
    const crypto = require('crypto');
    return crypto.randomBytes(16).toString('base64');
  }
}