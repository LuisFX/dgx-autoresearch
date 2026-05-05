#!/usr/bin/env bash
# One-time DGX setup: ensure uv installed + dependencies resolved + data prepared.
# Run from Mac after the first sync/push.sh.
#
# Idempotent — re-runs are cheap (uv sync no-op if synced; prepare.py
# no-op if data cached).
#
# Usage:  bash sync/spark_setup.sh

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"

ssh "$SPARK" "
  set -e
  cd '$REMOTE_DIR'

  # 1) uv (one-time install if missing)
  if ! command -v uv >/dev/null 2>&1; then
    echo '[setup] installing uv on DGX (one-time)'
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source \"\$HOME/.local/bin/env\" 2>/dev/null || source \"\$HOME/.cargo/env\" 2>/dev/null || true
  fi
  uv --version

  echo
  echo '[setup] uv sync (cu130 torch + deps; few minutes first time)'
  uv sync 2>&1 | tail -10

  echo
  echo '[setup] uv run prepare.py (data download + tokenizer; ~2 min first time)'
  uv run prepare.py 2>&1 | tail -10

  echo
  echo '[setup] DGX is ready. Verify with: bash sync/run.sh   (from Mac)'
"
