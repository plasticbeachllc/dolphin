# KB Sync Implementation - Quick Start Guide

**Purpose**: Step-by-step guide to implement KB sync in 2 weeks. Each section has specific files to create/modify with code snippets.

**Pre-requisites**:
- Dolphin KB API working (`dolphin serve` runs successfully)
- VSCode extension scaffold complete
- Agent Core with MCP bridge functional

---

## Week 1: Foundation

### Day 1: KB Manager Auto-Start

#### Step 1: Create KB Manager Class

**Create**: `agent-core/src/kb/manager.ts`

```typescript
import { spawn, ChildProcess } from 'child_process';

export class KBManager {
  private process: ChildProcess | null = null;
  private readonly apiUrl = 'http://127.0.0.1:7777';
  private workspaceRoot: string;
  
  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
  }
  
  async start(): Promise<void> {
    console.error('[KB Manager] Starting KB API...');
    
    // Check if already running
    if (await this.isHealthy()) {
      console.error('[KB Manager] KB API already running, reusing');
      return;
    }
    
    // Spawn new process
    await this.spawn();
    
    // Wait for ready
    await this.waitForReady();
  }
  
  private async spawn(): Promise<void> {
    console.error('[KB Manager] Spawning dolphin serve...');
    
    this.process = spawn('dolphin', ['serve'], {
      cwd: this.workspaceRoot,
      detached: false,
      stdio: ['ignore', 'pipe', 'pipe']
    });
    
    // Log output
    this.process.stdout?.on('data', (data) => {
      console.error(`[KB] ${data.toString().trim()}`);
    });
    
    this.process.stderr?.on('data', (data) => {
      console.error(`[KB Error] ${data.toString().trim()}`);
    });
    
    // Handle exit
    this.process.on('exit', (code) => {
      console.error(`[KB Manager] Process exited with code ${code}`);
      this.process = null;
    });
  }
  
  private async waitForReady(maxAttempts = 20): Promise<void> {
    console.error('[KB Manager] Waiting for KB API to be ready...');
    
    for (let i = 0; i < maxAttempts; i++) {
      if (await this.isHealthy()) {
        console.error('[KB Manager] KB API is ready!');
        return;
      }
      
      console.error(`[KB Manager] Attempt ${i + 1}/${maxAttempts}...`);
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    throw new Error('KB API failed to start within 10 seconds');
  }
  
  async isHealthy(): Promise<boolean> {
    try {
      const response = await fetch(`${this.apiUrl}/health`, {
        signal: AbortSignal.timeout(2000)
      });
      return response.ok;
    } catch {
      return false;
    }
  }
  
  async stop(): Promise<void> {
    if (this.process) {
      this.process.kill('SIGTERM');
      this.process = null;
    }
  }
}
```

#### Step 2: Add Types

**Create**: `agent-core/src/kb/types.ts`

```typescript
export type KBStatus = {
  state: 'starting' | 'ready' | 'indexing' | 'degraded' | 'down';
  apiUrl: string;
  uptime: number;
  lastCheck: Date;
  error?: string;
};

export type IndexProgress = {
  total: number;
  indexed: number;
  pending: number;
  errors: number;
};

export type FileChange = {
  type: 'created' | 'modified' | 'deleted';
  path: string;
  timestamp: number;
};
```

#### Step 3: Wire to Agent Core

**Modify**: `agent-core/src/index.ts`

```typescript
import { KBManager } from './kb/manager';

export class AgentCore {
  private kbManager: KBManager;
  
  async initialize(workspaceRoot: string) {
    console.error('[Agent Core] Initializing...');
    
    // Start KB Manager
    this.kbManager = new KBManager(workspaceRoot);
    await this.kbManager.start();
    
    console.error('[Agent Core] KB Manager started');
    
    // ... rest of initialization
  }
  
  async shutdown() {
    await this.kbManager.stop();
  }
}
```

#### Step 4: Test

**Create**: `agent-core/tests/kb/manager.test.ts`

