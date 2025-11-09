# KB Auto-Sync Testing Plan

Comprehensive testing strategy for the Knowledge Base auto-sync system.

---

## Test Levels

### 1. Unit Tests (Individual Components)
### 2. Integration Tests (Cross-Component)
### 3. End-to-End Tests (Full System)
### 4. Performance Tests
### 5. Manual Testing Procedures

---

## 1. Unit Tests

### KB API Tests (`kb/api/`)

**Test: task_queue.py**

```python
# tests/api/test_task_queue.py
import pytest
from kb.api.task_queue import TaskQueue, TaskStatus

def test_create_task():
    queue = TaskQueue()
    task = queue.create_task("test-repo", ["file1.py", "file2.py"])

    assert task.repo == "test-repo"
    assert len(task.files) == 2
    assert task.status == TaskStatus.QUEUED
    assert task.total == 2
    assert task.progress == 0

@pytest.mark.asyncio
async def test_update_task_progress():
    queue = TaskQueue()
    task = queue.create_task("test-repo", ["file1.py"])

    await queue.update_task(task.task_id, status=TaskStatus.PROCESSING, progress=1)

    updated = queue.get_task(task.task_id)
    assert updated.status == TaskStatus.PROCESSING
    assert updated.progress == 1
    assert updated.started_at is not None

@pytest.mark.asyncio
async def test_task_cleanup():
    queue = TaskQueue()
    task = queue.create_task("test-repo", ["file1.py"])

    # Complete task
    await queue.update_task(task.task_id, status=TaskStatus.COMPLETED)

    # Cleanup should remove old completed tasks
    removed = await queue.cleanup_old_tasks(max_age_seconds=0)
    assert removed == 1
    assert queue.get_task(task.task_id) is None
```

**Test: app.py endpoints**

```python
# tests/api/test_endpoints.py
import pytest
from fastapi.testclient import TestClient
from kb.api.app import app

client = TestClient(app)

def test_register_repo():
    response = client.post("/v1/repos", json={
        "name": "test-repo",
        "path": "/tmp/test-repo",
        "default_embed_model": "large"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-repo"
    assert "repo_id" in data

def test_index_files_async():
    # Register repo first
    client.post("/v1/repos", json={
        "name": "test-repo",
        "path": "/tmp/test-repo"
    })

    # Queue indexing
    response = client.post("/v1/index", json={
        "repo": "test-repo",
        "files": ["test.py"],
        "incremental": True
    })

    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"

    # Check status
    task_id = data["task_id"]
    status_response = client.get(f"/v1/index/status/{task_id}")
    assert status_response.status_code == 200

def test_list_tasks():
    response = client.get("/v1/index/tasks")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert isinstance(data["tasks"], list)
```

### Agent Core Tests (`agent-core/src/kb/`)

**Test: index-queue.ts**

```typescript
// agent-core/src/kb/__tests__/index-queue.test.ts
import { IndexQueue } from '../index-queue';
import fetchMock from 'jest-fetch-mock';

fetchMock.enableMocks();

describe('IndexQueue', () => {
  beforeEach(() => {
    fetchMock.resetMocks();
  });

  it('should queue files and return task ID', async () => {
    fetchMock.mockResponseOnce(JSON.stringify({
      task_id: 'test-task-123',
      status: 'queued',
      message: 'Queued 2 files'
    }));

    const queue = new IndexQueue('http://localhost:7777', 'test-repo');
    const taskId = await queue.enqueueBatch(['file1.ts', 'file2.ts']);

    expect(taskId).toBe('test-task-123');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:7777/v1/index',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          repo: 'test-repo',
          files: ['file1.ts', 'file2.ts'],
          incremental: true
        })
      })
    );
  });

  it('should poll for task status', async () => {
    jest.useFakeTimers();

    // Initial queue response
    fetchMock.mockResponseOnce(JSON.stringify({
      task_id: 'task-123',
      status: 'queued'
    }));

    const queue = new IndexQueue('http://localhost:7777', 'test-repo');
    const progressSpy = jest.fn();
    queue.on('progress', progressSpy);

    await queue.enqueueBatch(['file1.ts']);

    // Mock status polling responses
    fetchMock.mockResponseOnce(JSON.stringify({
      task_id: 'task-123',
      status: 'processing',
      progress: 1,
      total: 1,
      indexed: 0,
      skipped: 0
    }));

    // Advance timers to trigger poll
    jest.advanceTimersByTime(2000);
    await Promise.resolve(); // Flush promises

    expect(progressSpy).toHaveBeenCalledWith(1);

    jest.useRealTimers();
  });

  it('should emit complete event when task finishes', async () => {
    jest.useFakeTimers();

    fetchMock.mockResponseOnce(JSON.stringify({
      task_id: 'task-123',
      status: 'queued'
    }));

    const queue = new IndexQueue('http://localhost:7777', 'test-repo');
    const completeSpy = jest.fn();
    queue.on('complete', completeSpy);

    await queue.enqueueBatch(['file1.ts']);

    // Mock completed status
    fetchMock.mockResponseOnce(JSON.stringify({
      task_id: 'task-123',
      status: 'completed',
      progress: 1,
      total: 1,
      indexed: 5,
      skipped: 2
    }));

    jest.advanceTimersByTime(2000);
    await Promise.resolve();

    expect(completeSpy).toHaveBeenCalled();

    jest.useRealTimers();
  });
});
```

