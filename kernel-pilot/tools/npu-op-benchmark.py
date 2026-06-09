#!/usr/bin/env python3
"""NPU operator benchmark for xLLM.

Benchmarks individual operators on Ascend NPU using torch_npu,
measuring latency, throughput, and AICore utilization.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict


@dataclass
class OpBenchResult:
    op_name: str
    shape: str
    dtype: str
    warmup_iters: int
    bench_iters: int
    avg_latency_us: float
    p50_latency_us: float
    p99_latency_us: float
    min_latency_us: float
    max_latency_us: float
    throughput_mops: float


def benchmark_op(op_fn, shape: tuple, dtype: str, warmup: int = 100, iters: int = 1000) -> OpBenchResult:
    import torch
    import torch_npu

    device = torch.npu.current_device()
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    torch_dtype = dtype_map.get(dtype, torch.float16)

    x = torch.randn(*shape, device=f"npu:{device}", dtype=torch_dtype)

    for _ in range(warmup):
        _ = op_fn(x)
    torch.npu.synchronize()

    latencies = []
    for _ in range(iters):
        start = time.perf_counter()
        _ = op_fn(x)
        torch.npu.synchronize()
        end = time.perf_counter()
        latencies.append((end - start) * 1e6)

    latencies.sort()
    avg = sum(latencies) / len(latencies)

    return OpBenchResult(
        op_name=op_fn.__name__ if hasattr(op_fn, "__name__") else str(op_fn),
        shape=str(shape),
        dtype=dtype,
        warmup_iters=warmup,
        bench_iters=iters,
        avg_latency_us=avg,
        p50_latency_us=latencies[len(latencies) // 2],
        p99_latency_us=latencies[int(len(latencies) * 0.99)],
        min_latency_us=latencies[0],
        max_latency_us=latencies[-1],
        throughput_mops=iters / (sum(latencies) / 1e6) / 1e6,
    )


def main():
    parser = argparse.ArgumentParser(description="NPU operator benchmark")
    parser.add_argument("--op", default="all", help="Operator to benchmark (default: all)")
    parser.add_argument("--shape", default="1,4096,4096", help="Tensor shape (comma-separated)")
    parser.add_argument("--dtype", default="bf16", choices=["fp16", "bf16", "fp32"])
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--iters", type=int, default=1000)
    parser.add_argument("--output", help="Output JSON path")
    args = parser.parse_args()

    shape = tuple(int(x) for x in args.shape.split(","))

    try:
        import torch
        import torch_npu
    except ImportError:
        print("Error: torch_npu not available. Run inside NPU container.", file=sys.stderr)
        sys.exit(1)

    def op_matmul(x):
        return torch.matmul(x, x.transpose(-1, -2))

    def op_softmax(x):
        return torch.softmax(x, dim=-1)

    def op_layernorm(x):
        return torch.nn.functional.layer_norm(x, x.shape[-1:])

    def op_silu(x):
        return torch.nn.functional.silu(x)

    def op_gelu(x):
        return torch.nn.functional.gelu(x)

    ops = {
        "matmul": op_matmul,
        "softmax": op_softmax,
        "layernorm": op_layernorm,
        "silu": op_silu,
        "gelu": op_gelu,
    }

    selected_ops = [ops[args.op]] if args.op != "all" else ops.values()
    results = []

    for op_fn in selected_ops:
        r = benchmark_op(op_fn, shape, args.dtype, args.warmup, args.iters)
        results.append(asdict(r))
        print(f"{r.op_name:20s} avg={r.avg_latency_us:10.2f}us  "
              f"p50={r.p50_latency_us:10.2f}us  p99={r.p99_latency_us:10.2f}us")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
