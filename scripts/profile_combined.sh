#!/bin/zsh
# Combined profiling: index a repository, then profile searches on it
#
# Usage:
#   ./scripts/profile_combined.sh <repo_size> [--keep-repo]
#
# Where repo_size is one of: small (1K files), medium (10K files), large (50K files)
# Use --keep-repo flag to skip cleanup (useful for debugging)

set -e

REPO_SIZE=${1:-small}
KEEP_REPO=false
if [[ "$2" == "--keep-repo" ]]; then
  KEEP_REPO=true
fi

OUTPUT_DIR="profiling_results/combined"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_REPOS_DIR="./test-repos"
REPO_NAME="profile-combined-${REPO_SIZE}"
API_PORT=7777

# Create output directory
mkdir -p "$OUTPUT_DIR"
chmod 755 "$OUTPUT_DIR"

# Determine test repo configuration based on size
case $REPO_SIZE in
  small)
    REPO_PATH="$TEST_REPOS_DIR/combined-small"
    GITHUB_URL="https://github.com/expressjs/express"
    EXPECTED_FILES="~1,000"
    ;;
  medium)
    REPO_PATH="$TEST_REPOS_DIR/combined-medium"
    GITHUB_URL="https://github.com/django/django"
    EXPECTED_FILES="~10,000"
    ;;
  large)
    REPO_PATH="$TEST_REPOS_DIR/combined-large"
    GITHUB_URL="https://github.com/torvalds/linux"
    EXPECTED_FILES="~50,000"
    ;;
  *)
    echo "Error: Invalid repo size. Use: small, medium, or large"
    exit 1
    ;;
esac

echo "========================================="
echo "Combined Profiling (Indexing + Search)"
echo "========================================="
echo "Repository size: $REPO_SIZE"
echo "Expected files: $EXPECTED_FILES"
echo "Output directory: $OUTPUT_DIR"
echo "Repository name: $REPO_NAME"
echo ""

# Check if py-spy is installed
if ! command -v py-spy &> /dev/null; then
  echo "Error: py-spy not found. Install with: pipx install py-spy"
  echo "  or: pip install --user py-spy"
  exit 1
fi

# Cleanup function for error handling
cleanup() {
  local exit_code=$?
  if [ $exit_code -ne 0 ]; then
    echo ""
    echo "========================================="
    echo "Error occurred. Cleaning up..."
    echo "========================================="
  fi
  
  # Stop API server if running
  if [ -n "$API_PID" ]; then
    echo "Stopping KB API server (PID: $API_PID)..."
    kill $API_PID 2>/dev/null || true
    wait $API_PID 2>/dev/null || true
  fi
  
  if [ "$KEEP_REPO" = false ]; then
    echo "Removing repository from Dolphin KB..."
    uv run dolphin kb remove-repo "$REPO_NAME" &>/dev/null || true
    
    echo "Removing test repository directory..."
    rm -rf "$REPO_PATH"
  else
    echo "Keeping repository as requested (--keep-repo flag)"
  fi
  
  exit $exit_code
}

trap cleanup EXIT INT TERM

# ==============================================================================
# PHASE 1: INDEXING PROFILING
# ==============================================================================

echo "========================================="
echo "PHASE 1: Indexing Profiling"
echo "========================================="
echo ""

# Step 1: Clean up any existing test repository
echo "Step 1: Cleaning up existing test repository..."
if [ -d "$REPO_PATH" ]; then
  echo "  Removing existing directory: $REPO_PATH"
  rm -rf "$REPO_PATH"
fi

# Remove from Dolphin KB if registered
echo "  Removing from Dolphin KB (if registered)..."
uv run dolphin kb remove-repo "$REPO_NAME" &>/dev/null || true

# Step 2: Clone the test repository
echo ""
echo "Step 2: Cloning test repository..."
echo "  URL: $GITHUB_URL"
echo "  Path: $REPO_PATH"
mkdir -p "$TEST_REPOS_DIR"

if [ "$REPO_SIZE" = "large" ]; then
  # Use shallow clone for large repos
  echo "  Using shallow clone (--depth 1) for large repository..."
  git clone --depth 1 "$GITHUB_URL" "$REPO_PATH"
else
  git clone "$GITHUB_URL" "$REPO_PATH"
fi

echo "  Clone complete!"

# Step 3: Register with Dolphin KB
echo ""
echo "Step 3: Registering repository with Dolphin KB..."
uv run dolphin kb add-repo "$REPO_NAME" "$REPO_PATH"
echo "  Registration complete!"

