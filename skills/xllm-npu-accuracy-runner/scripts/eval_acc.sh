#!/bin/bash
MODEL_NAME="${MODEL_NAME:-Qwen35-27B}"
API_URL="${API_URL:-http://127.0.0.1:17112/v1}"
OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"

evalscope eval \
  --model "$MODEL_NAME" \
  --api-url "$API_URL" \
  --api-key "$OPENAI_API_KEY" \
  --eval-type openai_api \
  --datasets ceval --dataset-args '{"ceval": {"subset_list": ["computer_network", "operating_system", "marxism"]}}' \
  --eval-batch-size 4 \
  --generation-config '{"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5, "repetition_penalty": 1.0, "ignore_eos": false, "max_tokens": 32768}'
