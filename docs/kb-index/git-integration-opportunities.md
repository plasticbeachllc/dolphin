# Git Integration Opportunities for KB Sync

This document outlines potential enhancements to the KB sync system through deeper git integration.

## Current Git Integration

The KB sync system currently uses git for:

1. **Workspace Name Detection** (`agent-core/src/main.ts:180-203`)
   - Extracts repository name from git remote URL
   - Falls back to directory name if not a git repo
   - Used for KB repository registration

2. **Commit Provenance** (`kb/api/app.py:489-502`)
   - Captures commit SHA and branch name during indexing
   - Stored with each indexed chunk for traceability
   - Enables "what commit was this code from?" queries

## Future Enhancement Opportunities

### 1. Index on Git Events

**Opportunity**: Automatically trigger indexing when git operations complete.

**Implementation**:
- Use git hooks (post-commit, post-merge, post-checkout)
- Place hook scripts in `.git/hooks/` or use core.hooksPath
- Call KB index API when changes are committed

**Example Hook** (`.git/hooks/post-commit`):
```bash
#!/bin/bash
# Trigger KB incremental index after commit

# Get changed files from last commit
FILES=$(git diff --name-only HEAD~1 HEAD)

# Call KB API
curl -X POST http://127.0.0.1:7777/v1/index \
  -H "Content-Type: application/json" \
  -d "{
    \"repo\": \"$(basename $(git rev-parse --show-toplevel))\",
    \"files\": [$(echo "$FILES" | sed 's/^/\"/' | sed 's/$/\"/' | paste -sd,)],
    \"incremental\": true
  }"
```

**Benefits**:
- Ensures KB is updated whenever code is committed
- Catches changes made outside VSCode (CLI git operations)
- Works across different editors/IDEs

