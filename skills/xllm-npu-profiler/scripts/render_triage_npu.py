#!/usr/bin/env python3
"""Render five-table triage report for xLLM NPU profiling in Markdown format."""

import argparse
import json
import os
import sys
from datetime import datetime


def load_analysis(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def render_header(model: str, framework: str, timestamp: str) -> str:
    return f"""# xLLM NPU Profiling Report

- **Model**: {model}
- **Framework**: {framework}
- **Timestamp**: {timestamp}
"""


def render_kernel_section(kernels: list, title: str) -> str:
    if not kernels:
        return f"## {title}\n\nNo kernel data above cutoff.\n"

    lines = [
        f"## {title}",
        "",
        "| Kernel | Device Time (ms) | Device % | Count | Avg (ms) | Core | Stage |",
        "|--------|------------------|----------|-------|----------|------|-------|",
    ]
    for k in kernels[:20]:
        name = k.get("name", "unknown")[:60]
        time_ms = k.get("device_time_ms", k.get("gpu_time_ms", 0))
        time_pct = k.get("device_time_pct", k.get("gpu_time_pct", 0))
        lines.append(
            f"| {name} | {time_ms:.2f} | {time_pct:.1f}% | {k.get('count', 0)} | "
            f"{k.get('avg_time_ms', 0):.4f} | {k.get('core_type', 'unknown')} | "
            f"{k.get('stage', 'mixed')} |"
        )
    return "\n".join(lines)


def render_overlap_section(overlaps: list, title: str) -> str:
    if not overlaps:
        return f"## {title}\n\nNo overlap opportunities detected.\n"

    lines = [
        f"## {title}",
        "",
        "| Compute/Comm Kernel | Comm Kernel | Time (ms) | Potential (ms) | Stage |",
        "|---------------------|-------------|-----------|---------------|-------|",
    ]
    for o in overlaps[:20]:
        compute = o.get("compute_kernel", o.get("op_type", "unknown"))
        time_ms = o.get("overlap_ms", o.get("total_time_ms", 0))
        potential = o.get("potential_ms", o.get("time_pct", 0))
        lines.append(
            f"| {compute[:40]} | "
            f"{o.get('comm_kernel', 'unknown')[:40]} | "
            f"{time_ms:.2f} | {potential:.2f} | "
            f"{o.get('stage', 'mixed')} |"
        )
    return "\n".join(lines)


def render_fuse_section(fuses: list, title: str) -> str:
    if not fuses:
        return f"## {title}\n\nNo fuse patterns matched.\n"

    lines = [
        f"## {title}",
        "",
        "| Pattern | Matched Operators | Source | Applied | Notes |",
        "|---------|------------------|--------|---------|-------|",
    ]
    for f_ in fuses[:20]:
        lines.append(
            f"| {f_.get('pattern', 'unknown')[:50]} | "
            f"{f_.get('matched_operators', 'N/A')[:40]} | "
            f"{f_.get('source', 'N/A')} | "
            f"{'Y' if f_.get('applied', False) else 'N'} | "
            f"{f_.get('notes', '')} |"
        )
    return "\n".join(lines)


def render_dispatch_section(dispatches: list, title: str) -> str:
    if not dispatches:
        return f"## {title}\n\nNo dispatch data.\n"

    if "stream_id" in dispatches[0]:
        lines = [
            f"## {title}",
            "",
            "| Stream | Tasks | Task Time (ms) | Avg Wait (ms) | Avg Gap (ms) | Launches/ms |",
            "|--------|-------|----------------|---------------|--------------|-------------|",
        ]
        for d in dispatches[:20]:
            lines.append(
                f"| {d.get('stream_id', 'unknown')} | {d.get('task_count', 0)} | "
                f"{d.get('total_time_ms', 0):.2f} | {d.get('avg_wait_ms', 0):.4f} | "
                f"{d.get('avg_gap_ms', 0):.4f} | {d.get('launch_density_per_ms', 0):.3f} |"
            )
        return "\n".join(lines)

    lines = [
        f"## {title}",
        "",
        "| Step | Total (ms) | AICore (ms) | Idle (ms) | Utilization | Dispatch (ms) |",
        "|------|-----------|-------------|-----------|-------------|---------------|",
    ]
    avg_util = sum(d.get("aicore_utilization", 0) for d in dispatches) / len(dispatches)
    avg_idle = sum(d.get("idle_time_ms", 0) for d in dispatches) / len(dispatches)

    lines.append(f"| **Avg** | - | - | {avg_idle:.2f} | {avg_util:.1f}% | - |")
    lines.append("|---|---|---|---|---|---|")

    for d in dispatches[:20]:
        lines.append(
            f"| {d.get('step_id', 0)} | {d.get('total_time_ms', 0):.2f} | "
            f"{d.get('aicore_time_ms', 0):.2f} | {d.get('idle_time_ms', 0):.2f} | "
            f"{d.get('aicore_utilization', 0):.1f}% | "
            f"{d.get('dispatch_latency_ms', 0):.2f} |"
        )

    if avg_idle > 20:
        lines.append(f"\n**Hostbound**: Idle rate {avg_idle:.1f}% > 20%. Check dispatch efficiency.")
    elif avg_util > 85:
        lines.append(f"\n**Computing**: AICore utilization {avg_util:.1f}% > 85%. Focus on hot kernels.")
    else:
        lines.append(f"\n**Balanced**: AICore utilization {avg_util:.1f}%.")

    return "\n".join(lines)


def render_memory_section(memory: list, title: str) -> str:
    if not memory:
        return f"## {title}\n\nNo memory data.\n"

    lines = [
        f"## {title}",
        "",
        "| Region | Allocated (MB) | Used (MB) | Fragmentation | Stage |",
        "|--------|---------------|-----------|--------------|-------|",
    ]
    for m in memory[:20]:
        lines.append(
            f"| {m.get('name', 'unknown')[:40]} | "
            f"{m.get('allocated_mb', 0):.1f} | {m.get('used_mb', 0):.1f} | "
            f"{m.get('fragmentation_pct', 0):.1f}% | {m.get('stage', 'mixed')} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Render xLLM NPU triage report")
    parser.add_argument("--analysis-root", required=True, help="Analysis result directory")
    parser.add_argument("--output", required=True, help="Output Markdown file")
    parser.add_argument("--model", default="unknown", help="Model name")
    args = parser.parse_args()

    report_path = os.path.join(args.analysis_root, "report.json")
    if not os.path.exists(report_path):
        print(f"Error: {report_path} not found", file=sys.stderr)
        sys.exit(1)

    report = load_analysis(report_path)
    framework = report.get("framework", "xllm")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sections = [
        render_header(args.model, framework, timestamp),
        render_kernel_section(report.get("kernel_table", []), "1. Kernel Table"),
        render_overlap_section(
            report.get("overlap_table", report.get("communication_table", [])),
            "2. Communication / Overlap-Opportunity Table",
        ),
        render_fuse_section(report.get("fuse_table", []), "3. Fuse-Pattern Table"),
        render_dispatch_section(report.get("dispatch_table", []), "4. Dispatch Efficiency Table"),
        render_memory_section(report.get("memory_table", []), "5. Memory Efficiency Table"),
    ]

    output = "\n\n".join(sections)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        f.write(output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
