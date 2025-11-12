#!/bin/zsh
# Profile the KB search queries with py-spy
#
# Usage:
#   ./scripts/profile_search.sh <query_type> [--keep-repo]
#
# Where query_type is one of: cold, warm, concurrent
# Use --keep-repo flag to skip cleanup (useful for debugging)

set -e

QUERY_TYPE=${1:-cold}
KEEP_REPO=false
if [[ "$2" == "--keep-repo" ]]; then
  KEEP_REPO=true
fi

OUTPUT_DIR="profiling_results/search"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_REPOS_DIR="./test-repos"
REPO_NAME="profile-search-test"
REPO_PATH="$TEST_REPOS_DIR/search-test"
GITHUB_URL="https://github.com/expressjs/express"
API_PORT=7777

# Create output directory with proper permissions
mkdir -p "$OUTPUT_DIR"
chmod 755 "$OUTPUT_DIR"

echo "========================================="
echo "Profiling Search Queries (End-to-End)"
echo "========================================="
echo "Query type: $QUERY_TYPE"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check if py-spy is installed
if ! command -v py-spy &> /dev/null; then
  echo "Error: py-spy not found. Install with: pipx install py-spy"
  echo "  or: pip install --user py-spy"
  exit 1
fi


# Cleanup function for error handling (runs only once)
CLEANUP_DONE=false
cleanup() {
  # Prevent double cleanup
  if [ "$CLEANUP_DONE" = true ]; then
    return
  fi
  CLEANUP_DONE=true
  
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
git clone "$GITHUB_URL" "$REPO_PATH"
echo "  Clone complete!"

# Step 3: Register with Dolphin KB
echo ""
echo "Step 3: Registering repository with Dolphin KB..."
uv run dolphin kb add-repo "$REPO_NAME" "$REPO_PATH"
echo "  Registration complete!"

# Step 4: Index the repository
echo ""
echo "Step 4: Indexing repository..."
# Count files for progress bar
FILE_COUNT=$(cd "$REPO_PATH" && git ls-files | wc -l | tr -d ' ')
echo "  Files to index: $FILE_COUNT"
echo ""
(uv run dolphin kb index "$REPO_NAME" 2>&1 | \
  tee /dev/null | \
  grep --line-buffered "Chunked.*into.*chunks" | \
  pv -l -s "$FILE_COUNT" -N "🐬 Indexing files" > /dev/null)
echo ""
echo "  Indexing complete!"

# Step 5: Start API server
echo ""
echo "Step 5: Starting KB API server..."
# Start the API server using uvicorn directly
uv run uvicorn kb.api.app:app --host 127.0.0.1 --port $API_PORT &
API_PID=$!
echo "  API server started (PID: $API_PID)"
echo "  Waiting for server to be ready..."
sleep 5

# Check if server is running
if ! curl -s http://localhost:$API_PORT/health > /dev/null; then
  echo "  Error: API server not responding at http://localhost:$API_PORT"
  exit 1
fi
echo "  API server is ready!"

# Output files
PROFILE_FILE="$OUTPUT_DIR/search_${QUERY_TYPE}_${TIMESTAMP}.json"
FLAMEGRAPH_FILE="$OUTPUT_DIR/search_${QUERY_TYPE}_${TIMESTAMP}.svg"
LOG_FILE="$OUTPUT_DIR/search_${QUERY_TYPE}_${TIMESTAMP}.log"

echo ""
echo "Step 6: Running search profiling..."
echo "  Profile data: $PROFILE_FILE"
echo "  Flame graph: $FLAMEGRAPH_FILE"
echo "  Log file: $LOG_FILE"
echo ""

# Test queries
QUERIES=(
  "authentication middleware"
  "error handling utils"
  "database connection pool"
  "API endpoint handler"
  "configuration loader"
  "express router setup"
  "request validation"
  "response formatting"
  "session management"
  "logging mechanism"
)

case $QUERY_TYPE in
  cold)
    echo "Running cold cache queries (first-time searches)..."
    # For cold cache, we just indexed so cache should be relatively cold
    ;;
  warm)
    echo "Running warm cache queries (repeated searches)..."
    echo "  Pre-warming cache..."
    for query in "${QUERIES[@]}"; do
      curl -s -X POST http://localhost:$API_PORT/search \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"top_k\": 10}" > /dev/null
    done
    sleep 2
    echo "  Cache warmed!"
    ;;
  concurrent)
    echo "Running concurrent queries (10 simultaneous users)..."
    ;;
  *)
    echo "Error: Invalid query type. Use: cold, warm, or concurrent"
    exit 1
    ;;
