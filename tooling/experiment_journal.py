"""
Experiment journal for autoresearch on GB10 Blackwell.
Captures the full story of each experiment: hypothesis, diff, results, metrics.

Each experiment is one JSON file (~2-10KB). Metrics are summarized, not raw.
Raw metrics stay in metrics/ JSONL files for deep-dive analysis.

Usage:
    journal = ExperimentJournal("../results/journal")

    with journal.experiment("halve batch size for more steps") as exp:
        exp.hypothesis("GB10 is step-limited. 2x steps with half batch may help.")
        exp.record_config_change("TOTAL_BATCH_SIZE", "2**19", "2**18")
        exp.record_diff(diff_text)

        # ... run training ...

        exp.record_results(val_bpb=1.45, memory_gb=44.0, mfu=16.0, ...)
        exp.record_metrics_summary(metrics_file)  # summarizes, doesn't copy
        exp.decision("keep", "val_bpb improved by 0.01")
"""

import json
import os
import subprocess
import statistics
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Experiment:
    """A single experiment record."""

    def __init__(self, exp_id, description, journal_dir):
        self.data = {
            "id": exp_id,
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypothesis": None,
            "config_changes": [],
            "diff": None,
            "diff_stats": None,
            "commit": None,
            "results": {},
            "metrics_summary": {},
            "decision": None,
            "decision_reasoning": None,
            "agent_notes": [],
            "duration_seconds": {},
            "error": None,
        }
        self._journal_dir = journal_dir
        self._t_start = time.time()
        self._phase_start = None
        self._current_phase = None

    def hypothesis(self, text):
        self.data["hypothesis"] = text

    def note(self, text):
        """Free-form agent observation."""
        self.data["agent_notes"].append({
            "time": round(time.time() - self._t_start, 1),
            "text": text
        })

    def record_config_change(self, param, old_val, new_val):
        self.data["config_changes"].append({
            "param": param,
            "old": str(old_val),
            "new": str(new_val),
        })

    def record_diff(self, diff_text):
        """Store the git diff. Truncate if huge."""
        lines = diff_text.strip().split("\n")
        self.data["diff_stats"] = {
            "lines_added": sum(1 for l in lines if l.startswith("+")),
            "lines_removed": sum(1 for l in lines if l.startswith("-")),
            "total_lines": len(lines),
        }
        # Keep diff but cap at 5KB to prevent bloat
        if len(diff_text) > 5000:
            self.data["diff"] = diff_text[:5000] + "\n... [truncated]"
        else:
            self.data["diff"] = diff_text

    def record_commit(self, commit_hash):
        self.data["commit"] = commit_hash

    def start_phase(self, phase_name):
        """Time a phase (e.g., 'training', 'compilation', 'evaluation')."""
        if self._current_phase:
            self.end_phase()
        self._current_phase = phase_name
        self._phase_start = time.time()

    def end_phase(self):
        if self._current_phase and self._phase_start:
            self.data["duration_seconds"][self._current_phase] = round(
                time.time() - self._phase_start, 1
            )
        self._current_phase = None
        self._phase_start = None

    def record_results(self, **kwargs):
        """Record training results (val_bpb, memory_gb, mfu, etc.)."""
        self.data["results"] = kwargs

    def record_results_from_log(self, log_path):
        """Parse results from train.py output log."""
        results = {}
        try:
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    for key in ["val_bpb", "training_seconds", "total_seconds",
                                "peak_vram_mb", "mfu_percent", "total_tokens_M",
                                "num_steps", "num_params_M", "depth"]:
                        if line.startswith(f"{key}:"):
                            val = line.split(":")[1].strip()
                            try:
                                results[key] = float(val)
                            except ValueError:
                                results[key] = val
        except FileNotFoundError:
            results["error"] = "log file not found"

        if "peak_vram_mb" in results:
            results["memory_gb"] = round(results["peak_vram_mb"] / 1024, 1)

        self.data["results"] = results

    def record_metrics_summary(self, metrics_jsonl_path):
        """Summarize system metrics into key stats (no raw data copied)."""
        try:
            metrics = []
            with open(metrics_jsonl_path) as f:
                for line in f:
                    try:
                        metrics.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            if not metrics:
                return

            summary = {"sample_count": len(metrics)}

            for key, label in [
                ("gpu_temp_c", "gpu_temp"),
                ("gpu_util_pct", "gpu_util"),
                ("gpu_power_w", "gpu_power"),
                ("cpu_util_pct", "cpu_util"),
                ("ram_used_gb", "ram_used"),
            ]:
                vals = [m[key] for m in metrics if key in m and m[key] is not None]
                if vals:
                    summary[label] = {
                        "min": round(min(vals), 1),
                        "max": round(max(vals), 1),
                        "mean": round(statistics.mean(vals), 1),
                        "p50": round(sorted(vals)[len(vals)//2], 1),
                    }

            self.data["metrics_summary"] = summary
        except FileNotFoundError:
            self.data["metrics_summary"] = {"error": "metrics file not found"}

    def record_error(self, error_text):
        """Record crash/error info. Truncate to keep small."""
        if len(error_text) > 2000:
            error_text = error_text[-2000:]
        self.data["error"] = error_text

    def decision(self, status, reasoning):
        """Record keep/discard/crash decision with reasoning."""
        self.data["decision"] = status
        self.data["decision_reasoning"] = reasoning

    def save(self):
        self.end_phase()
        self.data["duration_seconds"]["total"] = round(time.time() - self._t_start, 1)

        path = os.path.join(self._journal_dir, f"exp_{self.data['id']:03d}.json")
        with open(path, "w") as f:
            json.dump(self.data, f, indent=2)

        size_kb = os.path.getsize(path) / 1024
        return path, size_kb


class ExperimentJournal:
    """Manages the collection of experiment records."""

    def __init__(self, journal_dir):
        self.journal_dir = journal_dir
        os.makedirs(journal_dir, exist_ok=True)
        self._next_id = self._find_next_id()

    def _find_next_id(self):
        existing = list(Path(self.journal_dir).glob("exp_*.json"))
        if not existing:
            return 0
        ids = []
        for p in existing:
            try:
                ids.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return max(ids) + 1 if ids else 0

    @contextmanager
    def experiment(self, description):
        exp = Experiment(self._next_id, description, self.journal_dir)
        try:
            yield exp
        finally:
            path, size_kb = exp.save()
            self._next_id += 1
            print(f"  Journal: saved {path} ({size_kb:.1f} KB)")

    def load_all(self):
        """Load all experiments, sorted by ID."""
        experiments = []
        for p in sorted(Path(self.journal_dir).glob("exp_*.json")):
            with open(p) as f:
                experiments.append(json.load(f))
        return experiments

    def summary(self):
        """Quick summary of all experiments."""
        exps = self.load_all()
        if not exps:
            return "No experiments recorded yet."

        lines = [f"Total: {len(exps)} experiments"]
        keeps = [e for e in exps if e.get("decision") == "keep"]
        discards = [e for e in exps if e.get("decision") == "discard"]
        crashes = [e for e in exps if e.get("decision") == "crash"]
        lines.append(f"  Kept: {len(keeps)}, Discarded: {len(discards)}, Crashed: {len(crashes)}")

        best = None
        for e in exps:
            bpb = e.get("results", {}).get("val_bpb")
            if bpb and bpb > 0:
                if best is None or bpb < best:
                    best = bpb
        if best:
            lines.append(f"  Best val_bpb: {best:.6f}")

        return "\n".join(lines)
