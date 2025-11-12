#!/bin/zsh
# Minimal test to debug timing issue

set -e

echo "========================================="
echo "Timing Debug Test"
echo "========================================="
echo ""

# Create a tiny test
echo "Test 1: Simple sleep with timestamp capture"
echo "Starting at: $(date +%H:%M:%S)"
START=$(date +%s.%N)
echo "START timestamp: $START"

sleep 3

END=$(date +%s.%N)
echo "END timestamp: $END"
echo "Ending at: $(date +%H:%M:%S)"

DURATION=$(echo "$END - $START" | bc)
DURATION_INT=$(echo "$DURATION / 1" | bc)

echo ""
echo "Duration: ${DURATION}s"
echo "Expected: ~3 seconds"
echo ""

# Test 2: With subshell and pipe
echo "Test 2: With subshell and tee"
echo "Starting at: $(date +%H:%M:%S)"
START2=$(date +%s.%N)
echo "START2 timestamp: $START2"

(sleep 3 && echo "Work done" | tee /tmp/test_output.log)

END2=$(date +%s.%N)
echo "END2 timestamp: $END2"
echo "Ending at: $(date +%H:%M:%S)"

DURATION2=$(echo "$END2 - $START2" | bc)
DURATION2_INT=$(echo "$DURATION2 / 1" | bc)

echo ""
echo "Duration: ${DURATION2}s"
echo "Expected: ~3 seconds"
echo ""

# Test 3: Check if variables persist
echo "Test 3: Variable persistence check"
echo "START from Test 1: $START"
echo "START2 from Test 2: $START2"
echo "Are they different? $([ "$START" != "$START2" ] && echo YES || echo NO)"