#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
cd "$PROJECT_ROOT"

MODEL="${MODEL:-Qwen35-27B}"
API_URL="${API_URL:-http://127.0.0.1:17112/v1}"
API_URL="${API_URL%/}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/models/Qwen35-27B}"
PARALLEL_LIST="${PARALLEL_LIST:-1}"
NUMBER="${NUMBER:-4}"
WARMUP_NUM="${WARMUP_NUM:-2}"
INPUT_TOKENS="${INPUT_TOKENS:-20000}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-1024}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs}"
if [ -z "${EXTRA_ARGS+x}" ]; then
  EXTRA_ARGS='{"ignore_eos": true}'
fi
SEED="${SEED:-}"
TEMPERATURE="${TEMPERATURE:-}"
TOP_P="${TOP_P:-}"
STREAM="${STREAM:-false}"

if [[ ! "$WARMUP_NUM" =~ ^[0-9]+$ ]]; then
  echo "ERROR: WARMUP_NUM must be a non-negative integer, got: $WARMUP_NUM" >&2
  exit 2
fi
for value_name in NUMBER INPUT_TOKENS OUTPUT_TOKENS; do
  value="${!value_name}"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: $value_name must be a positive integer, got: $value" >&2
    exit 2
  fi
done

IFS=',' read -r -a PARALLELS <<< "$PARALLEL_LIST"
mkdir -p "$OUTPUT_DIR"
for parallel in "${PARALLELS[@]}"; do
  if [[ ! "$parallel" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PARALLEL_LIST contains an invalid value: $parallel" >&2
    exit 2
  fi
  actual_number=$((NUMBER * parallel))
  echo "=== Running evalscope perf: parallel=$parallel, number=$actual_number ==="
  cmd=(evalscope perf \
    --parallel "$parallel" \
    --number "$actual_number" \
    --model "$MODEL" \
    --url "${API_URL}/chat/completions" \
    --api openai \
    --warmup-num "$WARMUP_NUM" \
    --dataset random \
    --max-tokens "$OUTPUT_TOKENS" \
    --min-tokens "$OUTPUT_TOKENS" \
    --prefix-length 0 \
    --min-prompt-length "$INPUT_TOKENS" \
    --max-prompt-length "$INPUT_TOKENS" \
    --tokenizer-path "$TOKENIZER_PATH" \
    --outputs-dir "$OUTPUT_DIR" \
    --extra-args "$EXTRA_ARGS")
  [ -z "$SEED" ] || cmd+=(--seed "$SEED")
  [ -z "$TEMPERATURE" ] || cmd+=(--temperature "$TEMPERATURE")
  [ -z "$TOP_P" ] || cmd+=(--top-p "$TOP_P")
  [ "$STREAM" != true ] || cmd+=(--stream)
  "${cmd[@]}"
done
