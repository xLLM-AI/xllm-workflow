import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "scripts" / "xllm_flow.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FLOW), *map(str, args)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_documented_lifecycle_sequence_runs_through_real_cli(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("synthetic repo\n", encoding="utf-8")
    binary = Path(sys.executable).resolve()
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "synthetic"], cwd=repo, check=True, capture_output=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = workspace / "workspace-tasks.json"
    run_root = tmp_path / "runs" / "synthetic"
    spec = tmp_path / "experiment.yaml"
    spec.write_text(
        f"""version: 1
identity:
  task_id: lifecycle-smoke
  purpose: validate documented lifecycle commands
  kind: benchmark
  level: smoke
  run_root: {run_root}
code:
  framework: xllm
  repo: {repo}
  binary: {binary}
model:
  name: synthetic
  path: {repo}
  tokenizer: {repo}
  dtype: bfloat16
service:
  tensor_parallel: 1
  devices: [0]
  host: localhost
  port: 18000
workload:
  dataset: random
  parallel: 1
  number: 1
  warmup: 1
  sampling: {{temperature: 0}}
environment:
  require_npu: false
evidence:
  type: performance
  level: smoke
  service_attempt_id: attempt-001
""",
        encoding="utf-8",
    )

    run_cli("preflight", "--spec", spec, "--output", run_root / "env")
    run_cli(
        "--workspace-root", workspace, "--registry", registry,
        "run", "create", "--spec", spec,
    )

    write_json(run_root / "build/verdict.json", {"status": "PASS", "binary_ready": True})
    write_json(
        run_root / "build/binary-provenance.json",
        {"commit": commit, "binary": {"path": str(binary), "sha256": sha256(binary)}},
    )
    service = run_root / "service/attempt-001"
    service.mkdir(parents=True)
    (service / "command.sh").write_text("true\n", encoding="utf-8")
    (service / "pids.txt").write_text("1\n", encoding="utf-8")
    (service / "node_0.log").write_text("synthetic\n", encoding="utf-8")
    write_json(service / "ready.json", {"status": "PASS", "attempt_id": "attempt-001"})
    write_json(service / "smoke.json", {"status": "PASS", "attempt_id": "attempt-001"})
    write_json(
        service / "cleanup.json",
        {"status": "PASS", "attempt_id": "attempt-001", "npu_quiescence": "PASS"},
    )
    (run_root / "env/before").mkdir()
    (run_root / "env/before/state.txt").write_text("before\n", encoding="utf-8")
    (run_root / "env/after").mkdir()
    (run_root / "env/after/state.txt").write_text("after\n", encoding="utf-8")
    (run_root / "perf/raw").mkdir(parents=True)
    (run_root / "perf/raw/result.txt").write_text("ok\n", encoding="utf-8")
    metrics = run_root / "perf/metrics.json"
    write_json(metrics, {"run_id": "lifecycle-smoke", "success": 1, "total": 1})

    run_cli(
        "attempt", "add", "--run-root", run_root, "--spec", spec,
        "--attempt-id", "baseline-r0", "--phase", "benchmark", "--status", "pass",
        "--hypothesis", "baseline", "--metrics-json", metrics,
        "--artifact", "perf/metrics.json", "--repeat-index", "0",
    )
    run_cli("run", "validate", "--run-root", run_root, "--status", "pass")
    run_cli("export", "evidence", "--run-root", run_root)
    run_cli(
        "gate", "all", "--run-root", run_root,
        "--require", "build", "--require", "service", "--require", "evidence",
    )
    run_cli(
        "--workspace-root", workspace, "run", "finalize", "--run-root", run_root,
        "--status", "pass", "--reviewed-by", "codex-test",
        "--retention-decision", "keep", "--kept-path", "perf/metrics.json",
    )
    run_cli(
        "--workspace-root", workspace, "--registry", registry,
        "run", "archive", "--task-id", "lifecycle-smoke",
    )

    task = json.loads(registry.read_text(encoding="utf-8"))["tasks"][0]
    assert task["state"] == "retired"
    assert "reviewed_by: codex-test" in (run_root / "retention-review.md").read_text(encoding="utf-8")
    assert json.loads((run_root / "gate-all-verdict.json").read_text(encoding="utf-8"))["status"] == "PASS"
