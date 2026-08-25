import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/xllm-npu-benchmark/scripts/capture_fairness_snapshot.py"
SPEC = importlib.util.spec_from_file_location("capture_fairness_snapshot", SCRIPT)
capture = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = capture
SPEC.loader.exec_module(capture)


MAPPING = """
NPU ID  Chip ID  Chip Logic ID  Chip Phy-ID  Chip Name
0       0        2              2            Ascend
0       1        3              3            Ascend
0       2        -              -            Mcu
"""
USAGES = """
HBM Usage Rate(%) : 4
Aicore Usage Rate(%) : 1
Chip ID : 0
HBM Usage Rate(%) : 8
Aicore Usage Rate(%) : 2
Chip ID : 1
"""
HEALTH = """
Health : OK
Chip ID : 0
Health : OK
Chip ID : 1
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parsers_keep_logic_to_chip_mapping_and_processes():
    mapping = capture.parse_mapping(MAPPING)
    usage = capture.parse_keyed_by_chip(
        USAGES,
        {"HBM Usage Rate(%)": "hbm_usage_pct", "Aicore Usage Rate(%)": "aicore_usage_pct"},
    )
    processes = capture.parse_processes(
        "Process id:123 Process name: worker Process memory(MB):42\nChip ID : 0\n"
    )

    assert mapping == {2: (0, 0), 3: (0, 1)}
    assert usage[0] == {"hbm_usage_pct": 4, "aicore_usage_pct": 1}
    assert processes[0][0]["pid"] == 123


def test_ascend_summary_maps_device_pid_to_current_namespace_pid():
    summary = """
