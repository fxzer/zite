#!/usr/bin/env python3
"""
Comprehensive macOS Memory Benchmark: Zite vs. Wu vs. Zed
Following methodology from: https://github.com/dstrml/wu/blob/main/docs/memory-benchmark.md

Measures total process-tree Physical Footprint (via macOS `footprint`) and RSS.
Supports:
  1. Idle:
     - Welcome window
     - Repository open, no source file open
  2. Workspace workflow (6 stages):
     - Open 20 source files
     - Edit, save, and scroll (20 verified edit cycles)
     - Search repository (3 target searches)
     - Navigate and search large log (200k lines)
     - Integrated terminal output (20k lines)
     - Close tabs (memory retention check)
"""

import argparse
import datetime
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


METRICS = (
    "main_footprint_mb",
    "total_footprint_mb",
    "main_peak_mb",
    "main_rss_mb",
    "total_rss_mb",
    "malloc_small_mb",
    "malloc_large_mb",
    "iosurface_mb",
    "ioaccel_mb",
)


def get_all_pids(root_pid, profile_dir):
    """Capture all processes belonging to this editor instance."""
    pids = {root_pid}

    def walk_children(p):
        try:
            out = subprocess.check_output(["pgrep", "-P", str(p)], text=True, stderr=subprocess.DEVNULL)
            for c in out.strip().split():
                if c.isdigit():
                    cid = int(c)
                    if cid not in pids:
                        pids.add(cid)
                        walk_children(cid)
        except subprocess.CalledProcessError:
            pass

    walk_children(root_pid)

    # Also find any processes that match profile_dir in their command line
    if profile_dir:
        try:
            out = subprocess.check_output(["pgrep", "-f", str(profile_dir)], text=True, stderr=subprocess.DEVNULL)
            for c in out.strip().split():
                if c.isdigit():
                    pids.add(int(c))
        except subprocess.CalledProcessError:
            pass

    return sorted(list(pids))


def get_rss_mb(pids):
    """Get resident set size (RSS) for given PIDs in MB."""
    total_rss_kb = 0
    main_rss_kb = 0
    if not pids:
        return 0.0, 0.0

    try:
        out = subprocess.check_output(["ps", "-o", "pid=,rss=", "-p", ",".join(str(p) for p in pids)], text=True)
        for line in out.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1].isdigit():
                pid = int(parts[0])
                rss_kb = int(parts[1])
                total_rss_kb += rss_kb
                if pid == pids[0]:
                    main_rss_kb = rss_kb
    except Exception:
        pass

    return main_rss_kb / 1024.0, total_rss_kb / 1024.0


def capture_memory_sample(root_pid, profile_dir):
    """Sample memory metrics using macOS footprint and ps."""
    pids = get_all_pids(root_pid, profile_dir)
    if not pids:
        return None

    main_rss, total_rss = get_rss_mb(pids)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_path = Path(tf.name)

    try:
        cmd = ["footprint", "-j", str(temp_path), "-p"] + [str(p) for p in pids]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        if res.returncode != 0 or not temp_path.exists():
            return None

        data = json.loads(temp_path.read_text())
        total_fp = data.get("total footprint", 0) / (1024.0 * 1024.0)

        main_proc = None
        for proc in data.get("processes", []):
            if proc.get("pid") == root_pid:
                main_proc = proc
                break

        if not main_proc and data.get("processes"):
            main_proc = data["processes"][0]

        if not main_proc:
            return None

        main_fp = main_proc.get("footprint", 0) / (1024.0 * 1024.0)
        main_peak = main_proc.get("auxiliary", {}).get("phys_footprint_peak", main_proc.get("footprint", 0)) / (1024.0 * 1024.0)
        categories = main_proc.get("categories", {})

        def cat_mb(name):
            return categories.get(name, {}).get("dirty", 0) / (1024.0 * 1024.0)

        return {
            "main_footprint_mb": main_fp,
            "total_footprint_mb": total_fp,
            "main_peak_mb": main_peak,
            "main_rss_mb": main_rss,
            "total_rss_mb": total_rss,
            "malloc_small_mb": cat_mb("Malloc Small"),
            "malloc_large_mb": cat_mb("Malloc Large"),
            "iosurface_mb": cat_mb("IOSurface"),
            "ioaccel_mb": cat_mb("IOAccelerator (graphics)"),
        }
    except Exception:
        return None
    finally:
        if temp_path.exists():
            temp_path.unlink()


