#!/bin/bash
# set -x
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

export PYTHON_INCLUDE_PATH="$(python3 -c 'from sysconfig import get_paths; print(get_paths()["include"])')"
export PYTHON_LIB_PATH="$(python3 -c 'from sysconfig import get_paths; print(get_paths()["include"])')"
export PYTORCH_NPU_INSTALL_PATH=/usr/local/libtorch_npu/
export PYTORCH_INSTALL_PATH="$(python3 -c 'import torch, os; print(os.path.dirname(os.path.abspath(torch.__file__)))')"
export LIBTORCH_ROOT="$PYTORCH_INSTALL_PATH"
export LD_LIBRARY_PATH=/usr/local/libtorch_npu/lib:$LD_LIBRARY_PATH

source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh

export ASCEND_RT_VISIBLE_DEVICES="${ASCEND_RT_VISIBLE_DEVICES:-12,13,14,15}"
export ASDOPS_LOG_TO_STDOUT=1
export ASDOPS_LOG_LEVEL=0
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export NPU_MEMORY_FRACTION="${NPU_MEMORY_FRACTION:-0.90}"
export ATB_WORKSPACE_MEM_ALLOC_ALG_TYPE=3
export ATB_WORKSPACE_MEM_ALLOC_GLOBAL=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-12}"
export HCCL_CONNECT_TIMEOUT="${HCCL_CONNECT_TIMEOUT:-7200}"
export INF_NAN_MODE_ENABLE=0
export INF_NAN_MODE_FORCE_DISABLE=1

LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/log}"
mkdir -p "$LOG_DIR"
rm -rf "$LOG_DIR"/node_*.log

export PROFILING_MODE="${PROFILING_MODE:-dynamic}"

MODEL_PATH="${MODEL_PATH:-/models/Qwen35-27B}"
DRAFT_MODEL_PATH="${DRAFT_MODEL_PATH:-}"
XLLM_BIN="${XLLM_BIN:-$PROJECT_ROOT/xllm/build/xllm/core/server/xllm}"

MASTER_NODE_ADDR="${MASTER_NODE_ADDR:-127.0.0.1:12345}"
START_PORT="${START_PORT:-17112}"
START_DEVICE=0
NNODES="${NNODES:-4}"

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
NUM_SPECULATIVE_TOKENS="${NUM_SPECULATIVE_TOKENS:-0}"

export HCCL_IF_BASE_PORT="${HCCL_IF_BASE_PORT:-43433}"

IFS=',' read -ra VISIBLE_DEVICES <<< "$ASCEND_RT_VISIBLE_DEVICES"

DRAFT_ARGS=""
if [ -n "$DRAFT_MODEL_PATH" ] && [ "$NUM_SPECULATIVE_TOKENS" -gt 0 ] 2>/dev/null; then
  DRAFT_ARGS="--draft_model $DRAFT_MODEL_PATH"
fi

for (( i=0; i<$NNODES; i++ ))
do
PORT=$((START_PORT + i))
DEVICE=$((START_DEVICE + i))
LOG_FILE="$LOG_DIR/node_$i.log"

CMD="$XLLM_BIN \
    --model $MODEL_PATH \
    --devices=npu:$DEVICE \
    --port $PORT \
    --master_node_addr=$MASTER_NODE_ADDR \
    --nnodes=$NNODES \
    --max_memory_utilization=$MAX_MEMORY_UTILIZATION \
    --max_tokens_per_batch=$MAX_TOKENS_PER_BATCH \
    --max_seqs_per_batch=$MAX_SEQS_PER_BATCH \
    --block_size=$BLOCK_SIZE \
    --communication_backend=$COMMUNICATION_BACKEND \
    --enable_prefix_cache=$ENABLE_PREFIX_CACHE \
    --enable_chunked_prefill=$ENABLE_CHUNKED_PREFILL \
    --max_concurrent_requests=$MAX_CONCURRENT_REQUESTS \
    --enable_schedule_overlap=$ENABLE_SCHEDULE_OVERLAP \
    --enable_graph=$ENABLE_GRAPH \
    --node_rank=$i \
    --enable_shm=$ENABLE_SHM \
    --task=generate \
    --backend llm"

if [ -n "$DRAFT_ARGS" ]; then
  CMD="$CMD $DRAFT_ARGS --draft_devices=npu:$DEVICE --num_speculative_tokens $NUM_SPECULATIVE_TOKENS"
fi

eval "$CMD" >> "$LOG_FILE" 2>&1 &
done
