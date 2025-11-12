#!/bin/zsh
# Quick test version of combined profiling with minimal data
# Uses a tiny test repo and only 5 queries for fast validation
#
# Usage:
#   ./scripts/profile_combined_small.sh [--keep-repo]
#
# Use --keep-repo flag to skip cleanup (useful for debugging)

set -e

KEEP_REPO=false
if [[ "$1" == "--keep-repo" ]]; then
  KEEP_REPO=true
fi

OUTPUT_DIR="profiling_results/combined-test"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_REPOS_DIR="./test-repos"
REPO_NAME="profile-test-quick"
API_PORT=7777

# Use a tiny repo for quick testing
REPO_PATH="$TEST_REPOS_DIR/test-quick"
GITHUB_URL="https://github.com/expressjs/body-parser"  # Small package, ~50 files

# Create output directory
mkdir -p "$OUTPUT_DIR"
chmod 755 "$OUTPUT_DIR"

echo "========================================="
echo "Quick Test: Combined Profiling"
echo "========================================="
echo "Repository: body-parser (tiny, ~50 files)"
echo "Queries: 5 (fast validation)"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check if py-spy is installed
if ! command -v py-spy &> /dev/null; then
  echo "❌ Error: py-spy not found. Install with: pipx install py-spy"
  exit 1
fi
echo "  ✅ py-spy installed"

# Check if pv is installed
if ! command -v pv &> /dev/null; then
  echo "❌ Error: pv not found. Install with: brew install pv (macOS)"
  exit 1
fi
echo "  ✅ pv installed"

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
  echo ""
  echo "❌ Error: OPENAI_API_KEY environment variable is not set"
  echo ""
  echo "Dolphin requires an OpenAI API key for embeddings."
  echo ""
  echo "Set it with:"
  echo "  export OPENAI_API_KEY='sk-...'"
  echo ""
  echo "Or add to your shell profile:"
  echo "  echo 'export OPENAI_API_KEY=\"sk-...\"' >> ~/.zshrc"
  echo "  source ~/.zshrc"
  echo ""
  exit 1
fi
echo "  ✅ OPENAI_API_KEY is set"
echo ""

