#!/usr/bin/env python3
"""xLLM vs vLLM-Ascend NPU benchmark comparison tool.

Compares benchmark results from xLLM and vLLM-Ascend, generating
summary tables and winning configuration reports.
"""

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BenchmarkResult:
    framework: str
    candidate_id: str
    qps: float
    requests_per_sec: float
    output_tokens_per_sec: float
    p50_ttft_ms: float
    p99_ttft_ms: float
    p50_tpot_ms: float
    p99_tpot_ms: float
    sla_pass: bool
    status: str
    start_command: str = ""
    error_reason: str = ""


def load_results(path: str, framework: str) -> list[BenchmarkResult]:
    results = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            results.append(BenchmarkResult(
                framework=framework,
                candidate_id=row.get("candidate_id", ""),
                qps=row.get("qps", 0),
                requests_per_sec=row.get("requests_per_sec", 0),
                output_tokens_per_sec=row.get("output_tokens_per_sec", 0),
                p50_ttft_ms=row.get("p50_ttft_ms", 0),
                p99_ttft_ms=row.get("p99_ttft_ms", 0),
                p50_tpot_ms=row.get("p50_tpot_ms", 0),
                p99_tpot_ms=row.get("p99_tpot_ms", 0),
                sla_pass=row.get("sla_pass", False),
                status=row.get("status", "unknown"),
                start_command=row.get("start_command", ""),
                error_reason=row.get("error_reason", ""),
            ))
    return results


def sort_results(results: list[BenchmarkResult]) -> list[BenchmarkResult]:
    return sorted(
        results,
        key=lambda r: (
            -int(r.sla_pass),
            -r.requests_per_sec,
            -r.output_tokens_per_sec,
            r.p50_ttft_ms,
            r.p50_tpot_ms,
        ),
    )


def render_markdown_table(title: str, results: list[BenchmarkResult]) -> str:
    lines = [
        f"## {title}",
        "",
        "| # | Framework | QPS | Req/s | Tok/s | p50 TTFT | p99 TTFT | p50 TPOT | p99 TPOT | SLA | Status |",
        "|---|-----------|-----|-------|-------|----------|----------|----------|----------|-----|--------|",
    ]
    for i, r in enumerate(results[:20], 1):
        lines.append(
            f"| {i} | {r.framework} | {r.qps:.2f} | {r.requests_per_sec:.2f} | "
            f"{r.output_tokens_per_sec:.1f} | {r.p50_ttft_ms:.1f} | {r.p99_ttft_ms:.1f} | "
            f"{r.p50_tpot_ms:.2f} | {r.p99_tpot_ms:.2f} | {'Y' if r.sla_pass else 'N'} | {r.status} |"
        )
    return "\n".join(lines)


def render_winning_commands(results: list[BenchmarkResult], framework: str) -> str:
    best = [r for r in results if r.framework.lower() == framework.lower() and r.sla_pass]
    best = sort_results(best)
    if not best:
        return f"## {framework}: No SLA-passing candidates\n"

    top = best[0]
    lines = [
        f"## {framework} Winning Command",
        "",
        f"- QPS: {top.qps:.2f}",
        f"- Req/s: {top.requests_per_sec:.2f}",
        f"- Output Tok/s: {top.output_tokens_per_sec:.1f}",
        f"- p50 TTFT: {top.p50_ttft_ms:.1f}ms",
        f"- p50 TPOT: {top.p50_tpot_ms:.2f}ms",
        "",
        "```bash",
        top.start_command,
        "```",
    ]
    return "\n".join(lines)


def render_csv(results: list[BenchmarkResult]) -> str:
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "rank", "framework", "candidate_id", "qps",
        "requests_per_sec", "output_tokens_per_sec",
        "p50_ttft_ms", "p99_ttft_ms", "p50_tpot_ms", "p99_tpot_ms",
        "sla_pass", "status",
    ])
    for i, r in enumerate(results, 1):
        writer.writerow([
            i, r.framework, r.candidate_id, f"{r.qps:.4f}",
            f"{r.requests_per_sec:.4f}", f"{r.output_tokens_per_sec:.2f}",
            f"{r.p50_ttft_ms:.2f}", f"{r.p99_ttft_ms:.2f}",
            f"{r.p50_tpot_ms:.4f}", f"{r.p99_tpot_ms:.4f}",
            r.sla_pass, r.status,
        ])
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Compare xLLM vs vLLM-Ascend benchmark results")
    parser.add_argument("--xllm-results", required=True, help="xLLM results JSONL path")
    parser.add_argument("--vllm-results", required=True, help="vLLM-Ascend results JSONL path")
    parser.add_argument("--output-dir", required=True, help="Output directory for comparison artifacts")
    parser.add_argument("--scenario-name", default="default", help="Scenario name for labeling")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    xllm_results = load_results(args.xllm_results, "xllm")
    vllm_results = load_results(args.vllm_results, "vllm-ascend")

    all_results = sort_results(xllm_results + vllm_results)

    summary_lines = [
        f"# Benchmark Comparison: {args.scenario_name}",
        "",
        f"- xLLM candidates: {len(xllm_results)}",
        f"- vLLM-Ascend candidates: {len(vllm_results)}",
        "",
        render_markdown_table("Combined Results (Top 20)", all_results),
        "",
        render_markdown_table("xLLM Results", sort_results(xllm_results)),
        "",
        render_markdown_table("vLLM-Ascend Results", sort_results(vllm_results)),
        "",
        render_winning_commands(xllm_results, "xLLM"),
        "",
        render_winning_commands(vllm_results, "vLLM-Ascend"),
    ]

    summary_path = os.path.join(args.output_dir, "summary.md")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary_lines))
    print(f"Summary written to {summary_path}")

    csv_path = os.path.join(args.output_dir, "summary.csv")
    with open(csv_path, "w") as f:
        f.write(render_csv(all_results))
    print(f"CSV written to {csv_path}")

    cmds_path = os.path.join(args.output_dir, "winning-commands.md")
    cmd_lines = [
        "# Winning Commands",
        "",
        render_winning_commands(xllm_results, "xLLM"),
        "",
        render_winning_commands(vllm_results, "vLLM-Ascend"),
    ]
    with open(cmds_path, "w") as f:
        f.write("\n".join(cmd_lines))
    print(f"Winning commands written to {cmds_path}")


if __name__ == "__main__":
    main()
