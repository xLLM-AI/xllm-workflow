#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"

source_if_present() {
  local path="$1"
  if [ -r "$path" ]; then
    # Vendor environment scripts are not guaranteed to be nounset-safe.
    set +u
    # shellcheck disable=SC1090
    source "$path"
    set -u
  fi
}

export PYTHON_INCLUDE_PATH="$(python3 -c 'from sysconfig import get_paths; print(get_paths()["include"])')"
export PYTHON_LIB_PATH="${PYTHON_LIB_PATH:-$PYTHON_INCLUDE_PATH}"
export PYTORCH_NPU_INSTALL_PATH="${PYTORCH_NPU_INSTALL_PATH:-/usr/local/libtorch_npu}"
export PYTORCH_INSTALL_PATH="${PYTORCH_INSTALL_PATH:-$(python3 -c 'import torch, os; print(os.path.dirname(os.path.abspath(torch.__file__)))')}"
export LIBTORCH_ROOT="${LIBTORCH_ROOT:-$PYTORCH_INSTALL_PATH}"
export LD_LIBRARY_PATH="${PYTORCH_NPU_INSTALL_PATH}/lib:${LD_LIBRARY_PATH:-}"

SOURCE_VENDOR_ENV="${SOURCE_VENDOR_ENV:-true}"
if [ "$SOURCE_VENDOR_ENV" = true ]; then
  source_if_present /usr/local/Ascend/ascend-toolkit/set_env.sh
  source_if_present /usr/local/Ascend/nnal/atb/set_env.sh
fi

: "${MODEL_PATH:?MODEL_PATH is required}"
: "${ASCEND_RT_VISIBLE_DEVICES:?ASCEND_RT_VISIBLE_DEVICES is required}"

XLLM_BIN="${XLLM_BIN:-$PROJECT_ROOT/code/xllm/build/xllm/core/server/xllm}"
NNODES="${NNODES:-1}"
START_PORT="${START_PORT:-17112}"
MASTER_NODE_ADDR="${MASTER_NODE_ADDR:-127.0.0.1:12345}"
DRAFT_MODEL_PATH="${DRAFT_MODEL_PATH:-}"
NUM_SPECULATIVE_TOKENS="${NUM_SPECULATIVE_TOKENS:-0}"

