#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"

SERVER_MANAGER_SCRIPTS="$PROJECT_ROOT/skills/xllm-npu-server-manager/scripts"
PERF_RUNNER_SCRIPTS="$PROJECT_ROOT/skills/xllm-npu-perf-runner/scripts"

: "${MODEL_NAME:?MODEL_NAME is required}"
: "${MODEL_PATH:?MODEL_PATH is required}"
: "${TOKENIZER_PATH:?TOKENIZER_PATH is required}"
: "${NNODES:?NNODES is required}"
: "${ASCEND_RT_VISIBLE_DEVICES:?ASCEND_RT_VISIBLE_DEVICES is required}"
: "${MODEL_ROOT:?MODEL_ROOT is required}"

DRAFT_MODEL_PATH="${DRAFT_MODEL_PATH:-}"
START_PORT="${START_PORT:-17112}"
MASTER_NODE_ADDR="${MASTER_NODE_ADDR:-127.0.0.1:12345}"
XLLM_BIN="${XLLM_BIN:-$PROJECT_ROOT/xllm/build/xllm/core/server/xllm}"
NUM_SPECULATIVE_TOKENS="${NUM_SPECULATIVE_TOKENS:-0}"
MAX_MEMORY_UTILIZATION="${MAX_MEMORY_UTILIZATION:-0.75}"
MAX_TOKENS_PER_BATCH="${MAX_TOKENS_PER_BATCH:-8192}"
MAX_SEQS_PER_BATCH="${MAX_SEQS_PER_BATCH:-8}"
BLOCK_SIZE="${BLOCK_SIZE:-128}"
COMMUNICATION_BACKEND="${COMMUNICATION_BACKEND:-lccl}"
MAX_CONCURRENT_REQUESTS="${MAX_CONCURRENT_REQUESTS:-8}"
ENABLE_PREFIX_CACHE="${ENABLE_PREFIX_CACHE:-true}"
ENABLE_CHUNKED_PREFILL="${ENABLE_CHUNKED_PREFILL:-true}"
ENABLE_SCHEDULE_OVERLAP="${ENABLE_SCHEDULE_OVERLAP:-true}"
ENABLE_GRAPH="${ENABLE_GRAPH:-true}"
ENABLE_SHM="${ENABLE_SHM:-true}"
NPU_MEMORY_FRACTION="${NPU_MEMORY_FRACTION:-0.90}"

PARALLEL_LIST="${PARALLEL_LIST:-1}"
NUMBER="${NUMBER:-4}"
WARMUP_NUM="${WARMUP_NUM:-2}"
INPUT_TOKENS="${INPUT_TOKENS:-2048}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-2048}"
EXTRA_ARGS="${EXTRA_ARGS:-{\"ignore_eos\": true}}"

READY_TIMEOUT="${READY_TIMEOUT:-600}"
READY_INTERVAL="${READY_INTERVAL:-10}"

SSH_HOST="${SSH_HOST:-}"
XLLM_CONTAINER="${XLLM_CONTAINER:-}"
EVALSCOPE_CONTAINER="${EVALSCOPE_CONTAINER:-}"
MTP_EXPORT_TOOL="${MTP_EXPORT_TOOL:-}"

API_URL="http://127.0.0.1:${START_PORT}/v1"

run_remote() {
  local container="$1"
  shift
  if [ -n "$SSH_HOST" ] && [ -n "$container" ]; then
    ssh "$SSH_HOST" "docker exec -u root $container bash -c '$*'"
  elif [ -n "$SSH_HOST" ]; then
    ssh "$SSH_HOST" "bash -c '$*'"
  elif [ -n "$container" ]; then
    docker exec -u root "$container" bash -c "$*"
  else
    eval "$@"
  fi
}

mkdir -p "$MODEL_ROOT"/{env,perf,service}

echo "[$(date '+%F %T')] === Batch Perf: $MODEL_NAME ==="
echo "  NNODES=$NNODES, DEVICES=$ASCEND_RT_VISIBLE_DEVICES"
echo "  PARALLEL_LIST=$PARALLEL_LIST, INPUT=$INPUT_TOKENS, OUTPUT=$OUTPUT_TOKENS"
echo "  SSH_HOST=$SSH_HOST, XLLM_CONTAINER=$XLLM_CONTAINER"

echo "[$(date '+%F %T')] Stopping any existing xLLM service..."
run_remote "$XLLM_CONTAINER" "pkill -9 xllm 2>/dev/null || true"
sleep 5

