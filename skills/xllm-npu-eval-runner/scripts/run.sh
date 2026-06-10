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

export ASCEND_RT_VISIBLE_DEVICES=12,13,14,15
export ASDOPS_LOG_TO_STDOUT=1
export ASDOPS_LOG_LEVEL=0
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export NPU_MEMORY_FRACTION=0.90
export ATB_WORKSPACE_MEM_ALLOC_ALG_TYPE=3
export ATB_WORKSPACE_MEM_ALLOC_GLOBAL=1
export OMP_NUM_THREADS=12
export HCCL_CONNECT_TIMEOUT=7200
export INF_NAN_MODE_ENABLE=0
export INF_NAN_MODE_FORCE_DISABLE=1

LOG_DIR="$PROJECT_ROOT/log"
mkdir -p "$LOG_DIR"
rm -rf "$LOG_DIR"/node_*.log

export PROFILING_MODE=dynamic

MODEL_PATH="${MODEL_PATH:-/models/Qwen35-27B}"
DRAFT_MODEL_PATH="${DRAFT_MODEL_PATH:-/models/Qwen35-27B-mtp}"
XLLM_BIN="$PROJECT_ROOT/xllm/build/xllm/core/server/xllm"

MASTER_NODE_ADDR="127.0.0.1:12345"
START_PORT=17112
START_DEVICE=0
NNODES=4

export HCCL_IF_BASE_PORT=43433

for (( i=0; i<$NNODES; i++ ))
do
PORT=$((START_PORT + i))
DEVICE=$((START_DEVICE + i))
LOG_FILE="$LOG_DIR/node_$i.log"
"$XLLM_BIN" \
    --model "$MODEL_PATH" \
    --devices="npu:$DEVICE" \
    --port $PORT \
    --master_node_addr=$MASTER_NODE_ADDR \
    --nnodes=$NNODES \
    --max_memory_utilization=0.75 \
    --max_tokens_per_batch=8192 \
    --max_seqs_per_batch=8 \
    --block_size=128 \
    --communication_backend="lccl" \
    --enable_prefix_cache=true \
    --enable_chunked_prefill=true \
    --max_concurrent_requests=8 \
    --draft_model "$DRAFT_MODEL_PATH" \
    --draft_devices="npu:$DEVICE" \
    --num_speculative_tokens 3 \
    --enable_schedule_overlap=true \
    --enable_graph=true \
    --node_rank=$i  \
    --enable_shm=true  \
    --task="generate" \
    --backend llm \
  >> "$LOG_FILE" 2>&1 &
done
