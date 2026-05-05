"""Live web dashboard for dgx-autoresearch.

Streamlit app served on :8088. Mirrors litesearch's gui.py concepts but
web-native: live train log, val_bpb chart, VRAM bar, results.tsv viewer.

This MVP is read-only — it polls files on disk every refresh:
  run.log               — current training output (`uv run train.py > run.log`)
  results.tsv           — running scoreboard (one row per experiment)
  exports/*.pth         — saved checkpoints

Future iterations (when we want them):
  - hook log_queue/stop_event from train.run_training() for real-time
    streaming + cooperative stop without process restart
  - "Try it" panel that calls train.generate() against the latest export
  - Git-diff viewer comparing current train.py to last "keep" commit
  - Config-slider hint generator that writes lines to program.md

Usage on DGX:
    streamlit run dashboard.py \
      --server.port 8088 \
      --server.address 0.0.0.0 \
      --server.headless true

Then open http://spark-28cb.tail462c57.ts.net:8088 from any tailnet device.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
RUN_LOG = REPO_ROOT / "run.log"
RESULTS_TSV = REPO_ROOT / "results.tsv"
EXPORTS_DIR = REPO_ROOT / "exports"

# val_bpb line format from prepare.py / train.py:
#   val_bpb:          1.234567
VAL_BPB_RE = re.compile(r"^val_bpb:\s+([0-9.]+)", re.MULTILINE)
PEAK_VRAM_RE = re.compile(r"^peak_vram_mb:\s+([0-9.]+)", re.MULTILINE)
STEP_RE = re.compile(r"step (\d+)\s*\(([\d.]+)%\)")


# --------------------------------------------------------------------------- #
# data fetchers (cached; refresh on every rerun via st.rerun)                 #
# --------------------------------------------------------------------------- #


def tail_log(path: Path, n_lines: int = 200) -> str:
    if not path.exists():
        return "(no run.log yet — start a training run with: uv run train.py > run.log 2>&1)"
    try:
        # cheap tail via shell — works on Linux + macOS
        out = subprocess.check_output(
            ["tail", "-n", str(n_lines), str(path)], text=True
        )
        return out
    except Exception as e:
        return f"(tail failed: {e})"


def load_results_tsv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["commit", "val_bpb", "memory_gb", "status", "description"])
    try:
        df = pd.read_csv(path, sep="\t")
        return df
    except Exception:
        # try lenient parse — handle malformed rows
        return pd.read_csv(path, sep="\t", on_bad_lines="skip")


def get_gpu_state() -> dict:
    """Single-shot nvidia-smi snapshot. Returns {} if not available."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,utilization.memory,"
                "memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=2,
        )
        fields = [s.strip() for s in out.strip().split(",")]
        return {
            "name": fields[0],
            "util_gpu_pct": int(fields[1]) if fields[1].isdigit() else None,
            "util_mem_pct": int(fields[2]) if fields[2].isdigit() else None,
            "mem_used_mb": int(fields[3]) if fields[3].isdigit() else None,
            "mem_total_mb": int(fields[4]) if fields[4].isdigit() else None,
            "temp_c": int(fields[5]) if fields[5].isdigit() else None,
            "power_w": float(fields[6]) if fields[6] not in ("[N/A]", "N/A") else None,
        }
    except Exception as e:
        return {"error": str(e)}


def get_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "(unknown)"


def get_recent_commits(n: int = 10) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "log", f"-{n}", "--oneline"], cwd=REPO_ROOT, text=True
        )
        return out.strip().splitlines()
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# panel renderers                                                             #
# --------------------------------------------------------------------------- #


def render_header():
    st.set_page_config(
        page_title="dgx-autoresearch",
        page_icon="🧪",
        layout="wide",
    )
    st.markdown(
        "## 🧪 dgx-autoresearch — live monitor "
        f"<sub><sub>branch <code>{get_branch()}</code></sub></sub>",
        unsafe_allow_html=True,
    )