if [ -n "$DRAFT_MODEL_PATH" ] && [ "$NUM_SPECULATIVE_TOKENS" -gt 0 ] 2>/dev/null; then
  DRAFT_EXISTS=false
  run_remote "$XLLM_CONTAINER" "test -d '$DRAFT_MODEL_PATH' && echo yes || echo no" | grep -q yes && DRAFT_EXISTS=true
  if [ "$DRAFT_EXISTS" != "true" ]; then
    if [ -n "$MTP_EXPORT_TOOL" ]; then
      echo "[$(date '+%F %T')] MTP weights not found at $DRAFT_MODEL_PATH, exporting..."
      run_remote "$XLLM_CONTAINER" "python3 $MTP_EXPORT_TOOL --model $MODEL_PATH --output $DRAFT_MODEL_PATH"
    else
      echo "[$(date '+%F %T')] WARNING: MTP weights not found and no mtp_export_tool configured"
      echo "  Draft path: $DRAFT_MODEL_PATH"
      echo "  Set MTP_EXPORT_TOOL to auto-export, or manually create the directory"
    fi
  fi
fi

echo "[$(date '+%F %T')] Saving pre-launch environment snapshot..."
run_remote "$XLLM_CONTAINER" "npu-smi info" > "$MODEL_ROOT/env/npu-smi.before.txt" 2>/dev/null || true
run_remote "$XLLM_CONTAINER" "free -h" > "$MODEL_ROOT/env/mem.before.txt" 2>/dev/null || true

echo "[$(date '+%F %T')] Starting xLLM service..."
export MODEL_PATH DRAFT_MODEL_PATH NNODES ASCEND_RT_VISIBLE_DEVICES START_PORT
export MASTER_NODE_ADDR XLLM_BIN NUM_SPECULATIVE_TOKENS MAX_MEMORY_UTILIZATION
export MAX_TOKENS_PER_BATCH MAX_SEQS_PER_BATCH BLOCK_SIZE COMMUNICATION_BACKEND
export MAX_CONCURRENT_REQUESTS ENABLE_PREFIX_CACHE ENABLE_CHUNKED_PREFILL
export ENABLE_SCHEDULE_OVERLAP ENABLE_GRAPH ENABLE_SHM NPU_MEMORY_FRACTION
export LOG_DIR="$MODEL_ROOT/service/log"

if [ -n "$SSH_HOST" ] || [ -n "$XLLM_CONTAINER" ]; then
  SERVER_ENV=""
  for VAR in MODEL_PATH DRAFT_MODEL_PATH NNODES ASCEND_RT_VISIBLE_DEVICES START_PORT \
             MASTER_NODE_ADDR XLLM_BIN NUM_SPECULATIVE_TOKENS MAX_MEMORY_UTILIZATION \
             MAX_TOKENS_PER_BATCH MAX_SEQS_PER_BATCH BLOCK_SIZE COMMUNICATION_BACKEND \
             MAX_CONCURRENT_REQUESTS ENABLE_PREFIX_CACHE ENABLE_CHUNKED_PREFILL \
             ENABLE_SCHEDULE_OVERLAP ENABLE_GRAPH ENABLE_SHM NPU_MEMORY_FRACTION LOG_DIR; do
    SERVER_ENV="$SERVER_ENV export ${VAR}='${!VAR}';"
  done

  START_CMD="bash $SERVER_MANAGER_SCRIPTS/run.sh"
  if [ -n "$SSH_HOST" ] && [ -n "$XLLM_CONTAINER" ]; then
    ssh "$SSH_HOST" "docker exec -u root -d $XLLM_CONTAINER bash -c '$SERVER_ENV $START_CMD'"
  elif [ -n "$XLLM_CONTAINER" ]; then
    docker exec -u root -d "$XLLM_CONTAINER" bash -c "$SERVER_ENV $START_CMD"
  else
    ssh "$SSH_HOST" "bash -c '$SERVER_ENV $START_CMD'"
  fi
else
  bash "$SERVER_MANAGER_SCRIPTS/run.sh"
fi