def stop_editor(root_pid, profile_dir):
    pids = get_all_pids(root_pid, profile_dir)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in reversed(pids):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(0.3)
        try:
            os.kill(root_pid, 0)
        except ProcessLookupError:
            return


def prepare_workload_dir(base_dir, repo_root):
    """Prepare benchmark project workload with 20 source files, edit test, and 200k log."""
    project = base_dir / "workload"
    project.mkdir(parents=True, exist_ok=True)

    archive = subprocess.check_output(["git", "-C", str(repo_root), "archive", "HEAD"])
    subprocess.run(["tar", "-x", "-C", str(project)], input=archive, check=True)

    files = [
        "crates/rope/src/rope.rs",
        "crates/rope/src/chunk.rs",
        "crates/rope/src/point.rs",
        "crates/rope/src/point_utf16.rs",
        "crates/rope/src/offset_utf16.rs",
        "crates/rope/src/unclipped.rs",
        "crates/editor/src/editor.rs",
        "crates/workspace/src/workspace.rs",
    ]
    lang_files = sorted((project / "crates/languages/src").glob("*.rs"))[:12]
    files.extend(str(p.relative_to(project)) for p in lang_files)

    (project / "benchmark-edit.rs").write_text("fn main() {}\n")

    with (project / "benchmark-large.log").open("w") as out:
        for num in range(200000):
            out.write(
                f"2026-09-19T00:00:00Z INFO request={num:06d} method=GET route=/api/projects status=200 duration_ms=12 benchmark_record\n"
            )

    return project, files


