#!/usr/bin/env bash
## sync/push.sh — Mac → Spark code push.
##
## SCOPE: Mac is authoritative for code AND git history. The DGX is a
## pure execution target — no .git, no commits, no version control there.
## We rsync the bits the DGX needs to run; we never push the DGX clone
## back as a git source.
##
## Excludes (in order of why):
##   .git/ .gitignore       ← Mac-only; DGX is execution target
##   .venv/                 ← uv recreates this on DGX
##   __pycache__/ *.pyc     ← regenerable
##   .DS_Store              ← macOS junk
##   .env .env.* *.env      ← secrets stay on Mac (defense-in-depth)
##   exports/               ← DGX writes these
##   run.log                ← DGX writes this
##   results.tsv            ← Mac writes this (loop runs Mac-side)
##   audit/                 ← Mac-side artifact archive
##   .cache/                ← HF cache; lives in $HOME on each side
##
## Convention shared with ../../dgx repo's sync-to-spark.sh — see
## sync/README.md for the full convention.
##
## Usage:
##   bash sync/push.sh
##   SPARK_HOST=other@host bash sync/push.sh           # override target
##   REMOTE_DIR=/elsewhere bash sync/push.sh           # override path

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "[push→spark] $TS — $LOCAL_DIR  →  $SPARK:$REMOTE_DIR"

ssh "$SPARK" "mkdir -p '$REMOTE_DIR'"

rsync -avz --delete \
  --exclude='.git/' \
  --exclude='.gitignore' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='.env' --exclude='.env.*' --exclude='*.env' \
  --exclude='exports/' \
  --exclude='run.log' \
  --exclude='results.tsv' \
  --exclude='audit/' \
  --exclude='.cache/' \
  "$LOCAL_DIR/" "$SPARK:$REMOTE_DIR/"

echo "[push→spark] done"
echo
echo "next:"
echo "  bash sync/spark_setup.sh           # one-time: uv + uv sync + prepare.py on Spark"
echo "  bash sync/run.sh                   # remote train.py + pull run.log"
