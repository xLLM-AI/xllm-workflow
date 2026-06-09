#!/usr/bin/env python3
"""Create pipeline-analysis artifacts for an Ascend profiling run."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


def find_trace(run_dir: Path, explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    candidates = sorted(run_dir.rglob("msprof_*.json"))
    if not candidates:
        candidates = sorted(run_dir.rglob("trace_view.json"))
    return candidates[-1] if candidates else None


def event_name(event: dict) -> str:
    args = event.get("args") if isinstance(event.get("args"), dict) else {}
    return str(event.get("name") or args.get("name") or "")


def load_events(path: Path) -> list[dict]:
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("traceEvents", [])
    return data if isinstance(data, list) else []


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[idx]


def summarize_gaps(events: list[dict], prev_pattern: str, next_pattern: str) -> dict:
    prev, next_events, complete = [], [], []
    for event in events:
        dur = float(event.get("dur", 0) or 0)
        ts = float(event.get("ts", 0) or 0)
        name = event_name(event)
        if dur > 0:
            complete.append((ts, ts + dur, name))
        if prev_pattern in name and dur > 0:
            prev.append((ts, ts + dur, name))
        if next_pattern in name and dur > 0:
            next_events.append((ts, ts + dur, name))

    prev.sort()
    next_events.sort()
    complete.sort()
    prev_ends = [item[1] for item in prev]
    gaps = []
    rows = []
    for next_event in next_events:
        idx = bisect.bisect_right(prev_ends, next_event[0]) - 1
        if idx < 0:
            continue
        gap = next_event[0] - prev[idx][1]
        if 0 <= gap < 5000:
            gaps.append(gap)
            top_events = events_between(complete, prev[idx][1], next_event[0])
            rows.append(
                {
                    "prev_event": prev[idx][2],
                    "prev_end_us": prev[idx][1],
                    "next_event": next_event[2],
                    "next_start_us": next_event[0],
                    "gap_us": gap,
                    "top_events": top_events,
                }
            )

    return {
        "prev_count": len(prev),
        "next_count": len(next_events),
        "pair_count": len(gaps),
        "gap_min_us": min(gaps) if gaps else None,
        "gap_median_us": statistics.median(gaps) if gaps else None,
        "gap_mean_us": statistics.mean(gaps) if gaps else None,
        "gap_p90_us": percentile(gaps, 0.9),
        "gap_max_us": max(gaps) if gaps else None,
        "sample_rows": rows,
        "top_host_events": top_event_names(rows),
    }


def events_between(complete: list[tuple[float, float, str]], start: float, end: float) -> str:
    names = []
    for event_start, event_end, name in complete:
        if event_start >= end:
            break
        if event_start >= start and event_end <= end and name:
            names.append(name)
    counts = Counter(names)
    return "; ".join(f"{name}:{count}" for name, count in counts.most_common(8))


def top_event_names(rows: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for row in rows:
        for item in str(row["top_events"]).split("; "):
            if not item:
                continue
            name, _, count = item.rpartition(":")
            try:
                counts[name] += int(count)
            except ValueError:
                counts[item] += 1
    return [{"name": name, "count": count} for name, count in counts.most_common(20)]


def fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--trace")
    parser.add_argument("--framework", default="unknown")
    parser.add_argument("--workload", default="unknown")
    parser.add_argument("--boundary", default="ArgMaxV2AiCore->MODEL_EXECUTE")
    parser.add_argument("--prev-event")
    parser.add_argument("--next-event")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    trace = find_trace(run_dir, args.trace)
    prev_event = args.prev_event
    next_event = args.next_event
    if (not prev_event or not next_event) and "->" in args.boundary:
        left, right = args.boundary.split("->", 1)
        prev_event = prev_event or left.strip()
        next_event = next_event or right.strip()
    prev_event = prev_event or "ArgMaxV2AiCore"
    next_event = next_event or "MODEL_EXECUTE"

    status = "OK"
    events: list[dict] = []
    summary = {
        "prev_count": 0,
        "next_count": 0,
        "pair_count": 0,
        "gap_min_us": None,
        "gap_median_us": None,
        "gap_mean_us": None,
        "gap_p90_us": None,
        "gap_max_us": None,
        "sample_rows": [],
        "top_host_events": [],
    }
    if trace is None:
        status = "INCONCLUSIVE"
    else:
        events = load_events(trace)
        summary = summarize_gaps(events, prev_event, next_event)
        if summary["pair_count"] == 0:
            status = "INCONCLUSIVE"

    bubble_rows = [
        {
            "run_id": run_dir.name,
            "framework": args.framework,
            "boundary": f"{prev_event}->{next_event}",
            "pair_count": summary["pair_count"],
            "gap_min_us": fmt(summary["gap_min_us"]),
            "gap_median_us": fmt(summary["gap_median_us"]),
            "gap_mean_us": fmt(summary["gap_mean_us"]),
            "gap_p90_us": fmt(summary["gap_p90_us"]),
            "gap_max_us": fmt(summary["gap_max_us"]),
            "top_host_events": "; ".join(
                f"{item['name']}:{item['count']}" for item in summary["top_host_events"][:8]
            ),
            "status": status,
        }
    ]
    write_csv(
        run_dir / "bubble-table.csv",
        [
            "run_id",
            "framework",
            "boundary",
            "pair_count",
            "gap_min_us",
            "gap_median_us",
            "gap_mean_us",
            "gap_p90_us",
            "gap_max_us",
            "top_host_events",
            "status",
        ],
        bubble_rows,
    )
    write_csv(
        run_dir / "stage-table.csv",
        ["run_id", "stage", "latency_us", "status", "notes"],
        [{"run_id": run_dir.name, "stage": "decode_bubble", "latency_us": fmt(summary["gap_median_us"]), "status": status, "notes": "Generated from boundary pairing only."}],
    )
    write_csv(
        run_dir / "rank-skew-table.csv",
        ["run_id", "rank", "metric", "value", "status", "notes"],
        [{"run_id": run_dir.name, "rank": "", "metric": "rank_skew", "value": "", "status": "NOT_ANALYZED", "notes": "Rank skew requires rank-separated profiling data."}],
    )

    analysis = {
        "schema": "xllm-npu-pipeline-analysis/v1",
        "status": status,
        "run_id": run_dir.name,
        "framework": args.framework,
        "workload": args.workload,
        "trace": str(trace) if trace else None,
        "boundary": {"previous": prev_event, "next": next_event},
        "event_count": len(events),
        "gap_summary": {key: value for key, value in summary.items() if key != "sample_rows"},
    }
    write_text(run_dir / "analysis.json", json.dumps(analysis, indent=2, ensure_ascii=False) + "\n")

    write_text(
        run_dir / "manifest.md",
        "\n".join(
            [
                "# Profiling Manifest",
                "",
                f"- run_id: `{run_dir.name}`",
                f"- status: `{status}`",
                f"- framework: `{args.framework}`",
                f"- workload: `{args.workload}`",
                f"- trace: `{trace if trace else 'MISSING'}`",
                f"- boundary: `{prev_event} -> {next_event}`",
                "",
                "Required capture notes should be filled by the profiling owner: service startup command, commit, warmup, capture command, and workload result.",
                "",
            ]
        ),
    )
    top_events = "\n".join(
        f"    - {item['name']}: {item['count']}" for item in summary["top_host_events"][:10]
    ) or "    - none"
    write_text(
        run_dir / "timeline_notes.md",
        "\n".join(
            [
                "# Timeline Notes",
                "",
                f"{prev_event} end -> next {next_event} start",
                f"  duration_us_median: {fmt(summary['gap_median_us'])}",
                "  observed host calls:",
                top_events,
                "  suspected root cause:",
                "    - TODO",
                "  candidate fix:",
                "    - TODO",
                "  validation plan:",
                "    - Pair profiling conclusion with non-profiling before/after perf.",
                "",
            ]
        ),
    )
    write_text(
        run_dir / "pipeline-analysis.md",
        "\n".join(
            [
                "# Pipeline Analysis",
                "",
                f"- status: `{status}`",
                f"- framework: `{args.framework}`",
                f"- workload: `{args.workload}`",
                f"- boundary: `{prev_event} -> {next_event}`",
                f"- pair_count: `{summary['pair_count']}`",
                f"- gap_median_us: `{fmt(summary['gap_median_us'])}`",
                f"- gap_p90_us: `{fmt(summary['gap_p90_us'])}`",
                "",
                "## Bottleneck Classification",
                "",
                "- Device compute: TODO",
                "- Communication/rank skew: TODO",
                "- Hostbound dispatch bubbles: TODO",
                "- Postprocess or sampling overhead: TODO",
                "",
                "## Tables",
                "",
                "- `bubble-table.csv`",
                "- `stage-table.csv`",
                "- `rank-skew-table.csv`",
                "",
            ]
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