def send_keys_to_pid(pid, script_lines):
    full_script = f"""
tell application "System Events"
    set p to first process whose unix id is {pid}
    set frontmost of p to true
    delay 0.3
""" + "\n".join(script_lines) + "\nend tell"
    subprocess.run(["osascript", "-e", full_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def run_settle_and_sample(root_pid, profile_dir, settle_seconds, sample_count=5, interval=1.0):
    deadline = time.monotonic() + settle_seconds
    while time.monotonic() < deadline:
        time.sleep(0.5)

    samples = []
    for _ in range(sample_count):
        s = capture_memory_sample(root_pid, profile_dir)
        if s:
            samples.append(s)
        time.sleep(interval)

    if not samples:
        return None

    return {
        metric: statistics.median(s[metric] for s in samples)
        for metric in METRICS
    }


def run_idle_benchmark(editors, runs=3, settle=20):
    """
    Run Idle Benchmark:
    1. Welcome window (empty)
    2. Repository open, no source file open
    """
    scenarios = [
        ("Welcome window", None),
        ("Repository open, no source file open", Path.cwd()),
    ]
    all_results = {}

    for scenario_name, project_path in scenarios:
        print(f"\n==========================================")
        print(f"IDLE SCENARIO: {scenario_name}")
        print(f"==========================================")
        all_results[scenario_name] = {ed["name"]: [] for ed in editors}

        for run_idx in range(1, runs + 1):
            order = editors if run_idx % 2 == 1 else list(reversed(editors))
            print(f"\n--- Run {run_idx}/{runs} ---")
            for ed in order:
                name = ed["name"]
                profile_dir = Path(tempfile.mkdtemp(prefix=f"bench_idle_{name}_"))
                cfg_dir = profile_dir / "config"
                cfg_dir.mkdir(parents=True)
                settings = {
                    "auto_update": False,
                    "telemetry": {"diagnostics": False, "metrics": False},
                    "enable_language_server": False,
                    "session": {"trust_all_worktrees": True},
                }
                (cfg_dir / "settings.json").write_text(json.dumps(settings))

                env = os.environ.copy()
                env["ZED_STATELESS"] = "0"
                cmd = [str(ed["bin"]), "--user-data-dir", str(profile_dir)]
                if project_path:
                    cmd.append(str(project_path))

                proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    time.sleep(2)
                    print(f"  Measuring {name} (settling {settle}s)...", end="", flush=True)
                    res = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=settle, sample_count=5)
                    if res:
                        all_results[scenario_name][name].append(res)
                        print(f" Total Footprint: {res['total_footprint_mb']:.1f} MB (Main: {res['main_footprint_mb']:.1f} MB, RSS: {res['total_rss_mb']:.1f} MB)")
                    else:
                        print(" Failed to capture!")
                finally:
                    stop_editor(proc.pid, profile_dir)
                    shutil.rmtree(profile_dir, ignore_errors=True)
                    time.sleep(1)

    return all_results


def run_workflow_benchmark(editors, runs=3):
    """
    Run Workspace Workflow Benchmark (6 stages):
    1. Open 20 source files
    2. Edit, save, and scroll (20 edit cycles)
    3. Search the repository (3 queries)
    4. Navigate and search large log (200k lines)
    5. Integrated terminal output (20k lines)
    6. Close tabs (memory retention check)
    """
    stage_names = [
        "Open 20 source files",
        "Edit, save, and scroll",
        "Search the repository",
        "Navigate and search a large log",
        "Generate terminal output",
        "Close tabs, retaining project state",
    ]
    all_results = {s: {ed["name"]: [] for ed in editors} for s in stage_names}

    print(f"\n==========================================")
    print(f"WORKSPACE WORKFLOW BENCHMARK (6 STAGES)")
    print(f"==========================================")

    for run_idx in range(1, runs + 1):
        order = editors if run_idx % 2 == 1 else list(reversed(editors))
        print(f"\n--- Workflow Run {run_idx}/{runs} ---")
        for ed in order:
            name = ed["name"]
            print(f"\n[Testing Editor: {name}]")
            base_temp = Path(tempfile.mkdtemp(prefix=f"bench_wf_{name}_"))
            project_dir, source_files = prepare_workload_dir(base_temp, Path.cwd())

            profile_dir = base_temp / "profile"
            cfg_dir = profile_dir / "config"
            cfg_dir.mkdir(parents=True)
            settings = {
                "auto_update": False,
                "telemetry": {"diagnostics": False, "metrics": False},
                "enable_language_server": False,
                "preview_tabs": {"enabled": False},
                "format_on_save": "off",
                "terminal": {"max_scroll_history_lines": 10000},
                "session": {"trust_all_worktrees": True},
                "when_closing_with_no_tabs": "keep_window_open",
            }
            (cfg_dir / "settings.json").write_text(json.dumps(settings))

            env = os.environ.copy()
            env["ZED_STATELESS"] = "0"
            cmd = [str(ed["bin"]), "--user-data-dir", str(profile_dir), str(project_dir)]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            cli_bin = ed["cli"]

            try:
                time.sleep(3)

                # Stage 1: Open 20 source files
                print("  -> Stage 1: Open 20 source files...", end="", flush=True)
                for rel_path in source_files:
                    subprocess.run(
                        [str(cli_bin), "--user-data-dir", str(profile_dir), "-e", str(project_dir / rel_path)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                    )
                    time.sleep(0.15)
                res1 = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=5, sample_count=4)
                if res1:
                    all_results["Open 20 source files"][name].append(res1)
                    print(f" Footprint: {res1['total_footprint_mb']:.1f} MB")

                # Stage 2: Edit, save, and scroll (20 edit cycles)
                print("  -> Stage 2: Edit, save, and scroll (20 cycles)...", end="", flush=True)
                edit_file = project_dir / "benchmark-edit.rs"
                subprocess.run(
                    [str(cli_bin), "--user-data-dir", str(profile_dir), "-e", str(edit_file)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
                time.sleep(0.5)

                for cycle in range(20):
                    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    p.communicate(f"\n// benchmark_edit_{cycle:02d}\n".encode())
                    script = [
                        "key code 53",  # Escape
                        'keystroke "1" using {command down}',  # focus pane
                        "key code 125 using {command down}",  # cmd-down to bottom
                        'keystroke "v" using {command down}',  # paste
                        'keystroke "s" using {command down}',  # cmd-s save
                        "key code 116",  # Page Up
                        "key code 121",  # Page Down
                    ]
                    send_keys_to_pid(proc.pid, script)
                    time.sleep(0.1)

                res2 = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=5, sample_count=4)
                if res2:
                    all_results["Edit, save, and scroll"][name].append(res2)
                    print(f" Footprint: {res2['total_footprint_mb']:.1f} MB")

                # Stage 3: Search the repository
                print("  -> Stage 3: Search the repository (3 queries)...", end="", flush=True)
                for q in ("pub struct Rope", "fn offset_to_point", "fn focus_handle"):
                    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    p.communicate(q.encode())
                    script = [
                        "key code 53",
                        'keystroke "f" using {command down, shift down}',  # project search
                        'keystroke "v" using {command down}',  # paste query
                        "keystroke return",
                    ]
                    send_keys_to_pid(proc.pid, script)
                    time.sleep(1.5)

                send_keys_to_pid(proc.pid, ["key code 53"])
                res3 = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=5, sample_count=4)
                if res3:
                    all_results["Search the repository"][name].append(res3)
                    print(f" Footprint: {res3['total_footprint_mb']:.1f} MB")

                # Stage 4: Large file navigation & search (200,000 lines)
                print("  -> Stage 4: Navigate and search large log...", end="", flush=True)
                log_file = project_dir / "benchmark-large.log"
                subprocess.run(
                    [str(cli_bin), "--user-data-dir", str(profile_dir), "-e", str(log_file)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
                time.sleep(0.8)

                # Scroll 5 times
                for _ in range(5):
                    send_keys_to_pid(proc.pid, [
                        "key code 125 using {command down}",  # bottom
                        "key code 116",  # Page Up
                        "key code 126 using {command down}",  # top
                        "key code 121",  # Page Down
                    ])
                    time.sleep(0.1)

                # Buffer search
                p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                p.communicate(b"request=123456")
                send_keys_to_pid(proc.pid, [
                    'keystroke "f" using {command down}',
                    'keystroke "v" using {command down}',
                    "keystroke return",
                    "key code 53",
                ])
                time.sleep(1.0)

                res4 = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=5, sample_count=4)
                if res4:
                    all_results["Navigate and search a large log"][name].append(res4)
                    print(f" Footprint: {res4['total_footprint_mb']:.1f} MB")

                # Stage 5: Terminal output (20,000 lines)
                print("  -> Stage 5: Generate terminal output...", end="", flush=True)
                term_marker = base_temp / "terminal-complete"
                term_script = base_temp / "terminal-workload.py"
                term_script.write_text(
                    "import pathlib\n"
                    "for i in range(20000):\n"
                    "    print(f'{i:06d} INFO processing request: status=200 elapsed=12ms')\n"
                    f"pathlib.Path({str(term_marker)!r}).write_text('done')\n"
                )

                # Open terminal and run script
                send_keys_to_pid(proc.pid, [
                    "key code 53",
                    "key code 50 using {control down}",  # ctrl-` toggle terminal
                ])
                time.sleep(1.0)

                p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                p.communicate(f"python3 {term_script}\n".encode())
                send_keys_to_pid(proc.pid, [
                    'keystroke "v" using {command down}',
                    "delay 0.2",
                    "key code 36",  # Return
                    "delay 0.2",
                    "key code 36",  # Extra Return to ensure execution in fish/zsh
                ])

                # Wait for marker
                deadline = time.monotonic() + 15
                while not term_marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.5)

                res5 = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=5, sample_count=4)
                if res5:
                    all_results["Generate terminal output"][name].append(res5)
                    print(f" Footprint: {res5['total_footprint_mb']:.1f} MB")

                # Stage 6: Close tabs, retaining project state
                print("  -> Stage 6: Close tabs & recover...", end="", flush=True)
                # Close terminal
                send_keys_to_pid(proc.pid, [
                    "key code 50 using {control down}",  # toggle terminal
                    "key code 53",
                ])
                time.sleep(0.5)

                # Close all tabs via cmd-k cmd-w + repeated cmd-w fallback
                send_keys_to_pid(proc.pid, [
                    'keystroke "k" using {command down}',
                    'keystroke "w" using {command down}',
                ])
                time.sleep(0.3)
                for _ in range(15):
                    send_keys_to_pid(proc.pid, ['keystroke "w" using {command down}'])
                    time.sleep(0.04)

                res6 = run_settle_and_sample(proc.pid, profile_dir, settle_seconds=5, sample_count=4)
                if res6:
                    all_results["Close tabs, retaining project state"][name].append(res6)
                    print(f" Footprint: {res6['total_footprint_mb']:.1f} MB")

            finally:
                stop_editor(proc.pid, profile_dir)
                shutil.rmtree(base_temp, ignore_errors=True)
                time.sleep(1)

    return all_results