echo "[$(date '+%F %T')] Waiting for service ready (timeout=${READY_TIMEOUT}s)..."
ELAPSED=0
READY=false
while [ "$ELAPSED" -lt "$READY_TIMEOUT" ]; do
  if curl -sf "$API_URL/models" > /dev/null 2>&1; then
    READY=true
    break
  fi
  sleep "$READY_INTERVAL"
  ELAPSED=$((ELAPSED + READY_INTERVAL))
  echo "  Waiting... (${ELAPSED}/${READY_TIMEOUT}s)"
done

if [ "$READY" != "true" ]; then
  echo "[$(date '+%F %T')] ERROR: Service failed to start within ${READY_TIMEOUT}s"
  echo "  Check logs at: $MODEL_ROOT/service/log/"
  echo "{\"model\": \"$MODEL_NAME\", \"status\": \"start_failed\"}" >> "${BATCH_ROOT:-.}/all_metrics.jsonl"
  run_remote "$XLLM_CONTAINER" "pkill -9 xllm 2>/dev/null || true"
  exit 1
fi

echo "[$(date '+%F %T')] Service ready. Running perf tests..."
PERF_CONTAINER="${EVALSCOPE_CONTAINER:-$XLLM_CONTAINER}"
export MODEL="$MODEL_NAME"
export API_URL
export TOKENIZER_PATH
export PARALLEL_LIST NUMBER WARMUP_NUM INPUT_TOKENS OUTPUT_TOKENS EXTRA_ARGS
export OUTPUT_DIR="$MODEL_ROOT/perf"

if [ -n "$SSH_HOST" ] || [ -n "$PERF_CONTAINER" ]; then
  PERF_ENV=""
  for VAR in MODEL API_URL TOKENIZER_PATH PARALLEL_LIST NUMBER WARMUP_NUM \
             INPUT_TOKENS OUTPUT_TOKENS EXTRA_ARGS OUTPUT_DIR; do
    PERF_ENV="$PERF_ENV export ${VAR}='${!VAR}';"
  done

  PERF_CMD="bash $PERF_RUNNER_SCRIPTS/eval_perf.sh"
  if [ -n "$SSH_HOST" ] && [ -n "$PERF_CONTAINER" ]; then
    ssh "$SSH_HOST" "docker exec -u root $PERF_CONTAINER bash -c '$PERF_ENV $PERF_CMD'"
  elif [ -n "$PERF_CONTAINER" ]; then
    docker exec -u root "$PERF_CONTAINER" bash -c "$PERF_ENV $PERF_CMD"
  else
    ssh "$SSH_HOST" "bash -c '$PERF_ENV $PERF_CMD'"
  fi
else
  bash "$PERF_RUNNER_SCRIPTS/eval_perf.sh"
fi

echo "[$(date '+%F %T')] Collecting results..."
SUMMARY_COUNT=0
for SUMMARY_FILE in "$MODEL_ROOT/perf"/**/benchmark_summary.json; do
  if [ -f "$SUMMARY_FILE" ]; then
    SUMMARY_COUNT=$((SUMMARY_COUNT + 1))
  fi
done
echo "  Found $SUMMARY_COUNT benchmark_summary.json files"

if [ -n "${BATCH_ROOT:-}" ]; then
  for SUMMARY_FILE in "$MODEL_ROOT/perf"/**/benchmark_summary.json; do
    if [ -f "$SUMMARY_FILE" ]; then
      PARALLEL_DIR="$(basename "$(dirname "$SUMMARY_FILE")")"
      jq -c --arg model "$MODEL_NAME" --arg parallel "$PARALLEL_DIR" \
        '. + {model: $model, parallel_dir: $parallel}' "$SUMMARY_FILE" \
        >> "$BATCH_ROOT/all_metrics.jsonl" 2>/dev/null || \
      echo "{\"model\": \"$MODEL_NAME\", \"parallel_dir\": \"$PARALLEL_DIR\", \"source\": \"$SUMMARY_FILE\"}" \
        >> "$BATCH_ROOT/all_metrics.jsonl"
    fi
  done
fi

echo "[$(date '+%F %T')] Stopping service..."
run_remote "$XLLM_CONTAINER" "pkill -9 xllm 2>/dev/null || true"
sleep 3

run_remote "$XLLM_CONTAINER" "npu-smi info" > "$MODEL_ROOT/env/npu-smi.after.txt" 2>/dev/null || true

echo "[$(date '+%F %T')] === $MODEL_NAME done ==="
echo "{\"model\": \"$MODEL_NAME\", \"status\": \"completed\"}" >> "${BATCH_ROOT:-.}/all_metrics.jsonl"
