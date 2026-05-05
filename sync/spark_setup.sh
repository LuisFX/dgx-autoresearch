#!/usr/bin/env bash
## sync/spark_setup.sh — one-time DGX setup, runs from Mac via ssh.
##
## Idempotent — re-runs are cheap. Steps:
##   1. (if needed) install uv
##   2. uv sync — resolves PyTorch cu130 + deps; ~few minutes first time
##   3. uv run prepare.py — downloads training data + builds tokenizer
##   4. preflight check — confirm uv version, GPU, tmux, disk
##   5. print monitoring hints
##
## Preflight pattern adopted from ../../dgx repo's ship-parallel.sh —
## see sync/README.md for the cross-repo convention.
##
## Usage:  bash sync/spark_setup.sh

set -euo pipefail

SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "[setup] $TS — bringing up $SPARK:$REMOTE_DIR"

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
  echo '[preflight] sanity checks'
  command -v tmux >/dev/null && echo '  ✓ tmux available' || echo '  ⚠ tmux NOT installed — long runs lose ssh-disconnect resilience'
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader || echo '  ⚠ nvidia-smi missing'
  echo '  disk free at \$HOME:'
  df -h \"\$HOME\" | tail -1
  mkdir -p '$REMOTE_DIR/audit-runs'
  mkdir -p '$REMOTE_DIR/exports'
  echo '  ✓ audit-runs/ + exports/ ready'
"

echo
echo "[setup] DGX is ready. Verify end-to-end:"
echo "  bash sync/run.sh                    # 5-min smoke train.py"
echo
echo "Live web monitor (in another terminal):"
echo "  ssh $SPARK 'cd $REMOTE_DIR && uv run streamlit run dashboard.py \\"
echo "    --server.port 8088 --server.address 0.0.0.0 --server.headless true'"
echo "  open http://${SPARK#*@}:8088"