# Cleanup function (runs only once)
CLEANUP_DONE=false
cleanup() {
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

# ==============================================================================
# PHASE 1: INDEXING PROFILING
# ==============================================================================

echo "========================================="
echo "PHASE 1: Indexing Profiling"
echo "========================================="
echo ""

# Step 1: Clean up existing test repository
echo "Step 1: Cleaning up existing test repository..."
if [ -d "$REPO_PATH" ]; then
  echo "  Removing existing directory: $REPO_PATH"
  rm -rf "$REPO_PATH"
fi

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

# Step 4: Profile indexing
echo ""
echo "Step 4: Profiling indexing..."
INDEX_PROFILE_FILE="$OUTPUT_DIR/indexing_test_${TIMESTAMP}.json"
INDEX_LOG_FILE="$OUTPUT_DIR/indexing_test_${TIMESTAMP}.log"

echo "  Profile data: $INDEX_PROFILE_FILE"
echo "  Log file: $INDEX_LOG_FILE"
echo ""

# Count files
echo "Counting files in repository..."
FILE_COUNT=$(cd "$REPO_PATH" && git ls-files | wc -l | tr -d ' ')
echo "  Files to index: $FILE_COUNT"
echo ""

# Run profiling with py-spy
echo "Starting indexing at: $(date +%H:%M:%S)"
INDEX_START=$(date +%s.%N)

# Show full output for debugging
echo "Running: uv run dolphin kb index \"$REPO_NAME\" --full --force"
echo "(Watch for 'Chunked X into Y chunks' messages per file)"
echo ""

(py-spy record \
  --format speedscope \
  --output "$INDEX_PROFILE_FILE" \
  --rate 100 \
  --subprocesses \
  -- uv run dolphin kb index "$REPO_NAME" --full --force 2>&1 | \
  tee "$INDEX_LOG_FILE" | \
  grep --line-buffered "Chunked.*into.*chunks" | \
  pv -l -s "$FILE_COUNT" -N "🐬 Indexing files" > /dev/null)

INDEX_END=$(date +%s.%N)
echo ""
echo "Indexing finished at: $(date +%H:%M:%S)"

INDEX_DURATION=$(echo "$INDEX_END - $INDEX_START" | bc)
INDEX_DURATION_INT=$(echo "$INDEX_DURATION / 1" | bc)

echo ""
echo "========================================="
echo "Indexing Profiling Complete"
echo "========================================="
echo "Duration: ${INDEX_DURATION}s"
echo "Profile data: $INDEX_PROFILE_FILE"
echo "Log: $INDEX_LOG_FILE"
echo ""

# Debug: Show what actually happened
echo "Debug info:"
if grep -q "Files processed" "$INDEX_LOG_FILE"; then
  echo "  $(grep 'Files processed' "$INDEX_LOG_FILE" | head -1)"
fi
if grep -q "Chunks indexed" "$INDEX_LOG_FILE"; then
  echo "  $(grep 'Chunks indexed' "$INDEX_LOG_FILE" | head -1)"
fi
if grep -q "skipped" "$INDEX_LOG_FILE"; then
  echo "  $(grep -i 'skipped' "$INDEX_LOG_FILE" | head -3)"
fi
echo "  Lines in log: $(wc -l < "$INDEX_LOG_FILE")"
echo ""

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
sleep 5

# Check if server is running
if ! curl -s http://localhost:$API_PORT/health > /dev/null; then
  echo "  Error: API server not responding at http://localhost:$API_PORT"
  exit 1
fi
echo "  API server is ready!"

# Output files for search profiling
SEARCH_PROFILE_FILE="$OUTPUT_DIR/search_test_${TIMESTAMP}.json"
SEARCH_LOG_FILE="$OUTPUT_DIR/search_test_${TIMESTAMP}.log"

echo ""
echo "Step 6: Profiling search queries..."
echo "  Profile data: $SEARCH_PROFILE_FILE"
echo "  Log file: $SEARCH_LOG_FILE"
echo ""

# Just 5 test queries for quick validation
QUERIES=(
  "body parser middleware"
  "JSON parsing"
  "URL encoded"
  "express integration"
  "content type"
)

echo "Running search queries with profiling..."
echo "Queries to execute: ${#QUERIES[@]}"
echo ""

# Profile the API server while making requests
py-spy record \
  --pid $API_PID \
  --format speedscope \
  --output "$SEARCH_PROFILE_FILE" \
  --rate 100 \
  --duration 30 &
PYSPY_PID=$!

# Run searches
echo "Starting searches at: $(date +%H:%M:%S)"
SEARCH_START=$(date +%s.%N)

QUERY_NUM=1
TOTAL_QUERIES=${#QUERIES[@]}
for query in "${QUERIES[@]}"; do
  echo "[$QUERY_NUM/$TOTAL_QUERIES] Searching: $query"
  START=$(uv run python -c 'import time; print(int(time.time() * 1000))')
  
  curl -s -X POST http://localhost:$API_PORT/search \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$query\", \"top_k\": 10}" >> "$SEARCH_LOG_FILE" 2>&1
  
  END=$(uv run python -c 'import time; print(int(time.time() * 1000))')
  LATENCY=$((END - START))
  echo "  Latency: ${LATENCY}ms" | tee -a "$SEARCH_LOG_FILE"
  QUERY_NUM=$((QUERY_NUM + 1))
done

SEARCH_END=$(date +%s.%N)
echo "Searches finished at: $(date +%H:%M:%S)"

SEARCH_DURATION=$(echo "$SEARCH_END - $SEARCH_START" | bc)
SEARCH_DURATION_INT=$(echo "$SEARCH_DURATION / 1" | bc)

# Wait for py-spy to finish
wait $PYSPY_PID || true

echo ""
echo "========================================="
echo "Search Profiling Complete"
echo "========================================="
echo "Duration: ${SEARCH_DURATION}s"
echo "Profile data: $SEARCH_PROFILE_FILE"
echo "Log: $SEARCH_LOG_FILE"
echo ""

# Calculate search metrics
if [ -f "$SEARCH_LOG_FILE" ] && grep -q "Latency:" "$SEARCH_LOG_FILE"; then
  AVG_LATENCY=$(grep "Latency:" "$SEARCH_LOG_FILE" | awk '{sum+=$2; count++} END {print sum/count}')
  echo "Average search latency: ${AVG_LATENCY}ms"
fi

# ==============================================================================
# SUMMARY
# ==============================================================================

# Calculate total duration
TOTAL_DURATION=$(echo "$INDEX_DURATION + $SEARCH_DURATION" | bc)
TOTAL_DURATION_INT=$(echo "$TOTAL_DURATION / 1" | bc)

INDEX_MINUTES=$((INDEX_DURATION_INT / 60))
INDEX_SECONDS=$((INDEX_DURATION_INT % 60))
SEARCH_MINUTES=$((SEARCH_DURATION_INT / 60))
SEARCH_SECONDS=$((SEARCH_DURATION_INT % 60))
TOTAL_MINUTES=$((TOTAL_DURATION_INT / 60))
TOTAL_SECONDS=$((TOTAL_DURATION_INT % 60))

echo ""
echo "========================================="
echo "Quick Test Summary"
echo "========================================="
echo ""
echo "Repository: body-parser (~50 files)"
echo "Repository name: $REPO_NAME"
echo ""
echo "INDEXING:"
echo "  Duration: ${INDEX_DURATION}s ($(printf '%02d:%02d' $INDEX_MINUTES $INDEX_SECONDS))"
echo "  Profile: $INDEX_PROFILE_FILE"
echo "  Log: $INDEX_LOG_FILE"
echo ""
echo "SEARCH:"
echo "  Duration: ${SEARCH_DURATION}s ($(printf '%02d:%02d' $SEARCH_MINUTES $SEARCH_SECONDS))"
echo "  Queries: ${#QUERIES[@]}"
echo "  Profile: $SEARCH_PROFILE_FILE"
echo "  Log: $SEARCH_LOG_FILE"
echo ""
echo "TOTAL RUNTIME: ${TOTAL_DURATION}s ($(printf '%02d:%02d' $TOTAL_MINUTES $TOTAL_SECONDS))"
echo ""
echo "✅ Quick test complete! If this worked, try the full profiling scripts:"
echo "   ./scripts/profile_combined.sh small"
echo "   ./scripts/profile_combined.sh medium"
echo "   ./scripts/profile_combined.sh large"
echo ""
echo "View profile at: https://speedscope.app"
echo "Upload: $INDEX_PROFILE_FILE"
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