# Step 4: Profile indexing
echo ""
echo "Step 4: Profiling indexing..."
INDEX_PROFILE_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.json"
INDEX_FLAMEGRAPH_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.svg"
INDEX_LOG_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.log"

echo "  Profile data: $INDEX_PROFILE_FILE"
echo "  Flame graph: $INDEX_FLAMEGRAPH_FILE"
echo "  Log file: $INDEX_LOG_FILE"
echo ""

INDEX_START_TIME=$(date +%s)

# Run profiling with py-spy
py-spy record \
  --format speedscope \
  --output "$INDEX_PROFILE_FILE" \
  --rate 100 \
  --subprocesses \
  -- uv run dolphin kb index "$REPO_NAME" 2>&1 | tee "$INDEX_LOG_FILE"

INDEX_END_TIME=$(date +%s)
INDEX_DURATION=$((INDEX_END_TIME - INDEX_START_TIME))

# Generate flame graph (reindex for flamegraph)
echo ""
echo "Generating indexing flame graph (reindexing)..."
py-spy record \
  --format flamegraph \
  --output "$INDEX_FLAMEGRAPH_FILE" \
  --rate 100 \
  --subprocesses \
  -- uv run dolphin kb index "$REPO_NAME" --full --force 2>&1 > /dev/null

echo ""
echo "========================================="
echo "Indexing Profiling Complete"
echo "========================================="
echo "Duration: ${INDEX_DURATION}s"
echo "Profile data: $INDEX_PROFILE_FILE"
echo "Flame graph: $INDEX_FLAMEGRAPH_FILE"
echo "Log: $INDEX_LOG_FILE"
echo ""

# Extract indexing metrics from log
if grep -q "files/min" "$INDEX_LOG_FILE"; then
  THROUGHPUT=$(grep -oP "[\d,]+ files/min" "$INDEX_LOG_FILE" | head -1)
  echo "Throughput: $THROUGHPUT"
fi

if grep -q "Chunks indexed" "$INDEX_LOG_FILE"; then
  CHUNKS=$(grep -oP "Chunks indexed: \d+" "$INDEX_LOG_FILE" | head -1)
  echo "$CHUNKS"
fi

# ==============================================================================
# PHASE 2: SEARCH PROFILING
# ==============================================================================

echo ""
echo "========================================="
echo "PHASE 2: Search Profiling"
echo "========================================="
echo ""

# Step 5: Start API server
echo "Step 5: Starting KB API server..."
uv run uvicorn kb.api.app:app --host 127.0.0.1 --port $API_PORT &
API_PID=$!
echo "  API server started (PID: $API_PID)"
echo "  Waiting for server to be ready..."
sleep 10

# Check if server is running
if ! curl -s http://localhost:$API_PORT/health > /dev/null; then
  echo "  Error: API server not responding at http://localhost:$API_PORT"
  exit 1
fi
echo "  API server is ready!"

# Output files for search profiling
SEARCH_PROFILE_FILE="$OUTPUT_DIR/search_${REPO_SIZE}_${TIMESTAMP}.json"
SEARCH_FLAMEGRAPH_FILE="$OUTPUT_DIR/search_${REPO_SIZE}_${TIMESTAMP}.svg"
SEARCH_LOG_FILE="$OUTPUT_DIR/search_${REPO_SIZE}_${TIMESTAMP}.log"

echo ""
echo "Step 6: Profiling search queries..."
echo "  Profile data: $SEARCH_PROFILE_FILE"
echo "  Flame graph: $SEARCH_FLAMEGRAPH_FILE"
echo "  Log file: $SEARCH_LOG_FILE"
echo ""

# Test queries appropriate for each repo type
case $REPO_SIZE in
  small)
    QUERIES=(
      "express router middleware"
      "request response handling"
      "HTTP methods GET POST"
      "error handling middleware"
      "application settings"
    )
    ;;
  medium)
    QUERIES=(
      "django ORM models"
      "database migrations"
      "view decorators"
      "template rendering"
      "admin interface"
    )
    ;;
  large)
    QUERIES=(
      "kernel memory management"
      "file system operations"
      "network stack TCP"
      "device drivers"
      "system calls"
    )
    ;;
esac

echo "Running search queries with profiling..."
echo "Queries to execute: ${#QUERIES[@]}"
echo ""

