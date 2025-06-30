#!/bin/bash
# Script to measure test performance improvements with pytest-xdist
set -e

echo "Test Performance Measurement Script"
echo "=================================="
echo ""

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Check if pytest-xdist is installed
if ! python -c "import xdist" 2>/dev/null; then
    echo "Error: pytest-xdist is not installed. Please run: pip install pytest-xdist"
    exit 1
fi

# Collect static files
echo "Collecting static files..."
manage collectstatic --noinput >/dev/null 2>&1

echo ""
echo "Running performance measurements..."
echo ""

# Measure sequential execution
echo "1. Sequential execution (baseline):"
echo "   Command: pytest --durations=20"
SEQUENTIAL_START=$(date +%s)
pytest --durations=20 -q 2>&1 | tail -5
SEQUENTIAL_END=$(date +%s)
SEQUENTIAL_TIME=$((SEQUENTIAL_END - SEQUENTIAL_START))
echo "   Total time: ${SEQUENTIAL_TIME}s"
echo ""

# Measure parallel execution with auto workers
echo "2. Parallel execution (auto workers):"
echo "   Command: pytest -n auto --durations=20"
PARALLEL_AUTO_START=$(date +%s)
pytest -n auto --durations=20 -q 2>&1 | tail -5
PARALLEL_AUTO_END=$(date +%s)
PARALLEL_AUTO_TIME=$((PARALLEL_AUTO_END - PARALLEL_AUTO_START))
echo "   Total time: ${PARALLEL_AUTO_TIME}s"
echo ""

# Measure with database reuse
echo "3. Sequential with database reuse:"
echo "   Command: pytest --reuse-db --durations=20"
REUSE_START=$(date +%s)
pytest --reuse-db --durations=20 -q 2>&1 | tail -5
REUSE_END=$(date +%s)
REUSE_TIME=$((REUSE_END - REUSE_START))
echo "   Total time: ${REUSE_TIME}s"
echo ""

# Measure parallel with database reuse
echo "4. Parallel with database reuse:"
echo "   Command: pytest -n auto --reuse-db --durations=20"
PARALLEL_REUSE_START=$(date +%s)
pytest -n auto --reuse-db --durations=20 -q 2>&1 | tail -5
PARALLEL_REUSE_END=$(date +%s)
PARALLEL_REUSE_TIME=$((PARALLEL_REUSE_END - PARALLEL_REUSE_START))
echo "   Total time: ${PARALLEL_REUSE_TIME}s"
echo ""

# Calculate improvements
echo "Performance Summary"
echo "==================="
echo "Sequential baseline: ${SEQUENTIAL_TIME}s"

if [ $PARALLEL_AUTO_TIME -gt 0 ]; then
    PARALLEL_SPEEDUP=$(awk "BEGIN {printf \"%.1f\", $SEQUENTIAL_TIME / $PARALLEL_AUTO_TIME}")
    echo "Parallel speedup: ${PARALLEL_SPEEDUP}x"
fi

if [ $REUSE_TIME -gt 0 ]; then
    REUSE_SPEEDUP=$(awk "BEGIN {printf \"%.1f\", $SEQUENTIAL_TIME / $REUSE_TIME}")
    echo "Database reuse speedup: ${REUSE_SPEEDUP}x"
fi

if [ $PARALLEL_REUSE_TIME -gt 0 ]; then
    COMBINED_SPEEDUP=$(awk "BEGIN {printf \"%.1f\", $SEQUENTIAL_TIME / $PARALLEL_REUSE_TIME}")
    echo "Combined speedup: ${COMBINED_SPEEDUP}x"
fi

echo ""
echo "Note: Actual speedup will vary based on:"
echo "  - Number of CPU cores"
echo "  - Test characteristics (I/O vs CPU bound)"
echo "  - Database transaction overhead"