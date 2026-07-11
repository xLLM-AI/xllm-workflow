import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
PERF_RUNNER = ROOT / "skills/xllm-npu-perf-runner/scripts/eval_perf.sh"
ACCURACY_RUNNER = ROOT / "skills/xllm-npu-accuracy-runner/scripts/eval_acc.sh"
SERVER_RUNNER = ROOT / "skills/xllm-npu-server-manager/scripts/run.sh"
SERVER_STOPPER = ROOT / "skills/xllm-npu-server-manager/scripts/stop.sh"
BATCH_RUNNER = ROOT / "skills/xllm-npu-batch-perf/scripts/run_single_model.sh"


def write_executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def run_script(script, *, env, cwd=None):
    full_env = os.environ.copy()
    full_env["BASH_ENV"] = "/dev/null"
    full_env.update({key: str(value) for key, value in env.items()})
    return subprocess.run(
        ["/bin/bash", str(script)],
        cwd=cwd,
        env=full_env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_perf_runner_uses_repo_root_outputs_dir_and_stops_on_first_failure(tmp_path):
    fakebin = tmp_path / "fakebin"
    args_file = tmp_path / "args.jsonl"
    cwd_file = tmp_path / "cwd.txt"
    count_file = tmp_path / "count.txt"
    write_executable(
        fakebin / "evalscope",
        """#!/bin/bash
python3 - "$ARGS_FILE" "$PWD" "$@" <<'PY'
import json
import sys
path, cwd, *args = sys.argv[1:]
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps({"cwd": cwd, "args": args}) + "\\n")
PY
count=0
[ ! -f "$COUNT_FILE" ] || count="$(cat "$COUNT_FILE")"
count=$((count + 1))
printf '%s\n' "$count" > "$COUNT_FILE"
if [ "${FAIL_FIRST:-false}" = true ] && [ "$count" -eq 1 ]; then
  exit 41
fi
""",
    )

    result = run_script(
        PERF_RUNNER,
        cwd=tmp_path,
        env={
            "PATH": f"{fakebin}:{os.environ['PATH']}",
            "ARGS_FILE": args_file,
            "CWD_FILE": cwd_file,
            "COUNT_FILE": count_file,
            "FAIL_FIRST": "true",
            "PARALLEL_LIST": "1,2",
            "OUTPUT_DIR": tmp_path / "outputs",
        },
    )

    assert result.returncode == 41
    calls = [json.loads(line) for line in args_file.read_text().splitlines()]
    assert len(calls) == 1
    assert calls[0]["cwd"] == str(ROOT)
    assert "--outputs-dir" in calls[0]["args"]
    assert "--output-dir" not in calls[0]["args"]


def test_accuracy_runner_writes_under_run_root(tmp_path):
    fakebin = tmp_path / "fakebin"
    args_file = tmp_path / "args.json"
    write_executable(
        fakebin / "evalscope",
        """#!/bin/bash
python3 - "$ARGS_FILE" "$@" <<'PY'
import json
import sys
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump(sys.argv[2:], stream)
PY
""",
    )
    run_root = tmp_path / "run"

    result = run_script(
        ACCURACY_RUNNER,
        env={
            "PATH": f"{fakebin}:{os.environ['PATH']}",
            "ARGS_FILE": args_file,
            "RUN_ROOT": run_root,
            "TEST_MODE": "full",
        },
    )

    assert result.returncode == 0, result.stderr
    args = json.loads(args_file.read_text())
    work_dir_index = args.index("--work-dir") + 1
    assert args[work_dir_index] == str(run_root / "accuracy")
    assert "--dataset-args" not in args


def process_is_running(pid):
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return False
    fields = stat_path.read_text(encoding="utf-8").split()
    return len(fields) > 2 and fields[2] != "Z"


def test_server_manager_records_and_stops_only_manifest_pids(tmp_path):
    fake_xllm = write_executable(
        tmp_path / "fake-xllm",
        """#!/bin/bash
printf '%s\n' "$$" > "$XLLM_TEST_PID"
trap 'exit 0' TERM INT
while true; do sleep 0.1; done
""",
    )
    run_root = tmp_path / "run"
    pid_file = run_root / "service/xllm.pids"
    env = {
        "MODEL_PATH": "/models/test",
        "NNODES": "1",
        "ASCEND_RT_VISIBLE_DEVICES": "3",
        "XLLM_BIN": fake_xllm,
        "RUN_ROOT": run_root,
        "PID_FILE": pid_file,
        "XLLM_TEST_PID": tmp_path / "child.pid",
        "PYTORCH_INSTALL_PATH": tmp_path / "torch",
        "PYTORCH_NPU_INSTALL_PATH": tmp_path / "torch_npu",
        "SOURCE_VENDOR_ENV": "false",
    }

    started = run_script(SERVER_RUNNER, env=env)
    assert started.returncode == 0, started.stderr
    deadline = time.time() + 3
    while not (tmp_path / "child.pid").exists() and time.time() < deadline:
        time.sleep(0.05)
    pid = int((tmp_path / "child.pid").read_text())
    recorded_pid, start_time = pid_file.read_text().split()
    assert recorded_pid == str(pid)
    assert start_time.isdigit()
    assert process_is_running(pid)

    stopped = run_script(
        SERVER_STOPPER,
        env={**env, "STOP_TIMEOUT": "2"},
    )
    assert stopped.returncode == 0, stopped.stderr
    deadline = time.time() + 2
    while process_is_running(pid) and time.time() < deadline:
        time.sleep(0.05)
    assert not process_is_running(pid)
    assert not pid_file.exists()


def test_server_stopper_skips_reused_or_stale_pid(tmp_path):
    sleeper = subprocess.Popen(["sleep", "10"])
    pid_file = tmp_path / "xllm.pids"
    pid_file.write_text(f"{sleeper.pid} 1\n", encoding="utf-8")
    try:
        result = run_script(
            SERVER_STOPPER,
            env={"PID_FILE": pid_file, "STOP_TIMEOUT": "0"},
        )
        assert result.returncode == 0, result.stderr
        assert "process identity no longer matches" in result.stdout
        assert sleeper.poll() is None
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=3)