if [[ ! "$NNODES" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: NNODES must be a positive integer, got: $NNODES" >&2
  exit 2
fi
if [[ ! "$START_PORT" =~ ^[0-9]+$ ]] || [ "$START_PORT" -lt 1 ] || [ "$START_PORT" -gt 65535 ]; then
  echo "ERROR: START_PORT must be in [1, 65535], got: $START_PORT" >&2
  exit 2
fi
if [[ ! "$NUM_SPECULATIVE_TOKENS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: NUM_SPECULATIVE_TOKENS must be a non-negative integer" >&2
  exit 2
fi
if [ ! -x "$XLLM_BIN" ]; then
  echo "ERROR: xLLM binary is not executable: $XLLM_BIN" >&2
  exit 2
fi

IFS=',' read -r -a VISIBLE_DEVICES <<< "$ASCEND_RT_VISIBLE_DEVICES"
if [ "${#VISIBLE_DEVICES[@]}" -ne "$NNODES" ]; then
  echo "ERROR: NNODES=$NNODES requires exactly $NNODES visible devices; got $ASCEND_RT_VISIBLE_DEVICES" >&2
  exit 2
fi
declare -A SEEN_DEVICES=()
for device in "${VISIBLE_DEVICES[@]}"; do
  if [[ ! "$device" =~ ^[0-9]+$ ]]; then
    echo "ERROR: invalid NPU device id: $device" >&2
    exit 2
  fi
  if [[ -n "${SEEN_DEVICES[$device]:-}" ]]; then
    echo "ERROR: duplicate NPU device id: $device" >&2
    exit 2
  fi
  SEEN_DEVICES[$device]=1
done

export ASCEND_RT_VISIBLE_DEVICES
export ASDOPS_LOG_TO_STDOUT="${ASDOPS_LOG_TO_STDOUT:-1}"
export ASDOPS_LOG_LEVEL="${ASDOPS_LOG_LEVEL:-0}"
export PYTORCH_NPU_ALLOC_CONF="${PYTORCH_NPU_ALLOC_CONF:-expandable_segments:True}"
export NPU_MEMORY_FRACTION="${NPU_MEMORY_FRACTION:-0.90}"
export ATB_WORKSPACE_MEM_ALLOC_ALG_TYPE="${ATB_WORKSPACE_MEM_ALLOC_ALG_TYPE:-3}"
export ATB_WORKSPACE_MEM_ALLOC_GLOBAL="${ATB_WORKSPACE_MEM_ALLOC_GLOBAL:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-12}"
export HCCL_CONNECT_TIMEOUT="${HCCL_CONNECT_TIMEOUT:-7200}"
export INF_NAN_MODE_ENABLE="${INF_NAN_MODE_ENABLE:-0}"
export INF_NAN_MODE_FORCE_DISABLE="${INF_NAN_MODE_FORCE_DISABLE:-1}"
export PROFILING_MODE="${PROFILING_MODE:-dynamic}"
export HCCL_IF_BASE_PORT="${HCCL_IF_BASE_PORT:-43433}"

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

RUN_ROOT="${RUN_ROOT:-}"
LOG_DIR="${LOG_DIR:-${RUN_ROOT:+$RUN_ROOT/service/log}}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/log}"
PID_FILE="${PID_FILE:-${RUN_ROOT:+$RUN_ROOT/service/xllm.pids}}"
PID_FILE="${PID_FILE:-$LOG_DIR/xllm.pids}"
mkdir -p "$LOG_DIR" "$(dirname "$PID_FILE")"
rm -f "$LOG_DIR"/node_*.log
: > "$PID_FILE"

started_pids=()
read_start_time() {
  local pid="$1" stat_line fields
  [ -r "/proc/$pid/stat" ] || return 1
  stat_line="$(< "/proc/$pid/stat")"
  fields="${stat_line##*) }"
  # After removing pid and comm, starttime (field 22) is positional field 20.
  set -- $fields
  [ "$#" -ge 20 ] || return 1
  printf '%s' "${20}"
}

cleanup_partial_launch() {
  local pid
  for pid in "${started_pids[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
}
trap cleanup_partial_launch ERR INT TERM

for ((i = 0; i < NNODES; i++)); do
  port=$((START_PORT + i))
  logical_device=$i
  log_file="$LOG_DIR/node_$i.log"
  cmd=(
    "$XLLM_BIN"
    --model "$MODEL_PATH"
    "--devices=npu:$logical_device"
    --port "$port"
    "--master_node_addr=$MASTER_NODE_ADDR"
    "--nnodes=$NNODES"
    "--max_memory_utilization=$MAX_MEMORY_UTILIZATION"
    "--max_tokens_per_batch=$MAX_TOKENS_PER_BATCH"
    "--max_seqs_per_batch=$MAX_SEQS_PER_BATCH"
    "--block_size=$BLOCK_SIZE"
    "--communication_backend=$COMMUNICATION_BACKEND"
    "--enable_prefix_cache=$ENABLE_PREFIX_CACHE"
    "--enable_chunked_prefill=$ENABLE_CHUNKED_PREFILL"
    "--max_concurrent_requests=$MAX_CONCURRENT_REQUESTS"
    "--enable_schedule_overlap=$ENABLE_SCHEDULE_OVERLAP"
    "--enable_graph=$ENABLE_GRAPH"
    "--node_rank=$i"
    "--enable_shm=$ENABLE_SHM"
    --task=generate
    --backend=llm
  )
  if [ -n "$DRAFT_MODEL_PATH" ] && [ "$NUM_SPECULATIVE_TOKENS" -gt 0 ]; then
    cmd+=(
      --draft_model "$DRAFT_MODEL_PATH"
      "--draft_devices=npu:$logical_device"
      --num_speculative_tokens "$NUM_SPECULATIVE_TOKENS"
    )
  fi

  nohup "${cmd[@]}" >> "$log_file" 2>&1 &
  pid=$!
  started_pids+=("$pid")
  if ! start_time="$(read_start_time "$pid")"; then
    echo "ERROR: xLLM rank $i exited before its process identity could be recorded" >&2
    exit 1
  fi
  printf '%s %s\n' "$pid" "$start_time" >> "$PID_FILE"
done

trap - ERR INT TERM
printf 'Started %s xLLM rank(s); PID file: %s\n' "$NNODES" "$PID_FILE"