**Considerations**:
- Hook must be fast to avoid slowing down git operations
- Should run in background (async)
- Need user opt-in (don't automatically modify .git/hooks)

---

### 2. Branch-Aware Indexing

**Opportunity**: Maintain separate indexes per branch or track branch context.

**Use Cases**:
- User switches from `main` to `feature/new-api` → KB shows code from feature branch
- User asks "what changed in this branch?" → KB can diff against main
- Multi-branch development: keep context relevant to current branch

**Implementation Options**:

**Option A: Multiple Repo Registrations (Simple)**
```typescript
// Register each branch as a separate "repo"
await registerRepo({
  name: `dolphin-main`,
  path: workspaceRoot,
});

await registerRepo({
  name: `dolphin-feature-new-api`,
  path: workspaceRoot,
});

// On branch switch, update active repo name
const currentBranch = await getCurrentGitBranch();
setActiveRepo(`${repoName}-${currentBranch}`);
```

**Option B: Branch Metadata in Chunks (Complex)**
- Store branch name in chunk metadata (already done!)
- Filter search results by current branch
- Show cross-branch results with lower priority

**Benefits**:
- Better context relevance during feature development
- Enables "show me what changed in this PR" queries
- Avoids confusion from stale code in inactive branches

**Considerations**:
- Disk usage increases (multiple indexes)
- Need branch switch detection in VSCode extension
- How to handle merged/deleted branches?

---

### 3. Diff-Based Incremental Indexing

**Opportunity**: Leverage git diff for smarter change detection.

**Current**: File watcher triggers on any file save
**Enhanced**: Compare git diff to determine actual changes

**Implementation**:
```typescript
async function getChangedLineRanges(filepath: string): Promise<LineRange[]> {
  // Get diff for this file
  const diff = await execAsync(`git diff ${filepath}`);

  // Parse diff hunks to extract changed line ranges
  // Example: @@ -10,5 +10,8 @@ means lines 10-15 in old, 10-18 in new
  const hunks = parseDiffHunks(diff);

  return hunks.map(h => ({ start: h.newStart, end: h.newEnd }));
}

// Only re-index chunks that overlap with changed lines
async function smartReindex(filepath: string) {
  const changedRanges = await getChangedLineRanges(filepath);
  const existingChunks = await getChunksForFile(filepath);

  // Filter to chunks that overlap changed ranges
  const chunksToReindex = existingChunks.filter(chunk =>
    changedRanges.some(range => rangesOverlap(chunk, range))
  );

  await reindexChunks(chunksToReindex);
}
```

**Benefits**:
- Reduces embedding API calls (only changed chunks)
- Faster incremental updates
- More precise deduplication

**Considerations**:
- Complex parsing of git diff format
- Doesn't catch changes in comments that affect semantics
- May miss cross-chunk dependencies

---

### 4. Commit History Context

**Opportunity**: Enrich AI responses with commit history.

**Use Cases**:
- "Why was this function added?" → Show commit message
- "Who worked on this feature?" → Show commit authors
- "What was the purpose of this code?" → Extract from commit history

**Implementation**:
```typescript
// Store commit metadata with each chunk
interface ChunkMetadata {
  // ... existing fields
  lastModifiedCommit: string;
  lastModifiedAuthor: string;
  lastModifiedDate: Date;
  commitMessage: string;
}

// Use git blame to enrich chunks
async function enrichWithGitBlame(chunk: Chunk): Promise<Chunk> {
  const blame = await execAsync(
    `git blame -L ${chunk.startLine},${chunk.endLine} ${chunk.filepath}`
  );

  const parsed = parseGitBlame(blame);

  return {
    ...chunk,
    lastModifiedCommit: parsed.commit,
    lastModifiedAuthor: parsed.author,
    lastModifiedDate: parsed.date,
    commitMessage: await getCommitMessage(parsed.commit),
  };
}
```

**Benefits**:
- Richer context for AI responses
- Helps understand "why" not just "what"
- Enables temporal queries ("show me recent changes")

**Considerations**:
- git blame is slow for large files
- Increases storage requirements
- Need caching strategy

---

### 5. Pre-Commit Index Validation

**Opportunity**: Ensure code is indexed before allowing commit.

**Use Case**: Enforce that all committed code is searchable in KB.

**Implementation** (git pre-commit hook):
```bash
#!/bin/bash
# Ensure all staged files are indexed before commit

STAGED_FILES=$(git diff --cached --name-only)

for FILE in $STAGED_FILES; do
  # Check if file is indexed
  INDEXED=$(curl -s "http://127.0.0.1:7777/v1/check_indexed?file=$FILE")

  if [ "$INDEXED" != "true" ]; then
    echo "Error: $FILE not indexed in KB. Run 'dolphin index' first."
    exit 1
  fi
done
```

**Benefits**:
- Guarantees KB completeness
- Enforces indexing discipline
- Prevents "stale KB" issues

**Considerations**:
- Could slow down commits significantly
- May be too strict for rapid prototyping
- Need opt-out mechanism

---

### 6. Pull Request Integration

**Opportunity**: Index PR diffs for review assistance.

**Use Case**: "Summarize changes in PR #123"

**Implementation**:
```typescript
async function indexPRDiff(prNumber: number) {
  // Fetch PR diff from GitHub API
  const diff = await fetchPRDiff(prNumber);

  // Parse changed files and lines
  const changes = parsePRDiff(diff);

  // Create temporary index for PR context
  for (const change of changes) {
    await indexFileWithContext(change.filepath, {
      context: "pr",
      prNumber,
      diffType: change.type, // added/modified/deleted
      author: change.author,
      reviewers: change.reviewers,
    });
  }
}

// AI can now query: "what does PR #123 change in auth.ts?"
```

**Benefits**:
- Enables AI-assisted code review
- Helps onboard reviewers to large PRs
- Can generate review summaries

**Considerations**:
- Requires GitHub API integration
- Need authentication tokens
- How to clean up PR indexes after merge?

---

### 7. Stash-Aware Indexing

**Opportunity**: Index stashed changes for later retrieval.

**Use Case**: User stashes WIP code → can still ask AI about it

**Implementation**:
```typescript
// Index stashed changes separately
async function indexGitStash() {
  const stashes = await listGitStashes();

  for (const stash of stashes) {
    const diff = await getStashDiff(stash.id);
    await indexDiff(diff, {
      context: "stash",
      stashId: stash.id,
      message: stash.message,
    });
  }
}
```

**Benefits**:
- No loss of context when stashing
- Can compare stash with current branch
- Helps recover "what was I working on?"

---

## Implementation Priority

**High Priority** (Immediate Value):
1. ✅ Workspace name from git (DONE)
2. ✅ Commit provenance tracking (DONE)
3. 🔄 Index on git hooks (post-commit, post-merge)

**Medium Priority** (Next Quarter):
4. Branch-aware indexing (Option A: multiple repos)
5. Diff-based incremental indexing

**Low Priority** (Future):
6. Commit history enrichment
7. Pre-commit validation
8. PR integration
9. Stash indexing

---

## Configuration

All git integration features should be configurable:

```json
{
  "dolphin.git.enabled": true,
  "dolphin.git.indexOnCommit": true,
  "dolphin.git.indexOnMerge": true,
  "dolphin.git.branchAwareIndexing": false,
  "dolphin.git.enrichWithBlame": false,
  "dolphin.git.validateBeforeCommit": false
}
```

---

## Resources

- Git Hooks Documentation: https://git-scm.com/docs/githooks
- Git Diff Format: https://git-scm.com/docs/diff-format
- GitHub REST API: https://docs.github.com/en/rest
- VSCode Git Extension API: https://code.visualstudio.com/api/extension-guides/scm-provider
