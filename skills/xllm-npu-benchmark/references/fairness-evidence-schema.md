# Benchmark Fairness Evidence Schema

`fairness.json` describes a comparison, not an individual run. Each candidate must first pass
Run Evidence Gate with `claim_scope=formal`.

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
      "identity": {
        "hardware_fingerprint": "<hardware and software stack fingerprint>",
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
  }
}
```

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
