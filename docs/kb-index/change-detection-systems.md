# Change Detection Systems: Git Diff vs File Sync

## Overview

Dolphin has **two complementary change detection systems** that serve different use cases:

1. **Git Diff Model** - For batch/CLI indexing
2. **File Sync System** - For real-time VSCode extension

## System Comparison

| Feature | Git Diff Model | File Sync System |
|---------|---------------|------------------|
| **Use Case** | Batch indexing, CI/CD, CLI | Real-time auto-sync in VSCode |
| **Trigger** | Manual command or scheduled job | File watcher events |
| **Detection Method** | `git diff` between commits | VSCode file system watcher |
| **Scope** | All changes since last successful index | Individual file changes as they happen |
| **Persistence** | Last indexed commit in sessions table | Pending changes in pending_changes table |
| **Crash Recovery** | Re-run from last successful commit | Pending changes survive crashes |
| **Requires Git** | Yes (uses git history) | No (works on any workspace) |
| **Mode** | Batch processing | Incremental, real-time |

## Git Diff Model (Existing)

### When It's Used

```bash
# CLI command
dolphin index my-repo

# Or via pipeline.index() in Python
from kb.ingest.pipeline import IngestionPipeline
pipeline.index(repo_name="my-repo", full_reindex=False)
```

### How It Works

```python
# From kb/ingest/_helpers.py

def git_changed_files_modified_added(repo_root, from_commit, to_commit='HEAD'):
    """Get files changed between commits using git diff."""

    # 1. Find merge base (handles pulls and merges correctly)
    merge_base = git merge-base from_commit to_commit

    # 2. Get all changed files from merge base to HEAD
    files = git diff --name-only merge_base..HEAD

    return files
```

**Flow:**
```
Last successful index: abc123 (stored in sessions table)
Current HEAD: def456

git diff abc123..def456
  ↓
Returns: [file1.py, file2.py, file3.py]
  ↓
Index those files
  ↓
Update sessions table with new commit: def456
```

### When to Use Git Diff

- **CI/CD pipelines**: Index after merge to main
- **Nightly batch jobs**: Index all changes from previous run
- **Manual reindexing**: User runs `dolphin index`
- **After git pull**: Detect remote changes
- **Large changesets**: Multiple commits, branch merges

## File Sync System (New)

### When It's Used

```typescript
// VSCode extension - automatic
// Runs continuously while VSCode is open

User edits file → File watcher fires → Record to API → Auto-sync triggers → Index
```

### How It Works

```
1. File watcher detects change
   ↓
2. POST /v1/repos/my-repo/changes
   (Persisted to SQLite immediately - crash-proof!)
   ↓
3. Auto-sync manager checks every 30s
   GET /v1/repos/my-repo/pending-changes
   ↓
4. If user is idle, trigger indexing:
   POST /v1/index {files: ["file.py"]}
   ↓
5. Python indexes and auto-marks as processed
```

### When to Use File Sync

- **Real-time editing**: Changes detected as user types and saves
- **VSCode integration**: Seamless auto-sync while coding
- **Crash recovery**: Changes survive VSCode crashes
- **Offline work**: Drift detection finds changes made while VSCode was closed
- **Non-git repos**: Works without git (uses file system directly)

## How They Interact

### Scenario 1: VSCode User with Git Repo

**Most common scenario** - User works in VSCode with git repo:

```
User edits file.py in VSCode
  ↓
File Sync System:
  - File watcher records change
  - Auto-sync indexes file.py
  - Marks change as processed
  ↓
Later: User runs 'dolphin index' from CLI
  ↓
Git Diff Model:
  - git diff shows file.py changed since last CLI index
  - RE-INDEXES file.py (safe, deduplication handles it)
  - Updates last successful commit
```

**Result**: File gets indexed twice (once by auto-sync, once by CLI), but deduplication ensures no duplicate chunks.

### Scenario 2: Git Pull Remote Changes

**Remote team member pushes changes**:

```
git pull origin main
  ↓
Option 1 (File Sync):
  - Drift detector runs on startup
  - Compares file snapshots to current state
  - Detects changes, records as pending
  - Auto-sync indexes them
  ↓
Option 2 (Git Diff):
  - Run 'dolphin index'
  - git diff detects remote changes
  - Indexes them in batch
```

**Result**: Both systems can handle this, depending on user workflow.

### Scenario 3: CI/CD Pipeline (No VSCode)

**GitHub Actions, Jenkins, etc.**:

```
on:
  push:
    branches: [main]

run: |
  dolphin index my-repo

Git Diff Model ONLY:
  - No VSCode, no file watcher
  - Uses git diff to detect changes
  - Batch indexes all changes since last run
```

**Result**: Git Diff is the only option here (and the right one).

### Scenario 4: Non-Git Workspace

**User opens a folder without git**:

```
VSCode opens /Users/me/scripts (no .git)
  ↓
File Sync System ONLY:
  - File watcher works fine
  - Records changes to SQLite
  - Auto-sync indexes files
  ↓
Git Diff Model:
  - Would fail (no git repo)
  - Not used in this scenario
```

**Result**: File Sync is the only option (and the right one).

## Design Principles

### 1. Complementary, Not Redundant

Both systems solve different problems:
- **Git Diff**: Batch processing, git-aware, commit-based
- **File Sync**: Real-time, VSCode-aware, file-based

