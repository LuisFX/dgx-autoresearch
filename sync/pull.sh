#!/usr/bin/env bash
# Spark → Mac: pull artifacts only (logs, exports).
#
# The DGX writes run.log + exports/ during a training run. Mac writes
# results.tsv (we run the loop on Mac; DGX just executes train.py).
# So this script ONLY pulls what the DGX uniquely produces.
#
# Usage:  bash sync/pull.sh
#         bash sync/pull.sh latest      # pull straight into ./run.log
#                                          (no timestamped audit dir)

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"

if [ "${1:-}" = "latest" ]; then
  # in-place mode — used by sync/run.sh during the inner loop
  rsync -avz "$SPARK:$REMOTE_DIR/run.log" "$LOCAL_DIR/run.log" 2>/dev/null || true
  rsync -avz --delete "$SPARK:$REMOTE_DIR/exports/" "$LOCAL_DIR/exports/" 2>/dev/null || true
  exit 0
fi

# audit-snapshot mode — used post-experiment to archive a run
AUDIT_DIR="$LOCAL_DIR/audit/$(date -u +%Y-%m-%dT%H%M)"
echo "[pull] spark    = $SPARK"
echo "[pull] remote   = $REMOTE_DIR"
echo "[pull] audit-to = $AUDIT_DIR"
mkdir -p "$AUDIT_DIR"

rsync -avz "$SPARK:$REMOTE_DIR/run.log"  "$AUDIT_DIR/run.log"  2>/dev/null || true
rsync -avz --delete "$SPARK:$REMOTE_DIR/exports/" "$AUDIT_DIR/exports/" 2>/dev/null || true

# Snapshot of train.py at DGX (what produced this run.log)
ssh "$SPARK" "cat '$REMOTE_DIR/train.py'" > "$AUDIT_DIR/train.py.snapshot" 2>/dev/null || true

# Quick at-a-glance summary
echo
echo "=== summary ==="
if [ -f "$AUDIT_DIR/run.log" ]; then
  grep -E "^(val_bpb|peak_vram_mb|training_seconds|num_steps|num_params_M|depth|GPU|Compute|Dtype|Peak FLOPs):" \
    "$AUDIT_DIR/run.log" 2>/dev/null | tail -15
fi
echo
echo "[pull] done — see $AUDIT_DIR"
