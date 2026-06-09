#!/usr/bin/env python3
"""Analyze Ascend msprof/MindStudio profiling output for xLLM NPU runs.

The script accepts either a raw PROF_* directory or its
mindstudio_profiler_output child. It understands timestamped Ascend CSV names
such as op_statistic_*.csv, op_summary_*.csv, task_time*.csv, and
communication_statistic_*.csv.
"""

import argparse
import csv
import glob
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class KernelEntry:
    name: str
    device_time_ms: float
    device_time_pct: float
    count: int
    avg_time_ms: float
    core_type: str
    stage: str = "mixed"


@dataclass
class CommunicationEntry:
    op_type: str
    total_time_ms: float
    time_pct: float
    count: int
    avg_time_ms: float


@dataclass
class DispatchEntry:
    stream_id: str
    task_count: int
    total_time_ms: float
    avg_wait_ms: float
    avg_gap_ms: float
    launch_density_per_ms: float


def read_csv(path: Path) -> list[dict]:
    if not path or not path.exists():
        return []
    with path.open("r", newline="") as f:
        return list(csv.DictReader(f))


def to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return default


def find_latest(root: Path, patterns: list[str]) -> Path | None:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(Path(p) for p in glob.glob(str(root / "**" / pattern), recursive=True))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_profile_root(input_dir: str) -> Path:
    root = Path(input_dir)
    if (root / "mindstudio_profiler_output").is_dir():
        return root / "mindstudio_profiler_output"
    return root


def parse_analysis_db(path: Path) -> dict:
    data = {"kernels": [], "operators": [], "steps": []}
    if not path or not path.exists():
        return data
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for (table_name,) in tables:
            lower = table_name.lower()
            if "kernel" not in lower and "operator" not in lower and "op" not in lower:
                continue
            rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()
            cols = [d[0] for d in cursor.description]
            target = "kernels" if "kernel" in lower else "operators"
            data[target].extend(dict(zip(cols, r)) for r in rows)
        conn.close()
    except Exception as exc:
        print(f"Warning: could not parse {path}: {exc}", file=sys.stderr)
    return data


def compute_kernel_table(
    op_stat_rows: list[dict],
    op_summary_rows: list[dict],
    cutoff_pct: float = 1.0,
) -> list[KernelEntry]:
    entries: list[KernelEntry] = []
    if op_stat_rows:
        for row in op_stat_rows:
            pct = to_float(row.get("Ratio(%)"))
            if pct < cutoff_pct:
                continue
            total_us = to_float(row.get("Total Time(us)"))
            count = to_int(row.get("Count"), 1)
            entries.append(
                KernelEntry(
                    name=row.get("OP Type", "unknown"),
                    device_time_ms=total_us / 1000,
                    device_time_pct=pct,
                    count=count,
                    avg_time_ms=to_float(row.get("Avg Time(us)")) / 1000,
                    core_type=row.get("Core Type", "unknown"),
                )
            )
        entries.sort(key=lambda item: -item.device_time_pct)
        return entries

    totals: dict[tuple[str, str], dict] = {}
    total_us = 0.0
    for row in op_summary_rows:
        name = row.get("Op Name") or row.get("OP Type") or row.get("kernel_name") or "unknown"
        core_type = row.get("Task Type") or row.get("Core Type") or "unknown"
        duration_us = to_float(row.get("Task Duration(us)")) or to_float(row.get("task_time(us)"))
        aicore_us = to_float(row.get("aicore_time(us)"))
        aiv_us = to_float(row.get("aiv_time(us)"))
        effective_us = max(duration_us, aicore_us, aiv_us)
        if effective_us <= 0:
            continue
        total_us += effective_us
        bucket = totals.setdefault((name, core_type), {"time_us": 0.0, "count": 0})
        bucket["time_us"] += effective_us
        bucket["count"] += 1

    if total_us <= 0:
        return []
    for (name, core_type), bucket in totals.items():
        pct = bucket["time_us"] / total_us * 100
        if pct < cutoff_pct:
            continue
        count = int(bucket["count"])
        entries.append(
            KernelEntry(
                name=name,
                device_time_ms=bucket["time_us"] / 1000,
                device_time_pct=pct,
                count=count,
                avg_time_ms=bucket["time_us"] / count / 1000 if count else 0,
                core_type=core_type,
            )
        )
    entries.sort(key=lambda item: -item.device_time_pct)
    return entries