def render_gpu_panel(col):
    gpu = get_gpu_state()
    with col:
        st.subheader("GPU")
        if "error" in gpu:
            st.warning(f"nvidia-smi unavailable: {gpu['error']}")
            return
        st.text(gpu.get("name", "?"))
        cols = st.columns(3)
        cols[0].metric("util %", gpu.get("util_gpu_pct"))
        cols[1].metric("temp °C", gpu.get("temp_c"))
        cols[2].metric("power W", gpu.get("power_w"))
        if gpu.get("mem_total_mb"):
            used = gpu["mem_used_mb"] or 0
            total = gpu["mem_total_mb"]
            st.progress(used / total, text=f"VRAM (reported): {used} / {total} MB")
        else:
            # GB10/UMA reports memory.total as N/A; show host RAM instead
            st.caption("VRAM total reported as N/A — UMA architecture (GB10).")
            try:
                with open("/proc/meminfo") as f:
                    meminfo = f.read()
                free_kb = int(re.search(r"MemAvailable:\s+(\d+)", meminfo).group(1))
                total_kb = int(re.search(r"MemTotal:\s+(\d+)", meminfo).group(1))
                used = total_kb - free_kb
                st.progress(used / total_kb, text=f"Host mem: {used // 1024} / {total_kb // 1024} MB")
            except Exception:
                pass


def render_log_panel(col):
    with col:
        st.subheader("run.log (last 50 lines)")
        st.code(tail_log(RUN_LOG, n_lines=50), language="text")


def render_results_panel():
    st.subheader("results.tsv")
    df = load_results_tsv(RESULTS_TSV)
    if df.empty:
        st.info("(no experiments logged yet)")
        return
    # show key metrics + a chart
    cols = st.columns(4)
    cols[0].metric("experiments", len(df))
    if "val_bpb" in df.columns:
        non_crash = df[df["val_bpb"] > 0]
        if not non_crash.empty:
            best = non_crash["val_bpb"].min()
            cols[1].metric("best val_bpb", f"{best:.6f}")
            cols[2].metric("best vs schaferk 1.135", f"{(1.135 - best):+.4f}")
        if "status" in df.columns:
            n_keep = (df["status"] == "keep").sum()
            cols[3].metric("kept", f"{n_keep} / {len(df)}")

    # chart
    if "val_bpb" in df.columns:
        chart_df = df[df["val_bpb"] > 0].reset_index(drop=True)
        if not chart_df.empty:
            chart_df = chart_df[["val_bpb"]].rename_axis("experiment").reset_index()
            st.line_chart(chart_df.set_index("experiment"), height=200)

    # full table
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_commits_panel():
    st.subheader("Recent commits")
    commits = get_recent_commits(15)
    if not commits:
        st.info("(no commits to show)")
        return
    for c in commits:
        st.text(c)


def render_exports_panel():
    st.subheader("Exports")
    if not EXPORTS_DIR.exists():
        st.info("(no exports/ dir)")
        return
    pths = sorted(EXPORTS_DIR.glob("*.pth"))
    if not pths:
        st.info("(no .pth checkpoints yet)")
        return
    for p in pths[-10:]:
        size_mb = p.stat().st_size / 1024 / 1024
        st.text(f"{p.name}  ({size_mb:.1f} MB)")


# --------------------------------------------------------------------------- #
# main                                                                        #
# --------------------------------------------------------------------------- #


def main():
    render_header()

    # auto-refresh control
    refresh_s = st.sidebar.slider("Auto-refresh (sec)", 1, 30, 5)
    st.sidebar.caption(
        "Page polls run.log + results.tsv + nvidia-smi every refresh. "
        "Set to 1s for fast feedback during a live experiment; higher for less load."
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**MVP read-only dashboard.** Future: live `log_queue` stream + "
        "stop button + 'Try it' generate + git diff viewer."
    )

    top_left, top_right = st.columns([2, 1])
    render_log_panel(top_left)
    render_gpu_panel(top_right)

    st.markdown("---")
    render_results_panel()

    st.markdown("---")
    bot_left, bot_right = st.columns(2)
    with bot_left:
        render_commits_panel()
    with bot_right:
        render_exports_panel()

    # autorefresh
    time.sleep(refresh_s)
    st.rerun()


if __name__ == "__main__":
    main()