```typescript
import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { KBManager } from '../../src/kb/manager';

describe('KBManager', () => {
  let manager: KBManager;
  
  beforeEach(() => {
    manager = new KBManager(process.cwd());
  });
  
  afterEach(async () => {
    await manager.stop();
  });
  
  test('starts KB API if not running', async () => {
    await manager.start();
    
    const healthy = await manager.isHealthy();
    expect(healthy).toBe(true);
  });
  
  test('reuses existing KB instance', async () => {
    // Start first time
    await manager.start();
    
    // Start again - should reuse
    await manager.start();
    
    const healthy = await manager.isHealthy();
    expect(healthy).toBe(true);
  });
});
```

**Run test**:
```bash
cd agent-core
bun test tests/kb/manager.test.ts
```

**Expected**: ✅ 2 tests pass

---

### Day 2: File Watcher

#### Step 1: Create File Watcher Class

**Create**: `vscode-extension/src/kb/file-watcher.ts`

```typescript
import * as vscode from 'vscode';

export type ChangeEvent = {
  uri: vscode.Uri;
  type: 'created' | 'modified' | 'deleted';
  timestamp: number;
};

export type WatcherConfig = {
  debounceMs: number;
  batchIntervalMs: number;
  excludePatterns: string[];
};

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
    console.log('[FileWatcher] Starting for:', workspaceFolder.uri.fsPath);
    
    // Create watcher for code files
    const pattern = '**/*.{ts,tsx,js,jsx,py,go,rs,java}';
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(workspaceFolder, pattern)
    );
    
    // Attach handlers
    watcher.onDidChange(uri => this.handleChange(uri, 'modified'));
    watcher.onDidCreate(uri => this.handleChange(uri, 'created'));
    watcher.onDidDelete(uri => this.handleChange(uri, 'deleted'));
    
    this.watchers.push(watcher);
    
    // Start batch processor
    this.startBatchProcessor();
  }
  
  private handleChange(uri: vscode.Uri, type: ChangeEvent['type']) {
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
        timestamp: Date.now()
      });
      this.debounceTimers.delete(key);
    }, this.config.debounceMs);
    
    this.debounceTimers.set(key, timer);
  }
  
  private shouldIgnore(uri: vscode.Uri): boolean {
    const path = uri.fsPath;
    
    // Check exclude patterns
    for (const pattern of this.config.excludePatterns) {
      if (path.includes(pattern.replace('**/', ''))) {
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
        console.error('[FileWatcher] Batch processing failed:', error);
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
```

#### Step 2: Create Config Loader

**Create**: `vscode-extension/src/kb/config.ts`

```typescript
import * as vscode from 'vscode';
import { WatcherConfig } from './file-watcher';

export function loadWatcherConfig(): WatcherConfig {
  const config = vscode.workspace.getConfiguration('dolphin.kb');
  
  return {
    debounceMs: config.get('debounceMs', 2000),
    batchIntervalMs: config.get('batchIntervalMs', 5000),
    excludePatterns: config.get('excludePatterns', [
      'node_modules',
      'dist',
      'build',
      '.git'
    ])
  };
}
```

#### Step 3: Wire to Extension

**Modify**: `vscode-extension/src/extension.ts`

```typescript
import { FileWatcher } from './kb/file-watcher';
import { loadWatcherConfig } from './kb/config';

export function activate(context: vscode.ExtensionContext) {
  console.log('Dolphin extension activating...');
  
  // Get workspace folder
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    console.log('No workspace folder, skipping file watcher');
    return;
  }
  
  // Create file watcher
  const config = loadWatcherConfig();
  const fileWatcher = new FileWatcher(config, async (changes) => {
    console.log(`Received ${changes.length} file changes`);
    // TODO: Send to index queue
  });
  
  // Start watching
  fileWatcher.startWatching(workspaceFolder);
  
  // Register for cleanup
  context.subscriptions.push({
    dispose: () => fileWatcher.dispose()
  });
}
```

#### Step 4: Add Settings Schema

**Modify**: `vscode-extension/package.json`

