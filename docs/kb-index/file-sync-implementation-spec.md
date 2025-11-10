# Knowledge Base File Synchronization - Implementation Specification

## Overview

This document provides a comprehensive implementation specification for ensuring the Knowledge Base index stays synchronized with the file system over time, even when files change during active indexing operations, VSCode restarts, or system crashes occur.

## Problem Statement

### Current Limitations

1. **Mid-Index Changes**: Files changed during indexing may result in stale index entries
2. **Race Conditions**: File deletion between validation and read causes silent failures
3. **No Change Tracking**: New files created during indexing require manual reindex
4. **Crash Recovery**: Incomplete indexing operations leave index in inconsistent state
5. **No Drift Detection**: Files modified while VSCode is closed aren't automatically detected

### Requirements

- ✅ Real-time file change detection
- ✅ Crash-proof change persistence
- ✅ Drift detection for offline changes
- ✅ Race-condition handling
- ✅ User-configurable sync modes
- ✅ Transparent conflict resolution

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     File System Watcher                          │
│  (VSCode API: onDidChange/Create/Delete/Rename)                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Change Queue (SQLite)                          │
│  pending_changes: [file_path, change_type, detected_at]         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              Debounce & Filter (5s batch)                        │
│  • Merge consecutive changes                                     │
│  • Apply .gitignore rules                                        │
│  • Skip binary/ignored files                                     │
└────────────────────┬────────────────────────────────────────────┘
                     │
         ┌───────────┴────────────┐
         ▼                        ▼
┌─────────────────┐    ┌──────────────────────┐
│  Active Index?  │    │  Post-Index          │
│     YES         │    │  Validation          │
│  Queue Changes  │    │  (Snapshot Compare)  │
└─────────────────┘    └──────────────────────┘
         │                        │
         └───────────┬────────────┘
                     ▼
         ┌─────────────────────────┐
         │  Trigger Incremental    │
         │  Index Operation        │
         └─────────────────────────┘
