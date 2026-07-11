import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xllm_flow", ROOT / "scripts" / "xllm_flow.py")
flow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(flow)


def make_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def write_spec(path: Path, repo: Path, run_root: Path) -> None:
    path.write_text(
        f"""version: 1
identity:
  task_id: task-a
  purpose: test workflow
  kind: benchmark
  level: smoke
  run_root: {run_root}
code:
  framework: xllm
  repo: {repo}
model:
  name: test
  path: {repo}
  tokenizer: {repo}
service:
  tensor_parallel: 1
  devices: [0]
workload:
  dataset: random
  parallel: 1
  number: 1
  warmup: 0
  sampling: {{temperature: 0}}
""",
        encoding="utf-8",
    )


def add_passing_attempt(run_root: Path, spec: Path) -> None:
    artifact = run_root / "reports" / "metrics.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"tpot_ms": 10.0}\n', encoding="utf-8")
    spec_fingerprint = flow.experiment_fingerprint(flow.load_spec(spec), spec)
    flow.append_attempt(run_root, {
        "entry_id": "attempt-a-pass", "run_id": "task-a", "attempt_id": "attempt-a",
        "phase": "benchmark", "status": "pass", "fingerprint": spec_fingerprint,
        "spec_fingerprint": spec_fingerprint,
        "hypothesis": "baseline", "metrics": {"tpot_ms": 10.0},
        "artifacts": ["reports/metrics.json"], "decision": "accept",
    })


def test_fingerprint_is_stable_across_mapping_order():
    assert flow.stable_fingerprint({"b": 2, "a": 1}) == flow.stable_fingerprint({"a": 1, "b": 2})


