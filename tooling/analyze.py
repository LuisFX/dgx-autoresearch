"""
Analysis and visualization for autoresearch experiments on GB10 Blackwell.
Generates blog-worthy charts from results.tsv and system metrics.

Usage:
    python analyze.py                          # Generate all charts
    python analyze.py --results ../results.tsv # Custom results path
    python analyze.py --metrics-dir metrics/   # Custom metrics dir
"""

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# Color palette - dark theme for blog
BG_COLOR = "#1a1a2e"
FG_COLOR = "#e0e0e0"
ACCENT_1 = "#00d2ff"  # cyan
ACCENT_2 = "#7b2ff7"  # purple
ACCENT_3 = "#ff6b6b"  # red
ACCENT_4 = "#51cf66"  # green
ACCENT_5 = "#ffd43b"  # yellow
GRID_COLOR = "#2a2a4e"


def setup_style():
    plt.rcParams.update({
        "figure.facecolor": BG_COLOR,
        "axes.facecolor": BG_COLOR,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": FG_COLOR,
        "text.color": FG_COLOR,
        "xtick.color": FG_COLOR,
        "ytick.color": FG_COLOR,
        "grid.color": GRID_COLOR,
        "grid.alpha": 0.5,
        "font.family": "monospace",
        "font.size": 11,
        "figure.dpi": 150,
    })


def load_results(path):
    """Load results.tsv into a list of dicts."""
    results = []
    with open(path) as f:
        header = f.readline().strip().split("\t")
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 5:
                row = dict(zip(header, parts))
                row["val_bpb"] = float(row.get("val_bpb", 0))
                row["memory_gb"] = float(row.get("memory_gb", 0))
                results.append(row)
    return results


def load_metrics(metrics_file):
    """Load a JSONL metrics file."""
    metrics = []
    with open(metrics_file) as f:
        for line in f:
            try:
                metrics.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return metrics


def plot_val_bpb_progression(results, output_dir):
    """val_bpb over experiments, highlighting keeps vs discards."""
    setup_style()
    fig, ax = plt.subplots(figsize=(14, 6))

    exps = list(range(len(results)))
    bpbs = [r["val_bpb"] for r in results]
    statuses = [r.get("status", "unknown") for r in results]

    # Best-so-far line
    best_so_far = []
    current_best = float("inf")
    for b in bpbs:
        if b > 0 and b < current_best:
            current_best = b
        best_so_far.append(current_best if current_best < float("inf") else None)

    # Plot all points
    for i, (x, b, s) in enumerate(zip(exps, bpbs, statuses)):
        if b == 0:
            ax.scatter(x, max(bpbs) * 1.02, color=ACCENT_3, marker="x", s=80, zorder=5, label="crash" if i == 0 or "crash" not in [statuses[j] for j in range(i)] else "")
        elif s == "keep":
            ax.scatter(x, b, color=ACCENT_4, s=80, zorder=5, edgecolors="white", linewidths=0.5)
        else:
            ax.scatter(x, b, color=ACCENT_3, s=40, zorder=4, alpha=0.6)

    # Best-so-far line
    valid_best = [(i, b) for i, b in enumerate(best_so_far) if b is not None]
    if valid_best:
        ax.step([v[0] for v in valid_best], [v[1] for v in valid_best],
                where="post", color=ACCENT_1, linewidth=2, alpha=0.8, label="Best so far")

    ax.set_xlabel("Experiment #")
    ax.set_ylabel("val_bpb (lower = better)")
    ax.set_title("Autoresearch: val_bpb Progression on GB10 Blackwell", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)

    # Legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ACCENT_4, markersize=10, label="Keep (improved)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ACCENT_3, markersize=8, alpha=0.6, label="Discard (worse)"),
        Line2D([0], [0], marker="x", color=ACCENT_3, markersize=10, linestyle="None", label="Crash"),
        Line2D([0], [0], color=ACCENT_1, linewidth=2, label="Best so far"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", facecolor=BG_COLOR, edgecolor=GRID_COLOR)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "val_bpb_progression.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved val_bpb_progression.png")


def plot_memory_usage(results, output_dir):
    """Memory usage across experiments."""
    setup_style()
    fig, ax = plt.subplots(figsize=(14, 5))

    exps = list(range(len(results)))
    mems = [r["memory_gb"] for r in results]
    statuses = [r.get("status", "unknown") for r in results]

    colors = [ACCENT_4 if s == "keep" else (ACCENT_3 if s == "crash" else ACCENT_5) for s in statuses]
    ax.bar(exps, mems, color=colors, alpha=0.8, edgecolor="white", linewidth=0.3)

    ax.axhline(y=128, color=ACCENT_3, linestyle="--", alpha=0.5, label="GB10 VRAM limit (128 GB)")
    ax.set_xlabel("Experiment #")
    ax.set_ylabel("Peak VRAM (GB)")
    ax.set_title("Peak GPU Memory per Experiment", fontsize=14, fontweight="bold")
    ax.legend(facecolor=BG_COLOR, edgecolor=GRID_COLOR)
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "memory_usage.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved memory_usage.png")


