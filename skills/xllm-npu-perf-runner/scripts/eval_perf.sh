#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$PROJECT_ROOT"

MODEL="${MODEL:-Qwen35-27B}"
API_URL="${API_URL:-http://127.0.0.1:17112/v1}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/models/Qwen35-27B}"
PARALLEL_LIST="${PARALLEL_LIST:-1}"
NUMBER="${NUMBER:-4}"
WARMUP_NUM="${WARMUP_NUM:-2}"
INPUT_TOKENS="${INPUT_TOKENS:-20000}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-1024}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs}"
EXTRA_ARGS="${EXTRA_ARGS:-{\"ignore_eos\": true}}"

IFS=',' read -ra PARALLELS <<< "$PARALLEL_LIST"

for PARALLEL in "${PARALLELS[@]}"; do
  ACTUAL_NUMBER=$((NUMBER * PARALLEL))
  echo "=== Running evalscope perf: parallel=$PARALLEL, number=$ACTUAL_NUMBER ==="
  evalscope perf \
    --parallel "$PARALLEL" \
    --number "$ACTUAL_NUMBER" \
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
    --output-dir "$OUTPUT_DIR" \
    --extra-args "$EXTRA_ARGS"
done
