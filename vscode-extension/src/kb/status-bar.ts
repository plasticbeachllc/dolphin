// vscode-extension/src/kb/status-bar.ts
import * as vscode from "vscode";

export class KBStatusBar {
  private item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = "dolphin.kb.showStatus";
    this.setReady(0);
    this.item.show();
  }

  setReady(chunkCount: number) {
    this.item.text = "$(database) KB Ready";
    this.item.tooltip = `Knowledge Base synced${chunkCount > 0 ? ` (${chunkCount} chunks)` : ""}`;
    this.item.backgroundColor = undefined;
  }

  setIndexing(current: number, total?: number) {
    if (total && total > 0) {
      const percent = Math.round((current / total) * 100);
      this.item.text = `$(sync~spin) Indexing ${percent}%`;
      this.item.tooltip = `Indexing: ${current}/${total} files`;
    } else {
      this.item.text = `$(sync~spin) Indexing`;
      this.item.tooltip = `Indexing workspace files...`;
    }
    this.item.backgroundColor = undefined;
  }

  setOffline() {
    this.item.text = "$(error) KB Offline";
    this.item.tooltip = "Click to restart Knowledge Base";
    this.item.backgroundColor = new vscode.ThemeColor(
      "statusBarItem.errorBackground"
    );
  }

  setDegraded() {
    this.item.text = "$(warning) KB Degraded";
    this.item.tooltip = "Some indexing errors occurred";
    this.item.backgroundColor = new vscode.ThemeColor(
      "statusBarItem.warningBackground"
    );
  }

  dispose() {
    this.item.dispose();
  }
}