def batch_env(tmp_path, fakebin):
    model_root = tmp_path / "run/model"
    return {
        "PATH": f"{fakebin}:{os.environ['PATH']}",
        "MODEL_NAME": "test-model",
        "MODEL_PATH": "/models/test-model",
        "TOKENIZER_PATH": "/models/test-model",
        "NNODES": "1",
        "ASCEND_RT_VISIBLE_DEVICES": "3",
        "MODEL_ROOT": model_root,
        "BATCH_ROOT": tmp_path / "run",
        "XLLM_BIN": tmp_path / "fake-xllm",
        "READY_TIMEOUT": "2",
        "READY_INTERVAL": "1",
        "STOP_TIMEOUT": "2",
        "PYTORCH_INSTALL_PATH": tmp_path / "torch",
        "PYTORCH_NPU_INSTALL_PATH": tmp_path / "torch_npu",
        "SOURCE_VENDOR_ENV": "false",
        "XLLM_TEST_PID": tmp_path / "child.pid",
    }


def test_batch_runner_resolves_children_and_collects_nested_results(tmp_path):
    fakebin = tmp_path / "fakebin"
    write_executable(fakebin / "curl", "#!/bin/bash\nexit 0\n")
    write_executable(fakebin / "npu-smi", "#!/bin/bash\necho 'fake npu status'\n")
    write_executable(
        fakebin / "evalscope",
        """#!/bin/bash
output=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = --outputs-dir ]; then output="$2"; shift 2; else shift; fi
done
mkdir -p "$output/parallel 1/nested"
printf '%s\n' '{"throughput": 12.5}' > "$output/parallel 1/nested/benchmark_summary.json"
""",
    )
    write_executable(
        tmp_path / "fake-xllm",
        """#!/bin/bash
printf '%s\n' "$$" > "$XLLM_TEST_PID"
trap 'exit 0' TERM INT
while true; do sleep 0.1; done
""",
    )
    env = batch_env(tmp_path, fakebin)

    result = run_script(BATCH_RUNNER, env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    records = [
        json.loads(line)
        for line in (tmp_path / "run/all_metrics.jsonl").read_text().splitlines()
    ]
    assert records[0]["throughput"] == 12.5
    assert records[0]["parallel_dir"] == "parallel 1/nested"
    assert records[-1] == {"model": "test-model", "status": "completed"}


def test_batch_runner_preserves_perf_failure_and_cleans_up(tmp_path):
    fakebin = tmp_path / "fakebin"
    events = tmp_path / "events.txt"
    write_executable(fakebin / "curl", "#!/bin/bash\nexit 0\n")
    write_executable(fakebin / "npu-smi", "#!/bin/bash\necho fake\n")
    server = write_executable(
        tmp_path / "server.sh",
        "#!/bin/bash\necho start >> \"$EVENTS\"\n",
    )
    stopper = write_executable(
        tmp_path / "stop.sh",
        "#!/bin/bash\necho stop >> \"$EVENTS\"\n",
    )
    perf = write_executable(
        tmp_path / "perf.sh",
        "#!/bin/bash\necho perf >> \"$EVENTS\"\nexit 42\n",
    )
    env = batch_env(tmp_path, fakebin)
    env.update(
        {
            "EVENTS": events,
            "SERVER_MANAGER_SCRIPT": server,
            "SERVER_STOP_SCRIPT": stopper,
            "PERF_RUNNER_SCRIPT": perf,
        }
    )

    result = run_script(BATCH_RUNNER, env=env, cwd=tmp_path)

    assert result.returncode == 42
    assert events.read_text().splitlines() == ["start", "perf", "stop"]
    records = [
        json.loads(line)
        for line in (tmp_path / "run/all_metrics.jsonl").read_text().splitlines()
    ]
    assert records[-1]["status"] == "perf_failed"
    assert all(record["status"] != "completed" for record in records if "status" in record)


def test_batch_runner_rejects_ambiguous_devices_and_cross_container_localhost(tmp_path):
    base = {
        "MODEL_NAME": "test-model",
        "MODEL_PATH": "/models/test-model",
        "TOKENIZER_PATH": "/models/test-model",
        "MODEL_ROOT": tmp_path / "run/model",
    }
    duplicate = run_script(
        BATCH_RUNNER,
        env={
            **base,
            "NNODES": "2",
            "ASCEND_RT_VISIBLE_DEVICES": "3,3",
        },
    )
    assert duplicate.returncode == 2
    assert "duplicate NPU device ID" in duplicate.stderr

    cross_container = run_script(
        BATCH_RUNNER,
        env={
            **base,
            "NNODES": "1",
            "ASCEND_RT_VISIBLE_DEVICES": "3",
            "XLLM_CONTAINER": "server",
            "EVALSCOPE_CONTAINER": "client",
            "API_URL": "http://127.0.0.1:17112/v1",
        },
    )
    assert cross_container.returncode == 2
    assert "not reachable from a different EvalScope container" in cross_container.stderr
