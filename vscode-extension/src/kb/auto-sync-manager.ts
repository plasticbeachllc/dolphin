// vscode-extension/src/kb/auto-sync-manager.ts
import * as vscode from "vscode";

type WorkspaceEventApi = Pick<typeof vscode.workspace, "onDidChangeTextDocument">;

export interface AutoSyncConfig {
  enabled: boolean;
  mode: "off" | "manual" | "smart" | "aggressive";
  idleTimeMs: number;
  maxBatchSize: number;
  checkIntervalMs: number;
}

export interface PendingChange {
  id: number;
  file_path: string;
  change_type: string;
  detected_at: string;
}

export class AutoSyncManager {
  private checkTimer: NodeJS.Timeout | null = null;
  private lastActivityTime: number = Date.now();
  private activityTracker: vscode.Disposable | null = null;
  private isProcessing: boolean = false;
  private isDisposed: boolean = false;

  private log(message: string): void {
    if (!this.isDisposed) {
      try {
        this.outputChannel.appendLine(message);
      } catch {
        // Silently fail if output channel is disposed
      }
    }
  }

  constructor(
    private config: AutoSyncConfig,
    private repoName: string,
    private apiBaseUrl: string,
    private outputChannel: vscode.OutputChannel,
    private workspaceApi: WorkspaceEventApi = vscode.workspace
  ) {}

  async start() {
    if (!this.config.enabled || this.config.mode === "off") {
      this.log("[AutoSync] Auto-sync disabled");
      return;
    }

    this.log(`[AutoSync] Starting in '${this.config.mode}' mode`);

    // Track user activity for idle detection
    this.startActivityTracking();

    // Start periodic check for pending changes
    this.startPeriodicCheck();
  }

  private startActivityTracking() {
    // Track text document changes
    try {
      this.activityTracker = this.workspaceApi.onDidChangeTextDocument(() => {
        if (!this.isDisposed) {
          this.lastActivityTime = Date.now();
        }
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      this.log(`[AutoSync] Failed to start activity tracking: ${message}`);
    }
  }

  private startPeriodicCheck() {
    if (this.checkTimer) {
      clearInterval(this.checkTimer);
    }

    this.checkTimer = setInterval(async () => {
      if (!this.isDisposed) {
        await this.checkAndSync();
      }
    }, this.config.checkIntervalMs);
  }

  private async checkAndSync() {
    if (this.isDisposed || this.isProcessing) {
      return; // Skip if disposed or already processing
    }

    try {
      this.isProcessing = true;

      // Get pending changes from API
      const changes = await this.getPendingChanges();

      if (changes.length === 0) {
        return;
      }

      this.log(`[AutoSync] Found ${changes.length} pending changes`);

      // Handle based on mode
      switch (this.config.mode) {
        case "manual":
          await this.handleManualMode(changes);
          break;
        case "smart":
          await this.handleSmartMode(changes);
          break;
        case "aggressive":
          await this.handleAggressiveMode(changes);
          break;
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      this.log(`[AutoSync] Error during sync: ${message}`);
    } finally {
      this.isProcessing = false;
    }
  }

  private async handleManualMode(changes: PendingChange[]) {
    if (this.isDisposed) {
      return;
    }

    // Notify user and require confirmation
    const choice = await vscode.window.showInformationMessage(
      `${changes.length} file(s) changed. Sync now?`,
      "Sync",
      "Later"
    );

    if (choice === "Sync") {
      await this.processPendingChanges(changes);
    }
  }

  private async handleSmartMode(changes: PendingChange[]) {
    // Check if user is idle
    const idleTime = Date.now() - this.lastActivityTime;

    if (idleTime >= this.config.idleTimeMs) {
      this.log(`[AutoSync] User idle for ${idleTime}ms, syncing...`);
      await this.processPendingChanges(changes);
    } else {
      this.log(`[AutoSync] User active (idle: ${idleTime}ms), deferring sync`);
    }
  }

  private async handleAggressiveMode(changes: PendingChange[]) {
    // Sync immediately
    await this.processPendingChanges(changes);
  }

  private async processPendingChanges(changes: PendingChange[]) {
    // Batch changes
    const batches = this.batchChanges(changes, this.config.maxBatchSize);

    this.log(`[AutoSync] Processing ${batches.length} batch(es)`);

    for (const batch of batches) {
      try {
        // Extract file paths
        const filePaths = batch.map((c) => c.file_path);

        // Trigger indexing via API
        // Note: Python backend will automatically mark changes as processed
        // after successfully indexing each file
        await this.triggerIndexing(filePaths);

        this.log(`[AutoSync] Queued batch of ${batch.length} files for indexing`);
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        this.log(`[AutoSync] Error queuing batch: ${message}`);
        // Continue with next batch even if one fails
      }
    }
  }

  private batchChanges(changes: PendingChange[], maxBatchSize: number): PendingChange[][] {
    const batches: PendingChange[][] = [];
    for (let i = 0; i < changes.length; i += maxBatchSize) {
      batches.push(changes.slice(i, i + maxBatchSize));
    }
    return batches;
  }

  private async getPendingChanges(): Promise<PendingChange[]> {
    const response = await fetch(`${this.apiBaseUrl}/v1/repos/${this.repoName}/pending-changes`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to get pending changes: ${response.statusText}`);
    }

    const data = (await response.json()) as { changes?: PendingChange[]; total?: number };
    return data.changes || [];
  }

  private async triggerIndexing(filePaths: string[]): Promise<void> {
    const response = await fetch(`${this.apiBaseUrl}/v1/index`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        repo: this.repoName,
        files: filePaths,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to trigger indexing: ${response.statusText}`);
    }
  }

  dispose() {
    this.isDisposed = true;

    if (this.checkTimer) {
      clearInterval(this.checkTimer);
      this.checkTimer = null;
    }

    if (this.activityTracker) {
      this.activityTracker.dispose();
      this.activityTracker = null;
    }

    this.log("[AutoSync] Disposed");
  }
}