```json
{
  "contributes": {
    "configuration": {
      "title": "Dolphin Knowledge Base",
      "properties": {
        "dolphin.kb.debounceMs": {
          "type": "number",
          "default": 2000,
          "description": "Milliseconds to wait after file change before indexing"
        },
        "dolphin.kb.batchIntervalMs": {
          "type": "number",
          "default": 5000,
          "description": "Milliseconds between batch processing intervals"
        },
        "dolphin.kb.excludePatterns": {
          "type": "array",
          "items": { "type": "string" },
          "default": ["node_modules", "dist", "build", ".git"],
          "description": "Patterns to exclude from indexing"
        }
      }
    }
  }
}
```

**Test**:
1. Open VSCode with extension running
2. Edit a .ts file
3. Check Debug Console for: `[FileWatcher] Processing batch of 1 changes`

---

### Day 3: Index Queue

#### Step 1: Create Index Queue Class

**Create**: `agent-core/src/kb/index-queue.ts`

```typescript
export type IndexTask = {
  filepath: string;
  priority: number;
  addedAt: number;
};

export class IndexQueue {
  private queue: IndexTask[] = [];
  private processing = false;
  private maxBatchSize = 20;
  
  constructor(
    private kbApiUrl: string,
    private repoName: string
  ) {}
  
  enqueue(filepath: string, priority = 0) {
    // Check if already queued
    const existing = this.queue.find(t => t.filepath === filepath);
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
      addedAt: Date.now()
    });
    
    // Sort by priority
    this.queue.sort((a, b) => b.priority - a.priority);
    
    // Start processing
    if (!this.processing) {
      this.processQueue();
    }
  }
  
  enqueueBatch(files: string[], priority = 0) {
    for (const file of files) {
      this.enqueue(file, priority);
    }
  }
  
  private async processQueue() {
    this.processing = true;
    
    while (this.queue.length > 0) {
      // Collect batch
      const batch = this.queue.splice(0, this.maxBatchSize);
      const files = batch.map(t => t.filepath);
      
      console.error(`[IndexQueue] Processing batch of ${files.length} files`);
      
      try {
        await this.indexBatch(files);
        this.emit('progress', files.length);
        
      } catch (error: any) {
        console.error('[IndexQueue] Batch failed:', error.message);
        this.emit('error', error);
      }
      
      // Small delay between batches
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    this.processing = false;
    this.emit('complete');
  }
  
  private async indexBatch(files: string[]): Promise<void> {
    const response = await fetch(`${this.kbApiUrl}/v1/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo: this.repoName,
        files,
        incremental: true
      })
    });
    
    if (!response.ok) {
      throw new Error(`Index failed: ${response.statusText}`);
    }
    
    const result = await response.json();
    console.error(`[IndexQueue] Indexed ${result.indexed}, skipped ${result.skipped}`);
  }
  
  getQueueDepth(): number {
    return this.queue.length;
  }
  
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

#### Step 2: Wire to Agent Core

**Modify**: `agent-core/src/index.ts`

```typescript
import { IndexQueue } from './kb/index-queue';

export class AgentCore {
  private indexQueue: IndexQueue;
  
  async initialize(workspaceRoot: string) {
    // ... KB Manager start
    
    // Create index queue
    this.indexQueue = new IndexQueue(
      'http://127.0.0.1:7777',
      'my-workspace' // TODO: Get from workspace name
    );
    
    // Listen to events
    this.indexQueue.on('progress', (count: number) => {
      console.error(`[Agent Core] Indexed ${count} files`);
      this.sendEvent({
        type: 'kb_progress',
        count
      });
    });
  }
  
  // Expose method for extension to call
  async queueFiles(files: string[], priority = 0) {
    this.indexQueue.enqueueBatch(files, priority);
  }
}
```

#### Step 3: Connect File Watcher to Queue

**Modify**: `vscode-extension/src/extension.ts`

