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
  apiBaseUrl?: string;
  repoName?: string;
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

      // Send to API endpoint (Phase 2 integration)
      if (this.config.apiBaseUrl && this.config.repoName) {
        try {
          await this.sendChangesToAPI(batch);
        } catch (error) {
          console.error("[FileWatcher] Failed to send changes to API:", error);
        }
      }

      // Send to handler (for backwards compatibility)
      try {
        await this.onBatch(batch);
      } catch (error) {
        console.error("[FileWatcher] Batch processing failed:", error);
      }
    }, this.config.batchIntervalMs);
  }

  private async sendChangesToAPI(batch: ChangeEvent[]): Promise<void> {
    if (!this.config.apiBaseUrl || !this.config.repoName) {
      return;
    }

    // Convert changes to API format
    const changes = batch.map((event) => ({
      file_path: vscode.workspace.asRelativePath(event.uri).replace(/\\/g, "/"),
      change_type: event.type,
    }));

    const response = await fetch(
      `${this.config.apiBaseUrl}/v1/repos/${this.config.repoName}/changes`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ changes }),
      }
    );

    if (!response.ok) {
      throw new Error(`API request failed: ${response.statusText}`);
    }

    console.log(`[FileWatcher] Sent ${changes.length} changes to API`);
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