### 2. Safe Overlap

It's **okay** if both systems index the same file:
- Deduplication handles duplicate chunks
- Ensures nothing is missed
- "Index twice, deduplicate once" is safer than "miss a change"

### 3. Each Owns Its Domain

```
Git Diff owns:
- sessions.last_successful_commit
- Batch indexing decisions
- CLI workflows

File Sync owns:
- pending_changes table
- file_snapshots table
- Real-time indexing decisions
- VSCode workflows
```

### 4. No Conflicts

The two systems **do not conflict** because:
- They write to different tables (sessions vs pending_changes)
- They both trigger the same indexing pipeline (same deduplication)
- File snapshots work for both (created by indexing pipeline regardless of trigger)
- Both update the same chunks/vectors (idempotent operations)

## Decision Tree: Which System Applies?

```
Is VSCode open with extension active?
├─ YES: File Sync System (real-time)
│   ├─ File changes detected by watcher
│   ├─ Recorded to pending_changes
│   └─ Auto-sync triggers indexing
│
└─ NO: Git Diff Model (batch)
    ├─ CLI command: dolphin index
    ├─ Uses git diff for incremental
    └─ Updates sessions table

Is it a git repository?
├─ YES: Both systems available
│   └─ Use whichever is active
│
└─ NO: File Sync only
    └─ Git Diff would fail

Running in CI/CD?
└─ YES: Git Diff only (no VSCode)
```

## Implementation Notes

### Git Diff Implementation

```python
# kb/ingest/pipeline.py

# Determine changed files list
if full_reindex or last_success is None:
    changed_files = get_all_tracked_files(root)
else:
    # Incremental: use git diff from last successful commit
    changed_files = git_changed_files_modified_added(root, last_success, commit_sha)
    deleted_files = git_changed_files_deleted(root, last_success, commit_sha)
```

### File Sync Implementation

```typescript
// vscode-extension/src/kb/file-watcher.ts

watcher.onDidChange((uri) => {
  // Record immediately (crash-proof)
  await fetch(`${apiBaseUrl}/v1/repos/${repo}/changes`, {
    method: "POST",
    body: JSON.stringify({
      changes: [{file_path: relativePath, change_type: "modified"}]
    })
  });
});
```

### Shared Indexing Pipeline

Both systems trigger the same `_process_index_task`:

```python
# kb/api/app.py

async def _process_index_task(task_id, repo_name, files):
    # Works the same whether triggered by:
    # - Git Diff (CLI batch)
    # - File Sync (VSCode auto-sync)

    for filepath in files:
        # 1. Capture snapshot
        # 2. Index file
        # 3. Save snapshot
        # 4. Auto-mark pending changes as processed
```

## Migration Path

For users transitioning from CLI-only to VSCode extension:

**Before (Git Diff only):**
```bash
# Manual workflow
git commit -m "changes"
dolphin index my-repo  # Indexes all changes since last run
```

**After (Both systems):**
```
# Automatic workflow (File Sync)
- Edit files in VSCode
- Auto-sync indexes in background
- No manual command needed

# Optional: Still run CLI for full reindex
dolphin index my-repo --full
```

**Migration is seamless** - both systems coexist without conflicts.

## Best Practices

### Use Git Diff When:
- Running batch indexing jobs
- CI/CD pipeline indexing
- Reindexing after git pull (if VSCode wasn't open)
- Full repository reindexing
- Non-VSCode workflows

### Use File Sync When:
- Working in VSCode
- Want real-time auto-sync
- Need crash recovery
- Working in non-git workspace
- Want "code and forget" workflow

### Use Both When:
- You have a git repo and use VSCode
- Most common scenario
- File Sync handles real-time, Git Diff handles batch
- Safe overlap with deduplication

## Frequently Asked Questions

### Q: Will files be indexed twice?

**A:** Sometimes yes, and that's okay!

- Deduplication ensures no duplicate chunks in database
- Better to index twice than miss a change
- Minimal overhead due to content hashing

### Q: Which system should I rely on?

**A:** Depends on your workflow:

- **VSCode user**: File Sync (automatic, real-time)
- **CLI user**: Git Diff (manual, batch)
- **Both**: Use both! They complement each other.

### Q: Do I need git for the file sync system?

**A:** No! File Sync works without git:

- Uses file system watcher directly
- Stores state in SQLite
- Works on any workspace (git or not)

### Q: What if I git pull while VSCode is closed?

**A:** Both systems can handle this:

**Option 1 (File Sync):**
- Open VSCode
- Drift detector runs on startup
- Detects changes, triggers indexing

**Option 2 (Git Diff):**
- Run `dolphin index`
- git diff detects changes
- Batch indexes

### Q: Can I disable one system?

**A:** Yes:

```typescript
// Disable File Sync in VSCode
"dolphin.kb.autoSync.mode": "off"

// Git Diff is always available via CLI
// Just don't run the CLI command if you don't want it
```

## Conclusion

The **Git Diff Model** and **File Sync System** are complementary:

- **Git Diff**: Batch, git-aware, CLI-focused
- **File Sync**: Real-time, VSCode-aware, file-focused

They work together seamlessly with:
- ✅ No conflicts (different tables)
- ✅ Safe overlap (deduplication)
- ✅ Clear domains (batch vs real-time)
- ✅ Shared pipeline (same indexing logic)

Use the right tool for your workflow, or use both!