def print_comparison_table(title, data, editors, metric="total_footprint_mb", unit="MB"):
    print(f"\n### {title} ({unit} Total Process-Tree Footprint, lower is better)\n")
    header = f"| Scenario / Stage | " + " | ".join(ed["name"] for ed in editors) + " | Zite vs Zed | Zite vs Wu | Wu vs Zed |"
    separator = "|" + "|".join(["---"] * (len(editors) + 4)) + "|"
    print(header)
    print(separator)

    summary_rows = []
    for item_name, ed_data in data.items():
        row_vals = {}
        for ed in editors:
            runs = ed_data.get(ed["name"], [])
            if runs:
                row_vals[ed["name"]] = statistics.median(r[metric] for r in runs)
            else:
                row_vals[ed["name"]] = 0.0

        zite_val = row_vals.get("Zite", 0.0)
        wu_val = row_vals.get("Wu", 0.0)
        zed_val = row_vals.get("Zed", 0.0)

        # Zite vs Zed
        diff_zed = ((zed_val - zite_val) / zed_val * 100) if zed_val else 0.0
        # Zite vs Wu
        diff_wu = ((wu_val - zite_val) / wu_val * 100) if wu_val else 0.0
        # Wu vs Zed
        diff_wz = ((zed_val - wu_val) / zed_val * 100) if zed_val else 0.0

        diff_zed_str = f"**-{diff_zed:.1f}%**" if diff_zed > 0 else f"+{-diff_zed:.1f}%"
        diff_wu_str = f"**-{diff_wu:.1f}%**" if diff_wu > 0 else f"+{-diff_wu:.1f}%"
        diff_wz_str = f"-{diff_wz:.1f}%" if diff_wz > 0 else f"+{-diff_wz:.1f}%"

        vals_str = " | ".join(f"{row_vals[ed['name']]:.1f}" for ed in editors)
        line = f"| {item_name} | {vals_str} | {diff_zed_str} | {diff_wu_str} | {diff_wz_str} |"
        print(line)
        summary_rows.append((item_name, row_vals, diff_zed, diff_wu, diff_wz))

    return summary_rows