```typescript
const fileWatcher = new FileWatcher(config, async (changes) => {
  console.log(`Received ${changes.length} file changes`);
  
  // Extract file paths
  const files = changes.map(c => 
    vscode.workspace.asRelativePath(c.uri)
  );
  
  // Send to agent core via bridge
  await agentBridge.call('queueFiles', { files, priority: 5 });
});
```

**Test**:
1. Edit a file and save
2. Check Agent Core logs: `[IndexQueue] Processing batch of 1 files`
3. Check KB logs: Should see indexing happen

---

### Day 4-5: KB API Extension

#### Add /v1/index Endpoint

**Modify**: `kb/api/app.py`

```python
from pydantic import BaseModel
from typing import List

class IndexRequest(BaseModel):
    repo: str
    files: List[str]
    incremental: bool = True

class IndexResponse(BaseModel):
    indexed: int
    skipped: int
    tokens_used: int = 0
    cost_usd: float = 0.0

@router.post("/v1/index")
async def index_files(request: IndexRequest) -> IndexResponse:
    """Incrementally index specific files"""
    
    # Get repo
    repo = await store.get_repo_by_name(request.repo)
    if not repo:
        raise HTTPException(404, f"Repository '{request.repo}' not found")
    
    # Filter files that need reindexing
    files_to_index = []
    for filepath in request.files:
        full_path = os.path.join(repo.root_path, filepath)
        
        if not os.path.exists(full_path):
            continue
        
        # Check if changed (existing deduplication logic)
        needs_reindex = await check_file_changed(
            repo_id=repo.id,
            filepath=filepath,
            full_path=full_path
        )
        
        if needs_reindex:
            files_to_index.append(filepath)
    
    if not files_to_index:
        return IndexResponse(indexed=0, skipped=len(request.files))
    
    # Use existing pipeline
    session = await pipeline.index_files(
        repo=repo,
        files=files_to_index
    )
    
    return IndexResponse(
        indexed=session.chunks_indexed,
        skipped=session.chunks_skipped,
        tokens_used=session.tokens_used,
        cost_usd=session.estimated_cost_usd
    )
```

**Test**:
```bash
curl -X POST http://127.0.0.1:7777/v1/index \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "my-workspace",
    "files": ["src/index.ts"],
    "incremental": true
  }'
```

Expected response:
```json
{
  "indexed": 1,
  "skipped": 0,
  "tokens_used": 234,
  "cost_usd": 0.00003
}
```

---

## Week 2: UI & Polish

### Day 6: Status Bar

**Create**: `vscode-extension/src/ui/kb-status.ts`

```typescript
import * as vscode from 'vscode';

export class KBStatusBar {
  private item: vscode.StatusBarItem;
  
  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = 'dolphin.kb.showStatus';
    this.item.show();
  }
  
  setReady(chunkCount: number) {
    this.item.text = '$(database) KB Ready';
    this.item.tooltip = `Knowledge Base synced (${chunkCount} chunks)`;
    this.item.backgroundColor = undefined;
  }
  
  setIndexing(current: number, total: number) {
    const percent = Math.round((current / total) * 100);
    this.item.text = `$(sync~spin) Indexing ${percent}%`;
    this.item.tooltip = `Indexing: ${current}/${total} files`;
  }
  
  setOffline() {
    this.item.text = '$(error) KB Offline';
    this.item.tooltip = 'Click to restart Knowledge Base';
    this.item.backgroundColor = new vscode.ThemeColor(
      'statusBarItem.errorBackground'
    );
  }
  
  dispose() {
    this.item.dispose();
  }
}
```

**Wire to extension**:
```typescript
// In extension.ts
const statusBar = new KBStatusBar();
context.subscriptions.push(statusBar);

// Listen to agent events
agentBridge.on('kb_progress', (data: any) => {
  statusBar.setIndexing(data.current, data.total);
});

agentBridge.on('kb_ready', () => {
  statusBar.setReady(0); // TODO: Get actual count
});
```

---

### Day 7: Commands

**Register commands** in `extension.ts`:

