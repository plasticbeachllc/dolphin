# KB File Sync Architecture

## Overview

The KB File Sync system ensures that the knowledge base index stays synchronized with file system changes across crashes, restarts, and mid-index modifications. It uses a crash-proof pending changes queue with automatic status updates.

## Responsibilities

### TypeScript (VSCode Extension)

**Responsibilities:**
- Detect file changes via VSCode file watcher API
- Record changes to the API immediately for crash-proof persistence
- Decide when to trigger indexing (manual/smart/aggressive modes)
- Display indexing status and progress to user
- Detect drift on startup (files changed while VSCode was closed)

**Does NOT:**
- Mark changes as processed (Python handles this automatically)
- Manage the indexing queue
- Track file snapshots

**Key Components:**
- `file-watcher.ts` - Detects file changes and sends to API
- `auto-sync-manager.ts` - Decides when to trigger indexing based on mode
- `drift-detector.ts` - Detects offline changes on startup

### Python (FastAPI Backend)

**Responsibilities:**
- Store pending changes in SQLite database
- Process the indexing queue
- **Automatically mark changes as processed after successful indexing**
- Track file snapshots for drift detection
- Detect mid-index changes and re-queue them
- Provide status API for UI display

**Does NOT:**
- Detect file changes (TypeScript handles this)
- Decide when to index (TypeScript triggers indexing)

**Key Components:**
- `sqlite_meta.py` - Stores pending changes and file snapshots
- `app.py` (_process_index_task) - Processes queue and auto-marks as processed
- File sync API endpoints - Receive changes from TypeScript

## The Flow

### 1. File Change Detection (TypeScript)

```
User edits file.py
  ↓
VSCode file watcher fires
  ↓
TypeScript sends:
POST /v1/repos/my-repo/changes
{
  "changes": [{
    "file_path": "file.py",
    "change_type": "modified"
  }]
}
  ↓
Python stores in pending_changes table
(Change is now crash-proof!)
```

### 2. Triggering Indexing (TypeScript)

```
Auto-sync manager checks every 30s
  ↓
GET /v1/repos/my-repo/pending-changes
  ↓
[Returns pending changes]
  ↓
If user is idle (smart mode):
  POST /v1/index
  {
    "repo": "my-repo",
    "files": ["file.py"]
  }
  ↓
Returns task_id immediately
```

### 3. Processing & Auto-Completion (Python)

```
_process_index_task runs in background
  ↓
For each file:
  1. Capture snapshot before indexing
  2. Index the file
  3. Save snapshot after indexing
  4. AUTOMATICALLY mark pending changes as processed ✅
     (calls mark_changes_for_file_processed)
  ↓
Update task status with progress and current_file
  ↓
On completion, clear current_file
```

### 4. Status Display (TypeScript)

```
Extension polls:
GET /v1/index/status/{task_id}
  ↓
Returns:
{
  "task_id": "...",
  "status": "processing",
  "progress": 3,
  "total": 10,
  "current_file": "src/main.py",  ← Shows user what's indexing
  "indexed": 45,
  "skipped": 12
}
  ↓
Display in UI: "Indexing src/main.py (3/10)..."
```

## API Endpoints

### For TypeScript to Call

- `POST /v1/repos/{repo}/changes` - Record file changes
- `GET /v1/repos/{repo}/pending-changes` - Get pending changes
- `POST /v1/index` - Trigger indexing (returns task_id)
- `GET /v1/index/status/{task_id}` - Poll for status/progress
- `GET /v1/repos/{repo}/drift` - Detect offline changes

### For Manual/Admin Use Only

- `POST /v1/repos/{repo}/changes/mark-processed` - Manually mark changes
  - **Not used by auto-sync** (Python does this automatically)
  - Useful for recovery scenarios, debugging, or cleanup scripts

## Database Schema

### pending_changes

```sql
CREATE TABLE pending_changes (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  change_type TEXT NOT NULL,  -- created/modified/deleted/renamed
  old_path TEXT,              -- for renames
  detected_at TEXT NOT NULL,
  processed BOOLEAN DEFAULT 0,
  processed_at TEXT,
  FOREIGN KEY (repo_id) REFERENCES repos(id)
);

CREATE INDEX idx_pending_changes_repo ON pending_changes(repo_id);
CREATE INDEX idx_pending_changes_processed ON pending_changes(processed);
```

### file_snapshots

```sql
CREATE TABLE file_snapshots (
  file_id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  mtime_ns INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL,
  content_hash TEXT NOT NULL,  -- SHA-256
  last_indexed_at TEXT NOT NULL,
  FOREIGN KEY (file_id) REFERENCES files(id),
  FOREIGN KEY (repo_id) REFERENCES repos(id),
  UNIQUE (repo_id, path)
);
```

## Auto-Sync Modes

### Off
- No automatic syncing
- User must manually trigger indexing

### Manual
- Show notification when changes detected
- Require user confirmation to sync

### Smart (Default)
- Monitor user activity
- Sync when user is idle for 30+ seconds
- Batch changes for efficiency

### Aggressive
- Sync immediately on every change
- Minimal batching
- Highest resource usage

## Crash Recovery

### On Extension Startup

```typescript
async function recoverFromCrash() {
  const response = await fetch(
    `/v1/repos/${repoName}/pending-changes?limit=10`
  );

  if (response.changes.length > 0) {
    vscode.window.showInformationMessage(
      `Found ${response.changes.length} pending changes from previous session. Sync now?`
    );
  }
}
```

### On Drift Detection (Every Hour)

```
GET /v1/repos/my-repo/drift
  ↓
Returns files that changed since last snapshot
  ↓
Record as pending changes
  ↓
Notify user: "3 files changed while VSCode was closed"
```

## Progress Tracking

The system provides detailed progress information for UI display:

```typescript
interface TaskStatus {
  task_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;        // Files processed
  total: number;           // Total files
  current_file: string;    // Currently processing file path
  indexed: number;         // Chunks indexed so far
  skipped: number;         // Chunks skipped (unchanged)
  error?: string;
  result?: {
    files_processed: number;
    indexed: number;
    skipped: number;
    mid_index_changes: number;
  };
}
```

Example UI display:
```
Indexing: src/components/Button.tsx (7/23)
✓ 156 chunks indexed, 42 skipped
```

## Key Design Principles

1. **Separation of Concerns**
   - TypeScript: Detection & UI
   - Python: Processing & Persistence

2. **Crash-Proof by Default**
   - Changes persisted immediately to SQLite
   - No in-memory state loss on crash

3. **Automatic Status Management**
   - Python owns the full indexing lifecycle
   - No manual status updates needed from TypeScript

4. **Who Does What**
   - Whoever does the work updates the status
   - Python indexes → Python marks as processed ✅
   - TypeScript detects → TypeScript records via API ✅

5. **Observable Progress**
   - Real-time progress with current file
   - Detailed metrics for UI display
   - Supports long-running indexing jobs

## Testing

See test files for comprehensive examples:
- `tests/unit/test_store/test_file_sync_store.py` - Database methods
- `tests/unit/test_file_sync_api.py` - API endpoints
- `tests/integration/test_file_sync_integration.py` - End-to-end workflows
- `vscode-extension/src/test/suite/auto-sync-manager.test.ts` - Auto-sync behavior
- `vscode-extension/src/test/suite/drift-detector.test.ts` - Drift detection
- `vscode-extension/src/test/suite/file-watcher-sync.test.ts` - File watching integration