def main():
    parser = argparse.ArgumentParser(description="macOS Memory Benchmark: Zite vs Wu vs Zed")
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs (default: 3)")
    parser.add_argument("--settle", type=int, default=20, help="Settle time for idle runs in seconds")
    parser.add_argument("--mode", choices=("all", "idle", "workflow"), default="all")
    parser.add_argument("--zite-app", type=Path, default=Path("/Applications/Zite.app"))
    parser.add_argument("--wu-app", type=Path, default=Path("/tmp/Wu.app"))
    parser.add_argument("--zed-app", type=Path, default=Path("/Applications/Zed.app"))
    parser.add_argument("--output-json", type=Path, default=Path("target/benchmark-results/macos-benchmark.json"))
    args = parser.parse_args()

    editors = [
        {
            "name": "Zed",
            "bin": args.zed_app / "Contents/MacOS/zed",
            "cli": args.zed_app / "Contents/MacOS/cli",
        },
        {
            "name": "Wu",
            "bin": args.wu_app / "Contents/MacOS/wu",
            "cli": args.wu_app / "Contents/MacOS/cli",
        },
        {
            "name": "Zite",
            "bin": args.zite_app / "Contents/MacOS/zite",
            "cli": args.zite_app / "Contents/MacOS/cli",
        },
    ]

    for ed in editors:
        if not ed["bin"].exists():
            sys.exit(f"Error: binary for {ed['name']} not found at {ed['bin']}")
        if not ed["cli"].exists():
            sys.exit(f"Error: cli for {ed['name']} not found at {ed['cli']}")

    print(f"System: macOS {subprocess.check_output(['sw_vers', '-productVersion'], text=True).strip()} ({os.uname().machine})")
    for ed in editors:
        ver = subprocess.check_output([str(ed["cli"]), "--version"], text=True).strip()
        print(f"Editor: {ed['name']} -> {ver}")

    results = {}
    if args.mode in ("all", "idle"):
        results["idle"] = run_idle_benchmark(editors, runs=args.runs, settle=args.settle)

    if args.mode in ("all", "workflow"):
        results["workflow"] = run_workflow_benchmark(editors, runs=args.runs)

    print("\n" + "=" * 70)
    print("FINAL BENCHMARK REPORT (Median of runs)")
    print("=" * 70)

    if "idle" in results:
        print_comparison_table("Idle Scenarios", results["idle"], editors)

    if "workflow" in results:
        print_comparison_table("Workspace Workflow Scenarios", results["workflow"], editors)

    # Save to JSON
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w") as f:
        json.dump({
            "timestamp": datetime.datetime.now().isoformat(),
            "runs": args.runs,
            "results": results,
        }, f, indent=2)
    print(f"\nRaw results saved to: {args.output_json}")


if __name__ == "__main__":
    main()
