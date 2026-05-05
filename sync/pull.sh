#!/usr/bin/env bash
## sync/pull.sh — Spark → Mac artifact pull.
##
## SCOPE: only what the DGX uniquely produces (run.log + exports/).
## Mac is authoritative for code + plan docs + results.tsv (the agent
## runs the loop on Mac), so we never pull those back.
##
## Two modes:
##   default  — timestamped audit snapshot at audit/<UTC-ts>/
##              (used post-experiment to archive a run)
##   latest   — in-place: rsync run.log + exports/ to repo root
##              (used by sync/run.sh during the inner loop)
##
## Defense-in-depth: explicitly exclude binary weight files (*.bin,
## *.safetensors, *.pt) at the rsync layer in case schaferk's tooling
## ever writes huge checkpoints we don't want lugging around. We DO
## pull exports/*.pth (litesearch's small checkpoint format), so the
## binary excludes are scoped per-rsync.
##
## Convention shared with ../../dgx repo's sync-audit-back.sh — see
## sync/README.md.
##
## Usage:
##   bash sync/pull.sh                  # timestamped snapshot mode
##   bash sync/pull.sh latest           # in-place mode for inner loop

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"
TS_LOG="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TS_DIR="$(date -u +%Y%m%dT%H%M%SZ)"  # compact, filename-safe, sortable

if [ "${1:-}" = "latest" ]; then
  # in-place mode — used by sync/run.sh during the inner loop
  rsync -avz "$SPARK:$REMOTE_DIR/run.log" "$LOCAL_DIR/run.log" 2>/dev/null || true
  rsync -avz --delete \
    --exclude='*.bin' --exclude='*.safetensors' \
    "$SPARK:$REMOTE_DIR/exports/" "$LOCAL_DIR/exports/" 2>/dev/null || true
  exit 0
fi

# audit-snapshot mode — used post-experiment to archive a run
AUDIT_DIR="$LOCAL_DIR/audit/$TS_DIR"
echo "[pull←spark] $TS_LOG — $SPARK:$REMOTE_DIR  →  $AUDIT_DIR"
mkdir -p "$AUDIT_DIR"

rsync -avz "$SPARK:$REMOTE_DIR/run.log" "$AUDIT_DIR/run.log" 2>/dev/null || true
rsync -avz --delete \
  --exclude='*.bin' --exclude='*.safetensors' \
  "$SPARK:$REMOTE_DIR/exports/" "$AUDIT_DIR/exports/" 2>/dev/null || true

# Snapshot of train.py at DGX (what produced this run.log)
ssh "$SPARK" "cat '$REMOTE_DIR/train.py'" > "$AUDIT_DIR/train.py.snapshot" 2>/dev/null || true

# Empty-result cleanup — if we got nothing useful, drop the empty dir
PULLED="$(find "$AUDIT_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')"
if [ "$PULLED" = "0" ]; then
  echo "[pull←spark] no artifacts pulled; cleaning up empty $AUDIT_DIR"
  rmdir "$AUDIT_DIR" 2>/dev/null || true
  exit 1
fi

# Quick at-a-glance summary
echo
echo "=== summary ==="
if [ -f "$AUDIT_DIR/run.log" ]; then
  grep -E "^(val_bpb|peak_vram_mb|training_seconds|num_steps|num_params_M|depth|GPU|Compute|Dtype|Peak FLOPs):" \
    "$AUDIT_DIR/run.log" 2>/dev/null | tail -15 || true
fi
echo
echo "[pull←spark] done — $PULLED file(s) at $AUDIT_DIR"
