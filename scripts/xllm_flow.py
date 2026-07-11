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
    for item in ["attempts", "reports", "env"]:
        (run_root / item).mkdir(parents=True, exist_ok=True)
    manifest = read_json(run_root / "manifest.json", {})
    fingerprint = stable_fingerprint(spec)
    if manifest and manifest.get("fingerprint") != fingerprint:
        raise ValueError(f"run_root already belongs to a different experiment: {run_root}")
    if not manifest:
        manifest = {"version": 1, "created_at_utc": utc_now(), "status": "pending", "fingerprint": fingerprint, "spec": spec}
        write_json(run_root / "manifest.json", manifest)
    (run_root / "attempts.jsonl").touch(exist_ok=True)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xllm-flow")
    parser.add_argument("--workspace-root", type=Path, default=Path(os.environ.get("XLLM_WORKSPACE_ROOT", Path.cwd())))
    parser.add_argument("--registry", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    registry = commands.add_parser("registry")
    registry_sub = registry.add_subparsers(dest="action", required=True)
    registry_sub.add_parser("sync")
    registry_sub.add_parser("list")
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
    checkpoint.add_argument("--phase", required=True)
    checkpoint.add_argument("--last-success", default="")
    checkpoint.add_argument("--next-command", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = args.workspace_root.resolve()
    registry_path = args.registry or workspace / "workspace-tasks.json"
    try:
        if args.command == "registry":
            data = registry_sync(workspace, registry_path) if args.action == "sync" else read_json(registry_path, {"tasks": []})
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "preflight":
            result = preflight(args.spec, args.output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result["status"] == "FAIL" else 0
        elif args.command == "fingerprint":
            print(stable_fingerprint(load_spec(args.spec)))
        elif args.command == "checkpoint":
            save_checkpoint(args.run_root, {"phase": args.phase, "last_success": args.last_success, "next_command": args.next_command})
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
