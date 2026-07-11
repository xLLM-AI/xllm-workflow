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
  run_root: {run_root}
code:
  repo: {repo}
model:
  name: test
workload:
  parallel: 1
""",
        encoding="utf-8",
    )


def test_fingerprint_is_stable_across_mapping_order():
    assert flow.stable_fingerprint({"b": 2, "a": 1}) == flow.stable_fingerprint({"a": 1, "b": 2})


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
    flow.save_checkpoint(run_root, {"phase": "benchmark", "last_success": "baseline", "next_command": "run candidate"})
    assert json.loads((run_root / "checkpoint.json").read_text())["phase"] == "benchmark"
    flow.run_finalize(run_root, "pass", retention_reviewed=True)
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
    spec.write_text(spec.read_text().replace("parallel: 1", "parallel: 2"), encoding="utf-8")
    try:
        flow.run_create(spec)
        assert False, "expected fingerprint conflict"
    except ValueError as exc:
        assert "different experiment" in str(exc)


def test_finalize_preserves_existing_retention_review(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    flow.write_json(run_root / "manifest.json", {"status": "pending"})
    retention = run_root / "retention-review.md"
    retention.write_text("manual decision\n", encoding="utf-8")
    flow.run_finalize(run_root, "pass")
    assert retention.read_text() == "manual decision\n"


def test_preflight_fails_when_repo_is_missing(tmp_path):
    spec = tmp_path / "experiment.yaml"
    spec.write_text("version: 1\nidentity: {}\ncode: {}\n", encoding="utf-8")
    assert flow.preflight(spec, None)["status"] == "FAIL"


def test_registry_archive_marks_task_retired(tmp_path):
    registry = tmp_path / "workspace-tasks.json"
    run_root = tmp_path / "run"
    run_root.mkdir()
    flow.write_json(run_root / "manifest.json", {"status": "pass", "retention_reviewed": True})
    (run_root / "retention-review.md").write_text("reviewed\n", encoding="utf-8")
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
    run_root.mkdir()
    flow.write_json(run_root / "manifest.json", {"status": "pass", "retention_reviewed": False})
    (run_root / "retention-review.md").write_text("review-required\n", encoding="utf-8")
    flow.write_json(registry, {"version": 1, "tasks": [{"task_id": "task-a", "state": "active", "run_root": str(run_root)}]})
    try:
        flow.registry_archive(registry, "task-a")
        assert False, "expected retention gate"
    except ValueError as exc:
        assert "retention decision" in str(exc)
