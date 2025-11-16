// vscode-extension/src/kb/drift-detector.ts
import * as vscode from "vscode";

export interface DriftEvent {
  file_id: number;
  path: string;
  drift_type: "modified" | "deleted";
}

export class DriftDetector {
  private checkTimer: NodeJS.Timeout | null = null;
  private checkIntervalMs: number = 3600000; // 1 hour default
  private isDisposed: boolean = false;
  private apiKey?: string;

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
    private repoName: string,
    private apiBaseUrl: string,
    private outputChannel: vscode.OutputChannel,
    checkIntervalMs?: number,
    apiKey?: string
  ) {
    if (checkIntervalMs) {
      this.checkIntervalMs = checkIntervalMs;
    }
    this.apiKey = apiKey;
  }

  public updateApiKey(apiKey?: string): void {
    this.apiKey = apiKey;
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }
    return headers;
  }

  async start() {
    this.log(`[DriftDetector] Starting with ${this.checkIntervalMs}ms interval`);

    // Run initial drift detection
    await this.detectDrift();

    // Schedule periodic drift detection
    this.startPeriodicCheck();
  }

  private startPeriodicCheck() {
    if (this.checkTimer) {
      clearInterval(this.checkTimer);
    }

    this.checkTimer = setInterval(async () => {
      if (!this.isDisposed) {
        await this.detectDrift();
      }
    }, this.checkIntervalMs);
  }

  async detectDrift(): Promise<void> {
    if (this.isDisposed) {
      return;
    }

    try {
      this.log("[DriftDetector] Running drift detection...");

      const driftEvents = await this.fetchDriftEvents();

      if (driftEvents.length === 0) {
        this.log("[DriftDetector] No drift detected");
        return;
      }

      this.log(`[DriftDetector] Found ${driftEvents.length} drifted files`);

      // Record drifted files as pending changes
      await this.recordDriftedFiles(driftEvents);

      // Notify user
      await this.notifyUser(driftEvents);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      this.log(`[DriftDetector] Error during drift detection: ${message}`);
    }
  }

  private async fetchDriftEvents(): Promise<DriftEvent[]> {
    const response = await fetch(`${this.apiBaseUrl}/v1/repos/${this.repoName}/drift`, {
      method: "GET",
      headers: this.buildHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch drift events: ${response.statusText}`);
    }

    const data = (await response.json()) as { drift_events?: DriftEvent[] };
    return data.drift_events || [];
  }

  private async recordDriftedFiles(driftEvents: DriftEvent[]): Promise<void> {
    // Convert drift events to pending changes
    const changes = driftEvents.map((event) => ({
      file_path: event.path,
      change_type: event.drift_type,
    }));

    const response = await fetch(`${this.apiBaseUrl}/v1/repos/${this.repoName}/changes`, {
      method: "POST",
      headers: this.buildHeaders(),
      body: JSON.stringify({
        changes,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to record drifted files: ${response.statusText}`);
    }

    this.log(`[DriftDetector] Recorded ${changes.length} drifted files as pending changes`);
  }

  private async notifyUser(driftEvents: DriftEvent[]): Promise<void> {
    if (this.isDisposed) {
      return;
    }

    const modifiedCount = driftEvents.filter((e) => e.drift_type === "modified").length;
    const deletedCount = driftEvents.filter((e) => e.drift_type === "deleted").length;

    let message = `Detected ${driftEvents.length} file change(s) while VSCode was closed`;
    if (modifiedCount > 0) {
      message += ` (${modifiedCount} modified`;
    }
    if (deletedCount > 0) {
      message += `, ${deletedCount} deleted`;
    }
    message += ")";

    const choice = await vscode.window.showInformationMessage(message, "Sync Now", "Later");

    if (choice === "Sync Now") {
      // Trigger auto-sync (if available) or manual reindex
      vscode.window.showInformationMessage(
        "Sync will be triggered automatically by auto-sync manager"
      );
    }
  }

  dispose() {
    this.isDisposed = true;

    if (this.checkTimer) {
      clearInterval(this.checkTimer);
      this.checkTimer = null;
    }

    this.log("[DriftDetector] Disposed");
  }
}
