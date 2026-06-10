#!/usr/bin/env python3
"""Collect evalscope benchmark artifacts into comparison-ready JSONL.

The collector scans a run directory for benchmark_summary.json files and emits
the normalized schema consumed by compare_npu_benchmark.py.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class EvalscopeResult:
    framework: str
    candidate_id: str
    qps: float
    requests_per_sec: float
    output_tokens_per_sec: float
    p50_ttft_ms: float
    p99_ttft_ms: float
    p50_tpot_ms: float
    p99_tpot_ms: float
    avg_latency_s: float
    avg_input_tokens: float
    avg_output_tokens: float
    decoded_tokens_per_iter: float
    spec_accept_rate: float
    sla_pass: bool
    status: str
    artifact_dir: str
    start_command: str = ""
    error_reason: str = ""


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def percentile_value(rows: list[dict], percentile: str, key: str) -> float:
    for row in rows:
        if str(row.get("Percentiles")) == percentile:
            return float(row.get(key, 0) or 0)
    return 0.0


def infer_candidate_id(summary_path: Path, root: Path) -> str:
    artifact_dir = summary_path.parent
    try:
        return str(artifact_dir.relative_to(root))
    except ValueError:
        return str(artifact_dir)


def load_start_command(artifact_dir: Path) -> str:
    candidates = [
        artifact_dir / "start_command.txt",
        artifact_dir.parent / "start_command.txt",
        artifact_dir.parent / "winning-command.txt",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def collect(root: Path, framework: str, sla_ttft_ms: float, sla_tpot_ms: float) -> list[EvalscopeResult]:
    results: list[EvalscopeResult] = []
    for summary_path in sorted(root.glob("**/benchmark_summary.json")):
        summary = load_json(summary_path)
        percentile_path = summary_path.with_name("benchmark_percentile.json")
        percentiles = load_json(percentile_path) if percentile_path.exists() else []

        p50_ttft = percentile_value(percentiles, "50%", "TTFT (ms)") or float(summary.get("TTFT (ms)", 0) or 0)
        p99_ttft = percentile_value(percentiles, "99%", "TTFT (ms)")
        p50_tpot = percentile_value(percentiles, "50%", "TPOT (ms)") or float(summary.get("TPOT (ms)", 0) or 0)
        p99_tpot = percentile_value(percentiles, "99%", "TPOT (ms)")
        success = int(summary.get("Success Requests", 0) or 0)
        failed = int(summary.get("Failed Requests", 0) or 0)
        status = "ok" if success > 0 and failed == 0 else "partial" if success > 0 else "failed"
        sla_pass = status == "ok"
        if sla_ttft_ms > 0:
            sla_pass = sla_pass and p99_ttft <= sla_ttft_ms
        if sla_tpot_ms > 0:
            sla_pass = sla_pass and p99_tpot <= sla_tpot_ms

        artifact_dir = summary_path.parent
        results.append(
            EvalscopeResult(
                framework=framework,
                candidate_id=infer_candidate_id(summary_path, root),
                qps=float(summary.get("Req Throughput (req/s)", 0) or 0),
                requests_per_sec=float(summary.get("Req Throughput (req/s)", 0) or 0),
                output_tokens_per_sec=float(summary.get("Output Throughput (tok/s)", 0) or 0),
                p50_ttft_ms=p50_ttft,
                p99_ttft_ms=p99_ttft,
                p50_tpot_ms=p50_tpot,
                p99_tpot_ms=p99_tpot,
                avg_latency_s=float(summary.get("Avg Latency (s)", 0) or 0),
                avg_input_tokens=float(summary.get("Avg Input Tokens", 0) or 0),
                avg_output_tokens=float(summary.get("Avg Output Tokens", 0) or 0),
                decoded_tokens_per_iter=float(summary.get("Decoded Tok/Iter", 0) or 0),
                spec_accept_rate=float(summary.get("Spec. Accept Rate", 0) or 0),
                sla_pass=sla_pass,
                status=status,
                artifact_dir=str(artifact_dir),
                start_command=load_start_command(artifact_dir),
                error_reason="" if status == "ok" else f"success={success}, failed={failed}",
            )
        )
    return results


def sort_results(results: list[EvalscopeResult]) -> list[EvalscopeResult]:
    return sorted(
        results,
        key=lambda item: (
            -int(item.sla_pass),
            -item.requests_per_sec,
            -item.output_tokens_per_sec,
            item.p50_ttft_ms,
            item.p50_tpot_ms,
        ),
    )


def write_jsonl(results: list[EvalscopeResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def write_summary(results: list[EvalscopeResult], path: Path) -> None:
    lines = [
        "# Evalscope Benchmark Summary",
        "",
        f"- Candidates: {len(results)}",
        "",
        "| # | Candidate | Req/s | Tok/s | p50 TTFT | p99 TTFT | p50 TPOT | p99 TPOT | DecTok/Iter | Accept | SLA |",
        "|---|-----------|-------|-------|----------|----------|----------|----------|-------------|--------|-----|",
    ]
    for idx, item in enumerate(sort_results(results), 1):
        lines.append(
            f"| {idx} | {item.candidate_id} | {item.requests_per_sec:.4f} | "
            f"{item.output_tokens_per_sec:.2f} | {item.p50_ttft_ms:.1f} | "
            f"{item.p99_ttft_ms:.1f} | {item.p50_tpot_ms:.2f} | "
            f"{item.p99_tpot_ms:.2f} | {item.decoded_tokens_per_iter:.2f} | "
            f"{item.spec_accept_rate:.1%} | {'Y' if item.sla_pass else 'N'} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Collect evalscope benchmark results")
    parser.add_argument("--root", required=True, help="Directory to scan")
    parser.add_argument("--framework", default="xllm", help="Framework label")
    parser.add_argument("--output-jsonl", required=True, help="Normalized JSONL output")
    parser.add_argument("--output-summary", help="Markdown summary output")
    parser.add_argument("--sla-ttft-ms", type=float, default=0, help="Optional p99 TTFT SLA")
    parser.add_argument("--sla-tpot-ms", type=float, default=0, help="Optional p99 TPOT SLA")
    args = parser.parse_args()

    results = collect(Path(args.root), args.framework, args.sla_ttft_ms, args.sla_tpot_ms)
    results = sort_results(results)
    write_jsonl(results, Path(args.output_jsonl))
    if args.output_summary:
        write_summary(results, Path(args.output_summary))

    print(f"Collected {len(results)} evalscope candidates")
    print(f"JSONL written to {args.output_jsonl}")
    if args.output_summary:
        print(f"Summary written to {args.output_summary}")


if __name__ == "__main__":
    main()