def plot_system_metrics(metrics_file, output_dir, run_label=""):
    """Plot GPU temp, utilization, power, CPU, RAM from a single run's metrics."""
    metrics = load_metrics(metrics_file)
    if not metrics:
        return

    setup_style()
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))

    t0 = metrics[0]["timestamp"]
    times = [(m["timestamp"] - t0) / 60 for m in metrics]  # minutes

    def safe_get(m, key):
        return m.get(key)

    # GPU Temperature
    ax = axes[0, 0]
    vals = [safe_get(m, "gpu_temp_c") for m in metrics]
    valid = [(t, v) for t, v in zip(times, vals) if v is not None]
    if valid:
        ax.plot([v[0] for v in valid], [v[1] for v in valid], color=ACCENT_3, linewidth=1)
        ax.set_ylabel("Temperature (C)")
        ax.set_title("GPU Temperature")
        ax.grid(True, alpha=0.3)

    # GPU Utilization
    ax = axes[0, 1]
    vals = [safe_get(m, "gpu_util_pct") for m in metrics]
    valid = [(t, v) for t, v in zip(times, vals) if v is not None]
    if valid:
        ax.fill_between([v[0] for v in valid], [v[1] for v in valid], color=ACCENT_1, alpha=0.3)
        ax.plot([v[0] for v in valid], [v[1] for v in valid], color=ACCENT_1, linewidth=1)
        ax.set_ylabel("Utilization (%)")
        ax.set_title("GPU Utilization")
        ax.set_ylim(0, 105)
        ax.grid(True, alpha=0.3)

    # GPU Power
    ax = axes[1, 0]
    vals = [safe_get(m, "gpu_power_w") for m in metrics]
    valid = [(t, v) for t, v in zip(times, vals) if v is not None]
    if valid:
        ax.plot([v[0] for v in valid], [v[1] for v in valid], color=ACCENT_5, linewidth=1)
        ax.set_ylabel("Power (W)")
        ax.set_title("GPU Power Draw")
        ax.grid(True, alpha=0.3)

    # CPU Utilization
    ax = axes[1, 1]
    vals = [safe_get(m, "cpu_util_pct") for m in metrics]
    valid = [(t, v) for t, v in zip(times, vals) if v is not None]
    if valid:
        ax.fill_between([v[0] for v in valid], [v[1] for v in valid], color=ACCENT_2, alpha=0.3)
        ax.plot([v[0] for v in valid], [v[1] for v in valid], color=ACCENT_2, linewidth=1)
        ax.set_ylabel("CPU (%)")
        ax.set_title("CPU Utilization")
        ax.set_ylim(0, 105)
        ax.grid(True, alpha=0.3)

    # RAM Usage
    ax = axes[2, 0]
    used = [safe_get(m, "ram_used_gb") for m in metrics]
    cached = [safe_get(m, "ram_cached_gb") for m in metrics]
    valid_used = [(t, v) for t, v in zip(times, used) if v is not None]
    valid_cached = [(t, v) for t, v in zip(times, cached) if v is not None]
    if valid_used:
        ax.fill_between([v[0] for v in valid_used], [v[1] for v in valid_used], color=ACCENT_1, alpha=0.3, label="Used")
    if valid_cached:
        ax.plot([v[0] for v in valid_cached], [v[1] for v in valid_cached], color=ACCENT_5, linewidth=1, alpha=0.6, label="Cached")
    ax.set_ylabel("RAM (GB)")
    ax.set_title("System RAM")
    ax.set_xlabel("Time (minutes)")
    ax.legend(facecolor=BG_COLOR, edgecolor=GRID_COLOR)
    ax.grid(True, alpha=0.3)

    # GPU Clocks
    ax = axes[2, 1]
    sm = [safe_get(m, "gpu_sm_clock_mhz") for m in metrics]
    valid_sm = [(t, v) for t, v in zip(times, sm) if v is not None]
    if valid_sm:
        ax.plot([v[0] for v in valid_sm], [v[1] for v in valid_sm], color=ACCENT_4, linewidth=1, label="SM Clock")
        ax.set_ylabel("Clock (MHz)")
        ax.set_title("GPU Clock Speed")
        ax.set_xlabel("Time (minutes)")
        ax.legend(facecolor=BG_COLOR, edgecolor=GRID_COLOR)
        ax.grid(True, alpha=0.3)

    title = f"System Metrics: {run_label}" if run_label else "System Metrics During Training"
    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    name = f"system_metrics_{run_label}.png" if run_label else "system_metrics.png"
    fig.savefig(os.path.join(output_dir, name), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {name}")


def plot_improvement_waterfall(results, output_dir):
    """Waterfall chart showing cumulative improvement from baseline."""
    setup_style()
    keeps = [r for r in results if r.get("status") == "keep"]
    if len(keeps) < 2:
        return

    fig, ax = plt.subplots(figsize=(14, 6))

    baseline = keeps[0]["val_bpb"]
    labels = [r.get("description", f"exp {i}")[:30] for i, r in enumerate(keeps)]
    improvements = [0]
    for i in range(1, len(keeps)):
        improvements.append(keeps[i-1]["val_bpb"] - keeps[i]["val_bpb"])

    cumulative = [0]
    for imp in improvements[1:]:
        cumulative.append(cumulative[-1] + imp)

    colors = [ACCENT_4 if imp >= 0 else ACCENT_3 for imp in improvements]

    bars = ax.bar(range(len(keeps)), improvements, color=colors, alpha=0.8, edgecolor="white", linewidth=0.3)

    # Annotate cumulative improvement
    for i, (c, imp) in enumerate(zip(cumulative, improvements)):
        if i > 0 and imp != 0:
            ax.annotate(f"{imp:+.4f}", (i, imp), textcoords="offset points",
                       xytext=(0, 10 if imp > 0 else -15), ha="center", fontsize=8, color=FG_COLOR)

    ax.set_xticks(range(len(keeps)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("val_bpb improvement (per step)")
    ax.set_title(f"Improvement Waterfall (baseline: {baseline:.4f}, final: {keeps[-1]['val_bpb']:.4f})",
                fontsize=14, fontweight="bold")
    ax.axhline(y=0, color=FG_COLOR, linewidth=0.5, alpha=0.5)
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "improvement_waterfall.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved improvement_waterfall.png")


def plot_pareto_frontier(results, output_dir):
    """val_bpb vs memory Pareto frontier."""
    setup_style()
    valid = [r for r in results if r["val_bpb"] > 0 and r["memory_gb"] > 0]
    if not valid:
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    for r in valid:
        color = ACCENT_4 if r.get("status") == "keep" else ACCENT_3
        ax.scatter(r["memory_gb"], r["val_bpb"], color=color, s=60, alpha=0.7, edgecolors="white", linewidths=0.3)

    # Pareto frontier
    sorted_by_mem = sorted(valid, key=lambda r: r["memory_gb"])
    pareto = []
    best_bpb = float("inf")
    for r in sorted_by_mem:
        if r["val_bpb"] < best_bpb:
            best_bpb = r["val_bpb"]
            pareto.append(r)
    if pareto:
        ax.plot([r["memory_gb"] for r in pareto], [r["val_bpb"] for r in pareto],
                color=ACCENT_1, linewidth=2, alpha=0.6, linestyle="--", label="Pareto frontier")

    ax.set_xlabel("Peak VRAM (GB)")
    ax.set_ylabel("val_bpb (lower = better)")
    ax.set_title("Quality vs Memory Tradeoff", fontsize=14, fontweight="bold")
    ax.legend(facecolor=BG_COLOR, edgecolor=GRID_COLOR)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "pareto_frontier.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved pareto_frontier.png")


def generate_summary_table(results, output_path):
    """Generate a markdown summary table."""
    keeps = [r for r in results if r.get("status") == "keep"]
    discards = [r for r in results if r.get("status") == "discard"]
    crashes = [r for r in results if r.get("status") == "crash"]

    best = min((r for r in results if r["val_bpb"] > 0), key=lambda r: r["val_bpb"], default=None)
    baseline = results[0] if results else None

    lines = [
        "# GB10 Blackwell Autoresearch Results Summary",
        "",
        "## Overview",
        f"- **Total experiments:** {len(results)}",
        f"- **Kept (improved):** {len(keeps)}",
        f"- **Discarded:** {len(discards)}",
        f"- **Crashes:** {len(crashes)}",
        f"- **Success rate:** {len(keeps)/max(len(results),1)*100:.0f}%",
        "",
    ]

    if baseline and best:
        improvement = baseline["val_bpb"] - best["val_bpb"]
        lines.extend([
            "## Best Result",
            f"- **Baseline val_bpb:** {baseline['val_bpb']:.6f}",
            f"- **Best val_bpb:** {best['val_bpb']:.6f}",
            f"- **Improvement:** {improvement:.6f} ({improvement/baseline['val_bpb']*100:.2f}%)",
            f"- **Best memory:** {best['memory_gb']:.1f} GB",
            f"- **Description:** {best.get('description', 'N/A')}",
            "",
        ])

    lines.extend([
        "## All Experiments",
        "",
        "| # | Commit | val_bpb | Memory (GB) | Status | Description |",
        "|---|--------|---------|-------------|--------|-------------|",
    ])
    for i, r in enumerate(results):
        status_icon = {"keep": "++", "discard": "--", "crash": "XX"}.get(r.get("status", ""), "??")
        lines.append(f"| {i} | `{r.get('commit', 'N/A')[:7]}` | {r['val_bpb']:.6f} | {r['memory_gb']:.1f} | {status_icon} | {r.get('description', '')} |")

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved {output_path}")


def generate_journal_report(journal_dir, output_path):
    """Generate a rich markdown report from experiment journal JSON files."""
    from experiment_journal import ExperimentJournal
    journal = ExperimentJournal(journal_dir)
    exps = journal.load_all()
    if not exps:
        return

    lines = [
        "# GB10 Blackwell Autoresearch: Agent Journal",
        "",
        f"**Experiments:** {len(exps)} | "
        f"**Kept:** {sum(1 for e in exps if e.get('decision')=='keep')} | "
        f"**Discarded:** {sum(1 for e in exps if e.get('decision')=='discard')} | "
        f"**Crashed:** {sum(1 for e in exps if e.get('decision')=='crash')}",
        "",
    ]

    best_bpb = float("inf")
    for e in exps:
        bpb = (e.get("results") or {}).get("val_bpb", 0) or 0
        exp_id = e.get("id", "?")
        desc = e.get("description", "")
        decision = e.get("decision", "?")
        reasoning = e.get("decision_reasoning", "")
        hyp = e.get("hypothesis", "")

        if bpb > 0 and bpb < best_bpb:
            best_bpb = bpb
            marker = " << NEW BEST"
        else:
            marker = ""

        status_icon = {"keep": "+", "discard": "x", "crash": "!!"}.get(decision, "?")

        lines.append(f"---")
        lines.append(f"### Experiment {exp_id}: {desc}")
        lines.append(f"**Decision:** [{status_icon}] {decision}{marker}")
        lines.append(f"")
        if hyp:
            lines.append(f"**Hypothesis:** {hyp}")
            lines.append(f"")

        # Config changes
        changes = e.get("config_changes", [])
        if changes:
            lines.append("**Changes:**")
            for c in (changes or []):
                if isinstance(c, dict):
                    lines.append(f"- `{c.get('param','')}`: {c.get('old','')} -> {c.get('new','')}")
                else:
                    lines.append(f"- {c}")
            lines.append("")

        # Results
        results = e.get("results", {})
        if results:
            bpb_str = f"{results.get('val_bpb', 0):.6f}" if results.get("val_bpb") else "N/A"
            mem_str = f"{results.get('memory_gb', 0):.1f} GB" if results.get("memory_gb") else "N/A"
            mfu_str = f"{results.get('mfu_percent', 0):.1f}%" if results.get("mfu_percent") else "N/A"
            steps_str = f"{int(results.get('num_steps', 0))}" if results.get("num_steps") else "N/A"
            lines.append(f"**Results:** val_bpb={bpb_str} | mem={mem_str} | MFU={mfu_str} | steps={steps_str}")
            lines.append("")

        if reasoning:
            lines.append(f"**Reasoning:** {reasoning}")
            lines.append("")

        # Agent notes
        notes = e.get("agent_notes", [])
        for note in (notes or []):
            text = note.get('text', '') if isinstance(note, dict) else str(note)
            lines.append(f"> {text}")
        if notes:
            lines.append("")

        # Metrics summary
        ms = e.get("metrics_summary", {})
        if ms and "gpu_temp" in ms:
            gpu_t = ms["gpu_temp"]
            gpu_p = ms.get("gpu_power", {})
            lines.append(f"**System:** GPU temp {gpu_t.get('mean',0):.0f}C (max {gpu_t.get('max',0):.0f}C)"
                        f" | Power {gpu_p.get('mean',0):.0f}W (max {gpu_p.get('max',0):.0f}W)")
            lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze autoresearch results")
    parser.add_argument("--results", default="../results.tsv", help="Path to results.tsv")
    parser.add_argument("--metrics-dir", default="../results/metrics/", help="Directory with metric JSONL files")
    parser.add_argument("--output-dir", default="../results/charts/", help="Output directory for charts")
    parser.add_argument("--journal-dir", default="../results/journal/", help="Experiment journal dir")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # Results analysis
    if os.path.exists(args.results):
        print("Generating results charts...")
        results = load_results(args.results)
        if results:
            plot_val_bpb_progression(results, output_dir)
            plot_memory_usage(results, output_dir)
            plot_improvement_waterfall(results, output_dir)
            plot_pareto_frontier(results, output_dir)
            generate_summary_table(results, os.path.join(output_dir, "SUMMARY.md"))
        else:
            print("  No results found in TSV")
    else:
        print(f"  Results file not found: {args.results}")

    # Journal report
    if os.path.isdir(args.journal_dir):
        print("Generating journal report...")
        generate_journal_report(args.journal_dir, os.path.join(output_dir, "JOURNAL.md"))
    else:
        print(f"  Journal directory not found: {args.journal_dir}")

    # System metrics analysis
    metrics_dir = args.metrics_dir
    if os.path.isdir(metrics_dir):
        print("Generating system metrics charts...")
        for f in sorted(Path(metrics_dir).glob("*.jsonl")):
            label = f.stem
            plot_system_metrics(str(f), output_dir, run_label=label)
    else:
        print(f"  Metrics directory not found: {metrics_dir}")

    print("Done!")


if __name__ == "__main__":
    main()
