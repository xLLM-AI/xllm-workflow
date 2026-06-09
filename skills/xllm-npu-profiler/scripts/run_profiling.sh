#!/usr/bin/env bash
# Dynamic msprof collection for an already-running xLLM service.
#
# Usage:
#   scripts/run_profiling.sh <xllm_parent_pid> [output_dir_prefix] [mode]
#
# mode:
#   warmup: run requests without profiling
#   test:   collect profiling for formal requests only
#   full:   warmup first, then collect profiling
#
# Before starting xLLM, the service startup script must include:
#   export PROFILING_MODE=dynamic

set -euo pipefail
set -x

XLLM_PID=${1:-}
OUTPUT_DIR=${2:-./xllm_profiling}_$(date +%Y%m%d)_$(date +%H%M%S)
MODE=${3:-full}

PORT=${PORT:-38050}
BATCH_SIZE=${BATCH_SIZE:-1}
NUM_BATCHES=${NUM_BATCHES:-5}
WARMUP_BATCHES=${WARMUP_BATCHES:-2}
INPUT_TOKENS=${INPUT_TOKENS:-128}
OUTPUT_TOKENS=${OUTPUT_TOKENS:-20}
MODEL=${MODEL:-Qwen35-27B}
TOKENIZER=${TOKENIZER:-/models/Qwen35-27B}

if [[ -z "$XLLM_PID" ]]; then
  echo "Usage: $0 <xllm_parent_pid> [output_dir_prefix] [warmup|test|full]"
  echo "Find the parent PID with: ps -ef | grep xllm"
  exit 1
fi

if [[ "$MODE" != "warmup" && "$MODE" != "test" && "$MODE" != "full" ]]; then
  echo "Invalid mode: $MODE"
  echo "Expected: warmup | test | full"
  exit 1
fi

echo "=== Profiling Test Configuration ==="
echo "Output Dir: $OUTPUT_DIR"
echo "XLLM PID: $XLLM_PID"
echo "Mode: $MODE"
echo "Batch Size: $BATCH_SIZE"
echo "Test Batches: $NUM_BATCHES"
echo "Warmup Batches: $WARMUP_BATCHES"
echo "Input Tokens: $INPUT_TOKENS"
echo "Output Tokens: $OUTPUT_TOKENS"
echo "Model: $MODEL"
echo "Tokenizer: $TOKENIZER"
echo "Port: $PORT"
echo "===================================="

mkdir -p "$OUTPUT_DIR"

PIPE_FILE="/tmp/2msprof_pipe_$$"
rm -f "$PIPE_FILE"
mkfifo "$PIPE_FILE"

MSPROF_PID=""
cleanup() {
  if [[ -z "$MSPROF_PID" ]]; then
    rm -f "$PIPE_FILE"
    return
  fi
  echo "quit" >&3 2>/dev/null || true
  sleep 1
  exec 3>&- 2>/dev/null || true
  rm -f "$PIPE_FILE"
  wait "$MSPROF_PID" 2>/dev/null || true
  MSPROF_PID=""
}
trap cleanup EXIT INT TERM

echo "Starting msprof in dynamic attach mode..."
msprof \
  --dynamic=on \
  --output="$OUTPUT_DIR" \
  --model-execution=on \
  --runtime-api=on \
  --aicpu=on \
  --pid="$XLLM_PID" < "$PIPE_FILE" &

MSPROF_PID=$!
exec 3>"$PIPE_FILE"
sleep 2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_ARGS=(
  --model "$MODEL"
  --tokenizer "$TOKENIZER"
  --port "$PORT"
  --input-tokens "$INPUT_TOKENS"
  --output-tokens "$OUTPUT_TOKENS"
)

run_warmup() {
  echo "========== WARMUP PHASE (Profiling OFF) =========="
  python3 "$SCRIPT_DIR/multibatch_test.py" \
    --batch-size "$BATCH_SIZE" \
    --num-batches "$WARMUP_BATCHES" \
    "${COMMON_ARGS[@]}" 2>&1 | sed 's/^/[WARMUP] /'
  sleep 3
}

run_test() {
  echo "========== FORMAL TEST PHASE (Profiling ON) =========="
  echo "start" >&3
  sleep 2
  python3 "$SCRIPT_DIR/multibatch_test.py" \
    --batch-size "$BATCH_SIZE" \
    --num-batches "$NUM_BATCHES" \
    "${COMMON_ARGS[@]}" 2>&1 | sed 's/^/[TEST] /'
  echo "stop" >&3
  sleep 3
}

case "$MODE" in
  warmup)
    run_warmup
    ;;
  test)
    run_test
    ;;
  full)
    run_warmup
    sleep 2
    run_test
    ;;
esac

LATEST_PROF=$(ls -td "$OUTPUT_DIR"/PROF_* 2>/dev/null | head -1 || true)

echo "=== Profiling completed ==="
echo "Raw data directory: $OUTPUT_DIR"
echo "Latest profiling dir: $LATEST_PROF"

if [[ -n "$LATEST_PROF" ]]; then
  echo "=== Exporting profiling data ==="
  msprof --export=on --output="$LATEST_PROF" 2>&1
  REPORT_DIR="$LATEST_PROF/mindstudio_profiler_output"
  if [[ -d "$REPORT_DIR" ]]; then
    echo "Report directory: $REPORT_DIR"
    ls -la "$REPORT_DIR"/
  else
    echo "[Warning] Report directory not found"
  fi
fi
