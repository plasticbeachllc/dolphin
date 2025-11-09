# Reference Implementation Examples

**Purpose**: Concrete code examples from Cline and Kilocode that we can adapt for Dolphin's KB sync implementation.

---

## Table of Contents

1. [File Watching (from Cline)](#file-watching-from-cline)
2. [Debouncing Strategy](#debouncing-strategy)
3. [Progress Indicators (from Kilocode)](#progress-indicators-from-kilocode)
4. [Health Monitoring](#health-monitoring)
5. [Queue Management](#queue-management)

---

## File Watching (from Cline)

### Pattern: VSCode File System Watcher

**Learned from**: Cline's workspace monitoring

**Core Pattern**:
```typescript
// Create watcher for specific patterns
const watcher = vscode.workspace.createFileSystemWatcher(
  new vscode.RelativePattern(workspaceFolder, '**/*.{ts,tsx,js,jsx,py}')
);

// Listen to file events
watcher.onDidCreate(uri => handleFileChange(uri, 'created'));
watcher.onDidChange(uri => handleFileChange(uri, 'modified'));
watcher.onDidDelete(uri => handleFileChange(uri, 'deleted'));

// Cleanup
context.subscriptions.push(watcher);
```

**Adaptation for Dolphin**:
```typescript
// vscode-extension/src/kb/file-watcher.ts
export class FileWatcher {
  private watchers: vscode.FileSystemWatcher[] = [];
  private pendingChanges = new Map<string, ChangeEvent>();
  
  async initialize(workspaceFolder: vscode.WorkspaceFolder) {
    // Read .gitignore patterns
    const ignorePatterns = await this.loadGitignore(workspaceFolder);
    
    // Create watcher for code files
    const codeWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(
        workspaceFolder,
        '**/*.{ts,tsx,js,jsx,py,go,rs,java,c,cpp,h}'
      )
    );
    
    // Create watcher for docs
    const docsWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceFolder, '**/*.{md,mdx,txt}')
    );
    
    // Attach handlers
    for (const watcher of [codeWatcher, docsWatcher]) {
      watcher.onDidChange(uri => this.scheduleIndex(uri, 'modified'));
      watcher.onDidCreate(uri => this.scheduleIndex(uri, 'created'));
      watcher.onDidDelete(uri => this.scheduleIndex(uri, 'deleted'));
      
      this.watchers.push(watcher);
    }
  }
  
  private scheduleIndex(uri: vscode.Uri, type: ChangeType) {
    // Check if should ignore
    if (this.shouldIgnore(uri)) {
      return;
    }
    
    // Debounce per file
    const key = uri.fsPath;
    this.pendingChanges.set(key, { uri, type, timestamp: Date.now() });
    
    // Clear existing timer
    if (this.debounceTimers.has(key)) {
      clearTimeout(this.debounceTimers.get(key)!);
    }
    
    // Set new timer
    this.debounceTimers.set(key, setTimeout(() => {
      this.flushChange(key);
    }, this.config.debounceMs));
  }
  
  dispose() {
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
  }
}
```

**Key Learnings**:
1. Use `RelativePattern` for workspace-relative paths
2. Create separate watchers for different file types (better control)
3. Always dispose watchers in `dispose()`
4. Use `context.subscriptions.push()` for cleanup

---

## Debouncing Strategy

### Pattern: Per-File Debouncing

**Problem**: User typing triggers hundreds of change events

**Solution**: Debounce per file, not globally

```typescript
// Bad: Global debounce (delays all files)
let globalTimer: NodeJS.Timeout;
function onChange(uri: vscode.Uri) {
  clearTimeout(globalTimer);
  globalTimer = setTimeout(() => {
    indexAllPendingFiles(); // Delays even unrelated files!
  }, 2000);
}

// Good: Per-file debounce
const fileTimers = new Map<string, NodeJS.Timeout>();
function onChange(uri: vscode.Uri) {
  const key = uri.fsPath;
  
  // Clear existing timer for this file
  if (fileTimers.has(key)) {
    clearTimeout(fileTimers.get(key)!);
  }
  
  // Set new timer for this file only
  fileTimers.set(key, setTimeout(() => {
    indexFile(uri); // Only this file
    fileTimers.delete(key);
  }, 2000));
}
```

**Adaptation for Dolphin**:
```typescript
class DebouncedQueue<T> {
  private timers = new Map<string, NodeJS.Timeout>();
  private pending = new Map<string, T>();
  
  schedule(key: string, item: T, delayMs: number) {
    // Clear existing
    const existingTimer = this.timers.get(key);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }
    
    // Store pending item
    this.pending.set(key, item);
    
    // Schedule new
    const timer = setTimeout(() => {
      this.flush(key);
    }, delayMs);
    
    this.timers.set(key, timer);
  }
  
  private flush(key: string) {
    const item = this.pending.get(key);
    if (item) {
      this.onFlush(key, item);
      this.pending.delete(key);
      this.timers.delete(key);
    }
  }
  
  flushAll() {
    for (const key of this.pending.keys()) {
      this.flush(key);
    }
  }
  
  onFlush: (key: string, item: T) => void = () => {};
}
```

---

## Progress Indicators (from Kilocode)

### Pattern: Non-Intrusive Status Updates

**Learned from**: Kilocode's indexing UI

**Key Insight**: Show progress without blocking user

```typescript
// vscode-extension/src/ui/progress.ts

// Pattern 1: Status Bar (always visible, non-intrusive)
class StatusBarProgress {
  private item: vscode.StatusBarItem;
  
  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100 // Priority
    );
  }
  
  show(message: string, progress?: number) {
    if (progress !== undefined) {
      this.item.text = `$(sync~spin) ${message} ${progress}%`;
    } else {
      this.item.text = `$(sync~spin) ${message}`;
    }
    this.item.show();
  }
  
  hide() {
    this.item.hide();
  }
  
  setReady() {
    this.item.text = '$(database) KB Ready';
    this.item.tooltip = 'Knowledge Base synced';
    this.item.show();
  }
}

// Pattern 2: Progress Notification (for long operations)
async function indexWithProgress<T>(
  operation: (progress: vscode.Progress<{message?: string; increment?: number}>) => Promise<T>
): Promise<T> {
  return vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Indexing workspace",
      cancellable: false
    },
    operation
  );
}

// Usage
await indexWithProgress(async (progress) => {
  progress.report({ message: "Scanning files..." });
  const files = await scanWorkspace();
  
  for (let i = 0; i < files.length; i++) {
    progress.report({
      message: `Indexing ${files[i]}`,
      increment: (1 / files.length) * 100
    });
    await indexFile(files[i]);
  }
});
```

**Adaptation for Dolphin**:
```typescript
// Combine both patterns
export class IndexingProgress {
  private statusBar: StatusBarProgress;
  
  constructor() {
    this.statusBar = new StatusBarProgress();
  }
  
  // Background indexing: status bar only
  startBackground(total: number) {
    let indexed = 0;
    
    return {
      increment() {
        indexed++;
        const percent = Math.round((indexed / total) * 100);
        this.statusBar.show(`Indexing`, percent);
      },
      complete() {
        this.statusBar.setReady();
      }
    };
  }
  
  // User-triggered reindex: notification + status bar
  async startForeground<T>(
    operation: (reporter: ProgressReporter) => Promise<T>
  ): Promise<T> {
    return vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Reindexing workspace",
        cancellable: false
      },
      async (progress) => {
        const reporter = {
          report: (message: string, increment?: number) => {
            progress.report({ message, increment });
            this.statusBar.show(message);
          }
        };
        
        const result = await operation(reporter);
        this.statusBar.setReady();
        return result;
      }
    );
  }
}
```

---

## Health Monitoring

### Pattern: Heartbeat with Auto-Recovery

**Learned from**: Standard microservice patterns

```typescript
export class HealthMonitor {
  private health: HealthState = { status: 'unknown' };
  private checkInterval = 30000; // 30s
  private timeoutMs = 5000; // 5s
  
  async startMonitoring(apiUrl: string) {
    // Initial check
    await this.checkHealth(apiUrl);
    
    // Periodic checks
    setInterval(async () => {
      await this.checkHealth(apiUrl);
    }, this.checkInterval);
  }
  
  private async checkHealth(apiUrl: string) {
    const startTime = Date.now();
    
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
      
      const response = await fetch(`${apiUrl}/health?check=deep`, {
        signal: controller.signal
      });
      
      clearTimeout(timeout);
      
      const latency = Date.now() - startTime;
      
      if (response.ok) {
        this.setHealth({
          status: latency < 1000 ? 'healthy' : 'degraded',
          latency,
          lastCheck: new Date()
        });
      } else {
        this.setHealth({
          status: 'degraded',
          error: `HTTP ${response.status}`,
          lastCheck: new Date()
        });
      }
      
    } catch (error: any) {
      // KB is down
      this.setHealth({
        status: 'down',
        error: error.message,
        lastCheck: new Date()
      });
      
      // Try auto-recovery
      await this.attemptRecovery(apiUrl);
    }
  }
  
  private async attemptRecovery(apiUrl: string) {
    console.log('[Health] KB is down, attempting restart...');
    
    try {
      // Trigger KB restart
      await this.kbManager.restart();
      
      // Wait and recheck
      await new Promise(resolve => setTimeout(resolve, 5000));
      await this.checkHealth(apiUrl);
      
    } catch (error) {
      console.error('[Health] Auto-recovery failed:', error);
      
      // Notify user
      const action = await vscode.window.showErrorMessage(
        'Knowledge Base is offline. Some features may be unavailable.',
        'Restart KB',
        'Dismiss'
      );
      
      if (action === 'Restart KB') {
        await this.kbManager.forceRestart();
      }
    }
  }
  
  private setHealth(state: Partial<HealthState>) {
    const oldStatus = this.health.status;
    this.health = { ...this.health, ...state };
    
    // Emit event if status changed
    if (oldStatus !== this.health.status) {
      this.emit('status-changed', this.health);
    }
  }
  
  getHealth(): HealthState {
    return { ...this.health };
  }
}

type HealthState = {
  status: 'unknown' | 'healthy' | 'degraded' | 'down';
  latency?: number;
  error?: string;
  lastCheck?: Date;
};
```

---

## Queue Management

### Pattern: Priority Queue with Batching

**Learned from**: Job queue systems

```typescript
type QueueItem<T> = {
  id: string;
  priority: number; // Higher = more urgent
  data: T;
  addedAt: number;
};

export class PriorityBatchQueue<T> {
  private queue: QueueItem<T>[] = [];
  private processing = false;
  private batchSize = 20;
  private batchTimeoutMs = 5000;
  
  enqueue(id: string, data: T, priority = 0) {
    // Check if already queued
    const existingIndex = this.queue.findIndex(item => item.id === id);
    
    if (existingIndex !== -1) {
      // Update priority if higher
      if (priority > this.queue[existingIndex].priority) {
        this.queue[existingIndex].priority = priority;
        this.queue[existingIndex].addedAt = Date.now();
      }
      return;
    }
    
    // Add new item
    this.queue.push({
      id,
      priority,
      data,
      addedAt: Date.now()
    });
    
    // Sort by priority (higher first)
    this.queue.sort((a, b) => b.priority - a.priority);
    
    // Start processing if not already
    if (!this.processing) {
      this.startProcessing();
    }
  }
  
  private async startProcessing() {
    this.processing = true;
    
    while (this.queue.length > 0) {
      const batch = await this.collectBatch();
      
      if (batch.length > 0) {
        await this.processBatch(batch);
      }
    }
    
    this.processing = false;
  }
  
  private async collectBatch(): Promise<QueueItem<T>[]> {
    const batch: QueueItem<T>[] = [];
    const deadline = Date.now() + this.batchTimeoutMs;
    
    while (batch.length < this.batchSize && this.queue.length > 0) {
      // Take highest priority item
      const item = this.queue.shift()!;
      batch.push(item);
      
      // If we're at deadline, stop collecting
      if (Date.now() >= deadline && batch.length > 0) {
        break;
      }
      
      // Small delay to allow more items to queue
      if (this.queue.length === 0 && batch.length < this.batchSize) {
        const remaining = deadline - Date.now();
        if (remaining > 0) {
          await new Promise(resolve => setTimeout(resolve, Math.min(remaining, 100)));
        }
      }
    }
    
    return batch;
  }
  
  private async processBatch(batch: QueueItem<T>[]) {
    console.log(`Processing batch of ${batch.length} items`);
    
    try {
      await this.onBatch(batch.map(item => item.data));
      this.emit('batch-complete', batch.length);
      
    } catch (error) {
      console.error('Batch processing failed:', error);
      
      // Retry high-priority items
      for (const item of batch) {
        if (item.priority >= 5) {
          this.enqueue(item.id, item.data, item.priority - 1);
        }
      }
      
      this.emit('batch-error', error);
    }
  }
  
  // Override this
  onBatch: (items: T[]) => Promise<void> = async () => {};
  
  // Event emitter
  private listeners = new Map<string, Function[]>();
  
  emit(event: string, ...args: any[]) {
    const handlers = this.listeners.get(event) || [];
    for (const handler of handlers) {
      handler(...args);
    }
  }
  
  on(event: string, handler: Function) {
    const handlers = this.listeners.get(event) || [];
    handlers.push(handler);
    this.listeners.set(event, handlers);
  }
}
```

**Usage**:
```typescript
const indexQueue = new PriorityBatchQueue<string>();

// Set batch handler
indexQueue.onBatch = async (files: string[]) => {
  await indexFiles(files);
};

// Listen to events
indexQueue.on('batch-complete', (count: number) => {
  console.log(`Indexed ${count} files`);
});

// Enqueue files
indexQueue.enqueue('file1.ts', 'file1.ts', 10); // High priority
indexQueue.enqueue('file2.ts', 'file2.ts', 5);  // Medium priority
indexQueue.enqueue('file3.ts', 'file3.ts', 1);  // Low priority
```

---

## Putting It All Together

### Complete File Watcher Example

```typescript
// vscode-extension/src/kb/complete-watcher.ts

import * as vscode from 'vscode';
import { PriorityBatchQueue } from './queue';
import { IndexQueue } from './index-queue';

export class CompleteFileWatcher {
  private watchers: vscode.FileSystemWatcher[] = [];
  private debounceQueue: DebouncedQueue<FileChange>;
  private indexQueue: PriorityBatchQueue<string>;
  
  constructor(
    private workspaceFolder: vscode.WorkspaceFolder,
    private kbClient: KBClient,
    private config: WatcherConfig
  ) {
    // Setup debounce queue
    this.debounceQueue = new DebouncedQueue();
    this.debounceQueue.onFlush = (filepath, change) => {
      this.queueForIndex(filepath, change);
    };
    
    // Setup index queue
    this.indexQueue = new PriorityBatchQueue();
    this.indexQueue.onBatch = async (files) => {
      await this.kbClient.indexFiles(files);
    };
  }
  
  async start() {
    // Create file watcher
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(
        this.workspaceFolder,
        '**/*.{ts,tsx,js,jsx,py}'
      )
    );
    
    // Attach handlers
    watcher.onDidChange(uri => {
      this.debounceQueue.schedule(
        uri.fsPath,
        { uri, type: 'modified' },
        this.config.debounceMs
      );
    });
    
    watcher.onDidCreate(uri => {
      this.debounceQueue.schedule(
        uri.fsPath,
        { uri, type: 'created' },
        this.config.debounceMs
      );
    });
    
    watcher.onDidDelete(uri => {
      // Delete: no debounce, immediate
      this.queueForIndex(uri.fsPath, { uri, type: 'deleted' });
    });
    
    this.watchers.push(watcher);
  }
  
  private queueForIndex(filepath: string, change: FileChange) {
    // Determine priority
    let priority = 1; // Default: low
    
    // High priority: Currently open files
    const openEditors = vscode.window.visibleTextEditors;
    if (openEditors.some(e => e.document.uri.fsPath === filepath)) {
      priority = 10;
    }
    
    // Medium priority: Recently modified
    if (change.type === 'modified' || change.type === 'created') {
      priority = Math.max(priority, 5);
    }
    
    // Enqueue
    this.indexQueue.enqueue(filepath, filepath, priority);
  }
  
  dispose() {
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
  }
}

type FileChange = {
  uri: vscode.Uri;
  type: 'created' | 'modified' | 'deleted';
};
```

---

## Key Takeaways

1. **Debouncing**: Always per-file, not global
2. **Batching**: Collect changes over time window, then process together
3. **Priority**: User-visible files first, background files later
4. **Health**: Monitor continuously, auto-recover
5. **Progress**: Non-intrusive (status bar), detailed when needed (notification)
6. **Queue**: Deduplicate, prioritize, batch

These patterns are battle-tested in Cline and Kilocode with thousands of users.
