#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
RUN_ROOT="${RUN_ROOT:-}"
LOG_DIR="${LOG_DIR:-${RUN_ROOT:+$RUN_ROOT/service/log}}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/log}"
PID_FILE="${PID_FILE:-${RUN_ROOT:+$RUN_ROOT/service/xllm.pids}}"
PID_FILE="${PID_FILE:-$LOG_DIR/xllm.pids}"
STOP_TIMEOUT="${STOP_TIMEOUT:-30}"

if [[ ! "$STOP_TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "ERROR: STOP_TIMEOUT must be a non-negative integer" >&2
  exit 2
fi
if [ ! -f "$PID_FILE" ]; then
  echo "No xLLM PID file found at $PID_FILE; nothing to stop."
  exit 0
fi

pids=()
declare -A EXPECTED_START_TIMES=()
while read -r pid start_time extra; do
  [ -z "$pid" ] && continue
  if [[ ! "$pid" =~ ^[1-9][0-9]*$ ]] || [[ ! "$start_time" =~ ^[0-9]+$ ]] || [ -n "${extra:-}" ]; then
    echo "ERROR: invalid process identity in $PID_FILE: $pid ${start_time:-}" >&2
    exit 2
  fi
  pids+=("$pid")
  EXPECTED_START_TIMES[$pid]="$start_time"
done < "$PID_FILE"

read_start_time() {
  local pid="$1" stat_line fields
  [ -r "/proc/$pid/stat" ] || return 1
  stat_line="$(< "/proc/$pid/stat")"
  fields="${stat_line##*) }"
  set -- $fields
  [ "$#" -ge 20 ] || return 1
  printf '%s' "${20}"
}

identity_matches() {
  local pid="$1" current_start_time
  current_start_time="$(read_start_time "$pid")" || return 1
  [ "$current_start_time" = "${EXPECTED_START_TIMES[$pid]}" ]
}

is_running() {
  local pid="$1" state
  if ! identity_matches "$pid" || ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  if [ -r "/proc/$pid/stat" ]; then
    state="$(awk '{print $3}' "/proc/$pid/stat")"
    [ "$state" != Z ]
  fi
}

for pid in "${pids[@]}"; do
  if identity_matches "$pid"; then
    kill -TERM "$pid" 2>/dev/null || true
  else
    echo "Skipping stale or exited PID $pid; process identity no longer matches."
  fi
done

deadline=$((SECONDS + STOP_TIMEOUT))
while [ "$SECONDS" -lt "$deadline" ]; do
  alive=false
  for pid in "${pids[@]}"; do
    if is_running "$pid"; then
      alive=true
      break
    fi
  done
  [ "$alive" = false ] && break
  sleep 1
done

for pid in "${pids[@]}"; do
  if is_running "$pid"; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
done
rm -f "$PID_FILE"
printf 'Stopped %s xLLM rank(s).\n' "${#pids[@]}"
