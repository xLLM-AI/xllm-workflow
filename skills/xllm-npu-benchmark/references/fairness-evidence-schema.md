# Benchmark Fairness Evidence Schema

`fairness.json` describes a comparison, not an individual run. Each candidate must first pass
Run Evidence Gate with `claim_scope=formal`.
The verdict's resolved `run_root` must equal the candidate's resolved `run_root`; placing a
verdict file under the candidate directory is not sufficient identity proof.

```json
{
  "schema_version": 1,
  "comparison_id": "<stable comparison id>",
  "policy": {
    "max_preexisting_hbm_pct": "<campaign threshold>",
    "max_idle_aicore_pct": "<campaign threshold>",
    "max_host_load1_delta_pct": "<campaign threshold>",
    "min_idle_samples": "<positive integer>"
  },
  "candidates": [
    {
      "name": "before",
      "run_root": "runs/before",
      "evidence_verdict": "evidence-verdict.json",
      "campaign_fingerprint": "<candidate manifest fingerprint>",
      "identity": {
        "hardware_fingerprint": "<hardware and software stack fingerprint>",
        "device_backend": "ascend-npu | nvidia-gpu",
        "physical_device_ids": [0, 1],
        "visible_device_order": [0, 1],
        "model_fingerprint": "<weights fingerprint>",
        "tokenizer_fingerprint": "<tokenizer fingerprint>",
        "dtype": "bf16",
        "quantization": "none",
        "workload_fingerprint": "<request set and order fingerprint>",
        "sampling_fingerprint": "<effective sampling fingerprint>",
        "sla_fingerprint": "<effective SLA fingerprint>",
        "optimization_policy_fingerprint": "<candidate search policy fingerprint>",
        "profiling_attached": false,
        "tuning_completed": true
      },
      "environment": {
        "before": "<normalized snapshot>",
        "idle_samples": ["<normalized snapshot>"],
        "after": "<normalized snapshot>"
      }
    }
  ]
}
```

Each normalized snapshot contains:

```json
{
  "backend": "ascend-npu",
  "parser_version": 2,
  "backend_version": "<collector tool version>",
  "devices": [
    {
      "physical_id": 0,
      "health": "OK",
      "hbm_usage_pct": 0,
      "aicore_usage_pct": 0,
      "processes": [
        {"pid": 1234, "host_visible": true, "owned_by_attempt": true}
      ]
    }
  ],
  "host": {
    "load1": 1.0,
    "swap_used_bytes": 0,
    "profiling_active": false,
    "build_active": false
  },
  "collection_errors": [],
  "raw_dir": "<preserved raw command output directory>"
}
```

Generate snapshots with `capture_fairness_snapshot.py`. Use `--attempt-pid-file` after service
startup so NPU processes are matched by PID plus `/proc` start time; PID equality alone is not
ownership proof. The collector preserves raw backend output next to the normalized JSON.

```bash
python skills/xllm-npu-benchmark/scripts/capture_fairness_snapshot.py \
  --backend ascend-npu \
  --output "$RUN_ROOT/env/before.json" \
  --raw-dir "$RUN_ROOT/env/raw/before" \
  --physical-device <id>
```

Use `--backend nvidia-gpu` for NVIDIA CSV query mode. Unknown formats, missing parser fields,
mixed backends, and a candidate campaign fingerprint that does not match its own manifest are
`BLOCKED`; the gate never translates them into guessed utilization values.

Capture `before` prior to service launch, one or more `idle` snapshots after ready/smoke, and
`after` after the benchmark. A parser or command failure is recorded in `collection_errors` and
must block formal comparison rather than being replaced by a guessed value.

The workflow intentionally provides no default utilization or load thresholds. Hardware,
deployment mode, and campaign purpose determine acceptable values. The campaign must declare
its policy before comparing candidates; a missing policy returns `BLOCKED` rather than silently
adopting a machine-specific assumption.

Verdicts:

- `PASS`: every candidate has formal run evidence, snapshots satisfy the declared policy, and
  comparison identities match.
- `INCONCLUSIVE`: evidence exists but contamination or a candidate mismatch prevents a fair
  formal comparison.
- `BLOCKED`: the contract, policy, snapshots, or prerequisite evidence is incomplete.
