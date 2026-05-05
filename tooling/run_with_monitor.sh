#!/bin/bash
# Run a single autoresearch training with system monitoring.
# Usage: ./run_with_monitor.sh [run_label]
#
# Outputs:
#   results/logs/<label>.log       - Full training log
#   results/metrics/<label>.jsonl  - Per-second system metrics
#   results/journal/exp_NNN.json   - Experiment record (written by caller)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../repo" && pwd)"
RESULTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/results"
LOGS_DIR="$RESULTS_DIR/logs"
METRICS_DIR="$RESULTS_DIR/metrics"

RUN_LABEL="${1:-run_$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$LOGS_DIR" "$METRICS_DIR"

echo "=== Autoresearch Training Run: $RUN_LABEL ==="
echo "Repo:    $REPO_DIR"
echo "Log:     $LOGS_DIR/$RUN_LABEL.log"
echo "Metrics: $METRICS_DIR/$RUN_LABEL.jsonl"
echo ""

# Start system monitor in background
cd "$SCRIPT_DIR"
python3 monitor.py start --output "$METRICS_DIR/$RUN_LABEL.jsonl"

# Run training
cd "$REPO_DIR"
echo "Starting training..."
uv run train.py > "$LOGS_DIR/$RUN_LABEL.log" 2>&1
EXIT_CODE=$?

# Stop monitor
cd "$SCRIPT_DIR"
python3 monitor.py stop

# Extract results
echo ""
echo "=== Results ==="
if [ $EXIT_CODE -eq 0 ]; then
    grep "^val_bpb:\|^peak_vram_mb:\|^mfu_percent:\|^total_tokens_M:\|^num_params_M:\|^num_steps:\|^depth:" "$LOGS_DIR/$RUN_LABEL.log" || true
else
    echo "CRASHED (exit code: $EXIT_CODE)"
    echo "Last 30 lines:"
    tail -30 "$LOGS_DIR/$RUN_LABEL.log"
fi

echo ""
echo "Log:     $LOGS_DIR/$RUN_LABEL.log"
echo "Metrics: $METRICS_DIR/$RUN_LABEL.jsonl"
exit $EXIT_CODE
