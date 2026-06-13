# Performance Artifact Schema

Formal performance results should be stored under:

```text
runs/perf/<run_id>/
  manifest.md
  env/
    npu-smi.before.txt
    npu-smi.after.txt
    process.before.txt
    process.after.txt
    mem.before.txt
    mem.after.txt
    load.before.txt
    load.after.txt
  service/
    command.sh
    pids.txt
    node_*.log
    healthcheck.json
  evalscope/
    raw/
    benchmark_summary.json
    benchmark_percentile.json
  metrics.json
  report.md
```

`metrics.json` should use stable field names:

```json
{
  "run_id": "",
  "framework": "xllm",
  "model": "",
  "commit": "",
  "level": "smoke",
  "input_tokens": null,
  "output_tokens": null,
  "parallel": null,
  "number": null,
  "warmup_num": null,
  "stream": true,
  "temperature": 0.0,
  "top_p": null,
  "top_k": null,
  "ttft_ms": null,
  "tpot_ms": null,
  "itl_ms": null,
  "output_tps": null,
  "request_throughput": null,
  "success": null,
  "total": null,
  "speculative_num_accepted_tokens_delta": null,
  "speculative_num_draft_tokens_delta": null,
  "server_accept_rate": null,
  "evalscope_decoded_tok_per_iter": null,
  "evalscope_spec_accept_rate": null
}
```

Rules:

- Formal steady-state performance must include request-level warmup
  (`--warmup-num 1` or higher for evalscope). Without warmup, mark the run as
  cold-start or smoke only.
- Do not compare msprof-attached runs with normal performance runs.
- Before/after comparisons must use the same devices, visible device order,
  model, workload, sampling parameters, and service startup parameters unless
  the changed parameter is the experiment itself.
- For MTP/speculative runs, record xLLM server counters from `/vars` before and
  after the workload. Evalscope accept rate is a weak signal only.
