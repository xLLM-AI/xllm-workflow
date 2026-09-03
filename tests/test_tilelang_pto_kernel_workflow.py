from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "tilelang-pto-kernel-workflow"
INIT = SKILL / "scripts" / "init_run.py"
VALIDATE = SKILL / "scripts" / "validate_run.py"


def run_script(script: Path, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *(str(arg) for arg in args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def init_package(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = run_script(
        INIT,
        "--op",
        "gdn",
        "--repo-root",
        tmp_path,
        "--output-root",
        "analysis/tilelang-pto",
    )
    assert result.returncode == 0, result.stderr
    return tmp_path / "analysis" / "tilelang-pto" / "gdn"


def add_plan_row(dashboard: str, plan_id: str, status: str, file_value: str) -> str:
    separator = "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    row = (
        f"| {plan_id} | PTO | profile | UB tiling | none | no | {status} | 1 | "
        f"fresh ABBA | accepted | {file_value} |"
    )
    assert separator in dashboard
    return dashboard.replace(separator, f"{separator}\n{row}", 1)


def make_valid_final_package(root: Path) -> None:
    plan_id = "plan-gdn-ub"
    dashboard_path = root / "plan-dashboard.md"
    dashboard = dashboard_path.read_text(encoding="utf-8")
    replacements = {
        "- Baseline：": "- Baseline：baseline-commit",
        "- round0：": "- round0：perf/round0/profile.json",
        "- 当前通过 baseline：": f"- 当前通过 baseline：{plan_id}",
        "- 当前 round：": "- 当前 round：1",
        "- 当前 Plan：": f"- 当前 Plan：{plan_id}",
        "- 当前 step：SELECT": "- 当前 step：CLOSED",
        "- 本轮唯一主要变量：": "- 本轮唯一主要变量：UB tiling",
        "- 最后 Gate 与 verdict：": "- 最后 Gate 与 verdict：W7 PASS",
        "- 下一动作：": "- 下一动作：CLOSED",
        "- 回退或派生目标：": "- 回退或派生目标：rollback switch verified",
    }
    for old, new in replacements.items():
        dashboard = dashboard.replace(old, new)
    dashboard = dashboard.replace("- [ ]", "- [x]")
    dashboard = add_plan_row(dashboard, plan_id, "通过", f"plans/{plan_id}.md")
    dashboard_path.write_text(dashboard, encoding="utf-8")

    plan = (root / "plans" / "_template.md").read_text(encoding="utf-8")
    plan = plan.replace("plan-<id>", plan_id).replace("<title>", "UB tiling")
    plan = plan.replace("<N>", "1").replace("- 最终状态：", "- 最终状态：通过")
    (root / "plans" / f"{plan_id}.md").write_text(plan, encoding="utf-8")

    report_path = root / "final-report.md"
    report = report_path.read_text(encoding="utf-8")
    report_values = {
        "- 通过 Plan：": f"- 通过 Plan：{plan_id}",
        "- 淘汰 Plan：": "- 淘汰 Plan：无",
        "- 公平 baseline：": "- 公平 baseline：baseline-commit",
        "- 按 Shape 延迟 / 加速比：": "- 按 Shape 延迟 / 加速比：1.00 ms -> 0.80 ms",
        "- Graph 路由 / 调用次数：": "- Graph 路由 / 调用次数：route hit, calls unchanged",
        "- Golden / 连续 state：": "- Golden / 连续 state：PASS",
        "- 任务精度：": "- 任务精度：PASS",
        "- rollback 与 smoke：": "- rollback 与 smoke：PASS",
        "- final evidence：": "- final evidence：final-evidence.json",
        "- final Profile：": "- final Profile：perf/final/evidence.json",
        "- precision：": "- precision：precision/final-evidence.json",
    }
    for old, new in report_values.items():
        report = report.replace(old, new)
    report_path.write_text(report, encoding="utf-8")

    artifact_paths = {
        "performance_ab": "perf/final/evidence.json",
        "precision": "precision/final-evidence.json",
        "route": "model/graph-route/final-evidence.json",
        "rollback": "model/rollback/final-evidence.json",
    }
    evidence = json.loads((root / "final-evidence.json").read_text(encoding="utf-8"))
    evidence.update({"verdict": "pass", "plans": {"passed": [plan_id], "eliminated": []}})
    for name, relative in artifact_paths.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"schema_version": 1, "verdict": "pass", "kind": name, "value": 1},
            sort_keys=True,
        ).encode("utf-8")
        path.write_bytes(payload)
        evidence["checks"][name] = {
            "verdict": "pass",
            "artifact": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    (root / "final-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_initialized_package_passes_non_final_validation(tmp_path: Path):
    root = init_package(tmp_path)
    result = run_script(VALIDATE, root)
    assert result.returncode == 0, result.stdout
    assert "OK statuses=0 warnings=0 final=False" in result.stdout


def test_final_rejects_empty_file_bypass(tmp_path: Path):
    root = init_package(tmp_path)
    for relative in ("perf/round0/empty", "precision/empty", "model/graph-route/empty"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    result = run_script(VALIDATE, root, "--final")
    assert result.returncode == 1
    assert "final validation requires at least one Plan row" in result.stdout
    assert "final-evidence verdict must be pass" in result.stdout
    assert "unchecked or missing final Dashboard item" in result.stdout


def test_legacy_and_unknown_manifest_schemas_fail_closed(tmp_path: Path):
    for schema_version in (1, 999):
        root = init_package(tmp_path / str(schema_version))
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = schema_version
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        dashboard_path = root / "plan-dashboard.md"
        dashboard = dashboard_path.read_text(encoding="utf-8")
        start = dashboard.index("## Loop 控制")
        end = dashboard.index("## 主瓶颈")
        dashboard_path.write_text(dashboard[:start] + dashboard[end:], encoding="utf-8")

        result = run_script(VALIDATE, root)
        assert result.returncode == 1
        assert f"unsupported manifest schema_version={schema_version}" in result.stdout


def test_every_plans_row_is_parsed_and_plan_id_is_enforced(tmp_path: Path):
    root = init_package(tmp_path)
    dashboard_path = root / "plan-dashboard.md"
    dashboard = add_plan_row(
        dashboard_path.read_text(encoding="utf-8"),
        "gdn-ub",
        "已通过",
        "plans/gdn-ub.md",
    )
    dashboard_path.write_text(dashboard, encoding="utf-8")

    result = run_script(VALIDATE, root)
    assert result.returncode == 1
    assert "invalid plan_id in Plans row 1: gdn-ub" in result.stdout
    assert "invalid Plan status for gdn-ub: 已通过" in result.stdout


def test_complete_machine_readable_final_evidence_passes(tmp_path: Path):
    root = init_package(tmp_path)
    make_valid_final_package(root)

    result = run_script(VALIDATE, root, "--final")
    assert result.returncode == 0, result.stdout
    assert "OK statuses=1 warnings=0 final=True" in result.stdout


def test_final_evidence_hash_mismatch_fails(tmp_path: Path):
    root = init_package(tmp_path)
    make_valid_final_package(root)
    artifact = root / "perf" / "final" / "evidence.json"
    artifact.write_text(
        json.dumps({"schema_version": 1, "verdict": "pass", "value": 2}),
        encoding="utf-8",
    )

    result = run_script(VALIDATE, root, "--final")
    assert result.returncode == 1
    assert "final-evidence check performance_ab sha256 mismatch" in result.stdout