| NPU     Chip | Process id | Process name | Process memory(MB) | Process id in container |
| 7       0    | 351533     |              | 51409              | 4109018                 |
"""
    mapping = capture.parse_container_pid_mapping(summary)
    processes = capture.apply_container_pid_mapping(
        [{"pid": 351533, "name": "", "memory_mb": 51409}], 7, 0, mapping
    )

    assert mapping == {(7, 0, 351533): 4109018}
    assert processes == [
        {"pid": 4109018, "device_pid": 351533, "name": "", "memory_mb": 51409}
    ]


def test_replay_capture_writes_normalized_snapshot(tmp_path):
    replay = tmp_path / "replay"
    write(replay / "mapping.txt", MAPPING)
    write(replay / "usages-npu0.txt", USAGES)
    write(replay / "health-npu0.txt", HEALTH)
    write(replay / "processes-npu0.txt", "No process in device.\nChip ID : 0\nChip ID : 1\n")
    write(replay / "meminfo.txt", "SwapTotal: 100 kB\nSwapFree: 75 kB\n")
    empty_proc = tmp_path / "proc"
    empty_proc.mkdir()
    output = tmp_path / "snapshot.json"
    raw = tmp_path / "raw"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output", str(output),
            "--raw-dir", str(raw),
            "--physical-device", "2",
            "--physical-device", "3",
            "--replay-dir", str(replay),
            "--load1", "1.25",
            "--process-scan-root", str(empty_proc),
        ],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "BASH_ENV": "/dev/null"},
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert [device["physical_id"] for device in snapshot["devices"]] == [2, 3]
    assert snapshot["devices"][0]["hbm_usage_pct"] == 4
    assert snapshot["host"]["swap_used_bytes"] == 25 * 1024
    assert snapshot["collection_errors"] == []
    assert snapshot["backend"] == "ascend-npu"
    assert snapshot["parser_version"] == 3
    assert (raw / "mapping.txt").is_file()


def test_ascend_parser_accepts_key_value_mapping_and_field_aliases():
    mapping = capture.parse_mapping(
        "NPU ID: 1\nChip ID: 3\nChip Physical ID: 7\n"
    )
    usage = capture.parse_keyed_by_chip(
        "HBM Usage Rate (%): 12\nAI Core Usage Rate(%): 9\nChip ID: 3\n",
        {
            "HBM Usage Rate (%)": "hbm_usage_pct",
            "AI Core Usage Rate(%)": "aicore_usage_pct",
        },
    )

    assert mapping == {7: (1, 3)}
    assert usage == {3: {"hbm_usage_pct": 12, "aicore_usage_pct": 9}}


def test_nvidia_replay_uses_same_normalized_snapshot_contract(tmp_path):
    replay = tmp_path / "replay"
    write(replay / "gpu-query.csv", "0, GPU-abc, 2048, 8192, 37\n1, GPU-def, 0, 8192, 0\n")
    write(replay / "process-query.csv", "GPU-abc, 999999, worker, 512\n")
    write(replay / "backend-version.txt", "600.01\n")
    write(replay / "meminfo.txt", "SwapTotal: 10 kB\nSwapFree: 10 kB\n")
    empty_proc = tmp_path / "proc"
    empty_proc.mkdir()
    output = tmp_path / "snapshot.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output", str(output),
            "--raw-dir", str(tmp_path / "raw"),
            "--backend", "nvidia-gpu",
            "--physical-device", "0",
            "--physical-device", "1",
            "--replay-dir", str(replay),
            "--load1", "0",
            "--process-scan-root", str(empty_proc),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output.read_text())
    assert snapshot["backend"] == "nvidia-gpu"
    assert snapshot["backend_version"] == "600.01"
    assert snapshot["devices"][0]["physical_id"] == 0
    assert snapshot["devices"][0]["hbm_usage_pct"] == 25.0
    assert snapshot["devices"][0]["aicore_usage_pct"] == 37.0
    assert snapshot["devices"][0]["processes"][0]["owned_by_attempt"] is False
    assert snapshot["devices"][1]["processes"] == []


def test_nvidia_process_parser_handles_quoted_process_names():
    processes = capture.parse_nvidia_processes(
        'GPU-abc, 123, "worker, shard 0", 256\n'
    )

    assert processes["GPU-abc"][0]["name"] == "worker, shard 0"


def test_unmapped_device_is_reported_without_guessing(tmp_path):
    replay = tmp_path / "replay"
    write(replay / "mapping.txt", MAPPING)
    write(replay / "meminfo.txt", "SwapTotal: 0 kB\nSwapFree: 0 kB\n")
    output = tmp_path / "snapshot.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output", str(output),
            "--raw-dir", str(tmp_path / "raw"),
            "--physical-device", "9",
            "--replay-dir", str(replay),
            "--load1", "0",
            "--process-scan-root", str(tmp_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot["devices"] == []
    assert "physical device missing from mapping: 9" in snapshot["collection_errors"]


def test_missing_per_device_records_fail_capture(tmp_path):
    replay = tmp_path / "replay"
    write(replay / "mapping.txt", MAPPING)
    write(replay / "usages-npu0.txt", "")
    write(replay / "health-npu0.txt", "")
    write(replay / "processes-npu0.txt", "")
    write(replay / "meminfo.txt", "SwapTotal: 0 kB\nSwapFree: 0 kB\n")
    output = tmp_path / "snapshot.json"

    result = subprocess.run([
        sys.executable, str(SCRIPT), "--output", str(output), "--raw-dir", str(tmp_path / "raw"),
        "--physical-device", "2", "--replay-dir", str(replay), "--load1", "0",
        "--process-scan-root", str(tmp_path),
    ], text=True, capture_output=True, check=False)

    assert result.returncode == 1
    errors = json.loads(output.read_text())["collection_errors"]
    assert "usage record missing for physical device: 2" in errors
    assert "health record missing for physical device: 2" in errors
    assert "process record missing for physical device: 2" in errors


def test_incomplete_per_device_records_fail_capture(tmp_path):
    replay = tmp_path / "replay"
    write(replay / "mapping.txt", MAPPING)
    write(replay / "usages-npu0.txt", "Chip ID : 0\n")
    write(replay / "health-npu0.txt", "Chip ID : 0\n")
    write(replay / "processes-npu0.txt", "Chip ID : 0\n")
    write(replay / "meminfo.txt", "SwapTotal: 0 kB\nSwapFree: 0 kB\n")
    output = tmp_path / "snapshot.json"

    result = subprocess.run([
        sys.executable, str(SCRIPT), "--output", str(output), "--raw-dir", str(tmp_path / "raw"),
        "--physical-device", "2", "--replay-dir", str(replay), "--load1", "0",
        "--process-scan-root", str(tmp_path),
    ], text=True, capture_output=True, check=False)

    assert result.returncode == 1
    errors = json.loads(output.read_text())["collection_errors"]
    assert "usage fields incomplete for physical device: 2" in errors
    assert "health fields incomplete for physical device: 2" in errors
