// vscode-extension/src/kb/auto-sync-manager.ts
import * as vscode from "vscode";

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

  constructor(
    private config: AutoSyncConfig,
    private repoName: string,
    private apiBaseUrl: string,
    private outputChannel: vscode.OutputChannel
  ) {}

  async start() {
    if (!this.config.enabled || this.config.mode === "off") {
      this.outputChannel.appendLine("[AutoSync] Auto-sync disabled");
      return;
    }

    this.outputChannel.appendLine(`[AutoSync] Starting in '${this.config.mode}' mode`);

    // Track user activity for idle detection
    this.startActivityTracking();

    // Start periodic check for pending changes
    this.startPeriodicCheck();
  }

  private startActivityTracking() {
    // Track text document changes
    this.activityTracker = vscode.workspace.onDidChangeTextDocument(() => {
      this.lastActivityTime = Date.now();
    });
  }

  private startPeriodicCheck() {
    if (this.checkTimer) {
      clearInterval(this.checkTimer);
    }

    this.checkTimer = setInterval(async () => {
      await this.checkAndSync();
    }, this.config.checkIntervalMs);
  }

  private async checkAndSync() {
    if (this.isProcessing) {
      return; // Skip if already processing
    }

    try {
      this.isProcessing = true;

      // Get pending changes from API
      const changes = await this.getPendingChanges();

      if (changes.length === 0) {
        return;
      }

      this.outputChannel.appendLine(`[AutoSync] Found ${changes.length} pending changes`);

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
    } catch (error: any) {
      this.outputChannel.appendLine(`[AutoSync] Error during sync: ${error.message}`);
    } finally {
      this.isProcessing = false;
    }
  }

  private async handleManualMode(changes: PendingChange[]) {
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
      this.outputChannel.appendLine(`[AutoSync] User idle for ${idleTime}ms, syncing...`);
      await this.processPendingChanges(changes);
    } else {
      this.outputChannel.appendLine(`[AutoSync] User active (idle: ${idleTime}ms), deferring sync`);
    }
  }

  private async handleAggressiveMode(changes: PendingChange[]) {
    // Sync immediately
    await this.processPendingChanges(changes);
  }

  private async processPendingChanges(changes: PendingChange[]) {
    // Batch changes
    const batches = this.batchChanges(changes, this.config.maxBatchSize);

    this.outputChannel.appendLine(`[AutoSync] Processing ${batches.length} batch(es)`);

    for (const batch of batches) {
      try {
        // Extract file paths
        const filePaths = batch.map((c) => c.file_path);

        // Trigger indexing via API
        // Note: Python backend will automatically mark changes as processed
        // after successfully indexing each file
        await this.triggerIndexing(filePaths);

        this.outputChannel.appendLine(
          `[AutoSync] Queued batch of ${batch.length} files for indexing`
        );
      } catch (error: any) {
        this.outputChannel.appendLine(`[AutoSync] Error queuing batch: ${error.message}`);
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
    if (this.checkTimer) {
      clearInterval(this.checkTimer);
      this.checkTimer = null;
    }

    if (this.activityTracker) {
      this.activityTracker.dispose();
      this.activityTracker = null;
    }

    this.outputChannel.appendLine("[AutoSync] Disposed");
  }
}
