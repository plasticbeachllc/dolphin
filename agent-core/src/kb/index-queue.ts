// agent-core/src/kb/index-queue.ts
import { EventEmitter } from "events";

export interface IndexProgress {
  task_id: string;
  status: string;
  progress: number;
  total: number;
  indexed: number;
  skipped: number;
  error?: string;
}

/**
 * Simplified IndexQueue that forwards requests to KB API.
 * The KB API handles all queueing and background processing internally.
 */
export class IndexQueue extends EventEmitter {
  private kbApiUrl: string;
  private repoName: string;
  private activeTasks: Set<string> = new Set();
  private pollInterval: NodeJS.Timeout | null = null;
  private kbApiKey?: string;

  constructor(kbApiUrl: string, repoName: string, kbApiKey?: string) {
    super();
    this.kbApiUrl = kbApiUrl;
    this.repoName = repoName;
    this.kbApiKey = kbApiKey || process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY;
  }

  /**
   * Queue files for indexing. Returns immediately with task ID.
   */
  async enqueueBatch(files: string[], _priority = 0): Promise<string> {
    console.error(`[IndexQueue] Queueing ${files.length} files for indexing`);

    const response = await fetch(`${this.kbApiUrl}/v1/index`, {
      method: "POST",
      headers: this.buildHeaders(),
      body: JSON.stringify({
        repo: this.repoName,
        files,
        incremental: true,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Index queue failed (${response.status}): ${errorText}`);
    }

    const result = (await response.json()) as { task_id: string };
    const taskId = result.task_id;

    console.error(`[IndexQueue] Created task ${taskId} for ${files.length} files`);

    // Track this task
    this.activeTasks.add(taskId);

    // Start polling for progress if not already polling
    this.startPolling();

    return taskId;
  }

  /**
   * Start polling for task progress.
   */
  private startPolling(): void {
    if (this.pollInterval) return; // Already polling

    this.pollInterval = setInterval(async () => {
      await this.pollActiveTasks();
    }, 2000); // Poll every 2 seconds
  }

  /**
   * Poll all active tasks for progress updates.
   */
  private async pollActiveTasks(): Promise<void> {
    if (this.activeTasks.size === 0) {
      // No active tasks, stop polling
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
      return;
    }

    const tasksToRemove: string[] = [];

    for (const taskId of this.activeTasks) {
      try {
        const response = await fetch(`${this.kbApiUrl}/v1/index/status/${taskId}`, {
          headers: this.buildHeaders(),
        });

        if (!response.ok) {
          console.error(`[IndexQueue] Failed to get status for task ${taskId}`);
          continue;
        }

        const status = (await response.json()) as IndexProgress;

        // Emit progress event
        this.emit("progress", status.progress);

        // Check if task is complete
        if (status.status === "completed") {
          console.error(
            `[IndexQueue] Task ${taskId} completed: ${status.indexed} indexed, ${status.skipped} skipped`
          );
          this.emit("complete", status);
          tasksToRemove.push(taskId);
        } else if (status.status === "failed") {
          console.error(`[IndexQueue] Task ${taskId} failed: ${status.error}`);
          this.emit("error", new Error(status.error || "Unknown error"));
          tasksToRemove.push(taskId);
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(`[IndexQueue] Error polling task ${taskId}:`, message);
      }
    }

    // Remove completed/failed tasks
    for (const taskId of tasksToRemove) {
      this.activeTasks.delete(taskId);
    }
  }

  /**
   * Get number of active indexing tasks.
   */
  getQueueDepth(): number {
    return this.activeTasks.size;
  }

  /**
   * Check if any tasks are being processed.
   */
  isIndexing(): boolean {
    return this.activeTasks.size > 0;
  }

  /**
   * Stop polling and clean up.
   */
  dispose(): void {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.activeTasks.clear();
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.kbApiKey) {
      headers["X-API-Key"] = this.kbApiKey;
    }
    return headers;
  }
}