### VSCode Extension Tests (`vscode-extension/src/kb/`)

**Test: file-watcher.ts**

```typescript
// vscode-extension/src/kb/__tests__/file-watcher.test.ts
import * as vscode from 'vscode';
import { FileWatcher } from '../file-watcher';

jest.mock('vscode');

describe('FileWatcher', () => {
  it('should debounce file changes', async () => {
    jest.useFakeTimers();

    const onBatch = jest.fn();
    const watcher = new FileWatcher(
      { debounceMs: 2000, batchIntervalMs: 5000, excludePatterns: [] },
      onBatch
    );

    // Simulate rapid file changes
    const uri = vscode.Uri.file('/test/file.ts');
    watcher['handleChange'](uri, 'modified');
    watcher['handleChange'](uri, 'modified');
    watcher['handleChange'](uri, 'modified');

    // Fast forward past debounce time
    jest.advanceTimersByTime(2000);

    // Should only have 1 pending change (debounced)
    expect(watcher['pendingChanges'].size).toBe(1);

    jest.useRealTimers();
  });

  it('should batch changes at intervals', async () => {
    jest.useFakeTimers();

    const onBatch = jest.fn();
    const watcher = new FileWatcher(
      { debounceMs: 100, batchIntervalMs: 1000, excludePatterns: [] },
      onBatch
    );

    watcher['startBatchProcessor']();

    // Add changes
    watcher['pendingChanges'].set('/file1.ts', {
      uri: vscode.Uri.file('/file1.ts'),
      type: 'modified',
      timestamp: Date.now()
    });

    // Advance to trigger batch
    jest.advanceTimersByTime(1000);
    await Promise.resolve();

    expect(onBatch).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ type: 'modified' })
      ])
    );

    jest.useRealTimers();
  });

  it('should respect exclude patterns', () => {
    const watcher = new FileWatcher(
      {
        debounceMs: 2000,
        batchIntervalMs: 5000,
        excludePatterns: ['**/node_modules/**', '**/dist/**']
      },
      jest.fn()
    );

    expect(watcher['shouldIgnore'](vscode.Uri.file('/project/node_modules/lib.js'))).toBe(true);
    expect(watcher['shouldIgnore'](vscode.Uri.file('/project/dist/bundle.js'))).toBe(true);
    expect(watcher['shouldIgnore'](vscode.Uri.file('/project/src/app.ts'))).toBe(false);
  });
});
```

---

## 2. Integration Tests

### KB API + Task Queue Integration

