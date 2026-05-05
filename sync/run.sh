#!/usr/bin/env bash
## sync/run.sh — Mac-side wrapper for the inner autoresearch loop step.
##
## What it does:
##   1. push current code to DGX  (sync/push.sh)
##   2. ssh + uv run train.py > run.log  ON DGX
##   3. pull run.log + exports/ back to Mac  (sync/pull.sh latest)
##
## Mac is git-authoritative; DGX is a bare-metal execution box. The
## Mac-side claude calls this script in place of `uv run train.py`
## during the autoresearch loop.
##
## Convention shared with the launch helpers in ../../dgx repo —
## see sync/README.md.
##
## Usage:
##   bash sync/run.sh                          # train then pull
##   bash sync/run.sh --no-pull                # train, leave log on DGX
##   bash sync/run.sh -- --export-dir exports  # extra train.py args
##   bash sync/run.sh --tmux                   # detach-friendly (long runs)

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TS_LOG="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TS_RUN="$(date -u +%Y%m%dT%H%M%SZ)"

NO_PULL=false
USE_TMUX=false
TRAIN_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull) NO_PULL=true; shift ;;
    --tmux)    USE_TMUX=true; shift ;;
    --) shift; TRAIN_ARGS+=("$@"); break ;;
    *) TRAIN_ARGS+=("$1"); shift ;;
  esac
done

echo "[run] $TS_LOG — push code to DGX"
bash "$SCRIPT_DIR/push.sh" >/dev/null

echo "[run] $TS_LOG — uv run train.py ON DGX (~5 min train + ~30s startup/eval)"
START=$(date +%s)

if $USE_TMUX; then
  # tmux mode: survive ssh disconnect; tail-friendly logs in audit-runs/.
  # Pattern adopted from ../../dgx repo's ship-parallel.sh.
  SESSION="autoresearch-train-$TS_RUN"
  ssh "$SPARK" "
    set -e
    mkdir -p '$REMOTE_DIR/audit-runs'
    LOG='$REMOTE_DIR/audit-runs/train-$TS_RUN.log'
    cd '$REMOTE_DIR'
    tmux new -d -s '$SESSION' \"
      uv run train.py ${TRAIN_ARGS[*]:-} 2>&1 | tee '\$LOG' | tee run.log
    \"
    echo '[run] tmux session: $SESSION'
    echo '[run] tail: ssh $SPARK \"tail -f $REMOTE_DIR/audit-runs/train-$TS_RUN.log\"'
    echo '[run] attach: ssh $SPARK \"tmux attach -t $SESSION\"'
  "
  echo "[run] tmux mode — script returns immediately. Pull artifacts later with bash sync/pull.sh"
  exit 0
fi

# default (synchronous) mode
ssh "$SPARK" "
  set -e
  cd '$REMOTE_DIR'
  uv run train.py ${TRAIN_ARGS[*]:-} > run.log 2>&1
" || { echo "[run] DGX-side training FAILED — pulling run.log for diagnosis"; }
DURATION=$(($(date +%s) - START))
echo "[run] DGX wallclock: ${DURATION}s"

if ! $NO_PULL; then
  echo "[run] pulling run.log + exports back to Mac"
  bash "$SCRIPT_DIR/pull.sh" latest

  echo
  echo "=== headline metrics ==="
  grep -E "^(val_bpb|peak_vram_mb|training_seconds|num_steps|num_params_M|depth):" \
    "$SCRIPT_DIR/../run.log" 2>/dev/null | head -10 \
    || tail -30 "$SCRIPT_DIR/../run.log"
fi
