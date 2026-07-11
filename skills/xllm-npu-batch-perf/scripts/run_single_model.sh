#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
TARGET_PROJECT_ROOT="${TARGET_PROJECT_ROOT:-$PROJECT_ROOT}"

SERVER_MANAGER_SCRIPT="${SERVER_MANAGER_SCRIPT:-$TARGET_PROJECT_ROOT/skills/xllm-npu-server-manager/scripts/run.sh}"
SERVER_STOP_SCRIPT="${SERVER_STOP_SCRIPT:-$TARGET_PROJECT_ROOT/skills/xllm-npu-server-manager/scripts/stop.sh}"
PERF_RUNNER_SCRIPT="${PERF_RUNNER_SCRIPT:-$TARGET_PROJECT_ROOT/skills/xllm-npu-perf-runner/scripts/eval_perf.sh}"

: "${MODEL_NAME:?MODEL_NAME is required}"
: "${MODEL_PATH:?MODEL_PATH is required}"
: "${TOKENIZER_PATH:?TOKENIZER_PATH is required}"
: "${NNODES:?NNODES is required}"
: "${ASCEND_RT_VISIBLE_DEVICES:?ASCEND_RT_VISIBLE_DEVICES is required}"
: "${MODEL_ROOT:?MODEL_ROOT is required}"

DRAFT_MODEL_PATH="${DRAFT_MODEL_PATH:-}"
START_PORT="${START_PORT:-17112}"
MASTER_NODE_ADDR="${MASTER_NODE_ADDR:-127.0.0.1:12345}"
XLLM_BIN="${XLLM_BIN:-$TARGET_PROJECT_ROOT/code/xllm/build/xllm/core/server/xllm}"
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
STOP_TIMEOUT="${STOP_TIMEOUT:-30}"
PERF_TIMEOUT="${PERF_TIMEOUT:-1800}"

SSH_HOST="${SSH_HOST:-}"
XLLM_CONTAINER="${XLLM_CONTAINER:-}"
EVALSCOPE_CONTAINER="${EVALSCOPE_CONTAINER:-}"
PERF_CONTAINER="${EVALSCOPE_CONTAINER:-$XLLM_CONTAINER}"
MTP_EXPORT_TOOL="${MTP_EXPORT_TOOL:-}"
TARGET_MODEL_ROOT="${TARGET_MODEL_ROOT:-$MODEL_ROOT}"
TARGET_PID_FILE="${TARGET_PID_FILE:-$TARGET_MODEL_ROOT/service/xllm.pids}"
METRICS_FILE="${BATCH_ROOT:-$MODEL_ROOT}/all_metrics.jsonl"

