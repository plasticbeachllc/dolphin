// agent-core/src/kb/index-queue.ts
import { EventEmitter } from "events";

export interface IndexTask {
  filepath: string;
  priority: number;
  addedAt: number;
}

export interface IndexProgress {
  total: number;
  indexed: number;
  pending: number;
  errors: number;
}

export class IndexQueue extends EventEmitter {
  private queue: IndexTask[] = [];
  private processing = false;
  private maxBatchSize: number;
  private kbApiUrl: string;
  private repoName: string;

  constructor(kbApiUrl: string, repoName: string, maxBatchSize = 20) {
    super();
    this.kbApiUrl = kbApiUrl;
    this.repoName = repoName;
    this.maxBatchSize = maxBatchSize;
  }

  enqueue(filepath: string, priority = 0): void {
    // Check if already queued
    const existing = this.queue.find((t) => t.filepath === filepath);
    if (existing) {
      // Update priority if higher
      if (priority > existing.priority) {
        existing.priority = priority;
        existing.addedAt = Date.now();
      }
      return;
    }

    // Add new task
    this.queue.push({
      filepath,
      priority,
      addedAt: Date.now(),
    });

    // Sort by priority (highest first)
    this.queue.sort((a, b) => b.priority - a.priority);

    // Start processing if not already running
    if (!this.processing) {
      this.processQueue();
    }
  }

  enqueueBatch(files: string[], priority = 0): void {
    for (const file of files) {
      this.enqueue(file, priority);
    }
  }

  private async processQueue(): Promise<void> {
    this.processing = true;

    while (this.queue.length > 0) {
      // Collect batch
      const batch = this.queue.splice(0, this.maxBatchSize);
      const files = batch.map((t) => t.filepath);

      console.error(`[IndexQueue] Processing batch of ${files.length} files`);

      try {
        await this.indexBatch(files);
        this.emit("progress", files.length);
      } catch (error: any) {
        console.error("[IndexQueue] Batch failed:", error.message);
        this.emit("error", error);
      }

      // Small delay between batches to avoid overwhelming KB API
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    this.processing = false;
    this.emit("complete");
  }

  private async indexBatch(files: string[]): Promise<void> {
    const response = await fetch(`${this.kbApiUrl}/v1/index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo: this.repoName,
        files,
        incremental: true,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Index failed (${response.status}): ${errorText}`);
    }

    const result = await response.json();
    console.error(
      `[IndexQueue] Indexed ${result.indexed}, skipped ${result.skipped}`
    );
  }

  getQueueDepth(): number {
    return this.queue.length;
  }

  isIndexing(): boolean {
    return this.processing;
  }

  getProgress(): IndexProgress {
    return {
      total: this.queue.length,
      indexed: 0, // TODO: Track indexed count
      pending: this.queue.length,
      errors: 0, // TODO: Track errors
    };
  }
}
