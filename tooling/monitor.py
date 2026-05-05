"""
Background system monitor for autoresearch experiments on GB10.
Captures GPU, CPU, RAM metrics at 1-second intervals during training runs.

Usage:
    # Start monitoring in background
    python monitor.py start --output metrics/run_001.jsonl

    # Stop monitoring
    python monitor.py stop

    # Or use as a context manager in Python
    from monitor import SystemMonitor
    with SystemMonitor("metrics/run_001.jsonl"):
        subprocess.run(["uv", "run", "train.py"])
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PID_FILE = "/tmp/autoresearch_monitor.pid"


def collect_metrics():
    """Collect a single snapshot of system metrics."""
    metrics = {"timestamp": time.time()}

    # GPU metrics via nvidia-smi (temp, utilization, power, clock)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,power.draw,clocks.current.sm,clocks.current.memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            metrics["gpu_temp_c"] = int(parts[0]) if parts[0] != "[N/A]" else None
            metrics["gpu_util_pct"] = int(parts[1]) if parts[1] != "[N/A]" else None
            metrics["gpu_power_w"] = float(parts[2]) if parts[2] != "[N/A]" else None
            metrics["gpu_sm_clock_mhz"] = int(parts[3]) if parts[3] != "[N/A]" else None
            metrics["gpu_mem_clock_mhz"] = int(parts[4]) if parts[4] != "[N/A]" else None
    except Exception:
        pass

    # GPU memory via PyTorch (nvidia-smi memory is unreliable on GB10)
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import torch; print(torch.cuda.memory_allocated(0), torch.cuda.memory_reserved(0), torch.cuda.max_memory_allocated(0))"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            metrics["gpu_mem_allocated_gb"] = round(int(parts[0]) / 1e9, 2)
            metrics["gpu_mem_reserved_gb"] = round(int(parts[1]) / 1e9, 2)
            metrics["gpu_mem_peak_gb"] = round(int(parts[2]) / 1e9, 2)
    except Exception:
        pass

    # CPU and RAM via /proc
    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()
            metrics["cpu_load_1m"] = float(load[0])
            metrics["cpu_load_5m"] = float(load[1])
    except Exception:
        pass

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                key = parts[0].strip()
                val = int(parts[1].strip().split()[0])  # kB
                meminfo[key] = val
            metrics["ram_total_gb"] = round(meminfo.get("MemTotal", 0) / 1e6, 2)
            metrics["ram_used_gb"] = round((meminfo.get("MemTotal", 0) - meminfo.get("MemAvailable", 0)) / 1e6, 2)
            metrics["ram_available_gb"] = round(meminfo.get("MemAvailable", 0) / 1e6, 2)
            metrics["ram_cached_gb"] = round(meminfo.get("Cached", 0) / 1e6, 2)
    except Exception:
        pass

    # CPU utilization from /proc/stat (instantaneous)
    try:
        with open("/proc/stat") as f:
            line = f.readline()
            parts = line.split()[1:]
            total = sum(int(x) for x in parts)
            idle = int(parts[3])
            metrics["_cpu_total"] = total
            metrics["_cpu_idle"] = idle
    except Exception:
        pass

    return metrics


def run_monitor(output_path, interval=1.0):
    """Run the monitoring loop, writing JSONL to output_path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    prev_cpu = None

    with open(output_path, "w") as f:
        while True:
            metrics = collect_metrics()

            # Calculate CPU % from delta
            if prev_cpu and "_cpu_total" in metrics:
                dt = metrics["_cpu_total"] - prev_cpu[0]
                di = metrics["_cpu_idle"] - prev_cpu[1]
                if dt > 0:
                    metrics["cpu_util_pct"] = round(100 * (1 - di / dt), 1)

            if "_cpu_total" in metrics:
                prev_cpu = (metrics.pop("_cpu_total"), metrics.pop("_cpu_idle"))

            f.write(json.dumps(metrics) + "\n")
            f.flush()

            time.sleep(interval)


def start_daemon(output_path):
    """Start monitor as a background process."""
    pid = os.fork()
    if pid > 0:
        # Parent
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
        print(f"Monitor started (PID {pid}), writing to {output_path}")
        return pid
    else:
        # Child - become daemon
        os.setsid()
        try:
            run_monitor(output_path)
        except KeyboardInterrupt:
            pass
        sys.exit(0)


def stop_daemon():
    """Stop the background monitor."""
    if not os.path.exists(PID_FILE):
        print("No monitor running")
        return
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Monitor stopped (PID {pid})")
    except ProcessLookupError:
        print(f"Monitor process {pid} already gone")
    os.unlink(PID_FILE)


class SystemMonitor:
    """Context manager for monitoring during a training run."""

    def __init__(self, output_path, interval=1.0):
        self.output_path = output_path
        self.interval = interval
        self.pid = None

    def __enter__(self):
        self.pid = start_daemon(self.output_path)
        return self

    def __exit__(self, *args):
        stop_daemon()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start")
    start.add_argument("--output", "-o", required=True)
    start.add_argument("--interval", type=float, default=1.0)

    sub.add_parser("stop")

    args = parser.parse_args()

    if args.command == "start":
        start_daemon(args.output)
    elif args.command == "stop":
        stop_daemon()
    else:
        parser.print_help()
