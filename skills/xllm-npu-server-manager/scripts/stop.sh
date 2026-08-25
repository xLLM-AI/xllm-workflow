#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
PID_FILE_EXPLICIT=false
[ -z "${PID_FILE+x}" ] || PID_FILE_EXPLICIT=true
RUN_ROOT="${RUN_ROOT:-}"
ATTEMPT_ID="${ATTEMPT_ID:-}"
if [ "$PID_FILE_EXPLICIT" = false ] && [ -z "$ATTEMPT_ID" ] && [ -n "$RUN_ROOT" ] && [ -f "$RUN_ROOT/service/current-attempt" ]; then
  ATTEMPT_ID="$(< "$RUN_ROOT/service/current-attempt")"
fi
if [ "$PID_FILE_EXPLICIT" = true ] && [ -z "${ATTEMPT_DIR:-}" ]; then
  ATTEMPT_DIR=""
else
  ATTEMPT_DIR="${ATTEMPT_DIR:-${ATTEMPT_ID:+$RUN_ROOT/service/$ATTEMPT_ID}}"
fi
LOG_DIR="${LOG_DIR:-${ATTEMPT_DIR:-${RUN_ROOT:+$RUN_ROOT/service/log}}}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/log}"
PID_FILE="${PID_FILE:-${ATTEMPT_DIR:+$ATTEMPT_DIR/pids.txt}}"
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

if [ -z "$ATTEMPT_DIR" ] && [ "$(basename "$PID_FILE")" = pids.txt ]; then
  ATTEMPT_DIR="$(dirname "$PID_FILE")"
fi
if [ -n "$ATTEMPT_DIR" ] && [ -f "$ATTEMPT_DIR/launch.json" ]; then
  ATTEMPT_ID="${ATTEMPT_ID:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["attempt_id"])' "$ATTEMPT_DIR/launch.json")}"
  mapfile -t PORTS < <(python3 -c 'import json,sys; [print(x) for x in json.load(open(sys.argv[1])).get("ports", [])]' "$ATTEMPT_DIR/launch.json")
  if [ -n "${NPU_PHYSICAL_DEVICES:-}" ] && [ -z "${NPU_QUIESCENCE_SNAPSHOT:-}" ]; then
    NPU_QUIESCENCE_SNAPSHOT="$ATTEMPT_DIR/npu-after.json"
    # Host-level physical-device checks must not inherit the service's logical
    # visibility remapping; otherwise physical card 7 can be queried as NPU 3.
    snapshot=(env -u ASCEND_RT_VISIBLE_DEVICES -u ASCEND_VISIBLE_DEVICES -u NPU_VISIBLE_DEVICES python3 "$PROJECT_ROOT/skills/xllm-npu-benchmark/scripts/capture_fairness_snapshot.py" --output "$NPU_QUIESCENCE_SNAPSHOT" --raw-dir "$ATTEMPT_DIR/npu-after-raw")
    IFS=',' read -ra physical_devices <<< "$NPU_PHYSICAL_DEVICES"
    for device in "${physical_devices[@]}"; do snapshot+=(--physical-device "$device"); done
    if ! "${snapshot[@]}"; then
      echo "WARNING: NPU quiescence snapshot reported collection errors" >&2
    fi
  fi
  cleanup=(python3 "$SCRIPT_DIR/service_lifecycle.py" cleanup --attempt-dir "$ATTEMPT_DIR" --attempt-id "$ATTEMPT_ID" --pid-file "$PID_FILE")
  if [ -n "${NPU_QUIESCENCE_SNAPSHOT:-}" ]; then cleanup+=(--npu-snapshot "$NPU_QUIESCENCE_SNAPSHOT"); fi
  if [ -n "${NPU_PHYSICAL_DEVICES:-}" ]; then
    IFS=',' read -ra expected_physical_devices <<< "$NPU_PHYSICAL_DEVICES"
    for device in "${expected_physical_devices[@]}"; do cleanup+=(--expected-physical-device "$device"); done
  fi
  for port in "${PORTS[@]}"; do cleanup+=(--port "$port"); done
  "${cleanup[@]}"
else
  rm -f "$PID_FILE"
fi
printf 'Stopped %s xLLM rank(s).\n' "${#pids[@]}"
