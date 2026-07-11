#!/usr/bin/env python3
"""Config-driven task, preflight, run, and archive workflow for xLLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - deployment guard
    yaml = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_spec(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read experiment.yaml")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"experiment spec must be a mapping: {path}")
    return value


def stable_fingerprint(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout.strip()


def git_identity(path: Path) -> dict[str, Any]:
    code, root = capture(["git", "rev-parse", "--show-toplevel"], path)
    if code != 0:
        return {"valid": False, "path": str(path)}
    _, branch = capture(["git", "branch", "--show-current"], path)
    _, commit = capture(["git", "rev-parse", "HEAD"], path)
    _, status = capture(["git", "status", "--short"], path)
    _, remotes = capture(["git", "remote", "-v"], path)
    return {
        "valid": True,
        "path": root,
        "branch": branch or "detached",
        "commit": commit,
        "dirty": bool(status),
        "status_short": status.splitlines(),
        "remotes": remotes.splitlines(),
    }


def find_task_sources(task_root: Path) -> list[Path]:
    if (task_root / ".git").exists():
        return [task_root]
    return [candidate for candidate in sorted(task_root.glob("*")) if candidate.is_dir() and (candidate / ".git").exists()]


def task_diagnostics(task_id: str, sources: list[Path], branch: str | None) -> list[str]:
    diagnostics = []
    if not sources:
        diagnostics.append("SOURCE_MISSING")
    if len(sources) > 1:
        diagnostics.append("MULTIPLE_SOURCES")
    task_tp = re.search(r"(?:^|[-_])tp(\d+)(?:[-_]|$)", task_id, re.I)
    branch_tp = re.search(r"(?:^|[-_/])tp(\d+)(?:[-_/]|$)", branch or "", re.I)
    if task_tp and branch_tp and task_tp.group(1) != branch_tp.group(1):
        diagnostics.append("TASK_BRANCH_TP_MISMATCH")
    return diagnostics


def registry_sync(workspace: Path, registry_path: Path) -> dict[str, Any]:
    current = read_json(registry_path, {"version": 1, "tasks": []})
    previous = {item["task_id"]: item for item in current.get("tasks", [])}
    tasks_root = workspace / "worktree" / "tasks"
    tasks = []
    discovered: set[str] = set()
    if tasks_root.is_dir():
        for root in sorted(tasks_root.iterdir()):
            if not root.is_dir():
                continue
            sources = find_task_sources(root)
            source = sources[0] if sources else None
            old = previous.get(root.name, {})
            discovered.add(root.name)
            identity = git_identity(source) if source else {"valid": False}
            tasks.append({
                "task_id": root.name,
                "state": old.get("state", "active"),
                "task_root": str(root.resolve()),
                "source_path": str(source.resolve()) if source else None,
                "source_paths": [str(item.resolve()) for item in sources],
                "run_root": old.get("run_root"),
                "task_doc": str(root / "TASK.md") if (root / "TASK.md").exists() else None,
                "branch": identity.get("branch"),
                "commit": identity.get("commit"),
                "dirty": identity.get("dirty"),
                "diagnostics": task_diagnostics(root.name, sources, identity.get("branch")),
                "present": True,
                "last_active_at": old.get("last_active_at", utc_now()),
            })
    for task_id, old in previous.items():
        if task_id not in discovered:
            retained = dict(old)
            retained["present"] = False
            tasks.append(retained)
    result = {
        "version": 1,
        "generated_at_utc": utc_now(),
        "workspace_root": str(workspace.resolve()),
        "diagnostic_count": sum(len(task.get("diagnostics", [])) for task in tasks),
        "tasks": tasks,
    }
    write_json(registry_path, result)
    return result


def resolve_spec_path(spec_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (spec_path.parent / path).resolve()


def preflight(spec_path: Path, output: Path | None) -> dict[str, Any]:
    spec = load_spec(spec_path)
    source_value = spec.get("code", {}).get("repo")
    source = resolve_spec_path(spec_path, source_value)
    run_root_value = spec.get("identity", {}).get("run_root")
    checks: list[dict[str, Any]] = []
    identity = git_identity(source) if source else {"valid": False, "path": None}
    checks.append({"name": "source_git", "status": "PASS" if identity.get("valid") else "FAIL"})
    expected_commit = spec.get("code", {}).get("commit")
    if expected_commit:
        checks.append({"name": "commit_match", "status": "PASS" if identity.get("commit", "").startswith(str(expected_commit)) else "FAIL"})
    if identity.get("dirty"):
        checks.append({"name": "dirty_worktree", "status": "INCONCLUSIVE"})
    run_root = resolve_spec_path(spec_path, run_root_value)
    checks.append({"name": "run_root", "status": "PASS" if run_root and run_root.parent.exists() else "FAIL"})
    statuses = {item["status"] for item in checks}
    verdict = "FAIL" if "FAIL" in statuses else "INCONCLUSIVE" if "INCONCLUSIVE" in statuses else "PASS"
    result = {"generated_at_utc": utc_now(), "status": verdict, "fingerprint": stable_fingerprint(spec), "source": identity, "checks": checks}
    if output:
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "preflight.json", result)
        lines = ["# Preflight", "", f"- status: **{verdict}**", f"- fingerprint: `{result['fingerprint']}`", ""]
        lines += [f"- {item['name']}: {item['status']}" for item in checks]
        (output / "preflight.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def render_checkpoint(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Task Checkpoint", "",
        f"- updated_at_utc: {state['updated_at_utc']}",
        f"- phase: {state.get('phase', 'created')}",
        f"- last_success: {state.get('last_success', '')}",
        f"- next_command: `{state.get('next_command', '')}`", "",
    ])


def save_checkpoint(run_root: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = utc_now()
    write_json(run_root / "checkpoint.json", state)
    (run_root / "CHECKPOINT.md").write_text(render_checkpoint(state), encoding="utf-8")


def validate_big_rock_gate(run_root: Path) -> list[str]:
    gate = read_json(run_root / "analysis" / "big-rock-gate.json", {})
    errors = []
    status = gate.get("status")
    if status not in {"PASS", "DISCOVERY", "BLOCKED", "EXEMPT"}:
        return ["status must be PASS, DISCOVERY, BLOCKED, or EXEMPT"]
    if status == "DISCOVERY":
        rounds = gate.get("discovery", {}).get("rounds")
        if not isinstance(rounds, int) or not 1 <= rounds <= 2:
            errors.append("discovery.rounds must be 1 or 2")
        if not gate.get("discovery", {}).get("next_measurement"):
            errors.append("discovery.next_measurement is required")
        return errors
    if status == "BLOCKED":
        return [] if gate.get("blocked_reason") else ["blocked_reason is required"]

    budget = gate.get("budget", {})
    wall = budget.get("wall_time")
    buckets = budget.get("buckets", {})
    exclusive = sum(buckets.values()) if isinstance(buckets, dict) and all(isinstance(value, (int, float)) and value >= 0 for value in buckets.values()) else None
    unclassified = budget.get("unclassified")
    required_buckets = {"compute", "communication", "host", "graph_sync", "copy_memory", "sampling_postprocess"}
    if not isinstance(buckets, dict) or not required_buckets.issubset(buckets):
        errors.append("budget.buckets must include compute, communication, host, graph_sync, copy_memory, and sampling_postprocess")
    if not all(isinstance(value, (int, float)) and value >= 0 for value in [wall, exclusive, unclassified]):
        errors.append("budget wall_time, bucket values, and unclassified must be non-negative numbers")
    elif wall <= 0 or abs((exclusive + unclassified) - wall) > max(wall * 0.05, 0.001):
        errors.append("exclusive_attributed + unclassified must equal wall_time within 5%")
    if not budget.get("phase") or not budget.get("unit") or not budget.get("evidence"):
        errors.append("budget phase, unit, and evidence are required")

    remaining_gap = gate.get("remaining_target_gap")
    noise_floor = gate.get("noise_floor")
    if not isinstance(remaining_gap, (int, float)) or remaining_gap <= 0:
        errors.append("remaining_target_gap must be positive")
    if not isinstance(noise_floor, (int, float)) or noise_floor < 0:
        errors.append("noise_floor must be non-negative")
    candidates = gate.get("candidates", [])
    selected = [item for item in candidates if item.get("selected") is True]
    if len(selected) != 1:
        errors.append("exactly one candidate must be selected")
    actionable = []
    for item in candidates:
        required = ["level", "hypothesis", "affected_budget", "removable_fraction", "expected_gain_low", "expected_gain_high", "remaining_gap_share", "implementation_cost", "validation_risk", "priority_score", "evidence"]
        if any(item.get(key) in {None, ""} for key in required):
            errors.append(f"candidate is missing ranking fields: {item.get('hypothesis', '<unnamed>')}")
            continue
        low, high = item["expected_gain_low"], item["expected_gain_high"]
        cost, risk = item["implementation_cost"], item["validation_risk"]
        fraction = item["removable_fraction"]
        if item["level"] not in {"L0", "L1", "L2", "L3"}:
            errors.append(f"invalid candidate level: {item['level']}")
        if not all(isinstance(value, (int, float)) for value in [low, high, cost, risk, fraction, item["priority_score"]]):
            errors.append(f"candidate numeric fields are invalid: {item['hypothesis']}")
            continue
        if low < 0 or high < low:
            errors.append(f"candidate gain range is invalid: {item['hypothesis']}")
        if not 0 <= fraction <= 1 or not 1 <= cost <= 5 or not 1 <= risk <= 5:
            errors.append(f"candidate fraction/cost/risk is invalid: {item['hypothesis']}")
        bucket_name = item["affected_budget"]
        if bucket_name not in buckets:
            errors.append(f"candidate affected_budget is unknown: {item['hypothesis']}")
        elif high > buckets[bucket_name] * fraction * 1.05 + 1e-9:
            errors.append(f"candidate gain exceeds affected budget upper bound: {item['hypothesis']}")
        if isinstance(remaining_gap, (int, float)) and remaining_gap > 0 and abs(item["remaining_gap_share"] - high / remaining_gap) > 0.02:
            errors.append(f"candidate remaining_gap_share is inconsistent: {item['hypothesis']}")
        expected_priority = ((low + high) / 2) / (cost * risk)
        if abs(item["priority_score"] - expected_priority) > max(expected_priority * 0.05, 0.001):
            errors.append(f"candidate priority_score is inconsistent: {item['hypothesis']}")
        if item.get("actionable", True):
            actionable.append(item)
        elif not item.get("blocked_reason"):
            errors.append(f"non-actionable candidate needs blocked_reason: {item['hypothesis']}")
    if selected:
        item = selected[0]
        if item not in actionable:
            errors.append("selected candidate must be actionable")
        elif actionable and item["priority_score"] < max(candidate["priority_score"] for candidate in actionable) - 1e-9:
            errors.append("selected candidate must have the highest actionable priority_score")
        if item.get("expected_gain_high", 0) <= (noise_floor if isinstance(noise_floor, (int, float)) else 0):
            errors.append("selected candidate expected gain must exceed noise_floor")
        if not item.get("ab_plan") or not item.get("rollback_plan"):
            errors.append("selected candidate requires ab_plan and rollback_plan")
        if status == "PASS" and item.get("remaining_gap_share", 0) < 0.2:
            errors.append("PASS candidate must close at least 20% of remaining gap")
        if status == "EXEMPT" and not gate.get("exemption_reason"):
            errors.append("EXEMPT requires exemption_reason")
        if item.get("level") == "L3" and not gate.get("l0_l2_disposition"):
            errors.append("L3 selection requires l0_l2_disposition")
        if item.get("affected_budget") in buckets:
            selected_budget = buckets[item["affected_budget"]]
            dispositions = gate.get("bucket_dispositions", {})
            for name, value in buckets.items():
                if value > selected_budget and not dispositions.get(name):
                    errors.append(f"larger budget bucket requires disposition: {name}")
    return errors


def update_registry_binding(registry_path: Path, spec: dict[str, Any], run_root: Path) -> None:
    registry = read_json(registry_path, {"version": 1, "tasks": []})
    task_id = spec.get("identity", {}).get("task_id")
    if not task_id:
        raise ValueError("identity.task_id is required")
    for task in registry["tasks"]:
        if task.get("task_id") == task_id:
            task["run_root"] = str(run_root)
            task["state"] = "active"
            write_json(registry_path, registry)
            return
    registry["tasks"].append({"task_id": task_id, "state": "active", "run_root": str(run_root), "present": False})
    write_json(registry_path, registry)


def run_create(spec_path: Path, registry_path: Path | None = None) -> Path:
    spec = load_spec(spec_path)
    run_root_value = spec.get("identity", {}).get("run_root")
    if not run_root_value:
        raise ValueError("identity.run_root is required")
    run_root = resolve_spec_path(spec_path, run_root_value)
    assert run_root is not None
    for item in ["attempts", "reports", "env", "analysis"]:
        (run_root / item).mkdir(parents=True, exist_ok=True)
    manifest = read_json(run_root / "manifest.json", {})
    fingerprint = stable_fingerprint(spec)
    if manifest and manifest.get("fingerprint") != fingerprint:
        raise ValueError(f"run_root already belongs to a different experiment: {run_root}")
    if not manifest:
        manifest = {"version": 1, "created_at_utc": utc_now(), "status": "pending", "fingerprint": fingerprint, "spec": spec}
        write_json(run_root / "manifest.json", manifest)
    (run_root / "attempts.jsonl").touch(exist_ok=True)
    budget = run_root / "analysis" / "bottleneck-budget.md"
    if not budget.exists():
        budget.write_text(
            "# Bottleneck Budget\n\n"
            "- baseline: \n- current_best: \n- target: \n- remaining_gap: \n- noise_floor: \n\n"
            "| category | measured cost | share | confidence | evidence |\n"
            "|---|---:|---:|---|---|\n"
            "| model compute / main operators | | | | |\n"
            "| communication | | | | |\n"
            "| host scheduling and dispatch | | | | |\n"
            "| graph gaps and synchronization | | | | |\n"
            "| copies and memory movement | | | | |\n"
            "| sampling and postprocess | | | | |\n"
            "| unclassified | | | | |\n",
            encoding="utf-8",
        )
    ranking = run_root / "analysis" / "candidate-ranking.md"
    if not ranking.exists():
        ranking.write_text(
            "# Candidate Ranking\n\n"
            "| rank | level | hypothesis | gain low | gain high | gap share | cost 1-5 | risk 1-5 | priority | evidence | blocked reason | selected |\n"
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|\n\n"
            "L3 remains locked until L0-L2 candidates are quantified or rejected with evidence.\n",
            encoding="utf-8",
        )
    gate = run_root / "analysis" / "big-rock-gate.json"
    if not gate.exists():
        write_json(gate, {
            "version": 1, "status": "PENDING",
            "budget": {"phase": "", "unit": "ms", "wall_time": 0, "buckets": {"compute": 0, "communication": 0, "host": 0, "graph_sync": 0, "copy_memory": 0, "sampling_postprocess": 0}, "unclassified": 0, "overlap_opportunity": 0, "evidence": ""},
            "remaining_target_gap": 0, "noise_floor": 0,
            "candidates": [], "bucket_dispositions": {}, "l0_l2_disposition": "", "exemption_reason": "", "blocked_reason": "",
            "discovery": {"rounds": 0, "next_measurement": ""},
        })
    if not (run_root / "checkpoint.json").exists():
        save_checkpoint(run_root, {"phase": "created", "last_success": "run-create", "next_command": "xllm-flow preflight"})
    if registry_path:
        update_registry_binding(registry_path, spec, run_root)
    return run_root


def run_finalize(run_root: Path, status: str, retention_reviewed: bool = False) -> None:
    manifest_path = run_root / "manifest.json"
    manifest = read_json(manifest_path, None)
    if manifest is None:
        raise ValueError(f"missing manifest.json: {run_root}")
    manifest["status"] = status
    manifest["finalized_at_utc"] = utc_now()
    manifest["retention_reviewed"] = retention_reviewed or manifest.get("retention_reviewed", False)
    write_json(manifest_path, manifest)
    retention = run_root / "retention-review.md"
    if not retention.exists():
        retention.write_text(
            f"# Retention Review\n\n- finalized_at_utc: {manifest['finalized_at_utc']}\n- conclusion_status: {status}\n- raw_artifact_cleanup: review-required\n",
            encoding="utf-8",
        )
    save_checkpoint(run_root, {"phase": "finalized", "last_success": "run-finalize", "next_command": "xllm-flow run archive"})


def registry_archive(registry_path: Path, task_id: str) -> None:
    registry = read_json(registry_path, {"version": 1, "tasks": []})
    for task in registry.get("tasks", []):
        if task.get("task_id") == task_id:
            if task.get("state") == "retired":
                return
            run_root = Path(task.get("run_root", ""))
            manifest = read_json(run_root / "manifest.json", {}) if str(run_root) else {}
            if manifest.get("status") not in {"pass", "fail", "inconclusive"}:
                raise ValueError("task run must be finalized before archive")
            if not (run_root / "retention-review.md").is_file():
                raise ValueError("retention-review.md is required before archive")
            if not manifest.get("retention_reviewed"):
                raise ValueError("retention decision must be reviewed before archive")
            task["state"] = "retired"
            task["retired_at_utc"] = utc_now()
            write_json(registry_path, registry)
            return
    raise ValueError(f"task not found in registry: {task_id}")


def workspace_check(workspace: Path, registry_path: Path, output: Path | None) -> dict[str, Any]:
    registry = registry_sync(workspace, registry_path)
    issues = []
    for task in registry.get("tasks", []):
        for diagnostic in task.get("diagnostics", []):
            issues.append({"scope": task["task_id"], "code": diagnostic})

    repos = {}
    for name, path in {
        "active_source": workspace / "active" / "source",
        "workflow": workspace / "active" / "workflow",
    }.items():
        identity = git_identity(path.resolve()) if path.exists() else {"valid": False, "path": str(path)}
        repos[name] = identity
        if not identity.get("valid"):
            issues.append({"scope": name, "code": "REPO_MISSING"})
        elif identity.get("dirty"):
            issues.append({"scope": name, "code": "DIRTY_WORKTREE"})

    runs = workspace / "runs"
    run_dirs = list(runs.iterdir()) if runs.is_dir() else []
    run_dirs = [path for path in run_dirs if path.is_dir()]
    manifested = sum(1 for path in run_dirs if (path / "manifest.md").is_file() or (path / "manifest.json").is_file())
    coverage = {"manifested": manifested, "total": len(run_dirs), "unmanifested": len(run_dirs) - manifested}

    reports = {}
    now = datetime.now(timezone.utc).timestamp()
    for name, path in {
        "build_storage": workspace / "BUILD-STORAGE.md",
        "worktree_storage": workspace / "WORKTREE-STORAGE.md",
        "runs_index": runs / "INDEX.md",
    }.items():
        if not path.is_file():
            reports[name] = {"path": str(path), "status": "MISSING"}
            issues.append({"scope": name, "code": "REPORT_MISSING"})
            continue
        age_hours = round((now - path.stat().st_mtime) / 3600, 1)
        status = "STALE" if age_hours > 24 else "FRESH"
        reports[name] = {"path": str(path), "status": status, "age_hours": age_hours}
        if status == "STALE":
            issues.append({"scope": name, "code": "REPORT_STALE"})

    verdict = "FAIL" if any(item["code"] == "REPO_MISSING" for item in issues) else "INCONCLUSIVE" if issues else "PASS"
    result = {
        "generated_at_utc": utc_now(),
        "status": verdict,
        "registry": {"task_count": len(registry.get("tasks", [])), "diagnostic_count": registry.get("diagnostic_count", 0)},
        "runs": coverage,
        "repos": repos,
        "reports": reports,
        "issues": issues,
    }
    if output:
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "workspace-preflight.json", result)
        lines = [
            "# Workspace Preflight", "", f"- status: **{verdict}**",
            f"- tasks: **{result['registry']['task_count']}**",
            f"- manifest coverage: **{manifested}/{len(run_dirs)}**", "", "## Issues", "",
        ]
        lines += [f"- `{item['code']}`: {item['scope']}" for item in issues] or ["- none"]
        (output / "workspace-preflight.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xllm-flow")
    parser.add_argument("--workspace-root", type=Path, default=Path(os.environ.get("XLLM_WORKSPACE_ROOT", Path.cwd())))
    parser.add_argument("--registry", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    registry = commands.add_parser("registry")
    registry_sub = registry.add_subparsers(dest="action", required=True)
    registry_sub.add_parser("sync")
    registry_sub.add_parser("list")
    workspace_command = commands.add_parser("workspace")
    workspace_sub = workspace_command.add_subparsers(dest="action", required=True)
    workspace_check_parser = workspace_sub.add_parser("check")
    workspace_check_parser.add_argument("--output", type=Path)
    pf = commands.add_parser("preflight")
    pf.add_argument("--spec", type=Path, required=True)
    pf.add_argument("--output", type=Path)
    fingerprint = commands.add_parser("fingerprint")
    fingerprint.add_argument("--spec", type=Path, required=True)
    run = commands.add_parser("run")
    run_sub = run.add_subparsers(dest="action", required=True)
    create = run_sub.add_parser("create")
    create.add_argument("--spec", type=Path, required=True)
    finalize = run_sub.add_parser("finalize")
    finalize.add_argument("--run-root", type=Path, required=True)
    finalize.add_argument("--status", choices=["pass", "fail", "inconclusive"], required=True)
    finalize.add_argument("--retention-reviewed", action="store_true")
    archive = run_sub.add_parser("archive")
    archive.add_argument("--task-id", required=True)
    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("--run-root", type=Path, required=True)
    checkpoint.add_argument("--phase", choices=["created", "baseline", "profiling", "analysis", "discovery", "planning", "implementation", "validation", "finalized", "blocked"], required=True)
    checkpoint.add_argument("--last-success", default="")
    checkpoint.add_argument("--next-command", default="")
    gate = commands.add_parser("gate")
    gate_sub = gate.add_subparsers(dest="action", required=True)
    gate_check = gate_sub.add_parser("check")
    gate_check.add_argument("--run-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = args.workspace_root.resolve()
    registry_path = args.registry or workspace / "workspace-tasks.json"
    try:
        if args.command == "registry":
            data = registry_sync(workspace, registry_path) if args.action == "sync" else read_json(registry_path, {"tasks": []})
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "workspace" and args.action == "check":
            result = workspace_check(workspace, registry_path, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result["status"] == "FAIL" else 0
        elif args.command == "preflight":
            result = preflight(args.spec, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result["status"] == "FAIL" else 0
        elif args.command == "fingerprint":
            print(stable_fingerprint(load_spec(args.spec)))
        elif args.command == "checkpoint":
            if args.phase == "implementation":
                gate_errors = validate_big_rock_gate(args.run_root)
                gate_status = read_json(args.run_root / "analysis" / "big-rock-gate.json", {}).get("status")
                if gate_errors or gate_status not in {"PASS", "EXEMPT"}:
                    raise ValueError("Big-Rock Gate blocks implementation: " + "; ".join(gate_errors or [f"status is {gate_status}"]))
            save_checkpoint(args.run_root, {"phase": args.phase, "last_success": args.last_success, "next_command": args.next_command})
        elif args.command == "gate" and args.action == "check":
            errors = validate_big_rock_gate(args.run_root)
            gate_status = read_json(args.run_root / "analysis" / "big-rock-gate.json", {}).get("status")
            valid = not errors
            print(json.dumps({"valid": valid, "gate_status": gate_status, "implementation_allowed": valid and gate_status in {"PASS", "EXEMPT"}, "errors": errors}, ensure_ascii=False, indent=2))
            return 2 if errors else 0 if gate_status in {"PASS", "EXEMPT"} else 1
        elif args.command == "run" and args.action == "create":
            print(run_create(args.spec, registry_path))
        elif args.command == "run" and args.action == "finalize":
            run_finalize(args.run_root, args.status, args.retention_reviewed)
        elif args.command == "run" and args.action == "archive":
            registry_archive(registry_path, args.task_id)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
