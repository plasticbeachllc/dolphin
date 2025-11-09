// vscode-extension/src/kb/file-watcher.ts
import * as vscode from "vscode";

export interface ChangeEvent {
  uri: vscode.Uri;
  type: "created" | "modified" | "deleted";
  timestamp: number;
}

export interface WatcherConfig {
  debounceMs: number;
  batchIntervalMs: number;
  excludePatterns: string[];
}

export class FileWatcher {
  private watchers: vscode.FileSystemWatcher[] = [];
  private debounceTimers = new Map<string, NodeJS.Timeout>();
  private pendingChanges = new Map<string, ChangeEvent>();
  private batchTimer: NodeJS.Timeout | null = null;

  constructor(
    private config: WatcherConfig,
    private onBatch: (changes: ChangeEvent[]) => Promise<void>
  ) {}

  async startWatching(workspaceFolder: vscode.WorkspaceFolder) {
    console.log("[FileWatcher] Starting for:", workspaceFolder.uri.fsPath);

    // Create watcher for code files
    const pattern = new vscode.RelativePattern(
      workspaceFolder,
      "**/*.{ts,tsx,js,jsx,py,go,rs,java,c,cpp,h,md,mdx,txt}"
    );
    const watcher = vscode.workspace.createFileSystemWatcher(pattern);

    // Attach handlers
    watcher.onDidChange((uri) => this.handleChange(uri, "modified"));
    watcher.onDidCreate((uri) => this.handleChange(uri, "created"));
    watcher.onDidDelete((uri) => this.handleChange(uri, "deleted"));

    this.watchers.push(watcher);

    // Start batch processor
    this.startBatchProcessor();
  }

  private handleChange(uri: vscode.Uri, type: ChangeEvent["type"]) {
    // Check if should ignore
    if (this.shouldIgnore(uri)) {
      return;
    }

    const key = uri.fsPath;

    // Clear existing debounce timer
    const existingTimer = this.debounceTimers.get(key);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    // Set new debounce timer
    const timer = setTimeout(() => {
      this.pendingChanges.set(key, {
        uri,
        type,
        timestamp: Date.now(),
      });
      this.debounceTimers.delete(key);
    }, this.config.debounceMs);

    this.debounceTimers.set(key, timer);
  }

  private shouldIgnore(uri: vscode.Uri): boolean {
    const path = uri.fsPath;

    // Check exclude patterns
    for (const pattern of this.config.excludePatterns) {
      const cleanPattern = pattern.replace("**/", "").replace("/**", "");
      if (path.includes(cleanPattern)) {
        return true;
      }
    }

    return false;
  }

  private startBatchProcessor() {
    if (this.batchTimer) return;

    this.batchTimer = setInterval(async () => {
      if (this.pendingChanges.size === 0) return;

      // Collect batch
      const batch = Array.from(this.pendingChanges.values());
      this.pendingChanges.clear();

      console.log(`[FileWatcher] Processing batch of ${batch.length} changes`);

      // Send to handler
      try {
        await this.onBatch(batch);
      } catch (error) {
        console.error("[FileWatcher] Batch processing failed:", error);
      }
    }, this.config.batchIntervalMs);
  }

  dispose() {
    // Clear timers
    for (const timer of this.debounceTimers.values()) {
      clearTimeout(timer);
    }

    if (this.batchTimer) {
      clearInterval(this.batchTimer);
    }

    // Dispose watchers
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
  }
}
