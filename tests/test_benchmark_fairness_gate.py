import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/xllm-npu-benchmark/scripts/benchmark_fairness_gate.py"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def snapshot(*, hbm=0, aicore=0, processes=None, load1=1.0, swap=0):
    return {
        "backend": "ascend-npu",
        "parser_version": 2,
        "collection_errors": [],
        "raw_dir": "env/raw/snapshot",
        "devices": [
            {
                "physical_id": 2,
                "health": "OK",
                "hbm_usage_pct": hbm,
                "aicore_usage_pct": aicore,
                "processes": processes or [],
            }
        ],
        "host": {
            "load1": load1,
            "swap_used_bytes": swap,
            "profiling_active": False,
            "build_active": False,
        },
    }


def candidate(root, name):
    run_root = root / name
    write_json(run_root / "evidence-verdict.json", {"status": "PASS", "claim_scope": "formal", "run_root": str(run_root.resolve())})
    write_json(run_root / "manifest.json", {"fingerprint": "campaign-a"})
    (run_root / "env/raw/snapshot").mkdir(parents=True)
    return {
        "name": name,
        "run_root": name,
        "evidence_verdict": "evidence-verdict.json",
        "campaign_fingerprint": "campaign-a",
        "identity": {
            "hardware_fingerprint": "hardware-a",
            "device_backend": "ascend-npu",
            "physical_device_ids": [2],
            "visible_device_order": [2],
            "model_fingerprint": "model-a",
            "tokenizer_fingerprint": "tokenizer-a",
            "dtype": "bf16",
            "quantization": "none",
            "workload_fingerprint": "workload-a",
            "sampling_fingerprint": "sampling-a",
            "sla_fingerprint": "sla-a",
            "optimization_policy_fingerprint": "search-policy-a",
            "profiling_attached": False,
            "tuning_completed": True,
        },
        "environment": {
            "before": snapshot(),
            "idle_samples": [snapshot(), snapshot(), snapshot()],
            "after": snapshot(load1=1.05),
        },
    }


def comparison(root):
    return {
        "schema_version": 1,
        "comparison_id": "comparison-001",
        "policy": {
            "max_preexisting_hbm_pct": 5,
            "max_idle_aicore_pct": 3,
            "max_host_load1_delta_pct": 20,
            "min_idle_samples": 3,
        },
        "candidates": [candidate(root, "before"), candidate(root, "after")],
    }


def invoke(root):
    env = os.environ.copy()
    env["BASH_ENV"] = "/dev/null"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--comparison-root", str(root)],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def verdict(root):
    return json.loads((root / "fairness-verdict.json").read_text(encoding="utf-8"))


def test_matching_clean_candidates_pass(tmp_path):
    write_json(tmp_path / "fairness.json", comparison(tmp_path))

    result = invoke(tmp_path)

    assert result.returncode == 0, result.stderr
    assert verdict(tmp_path)["status"] == "PASS"
    assert verdict(tmp_path)["claim_scope"] == "formal"


def test_thresholds_must_be_declared_in_policy(tmp_path):
    document = comparison(tmp_path)
    document["policy"].pop("max_preexisting_hbm_pct")
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "missing_or_invalid_policy:max_preexisting_hbm_pct" in verdict(tmp_path)["blockers"]


def test_negative_or_fractional_policy_values_are_blocked(tmp_path):
    document = comparison(tmp_path)
    document["policy"]["max_idle_aicore_pct"] = -1
    document["policy"]["min_idle_samples"] = 1.5
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "missing_or_invalid_policy:max_idle_aicore_pct" in verdict(tmp_path)["blockers"]
    assert "missing_or_invalid_policy:min_idle_samples" in verdict(tmp_path)["blockers"]


def test_preexisting_hbm_above_declared_policy_is_inconclusive(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][0]["environment"]["before"] = snapshot(hbm=6)
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 1
    assert "before:before:hbm_above_policy" in verdict(tmp_path)["contamination_findings"]


def test_unknown_npu_pid_is_inconclusive(tmp_path):
    document = comparison(tmp_path)
    process = {"pid": 123, "host_visible": False, "owned_by_attempt": False}
    document["candidates"][0]["environment"]["before"] = snapshot(processes=[process])
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 1
    assert any("stale_or_unknown_pid" in item for item in verdict(tmp_path)["contamination_findings"])


def test_profiling_attached_is_inconclusive(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][1]["identity"]["profiling_attached"] = True
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 1
    assert "after:profiling_attached" in verdict(tmp_path)["contamination_findings"]


def test_candidate_workload_mismatch_is_inconclusive(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][1]["identity"]["workload_fingerprint"] = "different"
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 1
    assert "after:identity.workload_fingerprint" in verdict(tmp_path)["candidate_mismatches"]


def test_nonformal_run_evidence_is_inconclusive(tmp_path):
    document = comparison(tmp_path)
    write_json(tmp_path / "after/evidence-verdict.json", {"status": "PASS", "claim_scope": "smoke", "run_root": str((tmp_path / "after").resolve())})
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 1
    assert "after:run_evidence_not_formal_pass" in verdict(tmp_path)["contamination_findings"]


def test_evidence_verdict_must_belong_to_candidate_run_root(tmp_path):
    document = comparison(tmp_path)
    write_json(tmp_path / "after/evidence-verdict.json", {"status": "PASS", "claim_scope": "formal", "run_root": str((tmp_path / "before").resolve())})
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "after:evidence_verdict_run_root_mismatch" in verdict(tmp_path)["blockers"]


def test_missing_idle_samples_blocks_comparison(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][0]["environment"]["idle_samples"] = []
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "before:missing:environment.idle_samples" in verdict(tmp_path)["blockers"]


def test_candidate_names_must_be_unique(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][1]["name"] = "before"
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "candidate_names_must_be_unique_and_nonempty" in verdict(tmp_path)["blockers"]


def test_snapshot_backend_must_match_declared_adapter(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][1]["environment"]["after"]["backend"] = "nvidia-gpu"
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "after:after:backend_mismatch" in verdict(tmp_path)["blockers"]


def test_candidate_campaign_must_match_own_manifest(tmp_path):
    document = comparison(tmp_path)
    document["candidates"][1]["campaign_fingerprint"] = "drifted"
    write_json(tmp_path / "fairness.json", document)

    result = invoke(tmp_path)

    assert result.returncode == 2
    assert "after:campaign_fingerprint_mismatch" in verdict(tmp_path)["blockers"]
