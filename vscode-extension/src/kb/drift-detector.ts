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

  constructor(
    private repoName: string,
    private apiBaseUrl: string,
    private outputChannel: vscode.OutputChannel,
    checkIntervalMs?: number
  ) {
    if (checkIntervalMs) {
      this.checkIntervalMs = checkIntervalMs;
    }
  }

  async start() {
    this.outputChannel.appendLine(
      `[DriftDetector] Starting with ${this.checkIntervalMs}ms interval`
    );

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
      await this.detectDrift();
    }, this.checkIntervalMs);
  }

  async detectDrift(): Promise<void> {
    try {
      this.outputChannel.appendLine("[DriftDetector] Running drift detection...");

      const driftEvents = await this.fetchDriftEvents();

      if (driftEvents.length === 0) {
        this.outputChannel.appendLine("[DriftDetector] No drift detected");
        return;
      }

      this.outputChannel.appendLine(`[DriftDetector] Found ${driftEvents.length} drifted files`);

      // Record drifted files as pending changes
      await this.recordDriftedFiles(driftEvents);

      // Notify user
      await this.notifyUser(driftEvents);
    } catch (error: any) {
      this.outputChannel.appendLine(
        `[DriftDetector] Error during drift detection: ${error.message}`
      );
    }
  }

  private async fetchDriftEvents(): Promise<DriftEvent[]> {
    const response = await fetch(`${this.apiBaseUrl}/v1/repos/${this.repoName}/drift`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
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
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        changes,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to record drifted files: ${response.statusText}`);
    }

    this.outputChannel.appendLine(
      `[DriftDetector] Recorded ${changes.length} drifted files as pending changes`
    );
  }

  private async notifyUser(driftEvents: DriftEvent[]): Promise<void> {
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
    if (this.checkTimer) {
      clearInterval(this.checkTimer);
      this.checkTimer = null;
    }

    this.outputChannel.appendLine("[DriftDetector] Disposed");
  }
}
