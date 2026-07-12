import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/xllm-npu-server-manager/scripts/service_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("service_lifecycle", SCRIPT)
lifecycle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = lifecycle
SPEC.loader.exec_module(lifecycle)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_launch_records_attempt_scoped_identity(tmp_path):
    attempt = tmp_path / "service/attempt-001"
    attempt.mkdir(parents=True)
    command = attempt / "command.sh"
    pids = attempt / "pids.txt"
    log = attempt / "node_0.log"
    for path in (command, pids, log):
        path.write_text("evidence\n", encoding="utf-8")

    code = lifecycle.command_launch(
        argparse.Namespace(
            attempt_dir=attempt,
            attempt_id="attempt-001",
            api_url="http://127.0.0.1:18000/v1",
            model="/models/test",
            command_file=command,
            pid_file=pids,
            logs=[log],
            ports=[18000],
            visible_devices=[3],
        )
    )

    assert code == 0
    assert read(attempt / "launch.json")["status"] == "PASS"
    assert read(attempt / "launch.json")["attempt_id"] == "attempt-001"
    assert (attempt / "environment.json").is_file()


def test_ready_requires_expected_advertised_model(tmp_path, monkeypatch):
    attempt = tmp_path / "attempt-001"
    monkeypatch.setattr(lifecycle, "fetch_json", lambda *_args, **_kwargs: {"data": [{"id": "served"}]})
    args = argparse.Namespace(
        attempt_dir=attempt,
        attempt_id="attempt-001",
        api_url="http://127.0.0.1:18000/v1",
        expected_model_id="expected",
        timeout=0,
        interval=0,
    )

    assert lifecycle.command_ready(args) == 1
    assert read(attempt / "ready.json")["status"] == "FAILED"

    args.expected_model_id = "served"
    assert lifecycle.command_ready(args) == 0
    assert read(attempt / "ready.json")["status"] == "PASS"


def test_smoke_requires_real_completion_choices(tmp_path, monkeypatch):
    attempt = tmp_path / "attempt-001"
    monkeypatch.setattr(lifecycle, "fetch_json", lambda *_args, **_kwargs: {"choices": []})
    args = argparse.Namespace(
        attempt_dir=attempt,
        attempt_id="attempt-001",
        api_url="http://127.0.0.1:18000/v1",
        model="test",
        request_json=None,
        prompt="Reply with OK.",
        max_tokens=1,
        timeout=1,
    )

    assert lifecycle.command_smoke(args) == 1
    assert read(attempt / "smoke.json")["status"] == "FAILED"

    monkeypatch.setattr(lifecycle, "fetch_json", lambda *_args, **_kwargs: {"choices": [{"message": {"content": "OK"}}]})
    assert lifecycle.command_smoke(args) == 0
    assert read(attempt / "smoke.json")["status"] == "PASS"
    assert (attempt / "smoke-response.json").is_file()


def test_cleanup_preserves_pid_evidence_and_checks_ports(tmp_path, monkeypatch):
    attempt = tmp_path / "attempt-001"
    attempt.mkdir()
    pids = attempt / "pids.txt"
    pids.write_text("123 456\n", encoding="utf-8")
    (attempt / "launch.json").write_text(json.dumps({"visible_devices": [2]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "process_identity_matches", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "port_is_free", lambda _host, port: port == 18000)
    snapshot = attempt / "npu-after.json"
    snapshot.write_text(json.dumps({"collection_errors": [], "devices": [{"physical_id": 2, "processes": []}]}) + "\n", encoding="utf-8")
    args = argparse.Namespace(
        attempt_dir=attempt,
        attempt_id="attempt-001",
        pid_file=pids,
        host="127.0.0.1",
        ports=[18000],
        npu_snapshot=snapshot,
    )

    assert lifecycle.command_cleanup(args) == 0
    assert pids.is_file()
    assert read(attempt / "cleanup.json")["status"] == "PASS"

    args.ports = [18001]
    assert lifecycle.command_cleanup(args) == 1
    assert read(attempt / "cleanup.json")["occupied_ports"] == [18001]


def test_cleanup_cannot_pass_without_machine_npu_snapshot(tmp_path, monkeypatch):
    attempt = tmp_path / "attempt-001"
    attempt.mkdir()
    pids = attempt / "pids.txt"
    pids.write_text("123 456\n", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "process_identity_matches", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "port_is_free", lambda *_args: True)
    args = argparse.Namespace(attempt_dir=attempt, attempt_id="attempt-001", pid_file=pids, host="127.0.0.1", ports=[], npu_snapshot=None)

    assert lifecycle.command_cleanup(args) == 1
    assert read(attempt / "cleanup.json")["npu_quiescence"] == "NOT_CHECKED"


def test_cleanup_snapshot_must_match_launched_devices(tmp_path, monkeypatch):
    attempt = tmp_path / "attempt-001"
    attempt.mkdir()
    pids = attempt / "pids.txt"
    pids.write_text("123 456\n", encoding="utf-8")
    (attempt / "launch.json").write_text(json.dumps({"visible_devices": [3]}) + "\n", encoding="utf-8")
    snapshot = attempt / "npu-after.json"
    snapshot.write_text(json.dumps({"collection_errors": [], "devices": [{"physical_id": 99, "processes": []}]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "process_identity_matches", lambda *_args: False)
    monkeypatch.setattr(lifecycle, "port_is_free", lambda *_args: True)
    args = argparse.Namespace(attempt_dir=attempt, attempt_id="attempt-001", pid_file=pids, host="127.0.0.1", ports=[], npu_snapshot=snapshot)

    assert lifecycle.command_cleanup(args) == 1
    assert read(attempt / "cleanup.json")["npu_quiescence"] == "FAILED"
