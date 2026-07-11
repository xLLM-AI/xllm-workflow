import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_run_evidence.py"
COMMIT = "1" * 40
BINARY_SHA = "2" * 64
REQUEST_SHA = "3" * 64


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def write_file(path, text="artifact\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def invoke(run_root):
    env = os.environ.copy()
    env["BASH_ENV"] = "/dev/null"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--run-root", str(run_root)],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def verdict(run_root):
    return json.loads((run_root / "evidence-verdict.json").read_text())


def base_evidence(run_root, evidence_type):
    attempt = "attempt-001"
    service_root = run_root / "service" / attempt
    for name in ("command.sh", "pids.txt", "node_0.log"):
        write_file(service_root / name)
    for name in ("ready.json", "smoke.json"):
        write_json(service_root / name, {"status": "PASS", "attempt_id": attempt})
    write_json(
        service_root / "cleanup.json",
        {"status": "PASS", "attempt_id": attempt, "npu_quiescence": "PASS"},
    )
    write_file(run_root / "env/before/npu-smi.txt")
    write_file(run_root / "env/after/npu-smi.txt")
    write_json(run_root / "build/verdict.json", {"status": "PASS", "binary_ready": True})
    write_json(
        run_root / "build/binary-provenance.json",
        {
            "commit": COMMIT,
            "binary": {"path": "/opt/xllm/bin/xllm", "sha256": BINARY_SHA},
        },
    )
    return {
        "schema_version": 1,
        "run_id": "run-001",
        "evidence_type": evidence_type,
        "level": "formal-pr",
        "identity": {
            "framework": "xllm",
            "repo_path": "/workspace/xllm",
            "commit": COMMIT,
            "dirty_diff_sha256": "0" * 64,
            "binary_path": "/opt/xllm/bin/xllm",
            "binary_sha256": BINARY_SHA,
            "build_verdict": "build/verdict.json",
            "binary_provenance": "build/binary-provenance.json",
        },
        "environment": {
            "physical_device_ids": [2, 3],
            "visible_device_order": [2, 3],
            "hardware": "NPU",
            "software_stack": {"runtime": "test"},
        },
        "model": {
            "name": "test-model",
            "path": "/models/test-model",
            "tokenizer_path": "/models/test-model",
            "dtype": "bf16",
        },
        "service": {
            "attempt_id": attempt,
            "api_url": "http://127.0.0.1:18000/v1",
            "startup_command": f"service/{attempt}/command.sh",
            "pid_file": f"service/{attempt}/pids.txt",
            "logs": [f"service/{attempt}/node_0.log"],
            "ready": {"status": "PASS", "artifact": f"service/{attempt}/ready.json"},
            "smoke": {"status": "PASS", "artifact": f"service/{attempt}/smoke.json"},
            "cleanup": {"status": "PASS", "artifact": f"service/{attempt}/cleanup.json"},
        },
        "workload": {
            "request_fingerprint": REQUEST_SHA,
            "dataset": "random",
            "sampling": {"temperature": 0.0},
        },
        "artifacts": {
            "environment": {"before": "env/before", "after": "env/after"}
        },
    }


def make_performance_run(run_root):
    evidence = base_evidence(run_root, "performance")
    evidence["workload"].update(
        {
            "input_tokens": 1024,
            "output_tokens": 512,
            "parallel": 4,
            "number": 8,
            "warmup_num": 2,
            "profiling_attached": False,
        }
    )
    raw = run_root / "perf/raw"
    write_file(raw / "benchmark_summary.json", "{}\n")
    write_json(
        run_root / "perf/metrics.json",
        {
            "run_id": "run-001",
            "commit": COMMIT,
            "model": "test-model",
            "success": 8,
            "total": 8,
        },
    )
    evidence["artifacts"]["performance"] = {
        "raw": "perf/raw",
        "metrics": "perf/metrics.json",
    }
    write_json(run_root / "run-evidence.json", evidence)
    return evidence


def make_accuracy_run(run_root):
    evidence = base_evidence(run_root, "accuracy")
    evidence["workload"].update(
        {
            "prompt_template_sha256": "4" * 64,
            "dataset_fingerprint": "5" * 64,
            "answer_extractor_version": "v1",
        }
    )
    for path in (
        "accuracy/request_config.json",
        "accuracy/dataset_config.json",
        "accuracy/raw_predictions.jsonl",
        "accuracy/failed_cases.jsonl",
    ):
        write_file(run_root / path)
    write_json(
        run_root / "accuracy/score.json",
        {"run_id": "run-001", "status": "pass", "num_total": 10},
    )
    evidence["artifacts"]["accuracy"] = {
        "request_config": "accuracy/request_config.json",
        "dataset_config": "accuracy/dataset_config.json",
        "raw_predictions": "accuracy/raw_predictions.jsonl",
        "failed_cases": "accuracy/failed_cases.jsonl",
        "score": "accuracy/score.json",
    }
    write_json(run_root / "run-evidence.json", evidence)
    return evidence


def make_profiling_run(run_root):
    evidence = base_evidence(run_root, "profiling")
    evidence["profiling"] = {
        "attached_parent_pid": 1234,
        "warmup_before_capture": True,
        "workload_status": "PASS",
    }
    for directory in ("profiling/PROF_001", "profiling/mindstudio_profiler_output"):
        write_file(run_root / directory / "data.bin")
    for path in ("profiling/capture.log", "profiling/workload.log"):
        write_file(run_root / path)
    write_json(run_root / "profiling/analysis.json", {"status": "complete"})
    evidence["artifacts"]["profiling"] = {
        "prof": "profiling/PROF_001",
        "export": "profiling/mindstudio_profiler_output",
        "capture_log": "profiling/capture.log",
        "workload_log": "profiling/workload.log",
        "analysis": "profiling/analysis.json",
    }
    write_json(run_root / "run-evidence.json", evidence)
    return evidence


def test_valid_performance_evidence_passes_and_creates_index(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)

    result = invoke(run_root)

    assert result.returncode == 0, result.stderr
    assert verdict(run_root)["status"] == "PASS"
    assert verdict(run_root)["claim_scope"] == "formal"
    assert (run_root / "artifact-index.json").is_file()


def test_complete_smoke_run_does_not_gain_formal_claim_scope(tmp_path):
    run_root = tmp_path / "run"
    evidence = make_performance_run(run_root)
    evidence["level"] = "smoke"
    write_json(run_root / "run-evidence.json", evidence)

    result = invoke(run_root)

    assert result.returncode == 0, result.stderr
    assert verdict(run_root)["status"] == "PASS"
    assert verdict(run_root)["claim_scope"] == "smoke"


def test_performance_without_warmup_is_inconclusive(tmp_path):
    run_root = tmp_path / "run"
    evidence = make_performance_run(run_root)
    evidence["workload"]["warmup_num"] = 0
    write_json(run_root / "run-evidence.json", evidence)

    result = invoke(run_root)

    assert result.returncode == 1
    assert "formal_performance_requires_request_warmup" in verdict(run_root)["mismatches"]


def test_build_gate_failure_blocks_claim(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)
    write_json(run_root / "build/verdict.json", {"status": "FAILED", "binary_ready": False})

    result = invoke(run_root)

    assert result.returncode == 2
    assert "build_gate_not_passed:FAILED" in verdict(run_root)["blockers"]


def test_binary_commit_mismatch_is_inconclusive(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)
    provenance = json.loads((run_root / "build/binary-provenance.json").read_text())
    provenance["commit"] = "9" * 40
    write_json(run_root / "build/binary-provenance.json", provenance)

    result = invoke(run_root)

    assert result.returncode == 1
    assert any(item.startswith("build_commit:") for item in verdict(run_root)["mismatches"])


def test_missing_build_provenance_identity_is_inconclusive(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)
    write_json(run_root / "build/binary-provenance.json", {"binary": {}})

    result = invoke(run_root)

    assert result.returncode == 1
    assert {"build_commit:missing", "binary_path:missing", "binary_sha256:missing"}.issubset(verdict(run_root)["mismatches"])


def test_service_smoke_failure_blocks_even_when_http_ready_passed(tmp_path):
    run_root = tmp_path / "run"
    evidence = make_performance_run(run_root)
    evidence["service"]["smoke"]["status"] = "FAIL"
    write_json(run_root / "run-evidence.json", evidence)

    result = invoke(run_root)

    assert result.returncode == 2
    assert "service_smoke_not_passed:FAIL" in verdict(run_root)["blockers"]


def test_service_smoke_artifact_failure_cannot_be_hidden_by_manifest(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)
    write_json(
        run_root / "service/attempt-001/smoke.json",
        {"status": "FAIL", "attempt_id": "attempt-001"},
    )

    result = invoke(run_root)

    assert result.returncode == 2
    assert "service_smoke_artifact_not_passed" in verdict(run_root)["blockers"]


def test_cleanup_failure_makes_completed_run_inconclusive(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)
    write_json(
        run_root / "service/attempt-001/cleanup.json",
        {"status": "FAIL", "attempt_id": "attempt-001"},
    )

    result = invoke(run_root)

    assert result.returncode == 1
    assert "service_cleanup_artifact_not_passed" in verdict(run_root)["mismatches"]


def test_cleanup_without_npu_quiescence_is_inconclusive(tmp_path):
    run_root = tmp_path / "run"
    evidence = make_performance_run(run_root)
    cleanup = run_root / evidence["service"]["cleanup"]["artifact"]
    write_json(cleanup, {"status": "PASS", "attempt_id": "attempt-001", "npu_quiescence": "NOT_CHECKED"})

    result = invoke(run_root)

    assert result.returncode == 1
    assert "service_cleanup_npu_quiescence_not_passed" in verdict(run_root)["mismatches"]


def test_accuracy_requires_prompt_and_dataset_fingerprints(tmp_path):
    run_root = tmp_path / "run"
    evidence = make_accuracy_run(run_root)
    evidence["workload"].pop("prompt_template_sha256")
    write_json(run_root / "run-evidence.json", evidence)

    result = invoke(run_root)

    assert result.returncode == 1
    assert "workload.prompt_template_sha256" in verdict(run_root)["missing"]


def test_complete_profiling_evidence_passes(tmp_path):
    run_root = tmp_path / "run"
    make_profiling_run(run_root)

    result = invoke(run_root)

    assert result.returncode == 0, result.stderr
    assert verdict(run_root)["status"] == "PASS"


def test_missing_profiling_export_is_inconclusive(tmp_path):
    run_root = tmp_path / "run"
    make_profiling_run(run_root)
    export = run_root / "profiling/mindstudio_profiler_output/data.bin"
    export.unlink()
    export.parent.rmdir()

    result = invoke(run_root)

    assert result.returncode == 1
    assert any("mindstudio_profiler_output" in item for item in verdict(run_root)["missing"])


def test_artifact_change_after_index_is_inconclusive_and_preserves_original_index(tmp_path):
    run_root = tmp_path / "run"
    make_performance_run(run_root)
    assert invoke(run_root).returncode == 0
    original_index = (run_root / "artifact-index.json").read_text()
    metrics = json.loads((run_root / "perf/metrics.json").read_text())
    metrics["success"] = 7
    write_json(run_root / "perf/metrics.json", metrics)

    result = invoke(run_root)

    assert result.returncode == 1
    assert "declared_artifacts_changed_after_index" in verdict(run_root)["mismatches"]
    assert (run_root / "artifact-index.json").read_text() == original_index
    assert (run_root / "artifact-index.current.json").is_file()


def test_missing_evidence_contract_is_blocked(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()

    result = invoke(run_root)

    assert result.returncode == 2
    assert verdict(run_root)["status"] == "BLOCKED"
    assert "missing JSON artifact" in verdict(run_root)["blockers"][0]
