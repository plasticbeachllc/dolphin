#!/bin/zsh
# Quick timing test to debug duration calculation

echo "Testing date command formats:"
echo ""

# Test 1: Basic date +%s
START1=$(date +%s)
echo "date +%s format: $START1"
echo "Type: $(echo $START1 | grep -q '\.' && echo 'decimal' || echo 'integer')"
echo ""

# Test 2: Try nanosecond format
START2=$(date +%s.%N 2>/dev/null || date +%s)
echo "date +%s.%N format: $START2"
echo "Type: $(echo $START2 | grep -q '\.' && echo 'decimal' || echo 'integer')"
echo ""

# Test 3: Simulate a 5 second delay
echo "Starting 5 second test..."
START=$(date +%s.%N 2>/dev/null || date +%s)
echo "Start time: $START"
sleep 5
END=$(date +%s.%N 2>/dev/null || date +%s)
echo "End time: $END"

# Test duration calculation
echo ""
echo "Duration calculation test:"
if [[ $START == *.* ]]; then
  DURATION=$(echo "$END - $START" | bc 2>/dev/null || echo "bc not available")
  echo "Using bc: $DURATION seconds"
else
  DURATION=$((END - START))
  echo "Using integer arithmetic: $DURATION seconds"
fi

echo ""
echo "Expected: ~5 seconds"
echo "Actual: $DURATION seconds"