// vscode-extension/src/views/provider.ts
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as http from "http";
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

        // KB API Operations
        case "kb_get_stats":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing kb_get_stats: ${message.repoName}`);
          try {
            const data = await this.httpRequest('GET', `/v1/repos/${message.repoName}/stats`);
            webviewView.webview.postMessage({
              type: 'kb_get_stats_response',
              requestId: message.requestId,
              data
            });
          } catch (error: any) {
            this.outputChannel.appendLine(`[DolphinViewProvider] Error getting KB stats: ${error.message}`);
            webviewView.webview.postMessage({
              type: 'kb_get_stats_response',
              requestId: message.requestId,
              error: error.message || 'Failed to get KB stats'
            });
          }
          break;

        case "kb_trigger_reindex":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing kb_trigger_reindex: ${message.repoName}`);
          try {
            const data = await this.httpRequest('POST', `/v1/repos/${message.repoName}/reindex`, message.request);
            webviewView.webview.postMessage({
              type: 'kb_trigger_reindex_response',
              requestId: message.requestId,
              data
            });
          } catch (error: any) {
            this.outputChannel.appendLine(`[DolphinViewProvider] Error triggering reindex: ${error.message}`);
            webviewView.webview.postMessage({
              type: 'kb_trigger_reindex_response',
              requestId: message.requestId,
              error: error.message || 'Failed to trigger reindex'
            });
          }
          break;

        case "kb_get_status":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing kb_get_status: ${message.taskId}`);
          try {
            this.outputChannel.appendLine(`[DolphinViewProvider] Making HTTP request for status: ${message.taskId}`);
            const data = await this.httpRequest('GET', `/v1/index/status/${message.taskId}`);
            this.outputChannel.appendLine(`[DolphinViewProvider] Got status data: ${JSON.stringify(data)}`);
            this.outputChannel.appendLine(`[DolphinViewProvider] Sending kb_get_status_response to webview with requestId: ${message.requestId}`);
            webviewView.webview.postMessage({
              type: 'kb_get_status_response',
              requestId: message.requestId,
              data
            });
            this.outputChannel.appendLine(`[DolphinViewProvider] Response sent successfully`);
          } catch (error: any) {
            this.outputChannel.appendLine(`[DolphinViewProvider] Error getting index status: ${error.message}`);
            this.outputChannel.appendLine(`[DolphinViewProvider] Sending error response to webview`);
            webviewView.webview.postMessage({
              type: 'kb_get_status_response',
              requestId: message.requestId,
              error: error.message || 'Failed to get index status'
            });
          }
          break;

        case "kb_clear_index":
          this.outputChannel.appendLine(`[DolphinViewProvider] Processing kb_clear_index: ${message.repoName}`);
          try {
            const data = await this.httpRequest('DELETE', `/v1/repos/${message.repoName}/index?confirmed=${message.confirmed}`);
            webviewView.webview.postMessage({
              type: 'kb_clear_index_response',
              requestId: message.requestId,
              data
            });
          } catch (error: any) {
            this.outputChannel.appendLine(`[DolphinViewProvider] Error clearing index: ${error.message}`);
            webviewView.webview.postMessage({
              type: 'kb_clear_index_response',
              requestId: message.requestId,
              error: error.message || 'Failed to clear index'
            });
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

      // Note: We don't add nonce to style tags because we need 'unsafe-inline' to work for UI libraries
      // If we add nonce to styles, 'unsafe-inline' will be ignored per CSP spec

      // Add CSP meta tag with nonce - allow connections to localhost KB API
      // Note: style-src uses 'unsafe-inline' (without nonce) to allow UI libraries (like AlertDialog) to set inline styles on body element
      // CSP spec: when a nonce is present, 'unsafe-inline' is ignored. So we only use nonce for scripts, not styles.
      const cspTag = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src ${webview.cspSource} 'nonce-${nonce}'; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}; connect-src ${webview.cspSource} http://127.0.0.1:7777;">`;
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
   * Make HTTP request to KB API with timeout
   */
  private httpRequest(method: string, path: string, body?: any, timeoutMs: number = 5000): Promise<any> {
    return new Promise((resolve, reject) => {
      const options = {
        hostname: '127.0.0.1',
        port: 7777,
        path: path,
        method: method,
        headers: {
          'Content-Type': 'application/json'
        },
        timeout: timeoutMs
      };

      this.outputChannel.appendLine(`[DolphinViewProvider] httpRequest ${method} ${path} (timeout: ${timeoutMs}ms)`);

      const req = http.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          this.outputChannel.appendLine(`[DolphinViewProvider] httpRequest ${method} ${path} response received (${res.statusCode}): ${data.substring(0, 200)}`);
          try {
            const parsed = JSON.parse(data);
            if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
              resolve(parsed);
            } else {
              reject(new Error(parsed.detail || `HTTP ${res.statusCode}`));
            }
          } catch (e) {
            this.outputChannel.appendLine(`[DolphinViewProvider] httpRequest parse error: ${e}`);
            reject(new Error(`Failed to parse response: ${data}`));
          }
        });
      });

      req.on('timeout', () => {
        this.outputChannel.appendLine(`[DolphinViewProvider] httpRequest ${method} ${path} TIMEOUT after ${timeoutMs}ms`);
        req.destroy();
        reject(new Error(`Request timeout after ${timeoutMs}ms`));
      });

      req.on('error', (error) => {
        this.outputChannel.appendLine(`[DolphinViewProvider] httpRequest ${method} ${path} ERROR: ${error.message}`);
        reject(error);
      });

      if (body) {
        req.write(JSON.stringify(body));
      }

      req.end();
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