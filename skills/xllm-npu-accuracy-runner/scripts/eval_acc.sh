#!/bin/bash
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-Qwen35-27B}"
API_URL="${API_URL:-http://127.0.0.1:17112/v1}"
API_URL="${API_URL%/}"
OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
WORK_DIR="${WORK_DIR:-${RUN_ROOT:-outputs}/accuracy}"
TEST_MODE="${TEST_MODE:-smoke}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-4}"
GENERATION_CONFIG="${GENERATION_CONFIG:-{\"temperature\": 1.0, \"top_p\": 0.95, \"top_k\": 20, \"min_p\": 0.0, \"presence_penalty\": 1.5, \"repetition_penalty\": 1.0, \"ignore_eos\": false, \"max_tokens\": 32768}}"

if [[ ! "$EVAL_BATCH_SIZE" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: EVAL_BATCH_SIZE must be a positive integer" >&2
  exit 2
fi

case "$TEST_MODE" in
  smoke)
    dataset_args=(
      --datasets ceval
      --dataset-args '{"ceval": {"subset_list": ["computer_network", "operating_system", "marxism"]}}'
    )
    ;;
  full)
    dataset_args=(--datasets ceval)
    ;;
  *)
    echo "ERROR: TEST_MODE must be smoke or full, got: $TEST_MODE" >&2
    exit 2
    ;;
esac
mkdir -p "$WORK_DIR"

evalscope eval \
  --model "$MODEL_NAME" \
  --api-url "$API_URL" \
  --api-key "$OPENAI_API_KEY" \
  --work-dir "$WORK_DIR" \
  --eval-type openai_api \
  "${dataset_args[@]}" \
  --eval-batch-size "$EVAL_BATCH_SIZE" \
  --generation-config "$GENERATION_CONFIG"