# Profile the API server while making requests
# Start py-spy in the background
py-spy record \
  --pid $API_PID \
  --format speedscope \
  --output "$SEARCH_PROFILE_FILE" \
  --rate 100 \
  --duration 60 &
PYSPY_PID=$!

SEARCH_START_TIME=$(date +%s)

# Run searches
for query in "${QUERIES[@]}"; do
  echo "Searching: $query"
  START=$(uv run python -c 'import time; print(int(time.time() * 1000))')
  
  curl -s -X POST http://localhost:$API_PORT/search \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$query\", \"top_k\": 10}" >> "$SEARCH_LOG_FILE" 2>&1
  
  END=$(uv run python -c 'import time; print(int(time.time() * 1000))')
  LATENCY=$((END - START))
  echo "Latency: ${LATENCY}ms" | tee -a "$SEARCH_LOG_FILE"
  echo ""
done

SEARCH_END_TIME=$(date +%s)
SEARCH_DURATION=$((SEARCH_END_TIME - SEARCH_START_TIME))

# Wait for py-spy to finish
wait $PYSPY_PID || true

# Generate flamegraph with a second profiling run
echo "Generating search flame graph..."
py-spy record \
  --pid $API_PID \
  --format flamegraph \
  --output "$SEARCH_FLAMEGRAPH_FILE" \
  --rate 100 \
  --duration 30 &
PYSPY_FLAME_PID=$!

# Run searches again for flamegraph
for query in "${QUERIES[@]}"; do
  curl -s -X POST http://localhost:$API_PORT/search \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$query\", \"top_k\": 10}" > /dev/null 2>&1
done

wait $PYSPY_FLAME_PID || true

echo ""
echo "========================================="
echo "Search Profiling Complete"
echo "========================================="
echo "Duration: ${SEARCH_DURATION}s"
echo "Profile data: $SEARCH_PROFILE_FILE"
echo "Flame graph: $SEARCH_FLAMEGRAPH_FILE"
echo "Log: $SEARCH_LOG_FILE"
echo ""

# Calculate search metrics
if [ -f "$SEARCH_LOG_FILE" ] && grep -q "Latency:" "$SEARCH_LOG_FILE"; then
  AVG_LATENCY=$(grep "Latency:" "$SEARCH_LOG_FILE" | awk '{sum+=$2; count++} END {print sum/count}')
  echo "Average search latency: ${AVG_LATENCY}ms"
  
  # Calculate p95
  P95_LATENCY=$(grep "Latency:" "$SEARCH_LOG_FILE" | awk '{print $2}' | sort -n | awk 'BEGIN{c=0} {latencies[c++]=$1} END{print latencies[int(c*0.95)]}')
  echo "p95 search latency: ${P95_LATENCY}ms"
fi

# ==============================================================================
# SUMMARY
# ==============================================================================

echo ""
echo "========================================="
echo "Combined Profiling Summary"
echo "========================================="
echo ""
echo "Repository: $REPO_SIZE ($EXPECTED_FILES files)"
echo "Repository name: $REPO_NAME"
echo ""
echo "INDEXING:"
echo "  Duration: ${INDEX_DURATION}s"
echo "  Profile: $INDEX_PROFILE_FILE"
echo "  Flamegraph: $INDEX_FLAMEGRAPH_FILE"
echo "  Log: $INDEX_LOG_FILE"
echo ""
echo "SEARCH:"
echo "  Duration: ${SEARCH_DURATION}s"
echo "  Queries: ${#QUERIES[@]}"
echo "  Profile: $SEARCH_PROFILE_FILE"
echo "  Flamegraph: $SEARCH_FLAMEGRAPH_FILE"
echo "  Log: $SEARCH_LOG_FILE"
echo ""
echo "View flame graphs at: https://speedscope.app"
echo "Upload both .json files for comparison"
echo ""

# Cleanup (handled by trap)
if [ "$KEEP_REPO" = false ]; then
  echo "Cleaning up..."
  echo "  (Repository and API server will be cleaned up by trap)"
else
  echo "Keeping repository as requested (--keep-repo flag)"
  echo "  Repository: $REPO_PATH"
  echo "  Dolphin KB name: $REPO_NAME"
  echo "  API server PID: $API_PID"
  echo "  To manually clean up later:"
  echo "    kill $API_PID"
  echo "    uv run dolphin kb remove-repo $REPO_NAME"
  echo "    rm -rf $REPO_PATH"
fi