```python
# tests/integration/test_indexing_flow.py
import pytest
import asyncio
from fastapi.testclient import TestClient
from kb.api.app import app

@pytest.mark.asyncio
async def test_full_indexing_flow():
    """Test complete indexing flow from request to completion."""
    client = TestClient(app)

    # 1. Register repo
    repo_response = client.post("/v1/repos", json={
        "name": "integration-test",
        "path": "/tmp/integration-test"
    })
    assert repo_response.status_code == 200

    # 2. Queue indexing
    index_response = client.post("/v1/index", json={
        "repo": "integration-test",
        "files": ["test1.py", "test2.py"]
    })
    assert index_response.status_code == 200
    task_id = index_response.json()["task_id"]

    # 3. Poll for completion (with timeout)
    max_polls = 30
    for _ in range(max_polls):
        status_response = client.get(f"/v1/index/status/{task_id}")
        status = status_response.json()

        if status["status"] in ["completed", "failed"]:
            break

        await asyncio.sleep(1)

    # 4. Verify completion
    assert status["status"] == "completed"
    assert status["total"] == 2
```

### Agent Core + KB API Integration

```typescript
// agent-core/src/__tests__/integration/kb-integration.test.ts
import { IndexQueue } from '../../kb/index-queue';
import { startMockKBServer } from '../helpers/mock-kb-server';

describe('Agent Core + KB API Integration', () => {
  let mockServer: any;

  beforeAll(async () => {
    mockServer = await startMockKBServer(7777);
  });

  afterAll(async () => {
    await mockServer.close();
  });

  it('should successfully queue and track indexing', async () => {
    const queue = new IndexQueue('http://localhost:7777', 'test-repo');

    const completedPromise = new Promise((resolve) => {
      queue.on('complete', resolve);
    });

    await queue.enqueueBatch(['file1.ts', 'file2.ts']);

    // Wait for completion (with timeout)
    await Promise.race([
      completedPromise,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), 10000)
      )
    ]);

    expect(queue.getQueueDepth()).toBe(0);
  });
});
```

---

## 3. End-to-End Tests

### Full System Flow Test

```typescript
// tests/e2e/kb-autosync.test.ts
import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { expect } from 'chai';

describe('KB Auto-Sync E2E', () => {
  let testWorkspace: string;

  before(async () => {
    // Create test workspace
    testWorkspace = path.join(__dirname, '../fixtures/test-workspace');
    fs.mkdirSync(testWorkspace, { recursive: true });

    // Initialize git repo
    execSync('git init', { cwd: testWorkspace });
    execSync('git config user.email "test@test.com"', { cwd: testWorkspace });
    execSync('git config user.name "Test User"', { cwd: testWorkspace });
  });

  it('should auto-index file when saved', async function() {
    this.timeout(30000); // 30 second timeout

    // 1. Open workspace in VSCode
    await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(testWorkspace));

    // 2. Wait for extension activation
    await waitFor(() => vscode.extensions.getExtension('pb.dolphin')?.isActive, 5000);

    // 3. Create and save a new file
    const testFile = path.join(testWorkspace, 'test.ts');
    const content = 'export function hello() { return "world"; }';
    fs.writeFileSync(testFile, content);

    const document = await vscode.workspace.openTextDocument(testFile);
    await vscode.window.showTextDocument(document);
    await document.save();

    // 4. Wait for debounce + batch interval
    await sleep(7000); // 2s debounce + 5s batch

    // 5. Verify file was indexed in KB
    const kbStatus = await fetch('http://localhost:7777/v1/index/tasks?repo=test-workspace');
    const tasks = await kbStatus.json();

    expect(tasks.tasks).to.have.length.greaterThan(0);
    const latestTask = tasks.tasks[0];
    expect(latestTask.status).to.equal('completed');
  });

  it('should update status bar during indexing', async function() {
    this.timeout(20000);

    // Create multiple files to trigger indexing
    for (let i = 0; i < 5; i++) {
      const file = path.join(testWorkspace, `file${i}.ts`);
      fs.writeFileSync(file, `export const x${i} = ${i};`);
    }

    // Trigger indexing
    await vscode.commands.executeCommand('workbench.action.files.saveAll');

    // Wait for status bar to show indexing
    await waitFor(() => {
      // Check status bar text (would need to expose this in extension)
      return true; // Placeholder - need actual status bar check
    }, 10000);
  });
});

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitFor(condition: () => boolean, timeout: number): Promise<void> {
  const start = Date.now();
  while (!condition()) {
    if (Date.now() - start > timeout) {
      throw new Error('Timeout waiting for condition');
    }
    await sleep(100);
  }
}
```

---

## 4. Performance Tests

### Load Testing