```

---

## Phase 1: Foundation

### 1.1 Database Schema Extensions

#### New Table: `pending_changes`

```sql
CREATE TABLE pending_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  change_type TEXT NOT NULL,  -- 'created', 'modified', 'deleted', 'renamed'
  old_path TEXT NULL,          -- For rename operations
  detected_at TEXT NOT NULL DEFAULT (datetime('now')),
  processed BOOLEAN DEFAULT 0,
  processed_at TEXT NULL,
  
  FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE,
  INDEX idx_pending_changes_repo (repo_id),
  INDEX idx_pending_changes_processed (processed),
  INDEX idx_pending_changes_detected (detected_at)
);
```

**Purpose**: Persist file changes across VSCode restarts and during active indexing.

#### New Table: `file_snapshots`

```sql
CREATE TABLE file_snapshots (
  file_id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  mtime_ns INTEGER NOT NULL,     -- Modification time (nanoseconds)
  size_bytes INTEGER NOT NULL,
  content_hash TEXT NOT NULL,    -- SHA-256 of file content
  last_indexed_at TEXT NOT NULL,
  
  FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
  UNIQUE (repo_id, path),
  INDEX idx_file_snapshots_repo (repo_id)
);
```

**Purpose**: Track file state at index time to detect drift and validate consistency.

### 1.2 SQLModel Class Definitions

**File**: `kb/store/sql_models.py`

```python
class PendingChange(SQLModel, table=True):
    """Tracks file changes detected by file watcher."""
    __tablename__ = "pending_changes"
    __table_args__ = (
        Index("idx_pending_changes_repo", "repo_id"),
        Index("idx_pending_changes_processed", "processed"),
        Index("idx_pending_changes_detected", "detected_at"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repos.id")
    file_path: str
    change_type: str  # 'created', 'modified', 'deleted', 'renamed'
    old_path: Optional[str] = Field(default=None)
    detected_at: str
    processed: bool = Field(default=False)
    processed_at: Optional[str] = Field(default=None)


class FileSnapshot(SQLModel, table=True):
    """Tracks file state at index time for drift detection."""
    __tablename__ = "file_snapshots"
    __table_args__ = (
        UniqueConstraint("repo_id", "path", name="uq_file_snapshot_repo_path"),
        Index("idx_file_snapshots_repo", "repo_id"),
    )
    
    file_id: int = Field(primary_key=True, foreign_key="files.id")
    repo_id: int = Field(foreign_key="repos.id")
    path: str
    mtime_ns: int
    size_bytes: int
    content_hash: str
    last_indexed_at: str
```

### 1.3 Implementation Checklist

- [ ] Add schema migrations to `kb/store/sqlite_meta.py`
- [ ] Create SQLModel classes in `kb/store/sql_models.py`
- [ ] Add metadata store methods (see section below)
- [ ] Test database creation and constraints
- [ ] Verify foreign key cascades work correctly

---

## Phase 2: File Watcher Enhancement

### 2.1 Enhanced File Watcher Implementation

**File**: `vscode-extension/src/kb/file-watcher.ts`

Key features:
- Debounced change batching (5 second window)
- Change merging (delete + create = modify)
- gitignore pattern filtering
- Retry logic for failed API calls

### 2.2 Backend API Endpoints

**File**: `kb/api/app.py`

New endpoints:
- `POST /v1/repos/{repo_name}/changes` - Record pending changes
- `GET /v1/repos/{repo_name}/pending-changes` - Get pending changes
- `POST /v1/repos/{repo_name}/changes/mark-processed` - Mark changes as processed

### 2.3 Implementation Checklist

- [ ] Implement enhanced file watcher class
- [ ] Add backend API endpoints
- [ ] Integrate file watcher with extension activation
- [ ] Test change detection for all file operations
- [ ] Verify debouncing and batching work correctly

---

## Phase 3: Post-Index Validation

### 3.1 Snapshot Tracking Strategy

1. **Before indexing**: Capture file state (mtime, size, content hash)
2. **During indexing**: Process files normally
3. **After each file**: Save snapshot to database
4. **After completion**: Compare current state to snapshots
5. **If changes detected**: Queue files for re-indexing

### 3.2 Modified Indexing Pipeline

**File**: `kb/api/app.py` - `_process_index_task()`

Changes:
- Add snapshot capture before processing
- Save snapshot after successful file indexing
- Add post-index validation step
- Queue changed files as pending changes

### 3.3 Implementation Checklist

- [ ] Add snapshot tracking to indexing pipeline
- [ ] Implement post-index validation logic
- [ ] Add warning messages for mid-index changes
- [ ] Test with simulated mid-index file changes
- [ ] Verify re-queuing works correctly

---

## Phase 4: Auto-Sync

### 4.1 Configuration Settings

**Sync Modes**:
- `off`: Disabled, manual reindex only
- `manual`: Notify user, require confirmation
- `smart`: Auto-sync after idle period (default)
- `aggressive`: Immediate incremental indexing

**Settings**:
- `dolphin.kb.autoSync.enabled`: Enable/disable (default: true)
- `dolphin.kb.autoSync.mode`: Sync mode (default: smart)
- `dolphin.kb.autoSync.debounceMs`: Batch window (default: 5000ms)
- `dolphin.kb.autoSync.maxBatchSize`: Max files per batch (default: 100)
- `dolphin.kb.autoSync.idleTimeMs`: Idle threshold (default: 30000ms)

### 4.2 Auto-Sync Manager

**File**: `vscode-extension/src/kb/auto-sync-manager.ts`

Features:
- Periodic pending change checking (every 30s)
- User activity tracking for idle detection
- Configurable sync modes
- Batch size limiting
- Integration with task queue

### 4.3 Implementation Checklist

- [ ] Add configuration settings to package.json
- [ ] Implement auto-sync manager class
- [ ] Integrate with extension activation
- [ ] Add user notifications for manual mode
- [ ] Test all sync modes
- [ ] Verify idle detection works correctly

---

## Phase 5: Testing & Polish

### 5.1 Crash Recovery

**Strategy**:
1. On extension activation, check for stuck tasks
2. Fail tasks stuck for > 5 minutes
3. Check for pending changes accumulated during offline period
4. Prompt user to sync if changes detected

**File**: `vscode-extension/src/extension.ts` - `recoverIncompleteIndexing()`

### 5.2 Drift Detection

**Strategy**:
1. Run hourly background job
2. Compare file snapshots to current filesystem state
3. Record drifted files as pending changes
4. Notify user if drift detected

**File**: `vscode-extension/src/kb/drift-detector.ts`

### 5.3 Testing Scenarios

#### Test 1: Mid-Index File Change
```typescript
test('should detect file changes during indexing', async () => {
  // Start reindex, modify file mid-operation, verify re-queued
});
```

#### Test 2: Crash Recovery
```typescript
test('should recover pending changes after restart', async () => {
  // Create changes, simulate restart, verify persistence
});
```

#### Test 3: Drift Detection
```typescript
test('should detect offline file changes', async () => {
  // Index file, modify externally, run drift detection
});
```

#### Test 4: Change Merging
```typescript
test('should merge consecutive file changes', async () => {
  // Delete + Create = Modify, Create + Delete = No-op
});
```

### 5.4 Implementation Checklist

- [ ] Implement crash recovery logic
- [ ] Implement drift detector
- [ ] Add backend drift detection endpoint
- [ ] Write comprehensive test suite
- [ ] Add telemetry and monitoring
- [ ] Document user-facing features

---

## Complete Implementation Files

### Metadata Store Methods

**File**: `kb/store/sqlite_meta.py`

```python
def record_pending_change(
    self,
    repo_id: int,
    file_path: str,
    change_type: str,
    old_path: str | None = None
) -> int:
    """Record a file change in the pending queue."""
    with self._connect() as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            INSERT INTO pending_changes 
            (repo_id, file_path, change_type, old_path, detected_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (repo_id, file_path, change_type, old_path))
        change_id = cur.lastrowid
        conn.commit()
        return change_id


def get_pending_changes(
    self,
    repo_id: int | None = None,
    limit: int = 1000
) -> list[dict]:
    """Get unprocessed pending changes."""
    with self._connect() as conn, closing(conn.cursor()) as cur:
        if repo_id:
            cur.execute("""
                SELECT id, repo_id, file_path, change_type, old_path, detected_at
                FROM pending_changes
                WHERE repo_id = ? AND processed = 0
                ORDER BY detected_at ASC
                LIMIT ?
            """, (repo_id, limit))
        else:
            cur.execute("""
                SELECT id, repo_id, file_path, change_type, old_path, detected_at
                FROM pending_changes
                WHERE processed = 0
                ORDER BY detected_at ASC
                LIMIT ?
            """, (limit,))
        
        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "repo_id": row[1],
                "file_path": row[2],
                "change_type": row[3],
                "old_path": row[4],
                "detected_at": row[5]
            }
            for row in rows
        ]