def test_campaign_fingerprint_is_stable_but_execution_changes_with_dirty_source(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    loaded = flow.load_spec(spec)
    campaign = flow.experiment_fingerprint(loaded, spec)
    before = flow.execution_fingerprint(loaded, spec)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert flow.experiment_fingerprint(flow.load_spec(spec), spec) == campaign
    assert flow.execution_fingerprint(flow.load_spec(spec), spec) != before


def test_candidate_attempt_can_follow_code_change_in_same_campaign(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    spec_path = tmp_path / "experiment.yaml"
    write_spec(spec_path, repo, run_root)
    flow.run_create(spec_path)
    spec = flow.load_spec(spec_path)
    campaign = flow.experiment_fingerprint(spec, spec_path)
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    (run_root / "reports" / "candidate.json").write_text("{}\n", encoding="utf-8")
    entry = flow.append_attempt(run_root, {
        "entry_id": "candidate-pass", "run_id": "task-a", "spec_fingerprint": campaign,
        "attempt_id": "candidate", "parent_attempt": "baseline", "phase": "benchmark",
        "status": "pass", "fingerprint": flow.attempt_fingerprint(spec, spec_path, ["code.diff"], 0),
        "hypothesis": "candidate", "changed_variables": ["code.diff"],
        "metrics": {"baseline": 10, "current": 9, "delta": -1},
        "artifacts": ["reports/candidate.json"], "decision": "accept",
    })
    assert entry["attempt_id"] == "candidate"


def test_validate_spec_rejects_invalid_tp_and_formal_zero_warmup():
    spec = {
        "identity": {"task_id": "x", "purpose": "x", "kind": "benchmark", "level": "quick", "run_root": "runs/x"},
        "code": {"framework": "xllm", "repo": "repo", "commit": "abc", "binary": "bin"},
        "model": {"name": "m", "path": "m", "tokenizer": "m", "dtype": "bf16"},
        "service": {"tensor_parallel": 2, "devices": [0]},
        "workload": {"dataset": "random", "input_tokens": 1, "output_tokens": 1, "parallel": 1, "number": 1, "warmup": 0, "sampling": {}},
        "evaluation": {"accuracy": {}, "performance": {}}, "profiling": {"enabled": False},
        "environment": {"require_npu": False}, "artifacts": {"required": []},
    }
    errors = flow.validate_spec(spec)
    assert "service.devices count must equal service.tensor_parallel" in errors
    assert "workload.warmup is invalid for the selected level" in errors


def test_validate_spec_rejects_boolean_counts_and_non_list_devices():
    spec = {
        "version": 1,
        "identity": {"task_id": "x", "purpose": "x", "kind": "benchmark", "level": "smoke", "run_root": "runs/x"},
        "code": {"framework": "xllm", "repo": "repo"}, "model": {"name": "m", "path": "m", "tokenizer": "m"},
        "service": {"tensor_parallel": True, "devices": "0"},
        "workload": {"dataset": "random", "parallel": True, "number": True, "warmup": False, "sampling": {}},
    }
    errors = flow.validate_spec(spec)
    assert "service.devices must be a list" in errors
    assert "service.tensor_parallel must be a positive integer" in errors


def test_registry_sync_discovers_task_checkout(tmp_path):
    source = tmp_path / "worktree" / "tasks" / "task-a" / "eval-lane"
    make_repo(source)
    registry = tmp_path / "workspace-tasks.json"
    result = flow.registry_sync(tmp_path, registry)
    assert result["tasks"][0]["task_id"] == "task-a"
    assert result["tasks"][0]["source_path"] == str(source.resolve())
    assert result["tasks"][0]["source_paths"] == [str(source.resolve())]
    assert json.loads(registry.read_text())["tasks"][0]["state"] == "active"


def test_registry_sync_preserves_missing_history(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    flow.write_json(registry, {"version": 1, "tasks": [{"task_id": "retired", "state": "retired", "run_root": "/old"}]})
    result = flow.registry_sync(tmp_path, registry)
    assert result["tasks"][0]["task_id"] == "retired"
    assert result["tasks"][0]["present"] is False


def test_registry_bind_override_is_used_without_missing_source_diagnostic(tmp_path):
    source = tmp_path / "shared-source"
    make_repo(source)
    (tmp_path / "worktree" / "tasks" / "task-a").mkdir(parents=True)
    registry = tmp_path / "workspace-tasks.json"
    flow.registry_bind(registry, "task-a", source_override=str(source), aliases=["old-task"])
    task = flow.registry_sync(tmp_path, registry)["tasks"][0]
    assert task["source_path"] == str(source.resolve())
    assert task["source_paths"] == [str(source.resolve())]
    assert task["aliases"] == ["old-task"]
    assert "SOURCE_MISSING" not in task["diagnostics"]


def test_registry_source_only_suppresses_container_identity_diagnostics(tmp_path):
    source = tmp_path / "worktree" / "tasks" / "task-tp3" / "eval-lane"
    make_repo(source)
    registry = tmp_path / "workspace-tasks.json"
    flow.registry_bind(registry, "task-tp3", state="source-only", canonical_task_id="task-tp2")
    task = flow.registry_sync(tmp_path, registry)["tasks"][0]
    assert task["state"] == "source-only"
    assert task["canonical_task_id"] == "task-tp2"
    assert task["diagnostics"] == []


def test_registry_bind_cannot_bypass_archive_gate(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    try:
        flow.registry_bind(registry, "task-a", state="retired")
        assert False, "expected retired transition rejection"
    except ValueError as exc:
        assert "run archive" in str(exc)


def test_task_diagnostics_detects_missing_multiple_and_tp_mismatch(tmp_path):
    assert flow.task_diagnostics("task-tp2", [], None) == ["SOURCE_MISSING"]
    diagnostics = flow.task_diagnostics("task-tp3", [tmp_path / "a", tmp_path / "b"], "perf/model-tp2-fast")
    assert diagnostics == ["MULTIPLE_SOURCES", "TASK_BRANCH_TP_MISMATCH"]


def test_preflight_and_run_lifecycle(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "campaign"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    result = flow.preflight(spec, tmp_path / "preflight")
    assert result["status"] == "PASS"
    assert (tmp_path / "preflight" / "preflight.json").is_file()
    assert flow.run_create(spec) == run_root
    flow.run_create(spec)
    assert (run_root / "manifest.json").is_file()
    assert (run_root / "CHECKPOINT.md").is_file()
    assert (run_root / "analysis" / "bottleneck-budget.md").is_file()
    assert (run_root / "analysis" / "candidate-ranking.md").is_file()
    assert (run_root / "analysis" / "big-rock-gate.json").is_file()
    flow.save_checkpoint(run_root, {"phase": "benchmark", "last_success": "baseline", "next_command": "run candidate"})
    assert json.loads((run_root / "checkpoint.json").read_text())["phase"] == "benchmark"
    add_passing_attempt(run_root, spec)
    flow.run_finalize(run_root, "pass", reviewed_by="tester", retention_decision="keep")
    assert json.loads((run_root / "manifest.json").read_text())["status"] == "pass"
    assert (run_root / "retention-review.md").is_file()


def test_run_create_rejects_different_fingerprint(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "campaign"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    spec.write_text(spec.read_text().replace("number: 1", "number: 2"), encoding="utf-8")
    try:
        flow.run_create(spec)
        assert False, "expected fingerprint conflict"
    except ValueError as exc:
        assert "different experiment" in str(exc)


def test_finalize_preserves_existing_retention_review(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    add_passing_attempt(run_root, spec)
    retention = run_root / "retention-review.md"
    retention.write_text("manual decision\n", encoding="utf-8")
    flow.run_finalize(run_root, "pass", reviewed_by="tester", retention_decision="keep")
    assert retention.read_text() == "manual decision\n"


def test_finalize_supports_relative_run_root(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    add_passing_attempt(run_root, spec)
    monkeypatch.chdir(tmp_path)
    flow.run_finalize(Path("runs/run"), "pass", reviewed_by="tester", retention_decision="keep")
    assert (run_root / "finalization-complete.json").is_file()
    assert flow.verify_checksums(run_root) == []


def test_finalized_run_can_add_retention_review_later(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    add_passing_attempt(run_root, spec)
    flow.run_finalize(run_root, "pass")
    assert "decision: review-required" in (run_root / "retention-review.md").read_text()
    flow.run_finalize(run_root, "pass", reviewed_by="tester", retention_decision="keep")
    manifest = json.loads((run_root / "manifest.json").read_text())
    assert manifest["retention"]["reviewed_by"] == "tester"
    assert "decision: keep" in (run_root / "retention-review.md").read_text()
    assert flow.verify_checksums(run_root) == []


def test_preflight_fails_when_repo_is_missing(tmp_path):
    spec = tmp_path / "experiment.yaml"
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    write_spec(spec, tmp_path / "missing-repo", run_root)
    assert flow.preflight(spec, None)["status"] == "FAIL"


def test_preflight_enforces_expected_versions(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "runs" / "run"
    run_root.parent.mkdir()
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    spec.write_text(spec.read_text() + "environment:\n  expected:\n    torch: 9.9\n", encoding="utf-8")
    monkeypatch.setattr(flow, "package_versions", lambda: {"python": "3.11", "torch": "2.7.1"})
    result = flow.preflight(spec, None)
    assert result["status"] == "FAIL"
    assert next(item for item in result["checks"] if item["name"] == "version_torch")["status"] == "FAIL"


def test_fairness_covers_mtp_flags_and_code_identity():
    baseline = {
        "code": {"framework": "xllm", "commit": "base"},
        "model": {"name": "m", "draft_model": "draft-a", "speculative_tokens": 3},
        "service": {"flags": {"graph": True}}, "workload": {},
    }
    candidate = json.loads(json.dumps(baseline))
    candidate["code"]["commit"] = "candidate"
    candidate["model"]["draft_model"] = "draft-b"
    candidate["model"]["speculative_tokens"] = 5
    candidate["service"]["flags"]["graph"] = False
    mismatches = flow.fairness_mismatches(candidate, baseline, set())
    assert {"code.commit", "model.draft_model", "model.speculative_tokens", "service.flags"}.issubset(mismatches)


def test_registry_archive_marks_task_retired(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_repo(repo)
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    add_passing_attempt(run_root, spec)
    flow.run_finalize(run_root, "pass", reviewed_by="tester", retention_decision="keep")
    flow.write_json(registry, {"version": 1, "tasks": [{"task_id": "task-a", "state": "active", "run_root": str(run_root)}]})
    flow.registry_archive(registry, "task-a")
    task = json.loads(registry.read_text())["tasks"][0]
    assert task["state"] == "retired"
    assert task["retired_at_utc"]
    retired_at = task["retired_at_utc"]
    flow.registry_archive(registry, "task-a")
    assert json.loads(registry.read_text())["tasks"][0]["retired_at_utc"] == retired_at


def test_registry_archive_rejects_unreviewed_retention(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_repo(repo)
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    add_passing_attempt(run_root, spec)
    flow.run_finalize(run_root, "pass")
    flow.write_json(registry, {"version": 1, "tasks": [{"task_id": "task-a", "state": "active", "run_root": str(run_root)}]})
    try:
        flow.registry_archive(registry, "task-a")
        assert False, "expected retention gate"
    except ValueError as exc:
        assert "retention decision" in str(exc)


def test_registry_archive_requires_run_root(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    flow.write_json(registry, {"version": 1, "tasks": [{"task_id": "task-a", "state": "active", "run_root": None}]})
    try:
        flow.registry_archive(registry, "task-a")
        assert False, "expected run_root gate"
    except ValueError as exc:
        assert "run_root is required" in str(exc)


def test_archive_rejects_tampered_preflight_evidence(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    repo = tmp_path / "repo"
    make_repo(repo)
    run_root = tmp_path / "run"
    spec = tmp_path / "experiment.yaml"
    write_spec(spec, repo, run_root)
    flow.run_create(spec)
    add_passing_attempt(run_root, spec)
    flow.run_finalize(run_root, "pass", reviewed_by="tester", retention_decision="keep")
    flow.write_json(run_root / "env" / "preflight.json", {"status": "FAIL"})
    assert any("preflight.json" in error for error in flow.verify_checksums(run_root))
    flow.write_json(registry, {"version": 1, "tasks": [{"task_id": "task-a", "state": "active", "run_root": str(run_root)}]})
    try:
        flow.registry_archive(registry, "task-a")
        assert False, "expected tampered evidence rejection"
    except ValueError as exc:
        assert "validation failed" in str(exc) or "checksums" in str(exc)


def test_workspace_check_writes_unified_report(tmp_path):
    source = tmp_path / "worktree" / "tasks" / "task-a" / "eval-lane"
    make_repo(source)
    active = tmp_path / "active"
    active.mkdir()
    (active / "source").symlink_to(source)
    (active / "workflow").symlink_to(source)
    run = tmp_path / "runs" / "run-a"
    run.mkdir(parents=True)
    (run / "manifest.md").write_text("# manifest\n", encoding="utf-8")
    for report in [tmp_path / "BUILD-STORAGE.md", tmp_path / "WORKTREE-STORAGE.md", tmp_path / "runs" / "INDEX.md"]:
        report.write_text("report\n", encoding="utf-8")
    output = tmp_path / "preflight"
    result = flow.workspace_check(tmp_path, tmp_path / "workspace-tasks.json", output)
    assert result["status"] == "PASS"
    assert result["runs"] == {"manifested": 1, "total": 1, "unmanifested": 0}
    assert (output / "workspace-preflight.json").is_file()
    assert (output / "workspace-preflight.md").is_file()


def test_big_rock_gate_requires_budget_and_ranked_candidate(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    flow.write_json(run_root / "analysis" / "big-rock-gate.json", {
        "status": "PASS",
        "budget": {"phase": "decode", "unit": "ms", "wall_time": 10, "buckets": {"compute": 5, "communication": 2, "host": 1, "graph_sync": 1, "copy_memory": 0, "sampling_postprocess": 0}, "unclassified": 1, "evidence": "trace.json"},
        "remaining_target_gap": 4, "noise_floor": 0.1,
        "bucket_dispositions": {"compute": "outside current software scope"},
        "candidates": [{
            "level": "L1", "hypothesis": "overlap communication", "affected_budget": "communication", "removable_fraction": 0.5,
            "expected_gain_low": 0.6, "expected_gain_high": 1.0, "remaining_gap_share": 0.25, "implementation_cost": 2,
            "validation_risk": 2, "priority_score": 0.2, "evidence": "timeline", "selected": True,
            "actionable": True, "ab_plan": "toggle overlap", "rollback_plan": "disable toggle",
        }],
    })
    assert flow.validate_big_rock_gate(run_root) == []


def test_big_rock_gate_rejects_small_pass_and_unexplained_l3(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    flow.write_json(run_root / "analysis" / "big-rock-gate.json", {
        "status": "PASS",
        "budget": {"phase": "decode", "unit": "ms", "wall_time": 10, "buckets": {"compute": 5, "communication": 2, "host": 1, "graph_sync": 1, "copy_memory": 1, "sampling_postprocess": 0}, "unclassified": 0, "evidence": "trace.json"},
        "remaining_target_gap": 4, "noise_floor": 0.005,
        "candidates": [{
            "level": "L3", "hypothesis": "one memcpy", "affected_budget": "copy_memory", "removable_fraction": 0.02,
            "expected_gain_low": 0.01, "expected_gain_high": 0.02, "remaining_gap_share": 0.005, "implementation_cost": 1,
            "validation_risk": 1, "priority_score": 0.015, "evidence": "timeline", "selected": True,
            "actionable": True, "ab_plan": "toggle copy", "rollback_plan": "disable toggle",
        }],
    })
    errors = flow.validate_big_rock_gate(run_root)
    assert any("20%" in item for item in errors)
    assert any("l0_l2_disposition" in item for item in errors)


def test_big_rock_discovery_is_bounded(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    flow.write_json(run_root / "analysis" / "big-rock-gate.json", {
        "status": "DISCOVERY", "discovery": {"rounds": 3, "next_measurement": "profile stages"}
    })
    assert "discovery.rounds must be 1 or 2" in flow.validate_big_rock_gate(run_root)


def test_big_rock_pass_requires_large_unclassified_disposition(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    flow.write_json(run_root / "analysis" / "big-rock-gate.json", {
        "status": "PASS",
        "budget": {"phase": "decode", "unit": "ms", "wall_time": 10, "buckets": {"compute": 3, "communication": 1, "host": 1, "graph_sync": 1, "copy_memory": 0, "sampling_postprocess": 0}, "unclassified": 4, "evidence": "trace.json"},
        "remaining_target_gap": 2, "noise_floor": 0.1,
        "candidates": [{"level": "L0", "hypothesis": "compute", "affected_budget": "compute", "removable_fraction": 0.5, "expected_gain_low": 0.4, "expected_gain_high": 0.6, "remaining_gap_share": 0.3, "implementation_cost": 1, "validation_risk": 2, "priority_score": 0.25, "evidence": "trace", "selected": True, "actionable": True, "ab_plan": "toggle", "rollback_plan": "disable"}],
        "bucket_dispositions": {},
    })
    assert "unclassified above 20% requires unclassified_disposition" in flow.validate_big_rock_gate(run_root)


def test_big_rock_rejects_non_numeric_gap_share_and_incomplete_exemption(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    flow.write_json(run_root / "analysis" / "big-rock-gate.json", {
        "status": "EXEMPT", "exemption_reason": "target is nearly closed",
        "budget": {"phase": "decode", "unit": "ms", "wall_time": 10, "buckets": {"compute": 6, "communication": 1, "host": 1, "graph_sync": 1, "copy_memory": 1, "sampling_postprocess": 0}, "unclassified": 0, "evidence": "trace.json"},
        "remaining_target_gap": 1, "noise_floor": 0.01, "bucket_dispositions": {},
        "candidates": [{"level": "L1", "hypothesis": "overlap", "affected_budget": "communication", "removable_fraction": 0.1, "expected_gain_low": 0.05, "expected_gain_high": 0.1, "remaining_gap_share": "0.1", "implementation_cost": 1, "validation_risk": 1, "priority_score": 0.075, "evidence": "trace", "selected": True, "actionable": True, "ab_plan": "toggle", "rollback_plan": "disable"}],
    })
    errors = flow.validate_big_rock_gate(run_root)
    assert any("numeric fields" in error for error in errors)
    assert "EXEMPT requires l0_l2_disposition" in errors


def test_big_rock_selects_largest_gain_not_cheapest_detail(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    flow.write_json(run_root / "analysis" / "big-rock-gate.json", {
        "status": "PASS",
        "budget": {"phase": "decode", "unit": "ms", "wall_time": 10, "buckets": {"compute": 6, "communication": 2, "host": 1, "graph_sync": 1, "copy_memory": 0, "sampling_postprocess": 0}, "unclassified": 0, "evidence": "trace.json"},
        "remaining_target_gap": 4, "noise_floor": 0.1, "bucket_dispositions": {"compute": "hardware bound"},
        "candidates": [
            {"level": "L1", "hypothesis": "overlap", "affected_budget": "communication", "removable_fraction": 0.5, "expected_gain_low": 0.6, "expected_gain_high": 1.0, "remaining_gap_share": 0.25, "implementation_cost": 3, "validation_risk": 3, "priority_score": 0.0888889, "evidence": "trace", "selected": True, "actionable": True, "ab_plan": "toggle", "rollback_plan": "disable"},
            {"level": "L2", "hypothesis": "host cache", "affected_budget": "host", "removable_fraction": 0.2, "expected_gain_low": 0.15, "expected_gain_high": 0.2, "remaining_gap_share": 0.05, "implementation_cost": 1, "validation_risk": 1, "priority_score": 0.175, "evidence": "trace", "selected": False, "actionable": True},
        ],
    })
    assert flow.validate_big_rock_gate(run_root) == []


def test_attempt_ledger_hash_chain_and_duplicate_guard(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "reports").mkdir(parents=True)
    artifact = run_root / "reports" / "metrics.json"
    artifact.write_text("{}\n", encoding="utf-8")
    entry = {"entry_id": "e1", "attempt_id": "a", "phase": "benchmark", "status": "pass", "fingerprint": "fp", "hypothesis": "x", "metrics": {"tpot": 1}, "artifacts": ["reports/metrics.json"]}
    flow.append_attempt(run_root, entry)
    assert flow.read_attempts(run_root)[0]["entry_hash"]
    try:
        flow.append_attempt(run_root, {**entry, "entry_id": "e2"})
        assert False, "expected duplicate fingerprint"
    except ValueError as exc:
        assert "duplicate completed experiment fingerprint" in str(exc)
    path = run_root / "attempts.jsonl"
    path.write_text(path.read_text().replace('"hypothesis": "x"', '"hypothesis": "tampered"'), encoding="utf-8")
    try:
        flow.read_attempts(run_root)
        assert False, "expected hash failure"
    except ValueError as exc:
        assert "hash" in str(exc)
    try:
        flow.append_attempt(run_root, {"entry_id": "e3", "attempt_id": "b", "phase": "benchmark", "status": "running", "hypothesis": "y"})
        assert False, "expected append to reject tampered ledger"
    except ValueError as exc:
        assert "hash" in str(exc)


def test_attempt_updates_checkpoint_and_derived_ledgers(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "reports").mkdir(parents=True)
    flow.save_checkpoint(run_root, {"phase": "baseline", "completed_artifacts": []})
    (run_root / "reports" / "metrics.json").write_text("{}\n", encoding="utf-8")
    flow.append_attempt(run_root, {
        "entry_id": "e1", "attempt_id": "child", "parent_attempt": "baseline", "source": "PR#1",
        "phase": "benchmark", "status": "pass", "fingerprint": "fp", "hypothesis": "overlap",
        "changed_variables": ["service.flags.overlap"], "metrics": {"tpot": 1},
        "artifacts": ["reports/metrics.json"], "decision": "accept",
    })
    checkpoint = json.loads((run_root / "checkpoint.json").read_text())
    assert checkpoint["last_completed_entry"] == 1
    assert checkpoint["last_ledger_hash"]
    assert "reports/metrics.json" in checkpoint["completed_artifacts"]
    assert "PR#1" in (run_root / "humanize" / "source-idea-ledger.md").read_text()
    assert '"parent_attempt": "baseline"' in (run_root / "humanize" / "lineage.jsonl").read_text()


def test_terminal_attempt_closes_prior_running_entry(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "env").mkdir(parents=True)
    (run_root / "reports").mkdir()
    (run_root / "reports" / "metrics.json").write_text("{}\n", encoding="utf-8")
    flow.write_json(run_root / "manifest.json", {"spec": {"identity": {"kind": "benchmark"}, "artifacts": {"required": []}}})
    flow.write_json(run_root / "env" / "preflight.json", {"status": "PASS"})
    common = {"attempt_id": "a", "phase": "benchmark", "fingerprint": "fp", "hypothesis": "baseline"}
    flow.append_attempt(run_root, {**common, "entry_id": "a-running", "status": "running"})
    flow.append_attempt(run_root, {**common, "entry_id": "a-pass", "status": "pass", "metrics": {"tpot": 1}, "artifacts": ["reports/metrics.json"]})
    assert flow.active_attempts(flow.read_attempts(run_root)) == []
    assert flow.validate_run(run_root, "pass") == []


def test_inconclusive_run_can_close_after_inconclusive_preflight(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "env").mkdir(parents=True)
    flow.write_json(run_root / "manifest.json", {"spec": {"identity": {"kind": "incident"}, "artifacts": {"required": []}}})
    flow.write_json(run_root / "env" / "preflight.json", {"status": "INCONCLUSIVE"})
    flow.append_attempt(run_root, {
        "entry_id": "a-fail", "attempt_id": "a", "phase": "validation", "status": "fail",
        "fingerprint": "fp", "hypothesis": "environment available", "reason": "NPU unavailable",
    })
    assert flow.validate_run(run_root, "inconclusive") == []


def test_finalize_rejects_empty_run(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "env").mkdir(parents=True)
    flow.write_json(run_root / "manifest.json", {"spec": {"identity": {"kind": "benchmark"}, "artifacts": {"required": []}}})
    flow.write_json(run_root / "env" / "preflight.json", {"status": "PASS"})
    try:
        flow.run_finalize(run_root, "pass")
        assert False, "expected empty run rejection"
    except ValueError as exc:
        assert "at least one attempt" in str(exc)


def test_attempt_rejects_artifact_outside_run_root(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    try:
        flow.append_attempt(run_root, {
            "entry_id": "e1", "attempt_id": "a", "phase": "benchmark", "status": "pass",
            "fingerprint": "fp", "hypothesis": "x", "metrics": {"tpot": 1},
            "artifacts": ["../outside.json"],
        })
        assert False, "expected artifact containment rejection"
    except ValueError as exc:
        assert "inside run_root" in str(exc)


def test_attempt_rejects_mismatched_manifest_identity(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    flow.write_json(run_root / "manifest.json", {"fingerprint": "expected", "spec": {"identity": {"task_id": "task-a"}}})
    try:
        flow.append_attempt(run_root, {
            "entry_id": "e1", "run_id": "task-b", "spec_fingerprint": "other",
            "attempt_id": "a", "phase": "benchmark", "status": "running", "hypothesis": "x",
        })
        assert False, "expected manifest identity rejection"
    except ValueError as exc:
        assert "does not match run manifest" in str(exc)


def test_performance_pass_requires_benchmark_attempt(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "env").mkdir(parents=True)
    (run_root / "reports").mkdir()
    (run_root / "reports" / "profile.json").write_text("{}\n", encoding="utf-8")
    flow.write_json(run_root / "manifest.json", {"spec": {"identity": {"kind": "benchmark"}, "artifacts": {"required": []}}})
    flow.write_json(run_root / "env" / "preflight.json", {"status": "PASS"})
    flow.append_attempt(run_root, {
        "entry_id": "e1", "attempt_id": "profile", "phase": "profiling", "status": "pass",
        "fingerprint": "fp", "hypothesis": "profile", "metrics": {"kernel_ms": 1},
        "artifacts": ["reports/profile.json"],
    })
    assert "performance conclusion requires a passing benchmark attempt" in flow.validate_run(run_root, "pass")


def test_performance_optimization_requires_accepted_candidate_comparison():
    baseline = {"attempt_id": "base", "phase": "benchmark", "status": "pass", "changed_variables": []}
    assert "performance optimization requires an accepted candidate with parent baseline and baseline/current/delta metrics" in flow.validate_performance_attempts([baseline])
    candidate = {
        "attempt_id": "candidate", "parent_attempt": "base", "phase": "benchmark", "status": "pass",
        "changed_variables": ["code.commit"], "decision": "accept",
        "metrics": {"baseline": {"tpot": 10}, "current": {"tpot": 9}, "delta": {"tpot": -1}},
    }
    assert flow.validate_performance_attempts([baseline, candidate]) == []
    candidate["metrics"] = {"baseline": None, "current": None, "delta": None}
    assert flow.validate_performance_attempts([baseline, candidate])
    candidate["metrics"] = {"baseline": {"tpot": 10}, "current": {"tpot": 9}, "delta": {"tpot": 1}}
    assert flow.validate_performance_attempts([baseline, candidate])
