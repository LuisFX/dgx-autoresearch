#!/usr/bin/env bash
# Mac → Spark: rsync the bits the DGX needs to run.
#
# Mac is authoritative for code AND for git history. The DGX is a
# pure execution target — no .git, no commits, no version control there.
# Strict scope — never sync .git, .venv, generated artifacts, secrets.
#
# Usage:  bash sync/push.sh
#         SPARK_HOST=other@host bash sync/push.sh    # override target
#         REMOTE_DIR=/elsewhere bash sync/push.sh    # override path

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"

echo "[push] local  = $LOCAL_DIR"
echo "[push] spark  = $SPARK"
echo "[push] remote = $REMOTE_DIR"

ssh "$SPARK" "mkdir -p '$REMOTE_DIR'"

# rsync — keep what the DGX needs to run + iterate; drop everything else.
# Specifically excluded:
#   .git/        ← Mac-only; DGX is execution-target, not a git source
#   .venv/       ← uv recreates this on DGX side
#   __pycache__/ ← regenerable
#   exports/     ← DGX writes these
#   run.log      ← DGX writes this
#   results.tsv  ← Mac writes this (Mac runs the loop; DGX runs train.py)
#   audit/       ← Mac-side artifact dir
#   .cache/      ← HF cache; lives in $HOME/.cache on each side
rsync -avz --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='exports/' \
  --exclude='run.log' \
  --exclude='results.tsv' \
  --exclude='.cache/' \
  --exclude='audit/' \
  "$LOCAL_DIR/" "$SPARK:$REMOTE_DIR/"

echo "[push] done — DGX has the latest code at $REMOTE_DIR"
echo
echo "next:"
echo "  bash sync/run.sh                   # remote train.py + pull run.log"
echo "  bash sync/spark_setup.sh           # one-time: install uv on spark"
