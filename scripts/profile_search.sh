#!/bin/bash
# Profile the KB search queries with py-spy
#
# Usage:
#   ./scripts/profile_search.sh <query_type>
#
# Where query_type is one of: cold, warm, concurrent

set -e

QUERY_TYPE=${1:-cold}
OUTPUT_DIR="profiling_results/search"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "========================================="
echo "Profiling Search Queries"
echo "========================================="
echo "Query type: $QUERY_TYPE"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check if py-spy is installed
if ! command -v py-spy &> /dev/null; then
  echo "Error: py-spy not found. Install with: pip install py-spy"
  exit 1
fi

# Output files
PROFILE_FILE="$OUTPUT_DIR/search_${QUERY_TYPE}_${TIMESTAMP}.json"
FLAMEGRAPH_FILE="$OUTPUT_DIR/search_${QUERY_TYPE}_${TIMESTAMP}.svg"
LOG_FILE="$OUTPUT_DIR/search_${QUERY_TYPE}_${TIMESTAMP}.log"

echo "Profile data: $PROFILE_FILE"
echo "Flame graph: $FLAMEGRAPH_FILE"
echo "Log file: $LOG_FILE"
echo ""

# Test queries
QUERIES=(
  "authentication middleware"
  "error handling utils"
  "database connection pool"
  "API endpoint handler"
  "configuration loader"
)

case $QUERY_TYPE in
  cold)
    echo "Running cold cache queries (first-time searches)..."
    # Clear cache before profiling
    echo "Clearing cache..."
    # Adjust based on your KB API
    curl -X DELETE http://localhost:8420/api/cache || true
    sleep 2
    ;;
  warm)
    echo "Running warm cache queries (repeated searches)..."
    # Pre-warm cache
    echo "Pre-warming cache..."
    for query in "${QUERIES[@]}"; do
      curl -s -X POST http://localhost:8420/api/search \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"top_k\": 10}" > /dev/null
    done
    sleep 2
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
  # Concurrent load test
  echo "Spawning 10 concurrent search requests..."

  # Simple concurrent test using background processes
  for i in {1..10}; do
    (
      for query in "${QUERIES[@]}"; do
        curl -s -X POST http://localhost:8420/api/search \
          -H "Content-Type: application/json" \
          -d "{\"query\": \"$query\", \"top_k\": 10}" > /dev/null
      done
    ) &
  done

  wait
else
  # Single-threaded search profiling
  for query in "${QUERIES[@]}"; do
    echo "Searching: $query"
    START=$(date +%s%3N)

    curl -s -X POST http://localhost:8420/api/search \
      -H "Content-Type: application/json" \
      -d "{\"query\": \"$query\", \"top_k\": 10}" | tee -a "$LOG_FILE"

    END=$(date +%s%3N)
    LATENCY=$((END - START))
    echo "Latency: ${LATENCY}ms" | tee -a "$LOG_FILE"
    echo ""
  done
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "Profiling Complete"
echo "========================================="
echo "Duration: ${DURATION}s"
echo "Log: $LOG_FILE"
echo ""

# Calculate average latency
if [ -f "$LOG_FILE" ] && grep -q "Latency:" "$LOG_FILE"; then
  AVG_LATENCY=$(grep "Latency:" "$LOG_FILE" | awk '{sum+=$2; count++} END {print sum/count}')
  echo "Average latency: ${AVG_LATENCY}ms"
fi
