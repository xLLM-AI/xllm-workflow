# Accuracy Debug Runbook

This runbook stores command templates for CEval probes and git bisect. Keep the
main skill focused on the investigation workflow.

Focused case studies:

- [Qwen3.5 chunked prefill init-state accuracy case](qwen35-chunked-prefill-init-state-case.md)
  shows how to localize a garbled-output regression to the first divergent
  recurrent-state tensor instead of guessing at scheduler or kernel changes.

## CEval Two-Subset Probe

Use Python to build JSON arguments and avoid shell escaping issues:

```bash
python3 - <<'PY'
import json
import os
import subprocess

work = os.environ.get("WORK_DIR", "runs/accuracy/ceval_ab")
port = os.environ.get("PORT", "28150")
model = os.environ.get("MODEL_NAME", "Qwen35-27B")
dataset_args = {
    "ceval": {
        "subset_list": ["operating_system", "computer_architecture"],
        "filters": {"remove_until": "}}}"}
    }
}
gen = {
    "max_tokens": int(os.environ.get("MAX_TOKENS", "30000")),
    "temperature": float(os.environ.get("TEMPERATURE", "0.6")),
    "top_p": float(os.environ.get("TOP_P", "0.95")),
    "top_k": int(os.environ.get("TOP_K", "20")),
    "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
    "stream": True,
    "timeout": 60000,
}
cmd = [
    "python3", "-m", "evalscope.cli.cli", "eval",
    "--model", model,
    "--eval-type", "openai_api",
    "--api-url", f"http://127.0.0.1:{port}/v1/chat/completions",
    "--datasets", "ceval",
    "--dataset-args", json.dumps(dataset_args, ensure_ascii=False),
    "--limit", os.environ.get("LIMIT", "10"),
    "--generation-config", json.dumps(gen),
    "--no-timestamp",
    "--work-dir", work,
]
raise SystemExit(subprocess.run(cmd, env=os.environ.copy()).returncode)
PY
```

`--limit 10` applies per subset, so the two listed CEval subsets produce 20
questions total.

## Git Bisect Template

Manual flow:

```bash
git bisect start
git bisect bad BAD_COMMIT
git bisect good GOOD_COMMIT

# For each step:
# 1. Build the current commit.
# 2. Start a fresh service.
# 3. Run the stable probe.
# 4. Mark good or bad.
git bisect good
git bisect bad

git bisect reset
```

Automated runner:

```bash
#!/usr/bin/env bash
set -euo pipefail

./scripts/build_xllm.sh
./scripts/start_server.sh
python3 ./scripts/run_accuracy_probe.py --case ceval_os_10
./scripts/stop_server.sh
```

Return code convention:

- `0`: pass, mark good.
- `1`: fail, mark bad.
- `125`: build or environment unavailable, skip current commit.

Run:

```bash
git bisect start BAD_COMMIT GOOD_COMMIT
git bisect run ./scripts/bisect_accuracy.sh
git bisect reset
```

Avoid classifying OOM, HCCL, startup failure, or reused service state as a
precision regression.
