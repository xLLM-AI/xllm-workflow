#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$PROJECT_ROOT"

SMOKE_MODE="${SMOKE_MODE:-true}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/models/Qwen35-27B}"

evalscope perf \
  --parallel 1 \
  --number 4 \
  --model Qwen35-27B \
  --url http://127.0.0.1:17112/v1/chat/completions \
  --api openai \
  --warmup-num 2 \
  --dataset random \
  --max-tokens 1024 \
  --min-tokens 1024 \
  --prefix-length 0 \
  --min-prompt-length 20000 \
  --max-prompt-length 20000 \
  --tokenizer-path "$TOKENIZER_PATH" \
  --extra-args '{"ignore_eos": true}'

if [ "$SMOKE_MODE" != "true" ]; then
  evalscope perf \
    --parallel 5 \
    --number 20 \
    --model Qwen35-27B \
    --url http://127.0.0.1:17112/v1/chat/completions \
    --api openai \
    --dataset random \
    --max-tokens 1024 \
    --min-tokens 1024 \
    --prefix-length 0 \
    --min-prompt-length 20000 \
    --max-prompt-length 20000 \
    --tokenizer-path "$TOKENIZER_PATH" \
    --extra-args '{"ignore_eos": true}'
fi