def mark_changes_processed(self, change_ids: list[int]) -> int:
    """Mark pending changes as processed."""
    if not change_ids:
        return 0
    
    placeholders = ",".join(["?"] * len(change_ids))
    with self._connect() as conn, closing(conn.cursor()) as cur:
        cur.execute(f"""
            UPDATE pending_changes
            SET processed = 1, processed_at = datetime('now')
            WHERE id IN ({placeholders})
        """, tuple(change_ids))
        updated = cur.rowcount
        conn.commit()
        return updated


def cleanup_old_changes(self, days: int = 7) -> int:
    """Delete processed changes older than specified days."""
    with self._connect() as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            DELETE FROM pending_changes
            WHERE processed = 1 
            AND processed_at < datetime('now', ?)
        """, (f"-{days} days",))
        deleted = cur.rowcount
        conn.commit()
        return deleted


def upsert_file_snapshot(
    self,
    file_id: int,
    repo_id: int,
    path: str,
    mtime_ns: int,
    size_bytes: int,
    content_hash: str
) -> None:
    """Record file state after successful indexing."""
    with self._connect() as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            INSERT INTO file_snapshots 
            (file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(file_id) DO UPDATE SET
                mtime_ns = excluded.mtime_ns,
                size_bytes = excluded.size_bytes,
                content_hash = excluded.content_hash,
                last_indexed_at = excluded.last_indexed_at
        """, (file_id, repo_id, path, mtime_ns, size_bytes, content_hash))
        conn.commit()