esac

START_TIME=$(date +%s)

# Profile search queries
if [ "$QUERY_TYPE" = "concurrent" ]; then
  # Concurrent load test with py-spy profiling
  echo "Spawning 10 concurrent search requests..."
  echo "Profiling API server process..."
  
  # Start background requests
  for i in {1..10}; do
    (
      for query in "${QUERIES[@]}"; do
        curl -s -X POST http://localhost:$API_PORT/search \
          -H "Content-Type: application/json" \
          -d "{\"query\": \"$query\", \"top_k\": 10}" >> "$LOG_FILE.worker$i" 2>&1
      done
    ) &
  done
  
  # Profile the API server during concurrent load
  # TODO: ensure sleep statement doesn't cause us to miss the action, ensure record shouldn't be called prior to actual queries
  sleep 1  # Let requests start
  py-spy record \
    --pid $API_PID \
    --format speedscope \
    --output "$PROFILE_FILE" \
    --rate 100 \
    --duration 30 || true
  
  # Generate flamegraph
  py-spy record \
    --pid $API_PID \
    --format flamegraph \
    --output "$FLAMEGRAPH_FILE" \
    --rate 100 \
    --duration 30 || true
  
  wait  # Wait for all background requests
else
  # Single-threaded search profiling
  echo "Running sequential searches with profiling..."
  
  # Profile the API server while making requests
  # Start py-spy in the background
  py-spy record \
    --pid $API_PID \
    --format speedscope \
    --output "$PROFILE_FILE" \
    --rate 100 \
    --duration 60 &
  PYSPY_PID=$!
  
  # Run searches with progress counter
  QUERY_NUM=0
  TOTAL_QUERIES=${#QUERIES[@]}
  echo "Running searches with progress..."
  
  # Run searches and log latencies separately from pv
  for query in "${QUERIES[@]}"; do
    QUERY_NUM=$((QUERY_NUM + 1))
    echo "[$QUERY_NUM/$TOTAL_QUERIES] $query" | pv -l -s "$TOTAL_QUERIES" -N "🐬 Search queries" > /dev/null
    
    START=$(uv run python -c 'import time; print(int(time.time() * 1000))')
    
    curl -s -X POST http://localhost:$API_PORT/search \
      -H "Content-Type: application/json" \
      -d "{\"query\": \"$query\", \"top_k\": 10}" >> "$LOG_FILE" 2>&1
    
    END=$(uv run python -c 'import time; print(int(time.time() * 1000))')
    LATENCY=$((END - START))
    echo "Latency: ${LATENCY}ms" | tee -a "$LOG_FILE"
  done
  echo ""
  
  # Wait for py-spy to finish
  wait $PYSPY_PID || true
  
  # Generate flamegraph with a second profiling run
  echo "Generating flamegraph..."
  py-spy record \
    --pid $API_PID \
    --format flamegraph \
    --output "$FLAMEGRAPH_FILE" \
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
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "Profiling Complete"
echo "========================================="
echo "Duration: ${DURATION}s"
echo "Profile data: $PROFILE_FILE"
echo "Flame graph: $FLAMEGRAPH_FILE"
echo "Log: $LOG_FILE"
echo ""
echo "View flame graph at: https://speedscope.app"
echo "Upload: $PROFILE_FILE"
echo ""

# Calculate average latency
if [ -f "$LOG_FILE" ] && grep -q "Latency:" "$LOG_FILE"; then
  AVG_LATENCY=$(grep "Latency:" "$LOG_FILE" | awk '{sum+=$2; count++} END {print sum/count}')
  echo "Average latency: ${AVG_LATENCY}ms"
  
  # Calculate p95
  P95_LATENCY=$(grep "Latency:" "$LOG_FILE" | awk '{print $2}' | sort -n | awk 'BEGIN{c=0} {latencies[c++]=$1} END{print latencies[int(c*0.95)]}')
  echo "p95 latency: ${P95_LATENCY}ms"
fi

# Step 7: Cleanup (handled by trap)
echo ""
if [ "$KEEP_REPO" = false ]; then
  echo "Step 7: Cleaning up..."
  echo "  (Repository and API server will be cleaned up by trap)"
else
  echo "Step 7: Skipping cleanup (--keep-repo flag set)"
  echo "  Repository: $REPO_PATH"
  echo "  Dolphin KB name: $REPO_NAME"
  echo "  API server PID: $API_PID"
  echo "  To manually clean up later:"
  echo "    kill $API_PID"
  echo "    uv run dolphin kb remove-repo $REPO_NAME"
  echo "    rm -rf $REPO_PATH"
fi