def compute_communication_table(rows: list[dict], cutoff_pct: float = 1.0) -> list[CommunicationEntry]:
    entries: list[CommunicationEntry] = []
    for row in rows:
        pct = to_float(row.get("Ratio(%)"))
        if pct < cutoff_pct:
            continue
        total_us = to_float(row.get("Total Time(us)"))
        entries.append(
            CommunicationEntry(
                op_type=row.get("OP Type", "unknown"),
                total_time_ms=total_us / 1000,
                time_pct=pct,
                count=to_int(row.get("Count")),
                avg_time_ms=to_float(row.get("Avg Time(us)")) / 1000,
            )
        )
    entries.sort(key=lambda item: -item.time_pct)
    return entries


def compute_dispatch_table(task_rows: list[dict]) -> list[DispatchEntry]:
    by_stream: dict[str, list[dict]] = {}
    for row in task_rows:
        stream = row.get("Stream ID") or row.get("stream_id") or "unknown"
        by_stream.setdefault(stream, []).append(row)

    entries: list[DispatchEntry] = []
    for stream, rows in by_stream.items():
        timed = []
        total_us = 0.0
        wait_us = 0.0
        for row in rows:
            duration_us = to_float(row.get("Task Duration(us)")) or to_float(row.get("task_time(us)"))
            start_us = to_float(row.get("Task Start Time(us)")) or to_float(row.get("task_start(us)"))
            stop_us = to_float(row.get("task_stop(us)")) or (start_us + duration_us if start_us else 0)
            wait_us += to_float(row.get("Task Wait Time(us)"))
            total_us += duration_us
            if start_us:
                timed.append((start_us, stop_us, duration_us))
        if not timed and total_us <= 0:
            continue
        timed.sort()
        gaps = []
        for idx in range(1, len(timed)):
            gap = timed[idx][0] - timed[idx - 1][1]
            if gap > 0:
                gaps.append(gap)
        span_us = (timed[-1][1] - timed[0][0]) if len(timed) >= 2 else total_us
        entries.append(
            DispatchEntry(
                stream_id=stream,
                task_count=len(rows),
                total_time_ms=total_us / 1000,
                avg_wait_ms=wait_us / len(rows) / 1000 if rows else 0,
                avg_gap_ms=sum(gaps) / len(gaps) / 1000 if gaps else 0,
                launch_density_per_ms=len(rows) / (span_us / 1000) if span_us > 0 else 0,
            )
        )
    entries.sort(key=lambda item: -item.total_time_ms)
    return entries


def render_kernel_table(entries: list[KernelEntry]) -> str:
    lines = [
        "| Kernel / OP Type | Device Time (ms) | Device % | Count | Avg (ms) | Core | Stage |",
        "|------------------|------------------|----------|-------|----------|------|-------|",
    ]
    for item in entries[:20]:
        lines.append(
            f"| {item.name[:80]} | {item.device_time_ms:.2f} | "
            f"{item.device_time_pct:.1f}% | {item.count} | {item.avg_time_ms:.4f} | "
            f"{item.core_type} | {item.stage} |"
        )
    return "\n".join(lines)


def render_communication_table(entries: list[CommunicationEntry]) -> str:
    if not entries:
        return "No communication statistic data above cutoff."
    lines = [
        "| Communication OP | Time (ms) | Time % | Count | Avg (ms) |",
        "|------------------|-----------|--------|-------|----------|",
    ]
    for item in entries[:20]:
        lines.append(
            f"| {item.op_type[:80]} | {item.total_time_ms:.2f} | {item.time_pct:.1f}% | "
            f"{item.count} | {item.avg_time_ms:.4f} |"
        )
    return "\n".join(lines)