def get_file_snapshot(self, file_id: int) -> dict | None:
    """Get snapshot for a file."""
    with self._connect() as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            SELECT file_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at
            FROM file_snapshots
            WHERE file_id = ?
        """, (file_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "file_id": row[0],
            "path": row[1],
            "mtime_ns": row[2],
            "size_bytes": row[3],
            "content_hash": row[4],
            "last_indexed_at": row[5]
        }


def detect_drift(self, repo_id: int) -> list[dict]:
    """Detect files that changed since last snapshot."""
    repo = self.get_repo_by_name(self._get_repo_name_by_id(repo_id))
    if not repo:
        return []
    
    from pathlib import Path
    import hashlib
    
    root = Path(repo["root_path"])
    drift_events = []
    
    with self._connect() as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            SELECT fs.file_id, fs.path, fs.mtime_ns, fs.size_bytes, fs.content_hash
            FROM file_snapshots fs
            WHERE fs.repo_id = ?
        """, (repo_id,))
        
        for row in cur.fetchall():
            file_id, path, snapshot_mtime, snapshot_size, snapshot_hash = row
            file_path = root / path
            
            if not file_path.exists():
                drift_events.append({
                    "file_id": file_id,
                    "path": path,
                    "drift_type": "deleted"
                })
                continue
            
            stat = file_path.stat()
            if stat.st_mtime_ns != snapshot_mtime or stat.st_size != snapshot_size:
                current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if current_hash != snapshot_hash:
                    drift_events.append({
                        "file_id": file_id,
                        "path": path,
                        "drift_type": "modified"
                    })
    
    return drift_events
```

---

## Performance Considerations

### Database Optimization

```sql
-- Indexes for fast queries
CREATE INDEX idx_pending_changes_lookup 
ON pending_changes(repo_id, processed, detected_at);

CREATE INDEX idx_file_snapshots_lookup 
ON file_snapshots(repo_id, path);
```

### Memory Management

- Limit pending changes query to 1000 records at a time
- Batch process changes in groups of 100 files
- Clean up old processed changes daily

### Network Optimization

- Debounce file watcher events (5 second window)
- Send changes in batches, not individually
- Use HTTP keep-alive for API requests

---

## Security Considerations

1. **Path Validation**: Ensure all file paths are within repo boundaries
2. **SQL Injection**: Use parameterized queries for all database operations
3. **Rate Limiting**: Limit pending change recording to prevent DoS
4. **Access Control**: Verify repo ownership before processing changes

---

## Monitoring & Telemetry

### Metrics to Track

- Pending changes queue depth
- Drift detection events per day
- Auto-sync success rate
- Average time from change detection to indexing
- Post-index validation warnings

### Logging Strategy

```typescript
// Log levels:
// - INFO: Normal operations (change detected, sync triggered)
// - WARN: Post-index changes, drift detected
// - ERROR: API failures, crash recovery issues
```

---

## Implementation Timeline

### Week 1: Foundation
- [ ] Day 1-2: Database schema and migrations
- [ ] Day 3-4: Metadata store methods
- [ ] Day 5: Testing and validation

### Week 2: File Watcher
- [ ] Day 1-2: Enhanced file watcher implementation
- [ ] Day 3: Backend API endpoints
- [ ] Day 4-5: Integration and testing

### Week 3: Post-Index Validation
- [ ] Day 1-3: Snapshot tracking in indexing pipeline
- [ ] Day 4-5: Testing and edge cases

### Week 4: Auto-Sync
- [ ] Day 1-2: Configuration and auto-sync manager
- [ ] Day 3-4: Integration with file watcher
- [ ] Day 5: User experience and notifications

### Week 5: Testing & Polish
- [ ] Day 1-2: Crash recovery implementation
- [ ] Day 3: Drift detection job
- [ ] Day 4-5: Comprehensive testing suite

---

## Success Criteria

✅ **Phase 1**: Database tables created, snapshot tracking works  
✅ **Phase 2**: File watcher detects 100% of file changes  
✅ **Phase 3**: Mid-index changes detected and re-queued  
✅ **Phase 4**: Auto-sync processes pending changes within 30s  
✅ **Phase 5**: Crash recovery restores pending changes on restart  

**Overall Success**: Knowledge base stays synchronized with file system without requiring manual full reindexes.

---

## Rollback Plan

If issues arise during implementation:

1. **Phase 1 Rollback**: Drop new tables, revert schema
2. **Phase 2 Rollback**: Disable file watcher, use manual sync only
3. **Phase 3 Rollback**: Remove post-index validation
4. **Phase 4 Rollback**: Disable auto-sync, manual mode only
5. **Phase 5 Rollback**: Remove crash recovery, require manual reindex

---

## Future Enhancements

1. **Conflict Resolution UI**: Show users which files have conflicts
2. **Selective Sync**: Allow users to exclude specific files/patterns
3. **Smart Batching**: Prioritize recently accessed files
4. **Multi-Workspace Support**: Sync across multiple workspace folders
5. **Remote Sync**: Sync across machines via cloud storage