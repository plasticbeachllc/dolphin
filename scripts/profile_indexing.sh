#!/bin/zsh
# Profile the KB indexing pipeline with py-spy
#
# Usage:
#   ./scripts/profile_indexing.sh <repo_size> [--keep-repo]
#
# Where repo_size is one of: small (1K files), medium (10K files), large (50K files)
# Use --keep-repo flag to skip cleanup (useful for debugging)

set -e

REPO_SIZE=${1:-small}
KEEP_REPO=false
if [[ "$2" == "--keep-repo" ]]; then
  KEEP_REPO=true
fi

OUTPUT_DIR="profiling_results/indexing"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_REPOS_DIR="./test-repos"
REPO_NAME="profile-test-${REPO_SIZE}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Determine test repo configuration based on size
case $REPO_SIZE in
  small)
    REPO_PATH="$TEST_REPOS_DIR/small"
    GITHUB_URL="https://github.com/expressjs/express"
    EXPECTED_FILES="~1,000"
    ;;
  medium)
    REPO_PATH="$TEST_REPOS_DIR/medium"
    GITHUB_URL="https://github.com/django/django"
    EXPECTED_FILES="~10,000"
    ;;
  large)
    REPO_PATH="$TEST_REPOS_DIR/large"
    GITHUB_URL="https://github.com/torvalds/linux"
    EXPECTED_FILES="~50,000"
    ;;
  *)
    echo "Error: Invalid repo size. Use: small, medium, or large"
    exit 1
    ;;
esac

echo "========================================="
echo "Profiling Indexing Pipeline (End-to-End)"
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

# Check if pv is installed
if ! command -v pv &> /dev/null; then
  echo "Error: pv not found. Install with: brew install pv (macOS) or apt-get install pv (Linux)"
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

# Step 4: Run profiling
echo ""
echo "Step 4: Starting profiling session..."
PROFILE_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.json"
FLAMEGRAPH_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.svg"
LOG_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.log"

echo "  Profile data: $PROFILE_FILE"
echo "  Flame graph: $FLAMEGRAPH_FILE"
echo "  Log file: $LOG_FILE"
echo ""

# Count actual files in repository
echo "Counting files in repository..."
FILE_COUNT=$(cd "$REPO_PATH" && git ls-files | wc -l | tr -d ' ')
echo "  Files to index: $FILE_COUNT"
echo ""

START_TIME=$(date +%s)

# Run profiling with py-spy and pv progress bar
echo "Starting indexing..."
(py-spy record \
  --format speedscope \
  --output "$PROFILE_FILE" \
  --rate 100 \
  --subprocesses \
  -- uv run dolphin kb index "$REPO_NAME" 2>&1 | \
  tee "$LOG_FILE" | \
  grep --line-buffered "Chunked.*into.*chunks" | \
  pv -l -s "$FILE_COUNT" -N "🐬 Indexing files" > /dev/null)

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo ""

# Generate flame graph (reindex for flamegraph)
echo ""
echo "Generating flame graph (reindexing)..."
py-spy record \
  --format flamegraph \
  --output "$FLAMEGRAPH_FILE" \
  --rate 100 \
  --subprocesses \
  -- uv run dolphin kb index "$REPO_NAME" --full --force 2>&1 > /dev/null

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

# Extract metrics from log
if grep -q "files/min" "$LOG_FILE"; then
  THROUGHPUT=$(grep -oP "[\d,]+ files/min" "$LOG_FILE" | head -1)
  echo "Throughput: $THROUGHPUT"
fi

if grep -q "Total time" "$LOG_FILE"; then
  TOTAL_TIME=$(grep -oP "Total time: [\d.]+s" "$LOG_FILE" | head -1)
  echo "$TOTAL_TIME"
fi

# Step 5: Cleanup (handled by trap)
echo ""
if [ "$KEEP_REPO" = false ]; then
  echo "Step 5: Cleaning up..."
  echo "  (Repository will be removed by cleanup trap)"
else
  echo "Step 5: Skipping cleanup (--keep-repo flag set)"
  echo "  Repository: $REPO_PATH"
  echo "  Dolphin KB name: $REPO_NAME"
  echo "  To manually clean up later:"
  echo "    uv run dolphin kb remove-repo $REPO_NAME"
  echo "    rm -rf $REPO_PATH"
fi