```python
# tests/performance/test_load.py
import pytest
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from kb.api.app import app

def test_concurrent_indexing():
    """Test KB API can handle concurrent indexing requests."""
    client = TestClient(app)

    # Register repo
    client.post("/v1/repos", json={
        "name": "perf-test",
        "path": "/tmp/perf-test"
    })

    # Submit 50 concurrent indexing requests
    def submit_index_request(i):
        response = client.post("/v1/index", json={
            "repo": "perf-test",
            "files": [f"file{i}.py"]
        })
        return response.status_code

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(submit_index_request, i) for i in range(50)]
        results = [f.result() for f in futures]

    # All requests should succeed
    assert all(status == 200 for status in results)

def test_large_file_batch():
    """Test indexing large batches of files."""
    client = TestClient(app)

    client.post("/v1/repos", json={
        "name": "large-batch",
        "path": "/tmp/large-batch"
    })

    # Submit 500 files at once
    files = [f"file{i}.py" for i in range(500)]

    import time
    start = time.time()

    response = client.post("/v1/index", json={
        "repo": "large-batch",
        "files": files
    })

    elapsed = time.time() - start

    assert response.status_code == 200
    assert elapsed < 1.0  # Should return immediately (async)
```

### Memory Leak Testing

```typescript
// tests/performance/memory-leak.test.ts
import { IndexQueue } from '../../agent-core/src/kb/index-queue';

describe('Memory Leak Tests', () => {
  it('should not leak memory with repeated operations', async () => {
    const queue = new IndexQueue('http://localhost:7777', 'test-repo');

    const initialMemory = process.memoryUsage().heapUsed;

    // Perform 1000 queue operations
    for (let i = 0; i < 1000; i++) {
      await queue.enqueueBatch([`file${i}.ts`]);

      // Simulate completion
      queue['activeTasks'].clear();
    }

    // Force garbage collection
    if (global.gc) {
      global.gc();
    }

    const finalMemory = process.memoryUsage().heapUsed;
    const memoryIncrease = finalMemory - initialMemory;

    // Memory increase should be reasonable (<10MB)
    expect(memoryIncrease).toBeLessThan(10 * 1024 * 1024);
  });
});
```

---

## 5. Manual Testing Procedures

### Test Checklist

#### ✅ Basic Functionality
- [ ] Extension activates without errors
- [ ] Status bar shows "KB Ready" on startup
- [ ] File watcher starts successfully

#### ✅ File Change Detection
- [ ] Save a TypeScript file → sees change in logs
- [ ] Save a Python file → sees change in logs
- [ ] Save a Markdown file → sees change in logs
- [ ] Rapid saves (10x within 1s) → debounced to single batch
- [ ] Changes in `node_modules/` → ignored
- [ ] Changes in `.git/` → ignored

#### ✅ Indexing Flow
- [ ] File changes → queued after 2s debounce
- [ ] Batch sent after 5s interval
- [ ] Status bar updates to "$(sync~spin) Indexing"
- [ ] Status bar returns to "$(database) KB Ready" when done
- [ ] Output channel shows progress logs

#### ✅ KB API
- [ ] `GET /health` → returns `{"status": "ok"}`
- [ ] `POST /v1/repos` → registers workspace
- [ ] `POST /v1/index` → returns task_id immediately
- [ ] `GET /v1/index/status/{task_id}` → shows progress
- [ ] `GET /v1/index/tasks` → lists all tasks

#### ✅ Error Handling
- [ ] KB API down → error logged, extension continues
- [ ] Invalid file path → skipped gracefully
- [ ] Permission denied → error logged, continues
- [ ] Network timeout → retries or fails gracefully

#### ✅ Commands
- [ ] "Dolphin: Show KB Status" → shows modal with status
- [ ] "Dolphin: Restart Knowledge Base" → shows message

### Manual Test Script

