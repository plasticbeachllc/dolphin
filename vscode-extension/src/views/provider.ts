// vscode-extension/src/views/provider.ts
import * as vscode from "vscode";

export class DolphinViewProvider implements vscode.WebviewViewProvider {
  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    webviewView.webview.options = {
      enableScripts: true,
    };

    webviewView.webview.html = this.getHtml();
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dolphin</title>
        <style>
          body {
            padding: 20px;
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
            font-family: var(--vscode-font-family);
          }
          h1 {
            color: var(--vscode-textLink-foreground);
          }
          .status {
            margin-top: 20px;
            padding: 10px;
            background-color: var(--vscode-textBlockQuote-background);
            border-left: 4px solid var(--vscode-textLink-foreground);
          }
        </style>
      </head>
      <body>
        <h1>🐬 Dolphin AI Assistant</h1>
        <div class="status">
          <strong>Status:</strong> Extension loaded successfully!
          <p>Day 1 Morning tasks completed ✅</p>
          <p>WebviewProvider placeholder active.</p>
          <p>Full UI coming in Day 5.</p>
        </div>
      </body>
    </html>`;
  }
}