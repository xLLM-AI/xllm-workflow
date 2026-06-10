# Benchmark Runbook

This runbook stores optional config examples and shell templates. Keep the main
benchmark skill focused on rules, workflow, and result interpretation.

## Example Config

```yaml
model:
  path: /models/Qwen3-32B
  tokenizer: /models/Qwen3-32B
  precision: bf16

npu:
  device: A3
  count: 4
  visible_devices: "0,1,2,3"

dataset:
  kind: random
  scenarios:
    - name: chat
      input_len: 1000
      output_len: 1000
    - name: summary
      input_len: 8000
      output_len: 1000

benchmark:
  num_prompts: 80
  qps:
    search: true
    max_rounds: 5
  sla:
    max_ttft_ms: 500
    max_tpot_ms: 50

search:
  tier: 2
  max_candidates: 8
  resume: true

frameworks:
  xllm:
    base_flags:
      tensor-parallel-size: 4
      graph-mode: npugraph_ex
      block-size: 128
    search_space:
      chunked-prefill-size: [256, 512, 1024]
      max-num-seqs: [64, 128, 256]
      speculative-model: ["", "/models/draft-2b"]
  vllm-ascend:
    base_flags:
      tensor-parallel-size: 4
      enforce-eager: true
      block-size: 128
      gpu-memory-utilization: 0.9
    search_space:
      enable-prefix-caching: [true, false]
```

## Evalscope Script Template

```bash
#!/bin/bash
set -euo pipefail

MODE=${1:-baseline}
PARALLEL=${2:-1}
NUMBER=${3:-5}
RUN_ROOT=${RUN_ROOT:-runs/perf/manual_benchmark}
DATASET=${DATASET:-$RUN_ROOT/datasets/workload_20k.jsonl}
BASELINE_URL=${BASELINE_URL:-http://127.0.0.1:18160/v1/chat/completions}
MTP_URL=${MTP_URL:-http://127.0.0.1:18170/v1/chat/completions}

if [ "$MODE" = "mtp" ]; then
  URL=$MTP_URL
else
  URL=$BASELINE_URL
fi

OUT_DIR=$RUN_ROOT/benchmark/${MODE}/parallel_${PARALLEL}_number_${NUMBER}
mkdir -p "$OUT_DIR"

evalscope perf \
  --model "${MODEL_NAME:-Qwen35-27B}" \
  --url "$URL" \
  --api openai \
  --dataset line_by_line \
  --dataset-path "$DATASET" \
  --parallel "$PARALLEL" \
  --number "$NUMBER" \
  --warmup-num "${WARMUP_NUM:-1}" \
  --connect-timeout 120 \
  --read-timeout 300 \
  --outputs-dir "$OUT_DIR"
```

Rules:

- Use environment variables for paths and ports.
- Do not hard-code host-specific run roots, private datasets, or device ids.
- Keep `--warmup-num` enabled for steady-state performance results.