```bash
#!/bin/bash
# Manual testing script

set -e

echo "=== KB Auto-Sync Manual Test ==="

# 1. Check KB API is running
echo "1. Testing KB API..."
curl -s http://localhost:7777/health | jq .

# 2. Create test workspace
TEST_DIR="/tmp/kb-test-$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# 3. Initialize git
git init
git config user.email "test@test.com"
git config user.name "Test"
git remote add origin https://github.com/test/test.git

# 4. Create test files
echo "export function test1() {}" > file1.ts
echo "export function test2() {}" > file2.ts
echo "def hello(): pass" > file3.py

# 5. Register repo
REPO_NAME=$(basename "$TEST_DIR")
curl -X POST http://localhost:7777/v1/repos \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$REPO_NAME\", \"path\": \"$TEST_DIR\"}"

echo ""

# 6. Index files
TASK_ID=$(curl -X POST http://localhost:7777/v1/index \
  -H "Content-Type: application/json" \
  -d "{\"repo\": \"$REPO_NAME\", \"files\": [\"file1.ts\", \"file2.ts\", \"file3.py\"]}" \
  | jq -r .task_id)

echo "Created task: $TASK_ID"

# 7. Poll for completion
echo "Polling for completion..."
for i in {1..30}; do
  STATUS=$(curl -s "http://localhost:7777/v1/index/status/$TASK_ID" | jq -r .status)
  echo "  [$i] Status: $STATUS"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi

  sleep 1
done

# 8. Get final result
echo ""
echo "Final result:"
curl -s "http://localhost:7777/v1/index/status/$TASK_ID" | jq .

# 9. List all tasks
echo ""
echo "All tasks:"
curl -s "http://localhost:7777/v1/index/tasks?repo=$REPO_NAME" | jq .

echo ""
echo "=== Test Complete ==="
```

### Performance Benchmarking

```bash
#!/bin/bash
# Benchmark indexing performance

REPO="benchmark-$(date +%s)"
TEST_DIR="/tmp/$REPO"

# Create 100 test files
mkdir -p "$TEST_DIR"
for i in {1..100}; do
  cat > "$TEST_DIR/file$i.ts" <<EOF
export class Test$i {
  private value: number = $i;

  getValue(): number {
    return this.value;
  }

  setValue(v: number): void {
    this.value = v;
  }
}
EOF
done

# Register repo
curl -X POST http://localhost:7777/v1/repos \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$REPO\", \"path\": \"$TEST_DIR\"}"

# Benchmark indexing
FILES=$(for i in {1..100}; do echo "file$i.ts"; done | jq -R . | jq -s .)

echo "Starting benchmark..."
START=$(date +%s%N)

TASK_ID=$(curl -X POST http://localhost:7777/v1/index \
  -H "Content-Type: application/json" \
  -d "{\"repo\": \"$REPO\", \"files\": $FILES}" \
  | jq -r .task_id)

# Wait for completion
while true; do
  STATUS=$(curl -s "http://localhost:7777/v1/index/status/$TASK_ID" | jq -r .status)
  if [ "$STATUS" = "completed" ]; then
    break
  fi
  sleep 0.5
done

END=$(date +%s%N)
ELAPSED=$(( (END - START) / 1000000 )) # Convert to ms

echo "Indexed 100 files in ${ELAPSED}ms"
echo "Average: $((ELAPSED / 100))ms per file"
```

---

## Test Execution Order

1. **Unit Tests First** - Verify individual components work
2. **Integration Tests** - Verify components work together
3. **E2E Tests** - Verify full system works
4. **Performance Tests** - Verify system scales
5. **Manual Testing** - Verify UX and edge cases

## CI/CD Integration

```yaml
# .github/workflows/test-kb-sync.yml
name: KB Auto-Sync Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run Python unit tests
        run: pytest tests/api/

      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install Bun
        run: curl -fsSL https://bun.sh/install | bash

      - name: Run TypeScript unit tests
        run: |
          cd agent-core
          bun test

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: pytest tests/integration/

  e2e-tests:
    runs-on: ubuntu-latest
    needs: integration-tests
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E tests
        run: npm run test:e2e
```

---

## Success Criteria

### Must Pass
- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ Manual test checklist 100% complete
- ✅ No memory leaks detected
- ✅ Can handle 100+ file changes without errors

### Performance Targets
- ⚡ API returns task_id in <100ms
- ⚡ 10 files indexed in <5 seconds
- ⚡ 100 files indexed in <30 seconds
- ⚡ Status bar updates within 2 seconds of completion

### Quality Targets
- 🎯 >80% test coverage on new code
- 🎯 Zero errors in manual testing
- 🎯 Works across Mac/Linux/Windows