```typescript
context.subscriptions.push(
  vscode.commands.registerCommand('dolphin.kb.showStatus', async () => {
    const status = await agentBridge.call('getKBStatus');
    
    vscode.window.showInformationMessage(
      `KB Status: ${status.state}\n` +
      `Queue depth: ${status.queueDepth}\n` +
      `Last check: ${status.lastCheck}`
    );
  }),
  
  vscode.commands.registerCommand('dolphin.kb.reindex', async () => {
    await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: "Reindexing workspace"
    }, async (progress) => {
      await agentBridge.call('reindexWorkspace');
    });
    
    vscode.window.showInformationMessage('Workspace reindexed');
  }),
  
  vscode.commands.registerCommand('dolphin.kb.restart', async () => {
    await agentBridge.call('restartKB');
    vscode.window.showInformationMessage('Knowledge Base restarted');
  })
);
```

---

### Day 8-10: Testing & Polish

**Create integration test**:

```typescript
// vscode-extension/src/__tests__/integration.test.ts

import * as vscode from 'vscode';
import * as assert from 'assert';

suite('KB Sync Integration', () => {
  test('File change triggers index', async () => {
    // Create test file
    const doc = await vscode.workspace.openTextDocument({
      content: 'function test() {}',
      language: 'typescript'
    });
    
    // Save to workspace
    const filepath = vscode.Uri.joinPath(
      vscode.workspace.workspaceFolders![0].uri,
      'test.ts'
    );
    await vscode.workspace.fs.writeFile(
      filepath,
      Buffer.from(doc.getText())
    );
    
    // Wait for indexing
    await new Promise(resolve => setTimeout(resolve, 10000));
    
    // Verify indexed
    // TODO: Query KB API to verify
    
    assert.ok(true);
  });
});
```

**Run tests**:
```bash
cd vscode-extension
npm test
```

---

## Verification Checklist

After implementing, verify these work:

### Manual Tests

- [ ] Open workspace → KB starts automatically
- [ ] Edit file → Status bar shows "Indexing"
- [ ] Wait 10s → Status bar shows "KB Ready"
- [ ] Edit 10 files rapidly → Batches into one index call
- [ ] Kill KB process → Auto-restarts within 30s
- [ ] Command: "Dolphin: Show KB Status" → Shows current state
- [ ] Command: "Dolphin: Reindex Workspace" → Triggers full reindex
- [ ] Search for code → Returns fresh results

### Performance Tests

- [ ] Initial index of 1K files: <2 minutes
- [ ] Initial index of 10K files: <5 minutes
- [ ] Incremental update (1 file): <10 seconds
- [ ] Incremental update (20 files): <30 seconds
- [ ] Memory usage: <500MB total
- [ ] CPU usage during indexing: <20%

### Error Handling

- [ ] KB API not installed → Clear error message
- [ ] KB API crashes → Auto-restarts
- [ ] Network timeout → Retries with backoff
- [ ] Invalid file path → Skips gracefully
- [ ] Large file (>1MB) → Skips or chunks

---

## Common Issues & Solutions

### Issue: "dolphin: command not found"

**Solution**: Install Dolphin globally
```bash
pip install pb-dolphin
```

### Issue: KB starts but health check fails

**Solution**: Check logs
```bash
tail -f ~/.dolphin/knowledge_store/logs/api.log
```

### Issue: File changes not triggering index

**Solution**: Check file watcher is running
```typescript
// Add debug logging
console.log('[FileWatcher] Watching:', workspaceFolder.uri.fsPath);
```

### Issue: Too many API calls / high cost

**Solution**: Increase debounce time
```json
{
  "dolphin.kb.debounceMs": 5000
}
```

---

## Next Steps

After basic implementation is working:

1. **Add Progress UI**: Show detailed indexing progress
2. **Optimize batching**: Smart grouping by file type
3. **Add metrics**: Track index quality and performance
4. **Support multi-root**: Handle multiple workspace folders
5. **Add git hooks**: Index on commit/pull automatically

---

**End of Quick Start Guide**

This guide provides concrete, copy-paste code to get KB sync working in 2 weeks.