def render_dispatch_table(entries: list[DispatchEntry]) -> str:
    if not entries:
        return "No task timeline data available."
    lines = [
        "| Stream | Tasks | Task Time (ms) | Avg Wait (ms) | Avg Gap (ms) | Launches/ms |",
        "|--------|-------|----------------|---------------|--------------|-------------|",
    ]
    for item in entries[:20]:
        lines.append(
            f"| {item.stream_id} | {item.task_count} | {item.total_time_ms:.2f} | "
            f"{item.avg_wait_ms:.4f} | {item.avg_gap_ms:.4f} | "
            f"{item.launch_density_per_ms:.3f} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze xLLM NPU profiling data")
    parser.add_argument("--input", required=True, help="PROF_* or mindstudio_profiler_output directory")
    parser.add_argument("--framework", default="xllm", choices=["xllm", "vllm-ascend"])
    parser.add_argument("--cutoff", type=float, default=1.0, help="Minimum device-time cutoff (default 1.0%%)")
    parser.add_argument("--output", help="Output JSON path for structured data")
    parser.add_argument("--url", help="Deprecated and ignored; collect with run_profiling.sh first")
    parser.add_argument("--output-dir", help="Deprecated and ignored; use --output for JSON")
    parser.add_argument("--num-steps", type=int, default=5, help="Deprecated and ignored")
    parser.add_argument("--profile-by-stage", action="store_true", help="Deprecated and ignored")
    parser.add_argument(
        "--profile-workload",
        choices=["prefill", "decode", "both"],
        default="both",
        help="Deprecated and ignored",
    )
    parser.add_argument("--mapping-input", help="Mapping trace input (two-trace mode)")
    parser.add_argument("--formal-input", help="Formal trace input (two-trace mode)")
    args = parser.parse_args()

    profile_root = resolve_profile_root(args.input)
    op_stat_path = find_latest(profile_root, ["op_statistic*.csv"])
    op_summary_path = find_latest(profile_root, ["op_summary*.csv"])
    task_time_path = find_latest(profile_root, ["task_time*.csv"])
    comm_path = find_latest(profile_root, ["communication_statistic*.csv"])
    db_path = find_latest(Path(args.input), ["analysis.db", "msprof_*.db"])

    op_stat_rows = read_csv(op_stat_path) if op_stat_path else []
    op_summary_rows = read_csv(op_summary_path) if op_summary_path else []
    task_rows = read_csv(task_time_path) if task_time_path else []
    comm_rows = read_csv(comm_path) if comm_path else []
    analysis_db = parse_analysis_db(db_path) if db_path else {"kernels": [], "operators": [], "steps": []}

    kernel_entries = compute_kernel_table(op_stat_rows, op_summary_rows, args.cutoff)
    comm_entries = compute_communication_table(comm_rows, args.cutoff)
    dispatch_entries = compute_dispatch_table(task_rows)

    report = {
        "framework": args.framework,
        "input_dir": args.input,
        "profile_root": str(profile_root),
        "source_files": {
            "op_statistic": str(op_stat_path) if op_stat_path else "",
            "op_summary": str(op_summary_path) if op_summary_path else "",
            "task_time": str(task_time_path) if task_time_path else "",
            "communication_statistic": str(comm_path) if comm_path else "",
            "analysis_db": str(db_path) if db_path else "",
        },
        "kernel_table": [item.__dict__ for item in kernel_entries],
        "communication_table": [item.__dict__ for item in comm_entries],
        "dispatch_table": [item.__dict__ for item in dispatch_entries],
        "db_table_counts": {key: len(value) for key, value in analysis_db.items()},
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {output_path}")

    print("## Kernel Table")
    print(render_kernel_table(kernel_entries))
    print()
    print("## Communication Table")
    print(render_communication_table(comm_entries))
    print()
    print("## Dispatch Efficiency Table")
    print(render_dispatch_table(dispatch_entries))


if __name__ == "__main__":
    main()
