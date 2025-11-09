# Knowledge Base Sync & Indexing - Project Plan

**Project**: Seamless KB Management for Dolphin VSCode Extension  
**Version**: 1.0  
**Date**: November 8, 2025  
**Scope**: Small to medium repositories (1K-50K files)  
**Timeline**: 2 weeks  

---

## Table of Contents

1. [Vision & Goals](#vision--goals)
2. [Technical Specification](#technical-specification)
3. [Reference Implementations](#reference-implementations)
4. [Architecture](#architecture)
5. [Implementation Checklist](#implementation-checklist)
6. [Testing Strategy](#testing-strategy)
7. [Success Metrics](#success-metrics)

---

## Vision & Goals

### What We're Building

A **zero-friction knowledge base sync system** that keeps the AI assistant's code understanding perfectly synchronized with workspace changes, requiring no manual intervention from users.

### Core User Experience

```
User opens VSCode → KB auto-starts and indexes workspace in background
User edits file   → Changes queue for indexing (debounced)
User saves file   → Index updated within 5 seconds
User asks AI      → AI has fresh, accurate codebase context
```

### Non-Goals (Out of Scope)

- ❌ Support for 100K+ file monorepos (future)
- ❌ Distributed/multi-machine indexing
- ❌ Real-time collaborative indexing
- ❌ Custom embedding model training
- ❌ Code graph/dependency analysis (Phase 2)

### Success Criteria

1. **Automatic**: KB starts and indexes on extension activation
2. **Fast**: <10s for incremental updates, <5min for initial index (10K files)
3. **Accurate**: 95%+ of workspace changes reflected within 10s
4. **Invisible**: No user action required; runs in background
5. **Resilient**: Gracefully handles KB downtime or errors

---

## Technical Specification

### 1. Auto-Start & Health Management

#### KB Manager

**Location**: `agent-core/src/kb/manager.ts`

**Responsibilities**:
- Detect if KB API is already running (health check)
- Auto-start KB API process if needed
- Monitor health with periodic heartbeat
- Handle graceful shutdown on extension deactivation

**API**:
```typescript
interface KBManager {
  // Lifecycle
  start(workspaceRoot: string): Promise<void>;
  stop(): Promise<void>;
  restart(): Promise<void>;
  
  // Health
  isHealthy(): Promise<boolean>;
  getStatus(): Promise<KBStatus>;
  
  // Events
  on(event: 'ready' | 'down' | 'indexing', handler: Function): void;
}

type KBStatus = {
  state: 'starting' | 'ready' | 'indexing' | 'degraded' | 'down';
  apiUrl: string;
  uptime: number;
  lastCheck: Date;
  error?: string;
};
```

**Startup Flow**:
```
1. Check if KB API responding at http://127.0.0.1:7777
   ├─ YES → Use existing instance
   └─ NO  → Spawn new process
   
2. Spawn: `dolphin serve --port 7777 --background`
   
3. Wait for ready signal (max 10s)
   ├─ Poll /health every 500ms
   └─ Timeout → Show error, offer manual restart
   
4. Register workspace
   ├─ POST /v1/repos {name, path}
   └─ Get repo ID for future queries
```

---

### 2. File Watching & Change Detection

#### Smart File Watcher

**Location**: `vscode-extension/src/kb/file-watcher.ts`

**Responsibilities**:
- Watch workspace for file changes
- Debounce rapid edits to same file
- Batch multiple file changes
- Filter out ignored patterns
- Queue changes for indexing

**Configuration**:
```typescript
interface WatcherConfig {
  // Timing
  debounceMs: number;        // Default: 2000ms (wait for typing to stop)
  batchIntervalMs: number;   // Default: 5000ms (collect changes into batches)
  maxBatchSize: number;      // Default: 20 files
  
  // Behavior
  watchOnActivation: boolean; // Default: true
  indexOnSave: boolean;       // Default: true
  indexOnOpen: boolean;       // Default: false (too aggressive)
  
  // Filters (respect .gitignore + these)
  additionalExcludes: string[]; // e.g., ['**/dist/**', '**/*.min.js']
}
```

**Change Detection Strategy**:
```typescript
type ChangeEvent = {
  type: 'created' | 'modified' | 'deleted';
  uri: vscode.Uri;
  timestamp: number;
};

class FileWatcher {
  private debounceTimers = new Map<string, NodeJS.Timeout>();
  private pendingChanges = new Set<ChangeEvent>();
  
  // Debounce: wait for user to stop typing
  private scheduleChange(event: ChangeEvent) {
    const key = event.uri.fsPath;
    
    if (this.debounceTimers.has(key)) {
      clearTimeout(this.debounceTimers.get(key)!);
    }
    
    this.debounceTimers.set(key, setTimeout(() => {
      this.pendingChanges.add(event);
      this.debounceTimers.delete(key);
    }, this.config.debounceMs));
  }
  
  // Batch: collect multiple changes, send together
  private async processBatch() {
    if (this.pendingChanges.size === 0) return;
    
    const batch = Array.from(this.pendingChanges);
    this.pendingChanges.clear();
    
    // Group by type
    const created = batch.filter(e => e.type === 'created');
    const modified = batch.filter(e => e.type === 'modified');
    const deleted = batch.filter(e => e.type === 'deleted');
    
    // Send to indexer
    await this.indexQueue.enqueue({
      created: created.map(e => e.uri.fsPath),
      modified: modified.map(e => e.uri.fsPath),
      deleted: deleted.map(e => e.uri.fsPath),
    });
  }
}
```

---

### 3. Incremental Indexing

#### Index Queue

**Location**: `agent-core/src/kb/index-queue.ts`

**Responsibilities**:
- Queue files for indexing
- Deduplicate requests (if same file queued multiple times)
- Prioritize user-visible files
- Call KB API with batched requests
- Track indexing progress

**API**:
```typescript
interface IndexQueue {
  // Queue management
  enqueue(files: FileChanges): Promise<void>;
  enqueueBatch(files: string[], priority?: number): Promise<void>;
  
  // Status
  getQueueDepth(): number;
  isIndexing(): boolean;
  
  // Events
  on(event: 'progress' | 'complete' | 'error', handler: Function): void;
}

type FileChanges = {
  created: string[];
  modified: string[];
  deleted: string[];
};

type IndexProgress = {
  total: number;
  indexed: number;
  pending: number;
  errors: number;
};
```

**Processing Strategy**:
```typescript
class IndexQueue {
  private queue: PriorityQueue<IndexTask>;
  private processing = false;
  private concurrency = 1; // Process one batch at a time
  
  async processQueue() {
    if (this.processing) return;
    this.processing = true;
    
    while (this.queue.length > 0) {
      const batch = this.collectBatch(20); // Up to 20 files
      
      try {
        // Call KB API for incremental index
        await this.callKBIndex(batch);
        
        // Update progress
        this.emit('progress', {
          indexed: batch.length,
          pending: this.queue.length
        });
        
      } catch (error) {
        // Handle errors gracefully
        this.handleIndexError(batch, error);
      }
      
      // Small delay to avoid overwhelming KB
      await sleep(100);
    }
    
    this.processing = false;
    this.emit('complete');
  }
  
  private async callKBIndex(files: string[]) {
    // Use existing Dolphin KB incremental index
    const response = await fetch(`${this.kbUrl}/v1/index`, {
      method: 'POST',
      body: JSON.stringify({
        repo: this.repoName,
        files: files,
        incremental: true
      })
    });
    
    if (!response.ok) {
      throw new Error(`Index failed: ${response.statusText}`);
    }
    
    return response.json();
  }
}
```

---

### 4. KB API Extensions

#### New Endpoint: Incremental Index

**Add to**: `kb/api/app.py`

```python
@router.post("/v1/index")
async def index_files(request: IndexRequest) -> IndexResponse:
    """
    Incrementally index specific files in a repository.
    
    This is optimized for real-time updates from VSCode,
    using the existing git-aware incremental indexing logic.
    """
    # Validate repo exists
    repo = store.get_repo(request.repo)
    if not repo:
        raise HTTPException(404, "Repository not found")
    
    # Filter files (check if actually changed via SHA256)
    files_to_index = []
    for filepath in request.files:
        full_path = os.path.join(repo.root_path, filepath)
        
        # Check if file content changed (existing logic)
        needs_reindex = await check_needs_reindex(
            repo_id=repo.id,
            filepath=filepath,
            full_path=full_path
        )
        
        if needs_reindex:
            files_to_index.append(filepath)
    
    if not files_to_index:
        return IndexResponse(
            indexed=0,
            skipped=len(request.files),
            message="No changes detected"
        )
    
    # Use existing pipeline with file list
    session = await pipeline.index_files(
        repo=repo,
        files=files_to_index,
        incremental=True
    )
    
    return IndexResponse(
        indexed=session.chunks_indexed,
        skipped=session.chunks_skipped,
        tokens_used=session.tokens_used,
        cost_usd=session.estimated_cost_usd
    )
```

**Request/Response**:
```python
class IndexRequest(BaseModel):
    repo: str
    files: List[str]
    incremental: bool = True

class IndexResponse(BaseModel):
    indexed: int
    skipped: int
    tokens_used: int = 0
    cost_usd: float = 0.0
    message: str = ""
```

---

### 5. UI Integration

#### Status Bar Indicator

**Location**: `vscode-extension/src/ui/kb-status.ts`

**Visual States**:
```
$(database) KB Ready              # Idle, synced
$(sync~spin) Indexing (5/20)      # Active indexing
$(warning) KB Degraded            # API slow/errors
$(error) KB Offline               # API unreachable
```

**Behavior**:
```typescript
class KBStatusBar {
  private item: vscode.StatusBarItem;
  
  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = 'dolphin.kb.showStatus';
  }
  
  setState(state: KBState) {
    switch (state.status) {
      case 'ready':
        this.item.text = '$(database) KB Ready';
        this.item.tooltip = `Indexed ${state.totalChunks} chunks`;
        this.item.backgroundColor = undefined;
        break;
        
      case 'indexing':
        this.item.text = `$(sync~spin) Indexing (${state.indexed}/${state.total})`;
        this.item.tooltip = 'Updating knowledge base...';
        this.item.backgroundColor = undefined;
        break;
        
      case 'degraded':
        this.item.text = '$(warning) KB Degraded';
        this.item.tooltip = 'Some indexing errors occurred';
        this.item.backgroundColor = new vscode.ThemeColor(
          'statusBarItem.warningBackground'
        );
        break;
        
      case 'offline':
        this.item.text = '$(error) KB Offline';
        this.item.tooltip = 'Click to restart Knowledge Base';
        this.item.backgroundColor = new vscode.ThemeColor(
          'statusBarItem.errorBackground'
        );
        break;
    }
    
    this.item.show();
  }
}
```

#### Commands

**Register in**: `vscode-extension/src/extension.ts`

```typescript
// KB management commands
context.subscriptions.push(
  vscode.commands.registerCommand('dolphin.kb.showStatus', async () => {
    const status = await kbManager.getStatus();
    
    const panel = vscode.window.createWebviewPanel(
      'dolphinKBStatus',
      'Knowledge Base Status',
      vscode.ViewColumn.One,
      {}
    );
    
    panel.webview.html = getStatusHTML(status);
  }),
  
  vscode.commands.registerCommand('dolphin.kb.reindex', async () => {
    await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: "Reindexing workspace",
      cancellable: false
    }, async (progress) => {
      await kbManager.reindexWorkspace(progress);
    });
  }),
  
  vscode.commands.registerCommand('dolphin.kb.restart', async () => {
    await kbManager.restart();
    vscode.window.showInformationMessage('Knowledge Base restarted');
  })
);
```

---

### 6. Error Handling & Fallbacks

#### Graceful Degradation

```typescript
class KBClient {
  async search(query: string, options?: SearchOptions) {
    try {
      // Try KB API first
      return await this.searchViaAPI(query, options);
      
    } catch (error) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ETIMEDOUT') {
        // KB is down - fall back to local search
        console.warn('[KB] API unavailable, using fallback search');
        return await this.fallbackSearch(query, options);
      }
      
      throw error;
    }
  }
  
  private async fallbackSearch(query: string, options?: SearchOptions) {
    // Use VSCode's built-in search as fallback
    const results = await vscode.workspace.findFiles(
      `**/*.{ts,tsx,js,jsx,py}`,
      '**/node_modules/**'
    );
    
    // Simple text matching (no embeddings)
    const matches = [];
    for (const uri of results) {
      const content = await vscode.workspace.fs.readFile(uri);
      const text = content.toString();
      
      if (text.toLowerCase().includes(query.toLowerCase())) {
        matches.push({
          path: vscode.workspace.asRelativePath(uri),
          score: 0.5, // Arbitrary score
          snippet: this.extractSnippet(text, query)
        });
      }
    }
    
    return {
      hits: matches.slice(0, options?.top_k || 5),
      meta: { fallback: true }
    };
  }
}
```

---

## Reference Implementations

### 1. Cline's Approach

**What to learn**:
- ✅ File system watcher with debouncing
- ✅ Human-in-the-loop for expensive operations
- ✅ Clear UI for showing indexing progress
- ✅ VSCode Timeline integration for file history

**Relevant code**:
```typescript
// From Cline's file watcher
const watcher = vscode.workspace.createFileSystemWatcher(
  new vscode.RelativePattern(workspaceFolder, '**/*')
);

watcher.onDidChange(uri => {
  // Debounce file changes
  debouncedUpdate(uri);
});

// Debounce helper
const debouncedUpdate = debounce((uri: vscode.Uri) => {
  updateIndex(uri);
}, 2000); // 2 second delay
```

**References**:
- https://github.com/cline/cline (File watching system)

---

### 2. Kilocode's Strategy

**What to learn**:
- ✅ Priority-based indexing (user-visible first)
- ✅ Batch processing for API efficiency
- ✅ Status indicators in UI
- ✅ Multiple indexing modes

**Key insight**: Index high-priority files first so users get value immediately, then backfill less-critical files in background.

**References**:
- https://github.com/Kilo-Org/kilocode (Indexing strategy)

---

### 3. Dolphin's Existing Implementation

**What to leverage**:
- ✅ Git-aware incremental indexing (already built!)
- ✅ SHA256 deduplication (skip unchanged chunks)
- ✅ LanceDB + SQLite storage (battle-tested)
- ✅ Hybrid BM25 + vector search
- ✅ 243/243 tests passing

**Extend, don't rebuild**: Add incremental endpoint + file watcher, leverage existing pipeline.

**References**:
- `kb/ingest/pipeline.py` - Incremental indexing logic
- `kb/store/sqlite_meta.py` - Deduplication via SHA256
- `kb/api/app.py` - Existing REST API

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   VSCode Extension (Node.js)                 │
│                                                              │
│  ┌──────────────────┐         ┌─────────────────┐          │
│  │  File Watcher    │────────▶│  Index Queue    │          │
│  │  (debounced)     │         │  (batching)     │          │
│  └──────────────────┘         └────────┬────────┘          │
│           │                             │                    │
│           │                             │                    │
│  ┌────────▼──────────┐         ┌───────▼────────┐          │
│  │  Status Bar       │         │  Agent Bridge  │          │
│  │  (UI indicator)   │         │  (stdio/IPC)   │          │
│  └───────────────────┘         └───────┬────────┘          │
└────────────────────────────────────────┼───────────────────┘
                                         │ stdio
┌────────────────────────────────────────▼───────────────────┐
│                 Agent Core (Bun/TypeScript)                 │
│                                                              │
│  ┌──────────────────┐         ┌─────────────────┐          │
│  │  KB Manager      │────────▶│  Health Monitor │          │
│  │  (auto-start)    │         │  (heartbeat)    │          │
│  └────────┬─────────┘         └─────────────────┘          │
│           │                                                  │
│           │ HTTP (spawn process)                            │
└───────────┼──────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────┐
│           Dolphin KB API (Python/FastAPI)                    │
│                                                              │
│  ┌──────────────────────────────────────────────┐           │
│  │  /v1/index (NEW)                             │           │
│  │  • Incremental file indexing                 │           │
│  │  • SHA256 deduplication                      │           │
│  │  • Batch embedding                           │           │
│  └──────────────────────────────────────────────┘           │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  LanceDB         │  │  SQLite          │                │
│  │  (vectors)       │  │  (metadata)      │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: File Change → Index Update

```
1. User saves file.py
   │
   ▼
2. VSCode fires onDidChange event
   │
   ▼
3. File Watcher debounces (2s)
   │
   ▼
4. Adds to pending changes Set
   │
   ▼
5. Batch processor (every 5s) collects changes
   │
   ▼
6. Index Queue receives batch: ['file.py', 'other.js']
   │
   ▼
7. Queue sends HTTP POST /v1/index
   │
   ▼
8. KB API checks SHA256 hashes
   ├─ file.py: changed → reindex
   └─ other.js: unchanged → skip
   │
   ▼
9. Pipeline chunks file.py
   │
   ▼
10. Embed chunks via OpenAI
    │
    ▼
11. Upsert to LanceDB + SQLite
    │
    ▼
12. Return success response
    │
    ▼
13. Index Queue emits 'progress' event
    │
    ▼
14. Status Bar updates: "$(database) KB Ready"
```

---

## Implementation Checklist

### Phase 1: Foundation (Week 1, Days 1-3)

#### Day 1: KB Manager & Auto-Start

**Location**: `agent-core/src/kb/manager.ts`

- [ ] Create `KBManager` class
  - [ ] `start()` method with health check
  - [ ] Process spawning: `dolphin serve`
  - [ ] Wait for ready signal (poll /health)
  - [ ] Error handling & retry logic
  
- [ ] Add health monitoring
  - [ ] `isHealthy()` method
  - [ ] `getStatus()` method
  - [ ] Periodic heartbeat (30s interval)
  
- [ ] Write unit tests
  - [ ] Test auto-start when KB down
  - [ ] Test reuse existing KB instance
  - [ ] Test health check recovery
  
**Files to create**:
- `agent-core/src/kb/manager.ts`
- `agent-core/src/kb/types.ts`
- `agent-core/tests/kb/manager.test.ts`

**Acceptance**: 
- KB API auto-starts on Agent Core activation
- Health checks pass every 30s
- Gracefully handles existing instances

---

#### Day 2: File Watcher

**Location**: `vscode-extension/src/kb/file-watcher.ts`

- [ ] Create `FileWatcher` class
  - [ ] Setup `createFileSystemWatcher` for workspace
  - [ ] Implement debouncing (2s per file)
  - [ ] Collect changes into Set
  - [ ] Filter by .gitignore patterns
  
- [ ] Add batch processing
  - [ ] Interval timer (5s)
  - [ ] Collect pending changes
  - [ ] Group by type (created/modified/deleted)
  - [ ] Send to Index Queue
  
- [ ] Configuration support
  - [ ] Read from `.vscode/settings.json`
  - [ ] Override defaults (debounce, batch size, etc.)
  
- [ ] Write tests
  - [ ] Test debouncing multiple edits
  - [ ] Test batching multiple files
  - [ ] Test gitignore filtering

**Files to create**:
- `vscode-extension/src/kb/file-watcher.ts`
- `vscode-extension/src/kb/config.ts`
- `vscode-extension/src/kb/__tests__/file-watcher.test.ts`

**Acceptance**:
- File changes trigger after 2s of inactivity
- Multiple files batched every 5s
- Respects .gitignore patterns

---

#### Day 3: Index Queue

**Location**: `agent-core/src/kb/index-queue.ts`

- [ ] Create `IndexQueue` class
  - [ ] Priority queue implementation
  - [ ] `enqueue()` method
  - [ ] `enqueueBatch()` method
  - [ ] Deduplication (same file queued multiple times)
  
- [ ] Add processing logic
  - [ ] `processQueue()` main loop
  - [ ] Batch collection (up to 20 files)
  - [ ] HTTP call to KB API `/v1/index`
  - [ ] Error handling & retry
  
- [ ] Event emitters
  - [ ] 'progress' event
  - [ ] 'complete' event
  - [ ] 'error' event
  
- [ ] Write tests
  - [ ] Test queue deduplication
  - [ ] Test batch processing
  - [ ] Test error recovery

**Files to create**:
- `agent-core/src/kb/index-queue.ts`
- `agent-core/tests/kb/index-queue.test.ts`

**Acceptance**:
- Files queued and batched correctly
- HTTP calls made to KB API
- Progress events emitted

---

### Phase 2: KB API Extension (Week 1, Days 4-5)

#### Day 4: Incremental Index Endpoint

**Location**: `kb/api/app.py`

- [ ] Add `/v1/index` endpoint
  - [ ] Request schema validation (Pydantic)
  - [ ] Repository lookup
  - [ ] File path validation (security)
  
- [ ] Implement incremental logic
  - [ ] Reuse existing `check_needs_reindex()`
  - [ ] Filter unchanged files (SHA256)
  - [ ] Call existing pipeline with file list
  
- [ ] Response with metrics
  - [ ] Files indexed vs skipped
  - [ ] Tokens used
  - [ ] Estimated cost
  
- [ ] Write API tests
  - [ ] Test successful indexing
  - [ ] Test deduplication (unchanged files)
  - [ ] Test error cases

**Files to modify**:
- `kb/api/app.py` (add endpoint)
- `kb/api/schemas.py` (add IndexRequest/Response)
- `tests/integration/test_api.py` (add tests)

**Acceptance**:
- POST /v1/index works
- Skips unchanged files
- Returns accurate metrics

---

#### Day 5: Pipeline Integration

**Location**: `kb/ingest/pipeline.py`

- [ ] Add `index_files()` method
  - [ ] Accept explicit file list
  - [ ] Reuse existing chunking logic
  - [ ] Reuse existing embedding logic
  - [ ] Atomic upsert to stores
  
- [ ] Optimize for small batches
  - [ ] Skip full repo scan
  - [ ] Direct file processing
  - [ ] Efficient DB transactions
  
- [ ] Add logging
  - [ ] File-level progress
  - [ ] Error details per file
  - [ ] Performance metrics

**Files to modify**:
- `kb/ingest/pipeline.py` (add method)
- `kb/ingest/cli.py` (expose via CLI if needed)

**Acceptance**:
- Can index specific files
- Performance: <5s for 20 files
- Errors don't block entire batch

---

### Phase 3: UI & Integration (Week 2, Days 6-8)

#### Day 6: Status Bar

**Location**: `vscode-extension/src/ui/kb-status.ts`

- [ ] Create `KBStatusBar` class
  - [ ] Create StatusBarItem
  - [ ] `setState()` method
  - [ ] Icon + text updates
  - [ ] Tooltip with details
  
- [ ] Wire to KB Manager events
  - [ ] Listen to 'indexing' event
  - [ ] Listen to 'ready' event
  - [ ] Listen to 'down' event
  
- [ ] Add click behavior
  - [ ] Open KB status webview
  - [ ] Show indexing progress
  - [ ] Show error details if degraded

**Files to create**:
- `vscode-extension/src/ui/kb-status.ts`
- `vscode-extension/src/ui/kb-status-panel.ts` (webview)

**Acceptance**:
- Status bar shows in VSCode
- Updates in real-time
- Click shows detailed status

---

#### Day 7: Commands

**Location**: `vscode-extension/src/extension.ts`

- [ ] Register commands
  - [ ] `dolphin.kb.showStatus`
  - [ ] `dolphin.kb.reindex`
  - [ ] `dolphin.kb.restart`
  
- [ ] Implement handlers
  - [ ] Status: Show webview panel
  - [ ] Reindex: Trigger full reindex with progress
  - [ ] Restart: Kill and restart KB API
  
- [ ] Add to package.json
  - [ ] Command contributions
  - [ ] Keybindings (optional)
  - [ ] Menu items (context menu)

**Files to modify**:
- `vscode-extension/src/extension.ts`
- `vscode-extension/package.json`

**Acceptance**:
- Commands available in Command Palette
- All commands work correctly
- Progress shown for long operations

---

#### Day 8: End-to-End Integration

**Tasks**:

- [ ] Wire all components together
  - [ ] Extension activates KB Manager
  - [ ] File Watcher starts on activation
  - [ ] Index Queue connects to KB API
  - [ ] Status Bar shows real-time status
  
- [ ] Add extension settings
  - [ ] `dolphin.kb.enabled`
  - [ ] `dolphin.kb.debounceMs`
  - [ ] `dolphin.kb.batchIntervalMs`
  - [ ] `dolphin.kb.excludePatterns`
  
- [ ] Write integration test
  - [ ] Open workspace
  - [ ] Edit file
  - [ ] Verify index updated
  - [ ] Check status bar

**Files to modify**:
- `vscode-extension/src/extension.ts` (wire everything)
- `vscode-extension/package.json` (settings schema)

**Acceptance**:
- Full flow works end-to-end
- Settings configurable by user
- Clean startup and shutdown

---

### Phase 4: Testing & Polish (Week 2, Days 9-10)

#### Day 9: Testing

- [ ] Unit tests
  - [ ] KB Manager: 10 tests
  - [ ] File Watcher: 8 tests
  - [ ] Index Queue: 10 tests
  - [ ] Status Bar: 5 tests
  
- [ ] Integration tests
  - [ ] File change → KB update: 5 scenarios
  - [ ] Error handling: 3 scenarios
  - [ ] Multi-file batch: 2 scenarios
  
- [ ] Manual testing
  - [ ] Large workspace (10K files)
  - [ ] Rapid file edits
  - [ ] KB restart scenarios
  - [ ] Extension reload

**Acceptance**:
- 90%+ test coverage
- All integration tests pass
- Manual test cases documented

---

#### Day 10: Documentation & Polish

- [ ] User documentation
  - [ ] Update README with KB sync info
  - [ ] Add configuration guide
  - [ ] Add troubleshooting section
  
- [ ] Developer documentation
  - [ ] Architecture diagram
  - [ ] API documentation
  - [ ] Testing guide
  
- [ ] Polish
  - [ ] Improve error messages
  - [ ] Add helpful tooltips
  - [ ] Optimize performance
  - [ ] Clean up console logs

**Files to create/update**:
- `docs/KB_SYNC.md` (this file!)
- `README.md` (update)
- `DEVELOPMENT.md` (update)

**Acceptance**:
- Documentation complete
- Code clean and commented
- Ready for user testing

---

## Testing Strategy

### Unit Tests

**Framework**: Bun test (TypeScript), pytest (Python)

**Coverage targets**:
- KB Manager: 90%+
- File Watcher: 85%+
- Index Queue: 90%+
- API endpoints: 95%+

**Key test cases**:
```typescript
// KB Manager
test('auto-starts KB when not running')
test('reuses existing KB instance')
test('handles KB crash and restarts')
test('health check detects degradation')

// File Watcher
test('debounces rapid file edits')
test('batches multiple file changes')
test('respects gitignore patterns')
test('handles file deletion')

// Index Queue
test('deduplicates queued files')
test('processes batches in order')
test('retries on network error')
test('emits progress events')
```

---

### Integration Tests

**Setup**: Real VSCode workspace with test files

**Key scenarios**:
```typescript
// Scenario 1: File edit → Index update
1. Open workspace
2. Edit file.ts
3. Save
4. Wait 10s
5. Assert: KB search returns updated content

// Scenario 2: Batch updates
1. Edit 10 files rapidly
2. Save all
3. Wait 10s
4. Assert: All files indexed

// Scenario 3: KB restart
1. Kill KB process
2. Trigger search
3. Assert: KB auto-restarts
4. Assert: Search works after restart
```

---

### Performance Tests

**Targets**:
- Initial index: <5min for 10K files
- Incremental update: <10s for 20 files
- Debounce latency: 2s ± 100ms
- Batch latency: 5s ± 200ms

**Load tests**:
- 100 rapid file edits → should batch efficiently
- 1000 file workspace → should index without errors
- Concurrent editing → should not drop changes

---

## Success Metrics

### Quantitative

1. **Indexing Speed**
   - Initial: <5 minutes for 10K files
   - Incremental: <10 seconds for 20 files
   - Target: 95% of updates within 10s

2. **Accuracy**
   - 95%+ of file changes reflected in KB
   - 0 data loss (all saves indexed eventually)
   - <1% false negatives in search

3. **Resource Usage**
   - Memory: <500MB for extension + KB
   - CPU: <10% average during indexing
   - Disk: <2GB for 10K file index

4. **Reliability**
   - 99%+ uptime for KB API
   - Auto-recovery within 30s of failure
   - 0 data corruption events

### Qualitative

1. **User Experience**
   - "I never think about indexing"
   - "Search results are always fresh"
   - "Extension doesn't slow down my editor"

2. **Developer Experience**
   - Easy to debug (good logging)
   - Easy to test (clear interfaces)
   - Easy to extend (modular design)

---

## Risk Mitigation

### Risk: KB API crashes during indexing

**Mitigation**:
- Auto-restart with exponential backoff
- Queue persistence (don't lose pending files)
- Graceful degradation to local search

**Test**: Kill KB process during indexing, verify recovery

---

### Risk: File watcher misses changes

**Mitigation**:
- Periodic reconciliation (compare git status)
- User-triggered reindex command
- Logging of all watch events

**Test**: Make changes outside VSCode, verify detection

---

### Risk: Too many API calls (cost)

**Mitigation**:
- SHA256 deduplication (skip unchanged)
- Batch embedding (reduce API calls)
- Configurable batch size/frequency
- Cost tracking and warnings

**Test**: Edit same file 100 times, verify 1 embedding call

---

### Risk: Large files slow indexing

**Mitigation**:
- File size limits (skip >1MB by default)
- Chunking for large files
- Async processing (non-blocking)

**Test**: Add 10MB file, verify doesn't block UI

---

## Future Enhancements (Out of Scope)

These are explicitly NOT in the current scope but documented for future consideration:

1. **Smart Priority**
   - Index recently-edited files first
   - Index imported/referenced files next
   - Backfill rarely-used files last

2. **Multi-Workspace**
   - Support multiple VSCode workspaces
   - Share KB across workspaces
   - Isolated indexes per workspace

3. **Code Graph**
   - Track function calls
   - Track imports/exports
   - Enable "find all references" via KB

4. **Streaming Indexing**
   - Index files as they're typed
   - Show partial results immediately
   - Progressive enhancement

5. **Distributed**
   - Remote KB API for teams
   - Shared index across developers
   - Conflict resolution

---

## Appendix: Configuration Schema

### VSCode Settings

Add to `package.json`:

```json
{
  "contributes": {
    "configuration": {
      "title": "Dolphin Knowledge Base",
      "properties": {
        "dolphin.kb.enabled": {
          "type": "boolean",
          "default": true,
          "description": "Enable automatic knowledge base indexing"
        },
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
        "dolphin.kb.maxBatchSize": {
          "type": "number",
          "default": 20,
          "description": "Maximum files to index in a single batch"
        },
        "dolphin.kb.indexOnSave": {
          "type": "boolean",
          "default": true,
          "description": "Trigger indexing when files are saved"
        },
        "dolphin.kb.excludePatterns": {
          "type": "array",
          "items": { "type": "string" },
          "default": [
            "**/node_modules/**",
            "**/dist/**",
            "**/build/**",
            "**/*.min.js",
            "**/.git/**"
          ],
          "description": "Additional patterns to exclude from indexing"
        },
        "dolphin.kb.showStatusBar": {
          "type": "boolean",
          "default": true,
          "description": "Show KB status in status bar"
        }
      }
    }
  }
}
```

---

## Appendix: API Contract

### POST /v1/index

**Request**:
```json
{
  "repo": "my-project",
  "files": [
    "src/index.ts",
    "src/components/Header.tsx"
  ],
  "incremental": true
}
```

**Response (Success)**:
```json
{
  "indexed": 2,
  "skipped": 0,
  "tokens_used": 1542,
  "cost_usd": 0.0002,
  "message": "Successfully indexed 2 files"
}
```

**Response (Partial Success)**:
```json
{
  "indexed": 1,
  "skipped": 1,
  "tokens_used": 750,
  "cost_usd": 0.0001,
  "message": "1 file unchanged, 1 file indexed"
}
```

**Response (Error)**:
```json
{
  "detail": "Repository 'my-project' not found",
  "error_code": "REPO_NOT_FOUND"
}
```

---

**End of Project Plan**

This plan is tightly scoped for 2 weeks of implementation, focusing on the core user experience of seamless KB sync without manual intervention. All components leverage existing Dolphin infrastructure and proven patterns from Cline/Kilocode.
