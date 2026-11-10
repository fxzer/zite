#!/usr/bin/env python3
"""
Normalized macOS Memory Benchmark for Zed and Zed Lite
Measures physical footprint (using macOS footprint tool) across:
1. Main editor process (Idle & Workspace)
2. Process tree (Editor + Language Servers / Child processes)
3. Peak physical footprint & category breakdown (Malloc Small/Large, IOSurface, IOAccelerator)
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time


def get_descendant_pids(root_pid):
    pids = [root_pid]
    try:
        output = subprocess.check_output(["pgrep", "-P", str(root_pid)], text=True, stderr=subprocess.DEVNULL)
        for child in output.strip().split():
            if child.isdigit():
                pids.extend(get_descendant_pids(int(child)))
    except subprocess.CalledProcessError:
        pass
    return sorted(list(set(pids)))


def capture_footprint(pids):
    if not pids:
        return None
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        cmd = ["footprint", "-j", str(temp_path), "-p"] + [str(p) for p in pids]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        if res.returncode != 0 or not temp_path.exists():
            return None
        data = json.loads(temp_path.read_text())
        return data
    except Exception:
        return None
    finally:
        if temp_path.exists():
            temp_path.unlink()


def parse_footprint_data(data, main_pid):
    if not data or "processes" not in data:
        return None
    main_proc = None
    children_footprint = 0
    total_footprint = data.get("total footprint", 0)

    for proc in data.get("processes", []):
        if proc.get("pid") == main_pid:
            main_proc = proc
        else:
            children_footprint += proc.get("footprint", 0)

    if not main_proc:
        return None

    main_footprint = main_proc.get("footprint", 0)
    main_peak = main_proc.get("auxiliary", {}).get("phys_footprint_peak", main_footprint)
    categories = main_proc.get("categories", {})

    def get_cat_mb(name):
        return categories.get(name, {}).get("dirty", 0) / (1024 * 1024)

    return {
        "main_footprint_mb": main_footprint / (1024 * 1024),
        "main_peak_mb": main_peak / (1024 * 1024),
        "children_footprint_mb": children_footprint / (1024 * 1024),
        "total_footprint_mb": total_footprint / (1024 * 1024),
        "malloc_small_mb": get_cat_mb("Malloc Small"),
        "malloc_large_mb": get_cat_mb("Malloc Large"),
        "iosurface_mb": get_cat_mb("IOSurface"),
        "ioaccel_mb": get_cat_mb("IOAccelerator (graphics)"),
    }


def stop_process_tree(root_pid):
    pids = get_descendant_pids(root_pid)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in reversed(pids):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(0.5)
        # Check if root still alive
        try:
            os.kill(root_pid, 0)
        except ProcessLookupError:
            return


def run_single_measurement(name, binary_path, project_path, settle_time=25):
    temp_dir = tempfile.mkdtemp(prefix=f"zed_bench_{name}_")
    env = os.environ.copy()
    env["ZED_STATELESS"] = "1"
    env["ZED_WINDOW_SIZE"] = "1280,800"

    cmd = [str(binary_path), "--user-data-dir", temp_dir]
    if project_path:
        cmd.append(str(project_path))

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    measurements = []
    try:
        # Sample points during settling
        sample_intervals = [5, 10, 15, settle_time]
        last_t = 0
        for target_t in sample_intervals:
            wait_t = target_t - last_t
            if wait_t > 0:
                time.sleep(wait_t)
            last_t = target_t

            if proc.poll() is not None:
                raise RuntimeError(f"{name} exited unexpectedly with code {proc.returncode}")

            pids = get_descendant_pids(proc.pid)
            raw = capture_footprint(pids)
            parsed = parse_footprint_data(raw, proc.pid)
            if parsed:
                parsed["t_sec"] = target_t
                measurements.append(parsed)

        return measurements[-1] if measurements else None
    finally:
        stop_process_tree(proc.pid)
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Normalized macOS Memory Benchmark for Zed vs Zed Lite")
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs")
    parser.add_argument("--settle", type=int, default=20, help="Settle time in seconds per run")
    parser.add_argument("--project", type=Path, default=None, help="Project directory to open")
    parser.add_argument("--wu", type=Path, default=Path("/Applications/Zed Lite.app/Contents/MacOS/wu"))
    parser.add_argument("--zed", type=Path, default=Path("/Applications/Zed.app/Contents/MacOS/zed"))
    args = parser.parse_args()

    targets = [("Zed Lite", args.wu), ("Zed", args.zed)]
    for name, bin_path in targets:
        if not bin_path.exists() or not os.access(bin_path, os.X_OK):
            sys.exit(f"Binary not found or executable: {bin_path}")

    project_desc = str(args.project) if args.project else "Idle (Welcome Window)"
    print(f"=== Starting Memory Benchmark ===")
    print(f"Scenario: {project_desc}")
    print(f"Runs: {args.runs}, Settle Time: {args.settle}s per run\n")

    results = {"Zed Lite": [], "Zed": []}

    for run_idx in range(1, args.runs + 1):
        order = targets if run_idx % 2 == 1 else list(reversed(targets))
        for name, bin_path in order:
            print(f"Run {run_idx}/{args.runs}: Measuring {name}...", end="", flush=True)
            res = run_single_measurement(name, bin_path, args.project, settle_time=args.settle)
            if res:
                results[name].append(res)
                print(f" Done! Main: {res['main_footprint_mb']:.1f} MB (Peak: {res['main_peak_mb']:.1f} MB), Tree Total: {res['total_footprint_mb']:.1f} MB")
            else:
                print(" Failed to capture footprint.")
            time.sleep(2)

    print("\n" + "=" * 60)
    print(f"BENCHMARK SUMMARY (Median across {args.runs} runs)")
    print(f"Target Project: {project_desc}")
    print("=" * 60)

    summary = {}
    for name in ("Zed Lite", "Zed"):
        runs = results[name]
        if not runs:
            continue
        summary[name] = {
            "main_footprint": statistics.median([r["main_footprint_mb"] for r in runs]),
            "main_peak": statistics.median([r["main_peak_mb"] for r in runs]),
            "children": statistics.median([r["children_footprint_mb"] for r in runs]),
            "tree_total": statistics.median([r["total_footprint_mb"] for r in runs]),
            "malloc_small": statistics.median([r["malloc_small_mb"] for r in runs]),
            "malloc_large": statistics.median([r["malloc_large_mb"] for r in runs]),
            "iosurface": statistics.median([r["iosurface_mb"] for r in runs]),
            "ioaccel": statistics.median([r["ioaccel_mb"] for r in runs]),
        }

    # Print Table
    header = f"{'Metric (MB)':<30} | {'Zed Lite':<12} | {'Zed':<12} | {'Difference':<12}"
    print(header)
    print("-" * len(header))

    metrics_map = [
        ("Main App Footprint (Settled)", "main_footprint"),
        ("Main App Peak Footprint", "main_peak"),
        ("Language Servers / Children", "children"),
        ("Total Process Tree Footprint", "tree_total"),
        ("  - Malloc Small (Dirty)", "malloc_small"),
        ("  - Malloc Large (Dirty)", "malloc_large"),
        ("  - IOSurface (Metal/UI)", "iosurface"),
        ("  - IOAccelerator (GPU)", "ioaccel"),
    ]

    for label, key in metrics_map:
        val_lite = summary["Zed Lite"][key]
        val_zed = summary["Zed"][key]
        diff = val_lite - val_zed
        pct = (diff / val_zed) * 100 if val_zed else 0
        diff_str = f"{diff:+.1f} MB ({pct:+.1f}%)"
        print(f"{label:<30} | {val_lite:<12.1f} | {val_zed:<12.1f} | {diff_str:<12}")

    print("=" * 60)


if __name__ == "__main__":
    main()