if [[ ! "$NNODES" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: NNODES must be a positive integer, got: $NNODES" >&2
  exit 2
fi
for value_name in START_PORT NUM_SPECULATIVE_TOKENS READY_TIMEOUT READY_INTERVAL STOP_TIMEOUT PERF_TIMEOUT; do
  value="${!value_name}"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "ERROR: $value_name must be a non-negative integer, got: $value" >&2
    exit 2
  fi
done
if [ "$START_PORT" -lt 1 ] || [ "$START_PORT" -gt 65535 ]; then
  echo "ERROR: START_PORT must be in [1, 65535]" >&2
  exit 2
fi
if [ "$READY_INTERVAL" -eq 0 ]; then
  echo "ERROR: READY_INTERVAL must be greater than zero" >&2
  exit 2
fi
if [ "$PERF_TIMEOUT" -eq 0 ]; then
  echo "ERROR: PERF_TIMEOUT must be greater than zero" >&2
  exit 2
fi

IFS=',' read -r -a DEVICES <<< "$ASCEND_RT_VISIBLE_DEVICES"
if [ "${#DEVICES[@]}" -ne "$NNODES" ]; then
  echo "ERROR: NNODES=$NNODES requires exactly $NNODES device IDs; got $ASCEND_RT_VISIBLE_DEVICES" >&2
  exit 2
fi
declare -A SEEN_DEVICES=()
for device in "${DEVICES[@]}"; do
  if [[ ! "$device" =~ ^[0-9]+$ ]]; then
    echo "ERROR: invalid NPU device ID: $device" >&2
    exit 2
  fi
  if [[ -n "${SEEN_DEVICES[$device]:-}" ]]; then
    echo "ERROR: duplicate NPU device ID: $device" >&2
    exit 2
  fi
  SEEN_DEVICES[$device]=1
done

API_URL_WAS_SET=false
if [ "${API_URL+x}" = x ]; then
  API_URL_WAS_SET=true
fi
API_URL="${API_URL:-http://127.0.0.1:${START_PORT}/v1}"
API_URL="${API_URL%/}"
if [ -n "$EVALSCOPE_CONTAINER" ] && [ "$EVALSCOPE_CONTAINER" != "$XLLM_CONTAINER" ]; then
  if [ "$API_URL_WAS_SET" = false ]; then
    echo "ERROR: API_URL is required when xLLM and EvalScope use different containers" >&2
    exit 2
  fi
  case "$API_URL" in
    http://127.0.0.1:* | https://127.0.0.1:* | http://localhost:* | https://localhost:*)
      echo "ERROR: API_URL=$API_URL is not reachable from a different EvalScope container" >&2
      exit 2
      ;;
  esac
fi

quote_command() {
  local quoted="" part
  for part in "$@"; do
    printf -v part '%q' "$part"
    quoted+="$part "
  done
  printf '%s' "$quoted"
}

run_in_context() {
  local container="$1"
  shift
  local command_string remote_command
  command_string="$(quote_command "$@")"
  if [ -n "$SSH_HOST" ] && [ -n "$container" ]; then
    printf -v remote_command 'docker exec -u root %q bash -lc %q' "$container" "$command_string"
    ssh -n "$SSH_HOST" "$remote_command"
  elif [ -n "$SSH_HOST" ]; then
    printf -v remote_command 'bash -lc %q' "$command_string"
    ssh -n "$SSH_HOST" "$remote_command"
  elif [ -n "$container" ]; then
    docker exec -u root "$container" bash -lc "$command_string"
  else
    "$@"
  fi
}

append_status() {
  local status="$1" detail="${2:-}"
  python3 - "$METRICS_FILE" "$MODEL_NAME" "$status" "$detail" <<'PY'
import json
import pathlib
import sys

path, model, status, detail = sys.argv[1:]
target = pathlib.Path(path)
target.parent.mkdir(parents=True, exist_ok=True)
record = {"model": model, "status": status}
if detail:
    record["detail"] = detail
with target.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
PY
}

SERVICE_STARTED=false
STATUS_WRITTEN=false
FAILURE_STATUS="failed"

stop_service() {
  run_in_context "$XLLM_CONTAINER" env \
    "PID_FILE=$TARGET_PID_FILE" \
    "STOP_TIMEOUT=$STOP_TIMEOUT" \
    bash "$SERVER_STOP_SCRIPT"
}

snapshot_after() {
  run_in_context "$XLLM_CONTAINER" npu-smi info \
    > "$MODEL_ROOT/env/npu-smi.after.txt" 2>/dev/null || true
}

cleanup_on_exit() {
  local exit_code=$? cleanup_code=0 detail
  trap - EXIT INT TERM
  if [ "$SERVICE_STARTED" = true ]; then
    stop_service || cleanup_code=$?
    SERVICE_STARTED=false
  fi
  snapshot_after
  if [ "$exit_code" -eq 0 ] && [ "$cleanup_code" -ne 0 ]; then
    exit_code=$cleanup_code
    FAILURE_STATUS="cleanup_failed"
  fi
  if [ "$exit_code" -ne 0 ] && [ "$STATUS_WRITTEN" = false ]; then
    detail="exit_code=$exit_code"
    if [ "$cleanup_code" -ne 0 ]; then
      detail+=";cleanup_exit_code=$cleanup_code"
    fi
    append_status "$FAILURE_STATUS" "$detail"
  fi
  exit "$exit_code"
}
trap cleanup_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$MODEL_ROOT"/{env,perf,service} "$(dirname "$METRICS_FILE")"
run_in_context "$XLLM_CONTAINER" mkdir -p \
  "$TARGET_MODEL_ROOT/env" "$TARGET_MODEL_ROOT/perf" "$TARGET_MODEL_ROOT/service/log"
run_in_context "$XLLM_CONTAINER" test -r "$SERVER_MANAGER_SCRIPT"
run_in_context "$XLLM_CONTAINER" test -r "$SERVER_STOP_SCRIPT"
run_in_context "$PERF_CONTAINER" test -r "$PERF_RUNNER_SCRIPT"

echo "[$(date '+%F %T')] === Batch Perf: $MODEL_NAME ==="
echo "  NNODES=$NNODES, DEVICES=$ASCEND_RT_VISIBLE_DEVICES"
echo "  PARALLEL_LIST=$PARALLEL_LIST, INPUT=$INPUT_TOKENS, OUTPUT=$OUTPUT_TOKENS"
echo "  SSH_HOST=$SSH_HOST, XLLM_CONTAINER=$XLLM_CONTAINER, EVALSCOPE_CONTAINER=$PERF_CONTAINER"
echo "  API_URL=$API_URL"

if [ -n "$DRAFT_MODEL_PATH" ] && [ "$NUM_SPECULATIVE_TOKENS" -gt 0 ]; then
  if ! run_in_context "$XLLM_CONTAINER" test -d "$DRAFT_MODEL_PATH"; then
    if [ -z "$MTP_EXPORT_TOOL" ]; then
      echo "ERROR: MTP weights are missing and MTP_EXPORT_TOOL is not configured: $DRAFT_MODEL_PATH" >&2
      FAILURE_STATUS="draft_model_missing"
      exit 2
    fi
    echo "[$(date '+%F %T')] Exporting MTP weights to $DRAFT_MODEL_PATH..."
    run_in_context "$XLLM_CONTAINER" python3 "$MTP_EXPORT_TOOL" \
      --model "$MODEL_PATH" --output "$DRAFT_MODEL_PATH"
  fi
fi

echo "[$(date '+%F %T')] Saving pre-launch environment snapshot..."
run_in_context "$XLLM_CONTAINER" npu-smi info \
  > "$MODEL_ROOT/env/npu-smi.before.txt" 2>/dev/null || true
run_in_context "$XLLM_CONTAINER" free -h \
  > "$MODEL_ROOT/env/mem.before.txt" 2>/dev/null || true

echo "[$(date '+%F %T')] Starting xLLM service..."
SERVICE_STARTED=true
run_in_context "$XLLM_CONTAINER" env \
  "MODEL_PATH=$MODEL_PATH" \
  "DRAFT_MODEL_PATH=$DRAFT_MODEL_PATH" \
  "NNODES=$NNODES" \
  "ASCEND_RT_VISIBLE_DEVICES=$ASCEND_RT_VISIBLE_DEVICES" \
  "START_PORT=$START_PORT" \
  "MASTER_NODE_ADDR=$MASTER_NODE_ADDR" \
  "XLLM_BIN=$XLLM_BIN" \
  "NUM_SPECULATIVE_TOKENS=$NUM_SPECULATIVE_TOKENS" \
  "MAX_MEMORY_UTILIZATION=$MAX_MEMORY_UTILIZATION" \
  "MAX_TOKENS_PER_BATCH=$MAX_TOKENS_PER_BATCH" \
  "MAX_SEQS_PER_BATCH=$MAX_SEQS_PER_BATCH" \
  "BLOCK_SIZE=$BLOCK_SIZE" \
  "COMMUNICATION_BACKEND=$COMMUNICATION_BACKEND" \
  "MAX_CONCURRENT_REQUESTS=$MAX_CONCURRENT_REQUESTS" \
  "ENABLE_PREFIX_CACHE=$ENABLE_PREFIX_CACHE" \
  "ENABLE_CHUNKED_PREFILL=$ENABLE_CHUNKED_PREFILL" \
  "ENABLE_SCHEDULE_OVERLAP=$ENABLE_SCHEDULE_OVERLAP" \
  "ENABLE_GRAPH=$ENABLE_GRAPH" \
  "ENABLE_SHM=$ENABLE_SHM" \
  "NPU_MEMORY_FRACTION=$NPU_MEMORY_FRACTION" \
  "RUN_ROOT=$TARGET_MODEL_ROOT" \
  "LOG_DIR=$TARGET_MODEL_ROOT/service/log" \
  "PID_FILE=$TARGET_PID_FILE" \
  bash "$SERVER_MANAGER_SCRIPT"

echo "[$(date '+%F %T')] Waiting for service ready (timeout=${READY_TIMEOUT}s)..."
elapsed=0
ready=false
while [ "$elapsed" -lt "$READY_TIMEOUT" ]; do
  if run_in_context "$PERF_CONTAINER" curl -sf "${API_URL}/models" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep "$READY_INTERVAL"
  elapsed=$((elapsed + READY_INTERVAL))
  echo "  Waiting... (${elapsed}/${READY_TIMEOUT}s)"
done
if [ "$ready" != true ]; then
  echo "ERROR: service did not become ready within ${READY_TIMEOUT}s" >&2
  FAILURE_STATUS="start_failed"
  exit 1
fi

echo "[$(date '+%F %T')] Service ready. Running perf tests..."
if run_in_context "$PERF_CONTAINER" timeout --signal=TERM --kill-after=30 \
  "${PERF_TIMEOUT}s" env \
  "MODEL=$MODEL_NAME" \
  "API_URL=$API_URL" \
  "TOKENIZER_PATH=$TOKENIZER_PATH" \
  "PARALLEL_LIST=$PARALLEL_LIST" \
  "NUMBER=$NUMBER" \
  "WARMUP_NUM=$WARMUP_NUM" \
  "INPUT_TOKENS=$INPUT_TOKENS" \
  "OUTPUT_TOKENS=$OUTPUT_TOKENS" \
  "EXTRA_ARGS=$EXTRA_ARGS" \
  "OUTPUT_DIR=$TARGET_MODEL_ROOT/perf" \
  bash "$PERF_RUNNER_SCRIPT"; then
  :
else
  perf_exit=$?
  FAILURE_STATUS="perf_failed"
  exit "$perf_exit"
fi

echo "[$(date '+%F %T')] Collecting results..."
run_in_context "$PERF_CONTAINER" test -d "$TARGET_MODEL_ROOT/perf"
summary_list="$MODEL_ROOT/env/benchmark-summary-files.list0"
run_in_context "$PERF_CONTAINER" find "$TARGET_MODEL_ROOT/perf" \
  -type f -name benchmark_summary.json -print0 | sort -z > "$summary_list"
SUMMARY_FILES=()
while IFS= read -r -d '' summary_file; do
  SUMMARY_FILES+=("$summary_file")
done < "$summary_list"
echo "  Found ${#SUMMARY_FILES[@]} benchmark_summary.json files"
if [ "${#SUMMARY_FILES[@]}" -eq 0 ]; then
  echo "ERROR: perf runner returned success but produced no benchmark_summary.json" >&2
  FAILURE_STATUS="artifact_missing"
  exit 1
fi

for summary_file in "${SUMMARY_FILES[@]}"; do
  relative_path="${summary_file#"$TARGET_MODEL_ROOT/perf/"}"
  artifact_dir="$(dirname "$relative_path")"
  if ! run_in_context "$PERF_CONTAINER" cat "$summary_file" | \
    python3 -c '
import json
import pathlib
import sys

output, model, artifact_dir, source = sys.argv[1:]
record = json.load(sys.stdin)
if not isinstance(record, dict):
    raise TypeError("benchmark_summary.json must contain a JSON object")
record.update(model=model, parallel_dir=artifact_dir, source=source)
target = pathlib.Path(output)
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
' "$METRICS_FILE" "$MODEL_NAME" "$artifact_dir" "$summary_file"; then
    FAILURE_STATUS="artifact_invalid"
    exit 1
  fi
done

echo "[$(date '+%F %T')] Stopping service..."
if stop_service; then
  SERVICE_STARTED=false
else
  FAILURE_STATUS="cleanup_failed"
  exit 1
fi
snapshot_after
append_status "completed"
STATUS_WRITTEN=true
echo "[$(date '+%F %T')] === $MODEL_NAME done ==="
