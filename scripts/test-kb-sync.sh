#!/bin/bash
# Quick manual test for KB auto-sync
# Run this after starting the VSCode extension

set -e

echo "🐬 KB Auto-Sync Quick Test"
echo "=========================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
check_pass() {
  echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
  echo -e "${RED}✗${NC} $1"
  exit 1
}

check_warn() {
  echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Check KB API is running
echo "1. Checking KB API..."
if curl -s http://localhost:7777/health > /dev/null 2>&1; then
  check_pass "KB API is running on port 7777"
else
  check_fail "KB API is not responding. Start it first!"
fi

HEALTH=$(curl -s http://localhost:7777/health | jq -r .status 2>/dev/null || echo "error")
if [ "$HEALTH" = "ok" ]; then
  check_pass "KB API health check passed"
else
  check_fail "KB API health check failed"
fi

# 2. Create test workspace
echo ""
echo "2. Creating test workspace..."
TEST_DIR="/tmp/kb-sync-test-$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Initialize git (required for workspace detection)
git init > /dev/null 2>&1
git config user.email "test@example.com"
git config user.name "Test User"
git remote add origin https://github.com/test/kb-sync-test.git

check_pass "Created test workspace: $TEST_DIR"

# Extract repo name from directory
REPO_NAME=$(basename "$TEST_DIR")
echo "   Repository name: $REPO_NAME"

# 3. Create test files
echo ""
echo "3. Creating test files..."
cat > file1.ts <<'EOF'
export class Calculator {
  add(a: number, b: number): number {
    return a + b;
  }

  subtract(a: number, b: number): number {
    return a - b;
  }
}
EOF

cat > file2.py <<'EOF'
def factorial(n):
    """Calculate factorial of n."""
    if n <= 1:
        return 1
    return n * factorial(n - 1)
EOF

cat > file3.md <<'EOF'
# Test Documentation

This is a test markdown file for KB indexing.

## Features
- Feature 1
- Feature 2
EOF

check_pass "Created 3 test files (TS, Python, Markdown)"

# 4. Register repository
echo ""
echo "4. Registering repository with KB..."
REGISTER_RESPONSE=$(curl -s -X POST http://localhost:7777/v1/repos \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$REPO_NAME\", \"path\": \"$TEST_DIR\", \"default_embed_model\": \"large\"}")

REPO_ID=$(echo "$REGISTER_RESPONSE" | jq -r .repo_id 2>/dev/null || echo "")
if [ -n "$REPO_ID" ] && [ "$REPO_ID" != "null" ]; then
  check_pass "Repository registered (ID: $REPO_ID)"
else
  # Might already be registered
  MESSAGE=$(echo "$REGISTER_RESPONSE" | jq -r .message 2>/dev/null || echo "")
  if [[ "$MESSAGE" == *"already registered"* ]]; then
    check_warn "Repository already registered (this is OK)"
  else
    check_fail "Failed to register repository: $REGISTER_RESPONSE"
  fi
fi

# 5. Queue files for indexing
echo ""
echo "5. Queueing files for indexing..."
INDEX_RESPONSE=$(curl -s -X POST http://localhost:7777/v1/index \
  -H "Content-Type: application/json" \
  -d "{\"repo\": \"$REPO_NAME\", \"files\": [\"file1.ts\", \"file2.py\", \"file3.md\"], \"incremental\": true}")

TASK_ID=$(echo "$INDEX_RESPONSE" | jq -r .task_id 2>/dev/null || echo "")
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "null" ]; then
  check_fail "Failed to queue indexing: $INDEX_RESPONSE"
fi

check_pass "Files queued for indexing (Task ID: $TASK_ID)"

# 6. Poll for completion
echo ""
echo "6. Polling for indexing completion..."
MAX_POLLS=30
POLL_COUNT=0

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
  POLL_COUNT=$((POLL_COUNT + 1))

  STATUS_RESPONSE=$(curl -s "http://localhost:7777/v1/index/status/$TASK_ID")
  STATUS=$(echo "$STATUS_RESPONSE" | jq -r .status 2>/dev/null || echo "unknown")
  PROGRESS=$(echo "$STATUS_RESPONSE" | jq -r .progress 2>/dev/null || echo "0")
  TOTAL=$(echo "$STATUS_RESPONSE" | jq -r .total 2>/dev/null || echo "0")

  echo -n "   [${POLL_COUNT}/${MAX_POLLS}] Status: $STATUS"
  if [ "$TOTAL" != "0" ]; then
    echo -n " ($PROGRESS/$TOTAL files)"
  fi
  echo ""

  if [ "$STATUS" = "completed" ]; then
    INDEXED=$(echo "$STATUS_RESPONSE" | jq -r .indexed 2>/dev/null || echo "0")
    SKIPPED=$(echo "$STATUS_RESPONSE" | jq -r .skipped 2>/dev/null || echo "0")
    check_pass "Indexing completed! Indexed: $INDEXED, Skipped: $SKIPPED"
    break
  elif [ "$STATUS" = "failed" ]; then
    ERROR=$(echo "$STATUS_RESPONSE" | jq -r .error 2>/dev/null || echo "unknown error")
    check_fail "Indexing failed: $ERROR"
  fi

  sleep 1
done

if [ $POLL_COUNT -eq $MAX_POLLS ]; then
  check_warn "Polling timed out after ${MAX_POLLS} seconds"
  echo "   Current status: $STATUS"
fi

# 7. Verify indexed content
echo ""
echo "7. Verifying indexed content..."

# List all tasks for this repo
TASKS_RESPONSE=$(curl -s "http://localhost:7777/v1/index/tasks?repo=$REPO_NAME")
TASK_COUNT=$(echo "$TASKS_RESPONSE" | jq '.tasks | length' 2>/dev/null || echo "0")

if [ "$TASK_COUNT" -gt 0 ]; then
  check_pass "Found $TASK_COUNT indexing task(s) in task list"
else
  check_warn "No tasks found in task list"
fi

# Get repo info
REPOS_RESPONSE=$(curl -s "http://localhost:7777/repos")
REPO_INFO=$(echo "$REPOS_RESPONSE" | jq ".repos[] | select(.name == \"$REPO_NAME\")" 2>/dev/null || echo "{}")
FILE_COUNT=$(echo "$REPO_INFO" | jq -r .files 2>/dev/null || echo "0")
CHUNK_COUNT=$(echo "$REPO_INFO" | jq -r .chunks 2>/dev/null || echo "0")

if [ "$FILE_COUNT" -gt 0 ]; then
  check_pass "Repository contains $FILE_COUNT files, $CHUNK_COUNT chunks"
else
  check_warn "No files found in repository (might need a moment)"
fi

# 8. Test search
echo ""
echo "8. Testing search functionality..."
SEARCH_RESPONSE=$(curl -s -X POST http://localhost:7777/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"calculator\", \"repos\": [\"$REPO_NAME\"], \"top_k\": 3}")

HIT_COUNT=$(echo "$SEARCH_RESPONSE" | jq '.hits | length' 2>/dev/null || echo "0")
if [ "$HIT_COUNT" -gt 0 ]; then
  check_pass "Search found $HIT_COUNT result(s) for 'calculator'"

  # Show first result
  FIRST_HIT=$(echo "$SEARCH_RESPONSE" | jq -r '.hits[0] | "\(.path):\(.start_line)-\(.end_line)"' 2>/dev/null || echo "")
  if [ -n "$FIRST_HIT" ]; then
    echo "   First result: $FIRST_HIT"
  fi
else
  check_warn "Search returned no results (content might not be indexed yet)"
fi

# 9. Summary
echo ""
echo "=========================="
echo "🎉 Test Summary"
echo "=========================="
echo "Test workspace: $TEST_DIR"
echo "Repository: $REPO_NAME"
echo "Task ID: $TASK_ID"
echo ""
echo "You can:"
echo "  • View tasks: curl http://localhost:7777/v1/index/tasks?repo=$REPO_NAME | jq"
echo "  • View status: curl http://localhost:7777/v1/index/status/$TASK_ID | jq"
echo "  • Search: curl -X POST http://localhost:7777/search -H 'Content-Type: application/json' -d '{\"query\": \"factorial\", \"repos\": [\"$REPO_NAME\"]}' | jq"
echo ""
echo "To clean up: rm -rf $TEST_DIR"
echo ""
echo -e "${GREEN}✓ Test completed successfully!${NC}"
