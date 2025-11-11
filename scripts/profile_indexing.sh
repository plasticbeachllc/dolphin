#!/bin/bash
# Profile the KB indexing pipeline with py-spy
#
# Usage:
#   ./scripts/profile_indexing.sh <repo_size>
#
# Where repo_size is one of: small (1K files), medium (10K files), large (50K files)

set -e

REPO_SIZE=${1:-small}
OUTPUT_DIR="profiling_results/indexing"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Determine test repo path based on size
case $REPO_SIZE in
  small)
    REPO_PATH="${TEST_REPO_SMALL:-./test-repos/small}"
    EXPECTED_FILES="~1,000"
    ;;
  medium)
    REPO_PATH="${TEST_REPO_MEDIUM:-./test-repos/medium}"
    EXPECTED_FILES="~10,000"
    ;;
  large)
    REPO_PATH="${TEST_REPO_LARGE:-./test-repos/large}"
    EXPECTED_FILES="~50,000"
    ;;
  *)
    echo "Error: Invalid repo size. Use: small, medium, or large"
    exit 1
    ;;
esac

if [ ! -d "$REPO_PATH" ]; then
  echo "Error: Test repository not found at $REPO_PATH"
  echo "Set TEST_REPO_${REPO_SIZE^^} environment variable to specify location"
  exit 1
fi

echo "========================================="
echo "Profiling Indexing Pipeline"
echo "========================================="
echo "Repository: $REPO_PATH"
echo "Expected files: $EXPECTED_FILES"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check if py-spy is installed
if ! command -v py-spy &> /dev/null; then
  echo "Error: py-spy not found. Install with: pip install py-spy"
  exit 1
fi

# Output files
PROFILE_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.json"
FLAMEGRAPH_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.svg"
LOG_FILE="$OUTPUT_DIR/indexing_${REPO_SIZE}_${TIMESTAMP}.log"

echo "Starting profiling session..."
echo "Profile data: $PROFILE_FILE"
echo "Flame graph: $FLAMEGRAPH_FILE"
echo "Log file: $LOG_FILE"
echo ""

# Start KB indexing with profiling
# Note: Adjust the command based on your KB CLI interface
START_TIME=$(date +%s)

py-spy record \
  --format speedscope \
  --output "$PROFILE_FILE" \
  --rate 100 \
  --subprocesses \
  -- python -m kb.cli index "$REPO_PATH" 2>&1 | tee "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Generate flame graph
py-spy record \
  --format flamegraph \
  --output "$FLAMEGRAPH_FILE" \
  --rate 100 \
  --subprocesses \
  -- python -m kb.cli index "$REPO_PATH" 2>&1 > /dev/null

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
