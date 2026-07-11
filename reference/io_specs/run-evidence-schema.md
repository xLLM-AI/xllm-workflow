# Run Evidence Schema

`run-evidence.json` is the machine-readable source of truth for deciding whether a run can
support a performance, accuracy, or profiling claim. Markdown manifests remain useful for
humans, but they do not replace this contract for formal evidence.

```json
{
  "schema_version": 1,
  "run_id": "<stable run id>",
  "evidence_type": "performance | accuracy | profiling",
  "level": "smoke | quick | full | formal-pr | sota-report",
  "identity": {
    "framework": "xllm",
    "repo_path": "<checkout or worktree>",
    "commit": "<40-hex commit>",
    "dirty_diff_sha256": "<sha256 or empty-tree sha>",
    "binary_path": "<tested binary>",
    "binary_sha256": "<sha256>",
    "build_verdict": "build/verdict.json",
    "binary_provenance": "build/binary-provenance.json"
  },
  "environment": {
    "physical_device_ids": [0, 1],
    "visible_device_order": [0, 1],
    "hardware": "<observed hardware>",
    "software_stack": {"runtime": "<observed runtime version>"}
  },
  "model": {
    "name": "<model name>",
    "path": "<model path>",
    "tokenizer_path": "<tokenizer path>",
    "dtype": "<dtype>"
  },
  "service": {
    "attempt_id": "attempt-001",
    "api_url": "<effective endpoint>",
    "startup_command": "service/attempt-001/command.sh",
    "pid_file": "service/attempt-001/pids.txt",
    "logs": ["service/attempt-001/node_0.log"],
    "ready": {"status": "PASS", "artifact": "service/attempt-001/ready.json"},
    "smoke": {"status": "PASS", "artifact": "service/attempt-001/smoke.json"},
    "cleanup": {"status": "PASS", "artifact": "service/attempt-001/cleanup.json"}
  },
  "workload": {
    "request_fingerprint": "<sha256 of the effective request set and order>",
    "dataset": "<dataset>",
    "input_tokens": 1024,
    "output_tokens": 512,
    "parallel": 1,
    "number": 4,
    "warmup_num": 1,
    "profiling_attached": false,
    "sampling": {}
  },
  "artifacts": {
    "environment": {
      "before": "env/before",
      "after": "env/after"
    },
    "performance": {
      "raw": "perf/raw",
      "metrics": "perf/metrics.json"
    }
  }
}
```

## Type-specific additions

Accuracy evidence adds these workload fields:

- `prompt_template_sha256`
- `dataset_fingerprint`
- `answer_extractor_version`

and these artifacts under `artifacts.accuracy`:

- `request_config`
- `dataset_config`
- `raw_predictions`
- `failed_cases`
- `score`

Profiling evidence adds:

```json
"profiling": {
  "attached_parent_pid": 1234,
  "warmup_before_capture": true,
  "workload_status": "PASS"
}
```

and `prof`, `export`, `capture_log`, `workload_log`, and `analysis` under
`artifacts.profiling`.

## Verdict semantics

- `PASS`: declared evidence exists, mandatory gates passed, and identities are consistent.
- `INCONCLUSIVE`: the run may be useful for debugging, but formal evidence is missing,
  stale, overwritten, or internally inconsistent.
- `BLOCKED`: a prerequisite gate failed, the contract cannot be parsed, or the service was
  not usable.

`PASS` means the evidence is complete for its declared level; it does not promote the run to
a broader claim. `smoke` and `quick` runs retain those claim scopes, while `full`, `formal-pr`,
and `sota-report` runs may support a `formal` claim.

The validator does not encode model names, PR numbers, device-specific performance
thresholds, or incident signatures. Those belong in model history, benchmark policy, or
incident catalogs only after independent validation.
