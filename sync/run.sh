#!/usr/bin/env bash
# Mac-side wrapper for the inner autoresearch loop step:
#   1. push current code to DGX
#   2. run `uv run train.py > run.log` ON DGX
#   3. pull run.log back to Mac
#
# This is what the Mac-side claude calls in place of `uv run train.py`
# during the autoresearch loop. Mac is git-authoritative; DGX is a
# bare-metal execution box.
#
# Usage:  bash sync/run.sh                         # train then pull
#         bash sync/run.sh --no-pull               # train, leave log on DGX
#         bash sync/run.sh -- --export-dir exports # extra train.py args

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"

NO_PULL=false
TRAIN_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull) NO_PULL=true; shift ;;
    --) shift; TRAIN_ARGS+=("$@"); break ;;
    *) TRAIN_ARGS+=("$1"); shift ;;
  esac
done

echo "[run] push code to DGX"
bash "$(dirname "$0")/push.sh" >/dev/null

echo "[run] uv run train.py ON DGX (~5 min for the time-budget plus startup)"
START=$(date +%s)
ssh "$SPARK" "
  set -e
  cd '$REMOTE_DIR'
  uv run train.py ${TRAIN_ARGS[*]:-} > run.log 2>&1
" || { echo "[run] DGX-side training FAILED — pulling run.log for diagnosis"; }
DURATION=$(($(date +%s) - START))
echo "[run] DGX wallclock: ${DURATION}s"

if ! $NO_PULL; then
  echo "[run] pulling run.log + exports back to Mac"
  bash "$(dirname "$0")/pull.sh" latest

  echo
  echo "=== headline metrics ==="
  grep -E "^(val_bpb|peak_vram_mb|training_seconds|num_steps|num_params_M|depth):" \
    "$(dirname "$0")/../run.log" 2>/dev/null | head -10 \
    || tail -30 "$(dirname "$0")/../run.log"
fi
