#!/usr/bin/env python3
"""Config-driven task, preflight, run, and archive workflow for xLLM."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
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
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def load_spec(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read experiment.yaml")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"experiment spec must be a mapping: {path}")
    errors = validate_spec(value)
    if errors:
        raise ValueError("invalid experiment spec: " + "; ".join(errors))
    return value


def get_nested(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors = []
    if spec.get("version") != 1:
        errors.append("version must be 1")
    mapping_sections = ["identity", "code", "model", "service", "workload"]
    optional_mappings = ["evaluation", "profiling", "environment", "comparison", "artifacts", "retention", "evidence"]
    for name in mapping_sections:
        if not isinstance(spec.get(name), dict):
            errors.append(f"{name} must be a mapping")
    for name in optional_mappings:
        if name in spec and not isinstance(spec[name], dict):
            errors.append(f"{name} must be a mapping")
    required = [
        "identity.task_id", "identity.purpose", "identity.kind", "identity.level", "identity.run_root",
        "code.framework", "code.repo", "model.name", "model.path", "model.tokenizer",
        "service.tensor_parallel", "service.devices", "workload.dataset",
        "workload.parallel", "workload.number", "workload.warmup", "workload.sampling",
    ]
    level = get_nested(spec, "identity.level")
    if level not in {"smoke", "quick", "full"}:
        return ["identity.level must be smoke, quick, or full"]
    if get_nested(spec, "identity.kind") not in {"performance_optimization", "benchmark", "profiling", "accuracy", "incident"}:
        errors.append("identity.kind has an unsupported value")
    if get_nested(spec, "code.framework") not in {"xllm", "vllm-ascend", "sglang"}:
        errors.append("code.framework has an unsupported value")
    if level in {"quick", "full"}:
        required += [
            "code.commit", "code.binary", "model.dtype", "workload.input_tokens",
            "workload.output_tokens", "evaluation.accuracy", "evaluation.performance",
            "profiling.enabled", "environment.require_npu", "artifacts.required",
        ]
    for name in required:
        value = get_nested(spec, name)
        if value is None or value == "":
            errors.append(f"missing required field: {name}")
    devices = get_nested(spec, "service.devices")
    tp = get_nested(spec, "service.tensor_parallel")
    if not isinstance(devices, list):
        errors.append("service.devices must be a list")
    if isinstance(devices, list) and is_integer(tp) and len(devices) != tp:
        errors.append("service.devices count must equal service.tensor_parallel")
    if isinstance(devices, list):
        valid_devices = all(is_integer(item) and item >= 0 for item in devices)
        if not valid_devices or len(set(devices)) != len(devices):
            errors.append("service.devices must contain unique non-negative integers")
    for name in ["service.tensor_parallel", "workload.parallel", "workload.number"]:
        value = get_nested(spec, name)
        if not is_integer(value) or value <= 0:
            errors.append(f"{name} must be a positive integer")
    warmup = get_nested(spec, "workload.warmup")
    if not is_integer(warmup) or warmup < 0 or (level in {"quick", "full"} and warmup == 0):
        errors.append("workload.warmup is invalid for the selected level")
    if level in {"quick", "full"}:
        for name in ["workload.input_tokens", "workload.output_tokens"]:
            value = get_nested(spec, name)
            if not is_integer(value) or value <= 0:
                errors.append(f"{name} must be a positive integer")
        repetitions = get_nested(spec, "evaluation.performance.repetitions")
        if repetitions is not None and (not is_integer(repetitions) or repetitions <= 0):
            errors.append("evaluation.performance.repetitions must be a positive integer")
    if get_nested(spec, "profiling.enabled") is True:
        for name in ["profiling.tool", "profiling.phase", "profiling.boundary"]:
            if not get_nested(spec, name):
                errors.append(f"missing required field: {name}")
    return errors


def stable_fingerprint(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def experiment_fingerprint(spec: dict[str, Any], spec_path: Path) -> str:
    material: dict[str, Any] = {"spec": spec}
    hashes = {}
    values = list(spec.get("code", {}).get("patches", []))
    values += [get_nested(spec, "workload.dataset_path")]
    for value in values:
        path = resolve_spec_path(spec_path, str(value)) if value else None
        if path and path.is_file():
            hashes[str(value)] = file_sha256(path)
    material["file_hashes"] = hashes
    return stable_fingerprint(material)


def execution_fingerprint(spec: dict[str, Any], spec_path: Path) -> str:
    return stable_fingerprint({
        "campaign_fingerprint": experiment_fingerprint(spec, spec_path),
        "code_identity": observed_code_identity(spec, spec_path),
    })


def capture(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout.strip()


def git_identity(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"valid": False, "path": str(path)}
    code, root = capture(["git", "rev-parse", "--show-toplevel"], path)
    if code != 0:
        return {"valid": False, "path": str(path)}
    _, branch = capture(["git", "branch", "--show-current"], path)
    _, commit = capture(["git", "rev-parse", "HEAD"], path)
    _, status = capture(["git", "status", "--short"], path)
    _, diff = capture(["git", "diff", "--binary", "HEAD"], path)
    _, untracked = capture(["git", "ls-files", "--others", "--exclude-standard"], path)
    untracked_hashes = {
        name: file_sha256(Path(root) / name)
        for name in untracked.splitlines()
        if (Path(root) / name).is_file()
    }
    _, remotes = capture(["git", "remote", "-v"], path)
    return {
        "valid": True,
        "path": root,
        "branch": branch or "detached",
        "commit": commit,
        "dirty": bool(status),
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "untracked_hashes": untracked_hashes,
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
            old = previous.get(root.name, {})
            override = Path(old["source_override"]) if old.get("source_override") else None
            if override and not override.is_absolute():
                override = (workspace / override).resolve()
            source = override if override and override.exists() else sources[0] if sources else None
            effective_sources = [source] if source else sources
            discovered.add(root.name)
            identity = git_identity(source) if source else {"valid": False}
            diagnostics = task_diagnostics(root.name, effective_sources, identity.get("branch"))
            if old.get("state") == "source-only":
                diagnostics = [item for item in diagnostics if item != "TASK_BRANCH_TP_MISMATCH"]
            tasks.append({
                "task_id": root.name,
                "state": old.get("state", "active"),
                "task_root": str(root.resolve()),
                "source_path": str(source.resolve()) if source else None,
                "source_paths": [str(item.resolve()) for item in effective_sources],
                "run_root": old.get("run_root"),
                "source_override": old.get("source_override"),
                "aliases": old.get("aliases", []),
                "owner": old.get("owner"),
                "priority": old.get("priority"),
                "objective": old.get("objective"),
                "current_phase": old.get("current_phase"),
                "canonical_task_id": old.get("canonical_task_id"),
                "task_doc": str(root / "TASK.md") if (root / "TASK.md").exists() else None,
                "branch": identity.get("branch"),
                "commit": identity.get("commit"),
                "dirty": identity.get("dirty"),
                "diagnostics": diagnostics,
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


def registry_bind(registry_path: Path, task_id: str, **updates: Any) -> dict[str, Any]:
    registry = read_json(registry_path, {"version": 1, "tasks": []})
    task = next((item for item in registry["tasks"] if item.get("task_id") == task_id), None)
    if task is None:
        task = {"task_id": task_id, "state": "active", "present": False}
        registry["tasks"].append(task)
    for key, value in updates.items():
        if value is not None:
            if key == "state" and value == "retired":
                raise ValueError("retired state can only be set by run archive")
            task[key] = value
    task["updated_at_utc"] = utc_now()
    write_json(registry_path, registry)
    return task


def resolve_spec_path(spec_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (spec_path.parent / path).resolve()


def observed_code_identity(spec: dict[str, Any], spec_path: Path) -> dict[str, Any]:
    source = resolve_spec_path(spec_path, get_nested(spec, "code.repo"))
    identity = git_identity(source) if source else {"valid": False}
    binary = resolve_spec_path(spec_path, get_nested(spec, "code.binary"))
    if binary and binary.is_file():
        identity = {**identity, "binary_path": str(binary), "binary_sha256": file_sha256(binary)}
    return identity


def add_check(checks: list[dict[str, Any]], name: str, status: str, detail: Any = None) -> None:
    item = {"name": name, "status": status}
    if detail is not None and detail != "":
        item["detail"] = detail
    checks.append(item)


def port_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def package_versions() -> dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    for key, distribution in {"torch": "torch", "torch_npu": "torch-npu", "yaml": "PyYAML"}.items():
        try:
            versions[key] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[key] = "unavailable"
    code, output = capture(["bash", "-lc", "${ASCEND_HOME_PATH:-/usr/local/Ascend/ascend-toolkit/latest}/bin/msprof --version 2>/dev/null | head -1"])
    versions["msprof"] = output if code == 0 else "unavailable"
    for name, candidates in {
        "cann": [
            "/usr/local/Ascend/ascend-toolkit/latest/version.cfg",
            "/usr/local/Ascend/ascend-toolkit/latest/version.info",
            "/usr/local/Ascend/ascend-toolkit/latest/opp/version.info",
        ],
        "driver": ["/usr/local/Ascend/driver/version.info"],
    }.items():
        version_file = next((Path(path) for path in candidates if Path(path).is_file()), None)
        versions[name] = version_file.read_text(encoding="utf-8", errors="ignore")[:1000].strip() if version_file else "unavailable"
    return versions


def fairness_mismatches(current: dict[str, Any], baseline: dict[str, Any], allowed: set[str]) -> list[str]:
    keys = [
        "code.framework", "code.commit", "code.base_commit", "code.build_command", "code.binary", "code.patches",
        "model.name", "model.path", "model.tokenizer", "model.dtype", "model.quantization",
        "model.draft_model", "model.speculative_tokens",
        "service.tensor_parallel", "service.pipeline_parallel", "service.devices", "service.flags",
        "workload.dataset", "workload.dataset_path", "workload.input_tokens", "workload.output_tokens",
        "workload.parallel", "workload.number", "workload.warmup", "workload.stream", "workload.sampling",
    ]
    return [key for key in keys if key not in allowed and get_nested(current, key) != get_nested(baseline, key)]


def preflight(spec_path: Path, output: Path | None) -> dict[str, Any]:
    spec = load_spec(spec_path)
    source_value = spec.get("code", {}).get("repo")
    source = resolve_spec_path(spec_path, source_value)
    run_root_value = spec.get("identity", {}).get("run_root")
    checks: list[dict[str, Any]] = []
    identity = observed_code_identity(spec, spec_path) if source else {"valid": False, "path": None}
    add_check(checks, "source_git", "PASS" if identity.get("valid") else "FAIL", identity.get("path"))
    expected_commit = spec.get("code", {}).get("commit")
    if expected_commit:
        add_check(checks, "commit_match", "PASS" if identity.get("commit", "").startswith(str(expected_commit)) else "FAIL", identity.get("commit"))
    if identity.get("dirty"):
        add_check(checks, "dirty_worktree", "INCONCLUSIVE" if spec.get("code", {}).get("allow_dirty") else "FAIL", identity.get("status_short"))
    if source and identity.get("valid") and spec.get("environment", {}).get("require_clean_submodules"):
        _, submodules = capture(["git", "submodule", "status", "--recursive"], source)
        bad = [line for line in submodules.splitlines() if line[:1] in {"-", "+", "U"}]
        add_check(checks, "submodules", "FAIL" if bad else "PASS", bad or "clean")
    for index, patch in enumerate(spec.get("code", {}).get("patches", [])):
        patch_path = resolve_spec_path(spec_path, str(patch))
        add_check(checks, f"patch_{index}", "PASS" if patch_path and patch_path.is_file() else "FAIL", str(patch_path))

    for name in ["path", "tokenizer", "draft_model"]:
        value = spec.get("model", {}).get(name)
        if value:
            path = resolve_spec_path(spec_path, str(value))
            readable = bool(path and path.exists() and os.access(path, os.R_OK))
            add_check(checks, f"model_{name}", "PASS" if readable else "FAIL", str(path))
    binary_value = spec.get("code", {}).get("binary")
    if binary_value:
        binary = resolve_spec_path(spec_path, str(binary_value))
        valid_binary = bool(binary and binary.is_file() and os.access(binary, os.X_OK))
        detail: dict[str, Any] = {"path": str(binary)}
        if valid_binary:
            _, detail["file"] = capture(["file", str(binary)])
            ldd_code, detail["ldd"] = capture(["ldd", str(binary)])
            detail["ldd_ok"] = ldd_code == 0 and "not found" not in detail["ldd"]
            valid_binary = valid_binary and detail["ldd_ok"]
        add_check(checks, "binary", "PASS" if valid_binary else "FAIL", detail)

    dataset_value = spec.get("workload", {}).get("dataset_path")
    if dataset_value:
        dataset = resolve_spec_path(spec_path, str(dataset_value))
        add_check(checks, "dataset", "PASS" if dataset and dataset.exists() else "FAIL", str(dataset))
    required_tools = set(spec.get("environment", {}).get("required_tools", []))
    if spec.get("profiling", {}).get("enabled"):
        required_tools.add(str(spec.get("profiling", {}).get("tool", "msprof")))
    for tool in sorted(required_tools):
        tool_path = shutil.which(tool)
        add_check(checks, f"tool_{tool}", "PASS" if tool_path else "FAIL", tool_path)

    host = str(spec.get("service", {}).get("host", "127.0.0.1"))
    for name in ["port", "hccl_port"]:
        value = spec.get("service", {}).get(name)
        if isinstance(value, int):
            add_check(checks, name, "PASS" if port_available(host, value) else "FAIL", value)
    npu_snapshot = ""
    if spec.get("environment", {}).get("require_npu"):
        npu_code, npu_snapshot = capture(["npu-smi", "info"])
        add_check(checks, "npu", "PASS" if npu_code == 0 else "FAIL", npu_snapshot[-4000:])

    baseline_value = spec.get("comparison", {}).get("baseline_manifest")
    if baseline_value:
        baseline_path = resolve_spec_path(spec_path, str(baseline_value))
        baseline_manifest = read_json(baseline_path, {}) if baseline_path and baseline_path.is_file() else {}
        baseline_spec = baseline_manifest.get("spec", baseline_manifest)
        mismatches = fairness_mismatches(spec, baseline_spec, set(spec.get("comparison", {}).get("changed_variables", [])))
        add_check(checks, "baseline_fairness", "FAIL" if mismatches else "PASS", mismatches or "matched")
    run_root = resolve_spec_path(spec_path, run_root_value)
    writable_parent = run_root.parent if run_root else None
    while writable_parent and not writable_parent.exists() and writable_parent != writable_parent.parent:
        writable_parent = writable_parent.parent
    run_root_ok = bool(run_root and writable_parent and writable_parent.is_dir() and os.access(writable_parent, os.W_OK))
    add_check(checks, "run_root", "PASS" if run_root_ok else "FAIL", str(run_root))
    versions = package_versions()
    for name, expected in spec.get("environment", {}).get("expected", {}).items():
        if expected:
            observed = versions.get(name, "unavailable")
            add_check(checks, f"version_{name}", "PASS" if str(expected) in observed else "FAIL", {"expected": expected, "observed": observed})
    statuses = {item["status"] for item in checks}
    verdict = "FAIL" if "FAIL" in statuses else "INCONCLUSIVE" if "INCONCLUSIVE" in statuses else "PASS"
    result = {"generated_at_utc": utc_now(), "status": verdict, "fingerprint": experiment_fingerprint(spec, spec_path), "source": identity, "versions": versions, "checks": checks}
    if output:
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "preflight.json", result)
        write_json(output / "versions.json", versions)
        if source and identity.get("dirty") and spec.get("artifacts", {}).get("save_git_diff", True):
            _, source_diff = capture(["git", "diff", "--binary", "HEAD"], source)
            write_text(output / "source.diff", source_diff + "\n")
        if npu_snapshot:
            write_text(output / "npu-smi.txt", npu_snapshot + "\n")
        lines = ["# Preflight", "", f"- status: **{verdict}**", f"- fingerprint: `{result['fingerprint']}`", ""]
        lines += [f"- {item['name']}: {item['status']}" for item in checks]
        write_text(output / "preflight.md", "\n".join(lines) + "\n")
    return result


def render_checkpoint(state: dict[str, Any]) -> str:
    return "\n".join([
        "# Task Checkpoint", "",
        f"- updated_at_utc: {state['updated_at_utc']}",
        f"- phase: {state.get('phase', 'created')}",
        f"- state: {state.get('state', 'active')}",
        f"- revision: {state.get('revision', 1)}",
        f"- active_attempt: {state.get('active_attempt', '')}",
        f"- current_best: {state.get('current_best', '')}",
        f"- remaining_gap: {state.get('remaining_gap', '')}",
        f"- last_success: {state.get('last_success', '')}",
        f"- next_command: `{state.get('next_command', '')}`", "",
        "## Blockers", "", *[f"- {item}" for item in state.get("blockers", [])], "",
        "## Completed Artifacts", "", *[f"- `{item}`" for item in state.get("completed_artifacts", [])], "",
    ])


def save_checkpoint(run_root: Path, state: dict[str, Any]) -> None:
    existing = read_json(run_root / "checkpoint.json", {})
    merged = {**existing, **{key: value for key, value in state.items() if value is not None}}
    merged["schema_version"] = 1
    merged["revision"] = int(existing.get("revision", 0)) + 1
    merged["updated_at_utc"] = utc_now()
    write_json(run_root / "checkpoint.json", merged)
    write_text(run_root / "CHECKPOINT.md", render_checkpoint(merged))


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
    elif status == "PASS" and unclassified / wall > 0.2 and not gate.get("unclassified_disposition"):
        errors.append("unclassified above 20% requires unclassified_disposition")
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
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in [low, high, cost, risk, fraction, item["remaining_gap_share"], item["priority_score"]]):
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
        elif actionable and item["expected_gain_high"] < max(candidate["expected_gain_high"] for candidate in actionable) - 1e-9:
            errors.append("selected candidate must have the largest actionable end-to-end gain")
        if item.get("expected_gain_high", 0) <= (noise_floor if isinstance(noise_floor, (int, float)) else 0):
            errors.append("selected candidate expected gain must exceed noise_floor")
        if not item.get("ab_plan") or not item.get("rollback_plan"):
            errors.append("selected candidate requires ab_plan and rollback_plan")
        if status == "PASS" and item.get("remaining_gap_share", 0) < 0.2:
            errors.append("PASS candidate must close at least 20% of remaining gap")
        if status == "EXEMPT":
            if not gate.get("exemption_reason"):
                errors.append("EXEMPT requires exemption_reason")
            if not gate.get("l0_l2_disposition"):
                errors.append("EXEMPT requires l0_l2_disposition")
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


def verify_attempt_entries(entries: list[dict[str, Any]]) -> None:
    previous_hash = ""
    for index, entry in enumerate(entries, start=1):
        if entry.get("sequence") != index or entry.get("previous_entry_hash", "") != previous_hash:
            raise ValueError("attempt ledger sequence or hash chain is invalid")
        payload = {key: value for key, value in entry.items() if key != "entry_hash"}
        expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if entry.get("entry_hash") != expected:
            raise ValueError("attempt ledger entry hash is invalid")
        previous_hash = entry.get("entry_hash", "")


def read_attempts(run_root: Path, verify: bool = True) -> list[dict[str, Any]]:
    path = run_root / "attempts.jsonl"
    if not path.exists():
        return []
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if verify:
        verify_attempt_entries(entries)
    return entries


def render_attempt_ledger(entries: list[dict[str, Any]]) -> str:
    lines = ["# Attempt Ledger", "", "| seq | attempt | phase | status | hypothesis | decision |", "|---:|---|---|---|---|---|"]
    for entry in entries:
        lines.append(f"| {entry['sequence']} | `{entry['attempt_id']}` | {entry['phase']} | {entry['status']} | {entry.get('hypothesis', '')} | {entry.get('decision', '')} |")
    return "\n".join(lines) + "\n"


def render_optimization_ledger(entries: list[dict[str, Any]]) -> str:
    completed = [entry for entry in entries if entry.get("status") in {"pass", "fail", "rejected"}]
    lines = ["# Optimization Ledger", "", "| attempt | status | changed variables | metrics | decision |", "|---|---|---|---|---|"]
    for entry in completed:
        changed = ", ".join(entry.get("changed_variables", [])) or "baseline"
        metrics = json.dumps(entry.get("metrics", {}), ensure_ascii=False, sort_keys=True)
        lines.append(f"| `{entry['attempt_id']}` | {entry['status']} | {changed} | `{metrics}` | {entry.get('decision') or entry.get('reason', '')} |")
    return "\n".join(lines) + "\n"


def render_source_idea_ledger(entries: list[dict[str, Any]]) -> str:
    sourced = [entry for entry in entries if entry.get("source")]
    lines = ["# Source Idea Ledger", "", "| source | attempt | hypothesis | outcome |", "|---|---|---|---|"]
    for entry in sourced:
        lines.append(f"| {entry['source']} | `{entry['attempt_id']}` | {entry.get('hypothesis', '')} | {entry.get('status', '')} |")
    return "\n".join(lines) + "\n"


def write_derived_ledgers(run_root: Path, entries: list[dict[str, Any]]) -> None:
    humanize = run_root / "humanize"
    humanize.mkdir(exist_ok=True)
    write_text(humanize / "attempt-ledger.md", render_attempt_ledger(entries))
    write_text(humanize / "optimization-ledger.md", render_optimization_ledger(entries))
    write_text(humanize / "source-idea-ledger.md", render_source_idea_ledger(entries))
    lineage = []
    for entry in entries:
        if entry.get("parent_attempt"):
            lineage.append(json.dumps({
                "parent_attempt": entry["parent_attempt"], "child_attempt": entry["attempt_id"],
                "entry_hash": entry["entry_hash"], "source": entry.get("source", ""),
            }, ensure_ascii=False, sort_keys=True))
    write_text(humanize / "lineage.jsonl", ("\n".join(lineage) + "\n") if lineage else "")


def append_attempt(run_root: Path, attempt: dict[str, Any]) -> dict[str, Any]:
    path = run_root / "attempts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = read_json(run_root / "manifest.json", {})
    if manifest.get("fingerprint"):
        expected_run_id = get_nested(manifest.get("spec", {}), "identity.task_id")
        if attempt.get("run_id") != expected_run_id or attempt.get("spec_fingerprint") != manifest["fingerprint"]:
            raise ValueError("attempt identity does not match run manifest")
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        entries = [json.loads(line) for line in handle.read().splitlines() if line.strip()]
        verify_attempt_entries(entries)
        if any(entry.get("entry_id") == attempt.get("entry_id") for entry in entries):
            raise ValueError(f"duplicate attempt entry_id: {attempt.get('entry_id')}")
        if attempt.get("fingerprint") and any(entry.get("fingerprint") == attempt["fingerprint"] and entry.get("status") in {"pass", "fail", "rejected"} for entry in entries):
            raise ValueError("duplicate completed experiment fingerprint")
        if attempt.get("status") in {"fail", "rejected"} and not attempt.get("reason"):
            raise ValueError("failed or rejected attempt requires reason")
        if attempt.get("status") == "pass" and (not attempt.get("metrics") or not attempt.get("artifacts")):
            raise ValueError("passing attempt requires metrics and artifacts")
        for artifact in attempt.get("artifacts", []):
            resolve_run_artifact(run_root, artifact)
        previous_hash = entries[-1].get("entry_hash", "") if entries else ""
        entry = {
            "schema_version": 1, "sequence": len(entries) + 1,
            "entry_id": attempt.get("entry_id") or f"entry-{len(entries) + 1}",
            "timestamp": utc_now(), "previous_entry_hash": previous_hash, **attempt,
        }
        payload = {key: value for key, value in entry.items() if key != "entry_hash"}
        entry["entry_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        handle.seek(0, os.SEEK_END)
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    entries.append(entry)
    write_derived_ledgers(run_root, entries)
    checkpoint_path = run_root / "checkpoint.json"
    if checkpoint_path.exists():
        existing = read_json(checkpoint_path, {})
        completed_artifacts = list(existing.get("completed_artifacts", []))
        for artifact in entry.get("artifacts", []):
            if artifact not in completed_artifacts:
                completed_artifacts.append(artifact)
        save_checkpoint(run_root, {
            "phase": entry.get("phase"),
            "active_attempt": entry.get("attempt_id") if entry.get("status") == "running" else "",
            "last_completed_entry": entry["sequence"] if entry.get("status") != "running" else existing.get("last_completed_entry", 0),
            "last_ledger_hash": entry["entry_hash"],
            "completed_artifacts": completed_artifacts,
            "last_success": f"attempt:{entry.get('attempt_id')}:{entry.get('status')}",
        })
    return entry


def check_duplicate_attempt(run_root: Path, fingerprint: str) -> dict[str, Any] | None:
    return next((entry for entry in read_attempts(run_root) if entry.get("fingerprint") == fingerprint), None)


def active_attempts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terminal_sequence: dict[str, int] = {}
    for entry in entries:
        if entry.get("status") in {"pass", "fail", "rejected"}:
            terminal_sequence[entry.get("attempt_id", "")] = entry["sequence"]
    return [
        entry for entry in entries
        if entry.get("status") == "running" and terminal_sequence.get(entry.get("attempt_id", ""), 0) < entry["sequence"]
    ]


def valid_metric_comparison(metrics: Any) -> bool:
    if not isinstance(metrics, dict):
        return False
    baseline, current, delta = (metrics.get(name) for name in ["baseline", "current", "delta"])
    if not all(isinstance(value, dict) and bool(value) for value in [baseline, current, delta]):
        return False
    if set(baseline) != set(current) or set(baseline) != set(delta):
        return False
    for name in baseline:
        values = [baseline[name], current[name], delta[name]]
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
            return False
        expected = current[name] - baseline[name]
        if abs(delta[name] - expected) > max(abs(expected) * 1e-6, 1e-9):
            return False
    return True


def validate_performance_attempts(entries: list[dict[str, Any]]) -> list[str]:
    baselines = {
        entry.get("attempt_id") for entry in entries
        if entry.get("status") == "pass" and entry.get("phase") == "benchmark" and not entry.get("changed_variables")
    }
    candidates = [
        entry for entry in entries
        if entry.get("status") == "pass" and entry.get("phase") == "benchmark" and entry.get("changed_variables")
    ]
    accepted = []
    for entry in candidates:
        metrics = entry.get("metrics", {})
        if (
            entry.get("parent_attempt") in baselines
            and str(entry.get("decision", "")).lower() in {"accept", "accepted", "keep"}
            and valid_metric_comparison(metrics)
        ):
            accepted.append(entry)
    errors = []
    if not baselines:
        errors.append("performance optimization requires a passing baseline benchmark")
    if not accepted:
        errors.append("performance optimization requires an accepted candidate with parent baseline and baseline/current/delta metrics")
    return errors


def attempt_fingerprint(spec: dict[str, Any], spec_path: Path, changed_variables: list[str], repeat_index: int) -> str:
    return stable_fingerprint({
        "execution": execution_fingerprint(spec, spec_path),
        "changed_variables": sorted(changed_variables),
        "repeat_index": repeat_index,
    })


def run_create(spec_path: Path, registry_path: Path | None = None, allow_inconclusive: bool = False) -> Path:
    spec = load_spec(spec_path)
    run_root_value = spec.get("identity", {}).get("run_root")
    if not run_root_value:
        raise ValueError("identity.run_root is required")
    run_root = resolve_spec_path(spec_path, run_root_value)
    assert run_root is not None
    preflight_result = preflight(spec_path, None)
    if preflight_result["status"] == "FAIL" or (preflight_result["status"] == "INCONCLUSIVE" and not allow_inconclusive):
        raise ValueError(f"preflight must pass before run create: {preflight_result['status']}")
    for item in ["attempts", "reports", "env", "analysis"]:
        (run_root / item).mkdir(parents=True, exist_ok=True)
    manifest = read_json(run_root / "manifest.json", {})
    fingerprint = experiment_fingerprint(spec, spec_path)
    if manifest and manifest.get("fingerprint") != fingerprint:
        raise ValueError(f"run_root already belongs to a different experiment: {run_root}")
    if not manifest:
        manifest = {
            "version": 1, "created_at_utc": utc_now(), "status": "pending",
            "fingerprint": fingerprint, "spec_path": str(spec_path.resolve()), "spec": spec,
            "code_identity": preflight_result.get("source"), "versions": preflight_result.get("versions"),
            "preflight_status": preflight_result["status"],
        }
        write_json(run_root / "manifest.json", manifest)
    (run_root / "attempts.jsonl").touch(exist_ok=True)
    write_derived_ledgers(run_root, read_attempts(run_root))
    budget = run_root / "analysis" / "bottleneck-budget.md"
    if not budget.exists():
        write_text(budget,
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
        )
    ranking = run_root / "analysis" / "candidate-ranking.md"
    if not ranking.exists():
        write_text(ranking,
            "# Candidate Ranking\n\n"
            "| rank | level | hypothesis | gain low | gain high | gap share | cost 1-5 | risk 1-5 | priority | evidence | blocked reason | selected |\n"
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|\n\n"
            "L3 remains locked until L0-L2 candidates are quantified or rejected with evidence.\n",
        )
    gate = run_root / "analysis" / "big-rock-gate.json"
    if not gate.exists():
        write_json(gate, {
            "version": 1, "status": "PENDING",
            "budget": {"phase": "", "unit": "ms", "wall_time": 0, "buckets": {"compute": 0, "communication": 0, "host": 0, "graph_sync": 0, "copy_memory": 0, "sampling_postprocess": 0}, "unclassified": 0, "overlap_opportunity": 0, "evidence": ""},
            "remaining_target_gap": 0, "noise_floor": 0,
            "candidates": [], "bucket_dispositions": {}, "unclassified_disposition": "", "l0_l2_disposition": "", "exemption_reason": "", "blocked_reason": "",
            "discovery": {"rounds": 0, "next_measurement": ""},
        })
    if not (run_root / "checkpoint.json").exists():
        save_checkpoint(run_root, {
            "run_id": spec.get("identity", {}).get("task_id"), "spec_fingerprint": fingerprint,
            "phase": "created", "state": "active", "active_attempt": "",
            "last_completed_entry": 0, "last_ledger_hash": "", "completed_artifacts": ["manifest.json", "env/preflight.json"],
            "blockers": [], "last_success": "run-create", "next_command": "xllm-flow checkpoint --phase baseline",
        })
    preflight(spec_path, run_root / "env")
    if registry_path:
        update_registry_binding(registry_path, spec, run_root)
    return run_root


def resolve_run_artifact(run_root: Path, value: str) -> Path:
    path = Path(value)
    resolved_root = run_root.resolve()
    candidate = (path if path.is_absolute() else run_root / path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"artifact must stay inside run_root: {value}") from exc
    return candidate


def relative_artifact(run_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(run_root.resolve()))


def selected_attempt(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    accepted = [
        entry for entry in entries
        if entry.get("status") == "pass" and str(entry.get("decision", "")).lower() in {"accept", "accepted", "keep"}
    ]
    passed = [entry for entry in entries if entry.get("status") == "pass"]
    return (accepted or passed or entries)[-1] if entries else None


def service_attempt_id(run_root: Path, spec: dict[str, Any], requested: str | None = None) -> str:
    if requested:
        return requested
    configured = get_nested(spec, "evidence.service_attempt_id")
    if configured:
        return str(configured)
    current = run_root / "service" / "current-attempt"
    if current.is_file():
        return current.read_text(encoding="utf-8").strip()
    attempts = sorted(path.name for path in (run_root / "service").glob("*") if path.is_dir()) if (run_root / "service").is_dir() else []
    return attempts[-1] if attempts else "attempt-001"


def artifact_status(path: Path) -> str:
    return str(read_json(path, {}).get("status", "MISSING"))


def build_run_evidence(run_root: Path, evidence_type: str | None = None, level: str | None = None, attempt_id: str | None = None) -> dict[str, Any]:
    run_root = run_root.resolve()
    manifest = read_json(run_root / "manifest.json", {})
    if not manifest:
        raise ValueError(f"manifest.json is required: {run_root}")
    spec = manifest.get("spec", {})
    entries = read_attempts(run_root)
    selected = selected_attempt(entries)
    code_identity = (selected or {}).get("code_identity") or manifest.get("code_identity", {})
    kind = get_nested(spec, "identity.kind")
    resolved_type = evidence_type or get_nested(spec, "evidence.type") or {"accuracy": "accuracy", "profiling": "profiling"}.get(kind, "performance")
    if resolved_type not in {"performance", "accuracy", "profiling"}:
        raise ValueError(f"unsupported evidence type: {resolved_type}")
    resolved_level = level or get_nested(spec, "evidence.level") or get_nested(spec, "identity.level")
    service_id = service_attempt_id(run_root, spec, attempt_id)
    service_root = run_root / "service" / service_id
    physical_devices = get_nested(spec, "service.physical_devices") or get_nested(spec, "service.devices") or []
    host = str(get_nested(spec, "service.host") or "127.0.0.1")
    port = int(get_nested(spec, "service.port") or 8000)
    evidence_artifacts = get_nested(spec, "evidence.artifacts") or {}
    defaults = {
        "environment": {"before": "env/before", "after": "env/after"},
        "performance": {"raw": "perf/raw", "metrics": "perf/metrics.json"},
        "accuracy": {
            "request_config": "accuracy/request-config.json", "dataset_config": "accuracy/dataset-config.json",
            "raw_predictions": "accuracy/raw-predictions.jsonl", "failed_cases": "accuracy/failed-cases.jsonl",
            "score": "accuracy/score.json",
        },
        "profiling": {
            "prof": "profiling/PROF", "export": "profiling/mindstudio_profiler_output",
            "capture_log": "profiling/capture.log", "workload_log": "profiling/workload.log",
            "analysis": "profiling/analysis.json",
        },
    }
    active_artifact_groups = {"environment", resolved_type}
    artifacts = {
        key: {**defaults[key], **evidence_artifacts.get(key, {})}
        for key in active_artifact_groups
    }
    artifacts.update({
        key: value
        for key, value in evidence_artifacts.items()
        if key not in active_artifact_groups
    })
    workload = spec.get("workload", {})
    document: dict[str, Any] = {
        "schema_version": 1,
        "run_id": get_nested(spec, "identity.task_id"),
        "campaign_fingerprint": manifest.get("fingerprint"),
        "evidence_type": resolved_type,
        "level": resolved_level,
        "identity": {
            "framework": get_nested(spec, "code.framework"), "repo_path": code_identity.get("path"),
            "commit": code_identity.get("commit"), "dirty_diff_sha256": code_identity.get("diff_sha256"),
            "binary_path": code_identity.get("binary_path") or get_nested(spec, "code.binary"),
            "binary_sha256": code_identity.get("binary_sha256"),
            "build_verdict": "build/verdict.json", "binary_provenance": "build/binary-provenance.json",
        },
        "environment": {
            "physical_device_ids": physical_devices, "visible_device_order": get_nested(spec, "service.devices") or [],
            "hardware": get_nested(spec, "environment.hardware") or "ascend-npu",
            "software_stack": manifest.get("versions", {}),
        },
        "model": {
            "name": get_nested(spec, "model.name"), "path": get_nested(spec, "model.path"),
            "tokenizer_path": get_nested(spec, "model.tokenizer"), "dtype": get_nested(spec, "model.dtype") or "unspecified",
        },
        "service": {
            "attempt_id": service_id, "api_url": f"http://{host}:{port}/v1",
            "startup_command": f"service/{service_id}/command.sh", "pid_file": f"service/{service_id}/pids.txt",
            "logs": [relative_artifact(run_root, path) for path in sorted(service_root.glob("*.log"))] or [f"service/{service_id}/node_0.log"],
            "ready": {"status": artifact_status(service_root / "ready.json"), "artifact": f"service/{service_id}/ready.json"},
            "smoke": {"status": artifact_status(service_root / "smoke.json"), "artifact": f"service/{service_id}/smoke.json"},
            "cleanup": {"status": artifact_status(service_root / "cleanup.json"), "artifact": f"service/{service_id}/cleanup.json"},
        },
        "workload": {
            "request_fingerprint": stable_fingerprint(workload), "dataset": workload.get("dataset"),
            "input_tokens": workload.get("input_tokens"), "output_tokens": workload.get("output_tokens"),
            "parallel": workload.get("parallel"), "number": workload.get("number"),
            "warmup_num": workload.get("warmup"), "profiling_attached": bool(get_nested(spec, "profiling.enabled")),
            "sampling": workload.get("sampling", {}),
        },
        "artifacts": artifacts,
    }
    if resolved_type == "accuracy":
        document["workload"].update({
            "prompt_template_sha256": get_nested(spec, "evidence.prompt_template_sha256"),
            "dataset_fingerprint": get_nested(spec, "evidence.dataset_fingerprint") or stable_fingerprint({"dataset": workload.get("dataset"), "path": workload.get("dataset_path")}),
            "answer_extractor_version": get_nested(spec, "evidence.answer_extractor_version"),
        })
    if resolved_type == "profiling":
        document["profiling"] = {
            "attached_parent_pid": get_nested(spec, "evidence.attached_parent_pid"),
            "warmup_before_capture": bool(workload.get("warmup", 0)),
            "workload_status": get_nested(spec, "evidence.workload_status") or "PASS",
        }
    return document


def export_run_evidence(run_root: Path, **kwargs: Any) -> Path:
    output = run_root.resolve() / "run-evidence.json"
    write_json(output, build_run_evidence(run_root, **kwargs))
    return output


def build_fairness_candidate(run_root: Path, name: str) -> dict[str, Any]:
    run_root = run_root.resolve()
    evidence = read_json(run_root / "run-evidence.json", {}) or build_run_evidence(run_root)
    manifest = read_json(run_root / "manifest.json", {})
    spec = manifest.get("spec", {})
    fairness = get_nested(spec, "evidence.fairness") or {}
    before_path = resolve_run_artifact(run_root, fairness.get("before", "env/fairness-before.json"))
    after_path = resolve_run_artifact(run_root, fairness.get("after", "env/fairness-after.json"))
    idle_paths = [resolve_run_artifact(run_root, value) for value in fairness.get("idle", ["env/fairness-idle-0.json"])]
    environment = evidence.get("environment", {})
    model = evidence.get("model", {})
    workload = evidence.get("workload", {})
    before = read_json(before_path, {})
    idle_samples = [read_json(path, {}) for path in idle_paths]
    after = read_json(after_path, {})
    snapshots = [before, *idle_samples, after]
    backends = {snapshot.get("backend") for snapshot in snapshots if snapshot.get("backend")}
    selected = selected_attempt(read_attempts(run_root))
    accepted = bool(
        selected
        and selected.get("status") == "pass"
        and str(selected.get("decision", "")).lower() in {"accept", "accepted", "keep"}
    )
    return {
        "name": name, "run_root": str(run_root), "evidence_verdict": "evidence-verdict.json",
        "campaign_fingerprint": manifest.get("fingerprint"),
        "identity": {
            "hardware_fingerprint": stable_fingerprint({"hardware": environment.get("hardware"), "software": environment.get("software_stack")}),
            "device_backend": next(iter(backends)) if len(backends) == 1 else None,
            "physical_device_ids": environment.get("physical_device_ids"), "visible_device_order": environment.get("visible_device_order"),
            "model_fingerprint": stable_fingerprint(model), "tokenizer_fingerprint": stable_fingerprint({"tokenizer": model.get("tokenizer_path")}),
            "dtype": model.get("dtype"), "quantization": get_nested(spec, "model.quantization") or "none",
            "workload_fingerprint": workload.get("request_fingerprint"), "sampling_fingerprint": stable_fingerprint(workload.get("sampling", {})),
            "sla_fingerprint": stable_fingerprint(get_nested(spec, "evaluation.performance.sla") or {}),
            "optimization_policy_fingerprint": stable_fingerprint({"changed_variables": get_nested(spec, "comparison.changed_variables") or [], "service_flags": get_nested(spec, "service.flags") or {}}),
            "profiling_attached": bool(workload.get("profiling_attached")), "tuning_completed": accepted,
        },
        "environment": {
            "before": before, "idle_samples": idle_samples, "after": after,
        },
    }


def export_fairness_candidate(run_root: Path, name: str, output: Path | None = None) -> Path:
    target = output or run_root.resolve() / "fairness-candidate.json"
    write_json(target, build_fairness_candidate(run_root, name))
    return target


def projected_identity_mismatches(run_root: Path, manifest: dict[str, Any]) -> list[str]:
    spec = manifest.get("spec", {})
    expected = {
        "campaign_fingerprint": manifest.get("fingerprint"),
        "run_id": get_nested(spec, "identity.task_id"),
        "framework": get_nested(spec, "code.framework"),
    }
    mismatches: list[str] = []
    evidence = read_json(run_root / "run-evidence.json", {})
    if evidence:
        observed = {
            "campaign_fingerprint": evidence.get("campaign_fingerprint"),
            "run_id": evidence.get("run_id"),
            "framework": get_nested(evidence, "identity.framework"),
        }
        mismatches.extend(
            f"run-evidence.{key}:{observed[key]!r}!={value!r}"
            for key, value in expected.items()
            if observed[key] != value
        )
    candidate = read_json(run_root / "fairness-candidate.json", {})
    if candidate and candidate.get("campaign_fingerprint") != expected["campaign_fingerprint"]:
        mismatches.append(
            "fairness-candidate.campaign_fingerprint:"
            f"{candidate.get('campaign_fingerprint')!r}!={expected['campaign_fingerprint']!r}"
        )
    provenance = read_json(run_root / "build" / "binary-provenance.json", {})
    if provenance and provenance.get("framework") is not None and provenance.get("framework") != expected["framework"]:
        mismatches.append(
            f"build.framework:{provenance.get('framework')!r}!={expected['framework']!r}"
        )
    return mismatches


def run_gate_all(run_root: Path, required: list[str] | None = None, fairness_root: Path | None = None, formal: bool = False, generate_evidence: bool = False) -> dict[str, Any]:
    run_root = run_root.resolve()
    manifest = read_json(run_root / "manifest.json", {})
    if not manifest:
        raise ValueError(f"manifest.json is required: {run_root}")
    kind = get_nested(manifest.get("spec", {}), "identity.kind")
    components = required or ["build", "service", "evidence"]
    if required is None and (fairness_root or (run_root / "fairness.json").is_file()):
        components.append("fairness")
    if required is None and kind == "performance_optimization":
        components.append("big-rock")
    components = list(dict.fromkeys(components))
    if generate_evidence:
        export_run_evidence(run_root)
    results: dict[str, Any] = {}
    blockers = []
    identity_mismatches = projected_identity_mismatches(run_root, manifest)
    results["identity"] = {"passed": not identity_mismatches, "mismatches": identity_mismatches}
    if identity_mismatches:
        blockers.append("projected identity does not match manifest")
    if "build" in components:
        verdict = read_json(run_root / "build" / "verdict.json", {})
        passed = verdict.get("status") == "PASS" and verdict.get("binary_ready") is True
        results["build"] = {"passed": passed, "verdict": verdict}
        if not passed:
            blockers.append("build gate did not pass")
    if "service" in components:
        service_id = service_attempt_id(run_root, manifest.get("spec", {}))
        statuses = {name: artifact_status(run_root / "service" / service_id / f"{name}.json") for name in ["ready", "smoke", "cleanup"]}
        passed = all(value == "PASS" for value in statuses.values())
        results["service"] = {"passed": passed, "attempt_id": service_id, "statuses": statuses}
        if not passed:
            blockers.append("service lifecycle gate did not pass")
    if "evidence" in components:
        script = Path(__file__).resolve().parent / "validate_run_evidence.py"
        completed = subprocess.run([sys.executable, str(script), "--run-root", str(run_root)], text=True, capture_output=True, check=False)
        verdict = read_json(run_root / "evidence-verdict.json", {})
        passed = completed.returncode == 0 and verdict.get("status") == "PASS" and (not formal or verdict.get("claim_scope") == "formal")
        results["evidence"] = {"passed": passed, "returncode": completed.returncode, "verdict": verdict}
        if not passed:
            blockers.append("run evidence gate did not pass")
    if "fairness" in components:
        root = (fairness_root or run_root).resolve()
        script = Path(__file__).resolve().parents[1] / "skills" / "xllm-npu-benchmark" / "scripts" / "benchmark_fairness_gate.py"
        completed = subprocess.run([sys.executable, str(script), "--comparison-root", str(root)], text=True, capture_output=True, check=False)
        verdict = read_json(root / "fairness-verdict.json", {})
        passed = completed.returncode == 0 and verdict.get("status") == "PASS"
        results["fairness"] = {"passed": passed, "returncode": completed.returncode, "verdict": verdict}
        if not passed:
            blockers.append("benchmark fairness gate did not pass")
    if "big-rock" in components:
        errors = validate_big_rock_gate(run_root)
        status = read_json(run_root / "analysis" / "big-rock-gate.json", {}).get("status")
        passed = not errors and status in {"PASS", "EXEMPT"}
        results["big-rock"] = {"passed": passed, "status": status, "errors": errors}
        if not passed:
            blockers.append("Big-Rock gate did not pass")
    result = {
        "schema_version": 1, "generated_at_utc": utc_now(), "run_root": str(run_root),
        "campaign_fingerprint": manifest.get("fingerprint"), "required": components,
        "status": "PASS" if not blockers else "BLOCKED", "blockers": blockers, "components": results,
    }
    write_json(run_root / "gate-all-verdict.json", result)
    return result


def validate_run(run_root: Path, conclusion_status: str | None = None) -> list[str]:
    errors = []
    manifest = read_json(run_root / "manifest.json", {})
    if not manifest:
        return ["manifest.json is missing"]
    preflight_data = read_json(run_root / "env" / "preflight.json", {})
    allowed_preflight = {"PASS", "INCONCLUSIVE"} if conclusion_status == "inconclusive" else {"PASS"}
    if preflight_data.get("status") not in allowed_preflight:
        errors.append(f"preflight status must be one of: {', '.join(sorted(allowed_preflight))}")
    try:
        entries = read_attempts(run_root)
    except (ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if not entries:
        errors.append("at least one attempt is required")
    if active_attempts(entries):
        errors.append("active running attempt must be closed")
    if conclusion_status == "pass":
        passed = [entry for entry in entries if entry.get("status") == "pass"]
        if not passed:
            errors.append("pass conclusion requires a passing attempt")
        for entry in passed:
            for artifact in entry.get("artifacts", []):
                if not resolve_run_artifact(run_root, artifact).exists():
                    errors.append(f"attempt artifact is missing: {artifact}")
    spec = manifest.get("spec", {})
    for entry in entries:
        if manifest.get("fingerprint") and (
            entry.get("run_id") != get_nested(spec, "identity.task_id")
            or entry.get("spec_fingerprint") != manifest["fingerprint"]
        ):
            errors.append(f"attempt identity does not match run manifest: {entry.get('entry_id')}")
    if conclusion_status == "pass" and get_nested(spec, "identity.kind") in {"performance_optimization", "benchmark"}:
        if not any(entry.get("status") == "pass" and entry.get("phase") == "benchmark" for entry in entries):
            errors.append("performance conclusion requires a passing benchmark attempt")
    if conclusion_status == "pass" and get_nested(spec, "identity.kind") == "performance_optimization":
        errors.extend(validate_performance_attempts(entries))
    for artifact in spec.get("artifacts", {}).get("required", []):
        try:
            artifact_path = resolve_run_artifact(run_root, artifact)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not artifact_path.exists():
            errors.append(f"required artifact is missing: {artifact}")
    if get_nested(spec, "identity.kind") == "performance_optimization" and conclusion_status == "pass":
        gate_errors = validate_big_rock_gate(run_root)
        gate_status = read_json(run_root / "analysis" / "big-rock-gate.json", {}).get("status")
        if gate_errors or gate_status not in {"PASS", "EXEMPT"}:
            errors.append("Big-Rock Gate must allow implementation before pass conclusion")
    return errors


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(run_root: Path) -> list[str]:
    run_root = run_root.resolve()
    checksum_file = run_root / "checksums.sha256"
    if not checksum_file.is_file():
        return ["checksums.sha256 is missing"]
    errors = []
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
            path = resolve_run_artifact(run_root, relative)
        except ValueError:
            errors.append(f"invalid checksum entry: {line}")
            continue
        if not path.is_file():
            errors.append(f"checksummed artifact is missing: {relative}")
        elif file_sha256(path) != expected:
            errors.append(f"checksum mismatch: {relative}")
    return errors


def run_finalize(
    run_root: Path,
    status: str,
    reviewed_by: str | None = None,
    retention_decision: str | None = None,
    kept_paths: list[str] | None = None,
    deleted_paths: list[str] | None = None,
    workspace: Path | None = None,
) -> None:
    run_root = run_root.resolve()
    if bool(reviewed_by) != bool(retention_decision):
        raise ValueError("reviewed_by and retention_decision must be provided together")
    validation_errors = validate_run(run_root, status)
    if validation_errors:
        raise ValueError("run validation failed: " + "; ".join(validation_errors))
    manifest_path = run_root / "manifest.json"
    manifest = read_json(manifest_path, None)
    if manifest is None:
        raise ValueError(f"missing manifest.json: {run_root}")
    if manifest.get("status") in {"pass", "fail", "inconclusive"}:
        if manifest["status"] != status:
            raise ValueError(f"run is already finalized as {manifest['status']}")
        required_final = [run_root / "env" / "final-state.json", run_root / "checksums.sha256", run_root / "finalization-complete.json"]
        if all(path.is_file() for path in required_final) and not reviewed_by:
            completion = read_json(run_root / "finalization-complete.json", {})
            if (
                completion.get("status") == status
                and completion.get("checksums_sha256") == file_sha256(run_root / "checksums.sha256")
                and not verify_checksums(run_root)
            ):
                return
    manifest["status"] = status
    manifest.setdefault("finalized_at_utc", utc_now())
    if reviewed_by and retention_decision:
        manifest["retention"] = {
            "reviewed_by": reviewed_by, "reviewed_at_utc": utc_now(), "decision": retention_decision,
            "kept_paths": kept_paths or [], "deleted_paths": deleted_paths or [],
        }
    write_json(manifest_path, manifest)
    retention = run_root / "retention-review.md"
    replace_pending_retention = retention.is_file() and reviewed_by and "decision: review-required" in retention.read_text(encoding="utf-8")
    if not retention.exists() or replace_pending_retention:
        decision = retention_decision or "review-required"
        reviewer = reviewed_by or ""
        kept = ", ".join(kept_paths or []) or "review-required"
        deleted = ", ".join(deleted_paths or []) or "none"
        write_text(retention, f"# Retention Review\n\n- finalized_at_utc: {manifest['finalized_at_utc']}\n- conclusion_status: {status}\n- reviewed_by: {reviewer}\n- decision: {decision}\n- kept_paths: {kept}\n- deleted_paths: {deleted}\n")
    entries = read_attempts(run_root)
    write_derived_ledgers(run_root, entries)
    spec_path = Path(manifest.get("spec_path", ""))
    final_code_identity = observed_code_identity(manifest.get("spec", {}), spec_path) if str(spec_path) else manifest.get("code_identity")
    final_state = {
        "finalized_at_utc": manifest["finalized_at_utc"], "status": status,
        "code_identity": final_code_identity, "versions": package_versions(),
        "ledger_tail": entries[-1], "validation_errors": [],
    }
    write_json(run_root / "env" / "final-state.json", final_state)
    save_checkpoint(run_root, {"phase": "finalized", "state": "complete", "active_attempt": "", "last_success": "run-finalize", "completed_artifacts": ["manifest.json", "attempts.jsonl", "env/final-state.json", "checksums.sha256", "finalization-complete.json"], "next_command": "xllm-flow run archive"})
    checksum_paths = [
        run_root / "manifest.json", run_root / "checkpoint.json", run_root / "attempts.jsonl",
        run_root / "env" / "final-state.json", run_root / "retention-review.md",
        run_root / "humanize" / "lineage.jsonl", run_root / "humanize" / "attempt-ledger.md",
        run_root / "humanize" / "optimization-ledger.md", run_root / "humanize" / "source-idea-ledger.md",
    ]
    for directory in [run_root / "env", run_root / "analysis"]:
        if directory.is_dir():
            checksum_paths.extend(path for path in directory.rglob("*") if path.is_file())
    for artifact in manifest.get("spec", {}).get("artifacts", {}).get("required", []):
        checksum_paths.append(resolve_run_artifact(run_root, artifact))
    for entry in entries:
        checksum_paths.extend(resolve_run_artifact(run_root, item) for item in entry.get("artifacts", []))
    checksums = [f"{file_sha256(path)}  {path.relative_to(run_root)}" for path in sorted(set(checksum_paths)) if path.is_file()]
    write_text(run_root / "checksums.sha256", "\n".join(checksums) + "\n")
    checksum_errors = verify_checksums(run_root)
    if checksum_errors:
        raise ValueError("checksum verification failed: " + "; ".join(checksum_errors))
    write_json(run_root / "finalization-complete.json", {
        "status": status, "finalized_at_utc": manifest["finalized_at_utc"],
        "checksums_sha256": file_sha256(run_root / "checksums.sha256"),
    })
    if workspace and (workspace / "scripts" / "update-runs-index.sh").is_file():
        subprocess.run([str(workspace / "scripts" / "update-runs-index.sh"), str(workspace)], check=False)


def registry_archive(registry_path: Path, task_id: str) -> None:
    registry = read_json(registry_path, {"version": 1, "tasks": []})
    for task in registry.get("tasks", []):
        if task.get("task_id") == task_id:
            if task.get("state") == "retired":
                return
            run_root_value = task.get("run_root")
            if not isinstance(run_root_value, str) or not run_root_value:
                raise ValueError("task run_root is required before archive")
            run_root = Path(run_root_value).resolve()
            manifest = read_json(run_root / "manifest.json", {})
            if manifest.get("status") not in {"pass", "fail", "inconclusive"}:
                raise ValueError("task run must be finalized before archive")
            validation_errors = validate_run(run_root, manifest["status"])
            if validation_errors:
                raise ValueError("run validation failed before archive: " + "; ".join(validation_errors))
            if not (run_root / "retention-review.md").is_file():
                raise ValueError("retention-review.md is required before archive")
            retention_data = manifest.get("retention", {})
            if not retention_data.get("reviewed_by") or not retention_data.get("reviewed_at_utc") or not retention_data.get("decision") or not isinstance(retention_data.get("kept_paths"), list) or not isinstance(retention_data.get("deleted_paths"), list):
                raise ValueError("retention decision must be reviewed before archive")
            completion = read_json(run_root / "finalization-complete.json", {})
            if completion.get("status") != manifest.get("status") or verify_checksums(run_root):
                raise ValueError("verified finalization marker and checksums are required before archive")
            if completion.get("checksums_sha256") != file_sha256(run_root / "checksums.sha256"):
                raise ValueError("finalization checksum marker does not match")
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
    registry_bind_parser = registry_sub.add_parser("bind")
    registry_bind_parser.add_argument("--task-id", required=True)
    registry_bind_parser.add_argument("--source-path")
    registry_bind_parser.add_argument("--run-root")
    registry_bind_parser.add_argument("--state", choices=["active", "parked", "retire-review", "source-only"])
    registry_bind_parser.add_argument("--canonical-task-id")
    registry_bind_parser.add_argument("--alias", action="append")
    registry_bind_parser.add_argument("--owner")
    registry_bind_parser.add_argument("--priority", choices=["P0", "P1", "P2", "P3"])
    registry_bind_parser.add_argument("--objective")
    registry_bind_parser.add_argument("--phase")
    workspace_command = commands.add_parser("workspace")
    workspace_sub = workspace_command.add_subparsers(dest="action", required=True)
    workspace_check_parser = workspace_sub.add_parser("check")
    workspace_check_parser.add_argument("--output", type=Path)
    pf = commands.add_parser("preflight")
    pf.add_argument("--spec", type=Path, required=True)
    pf.add_argument("--output", type=Path)
    fingerprint = commands.add_parser("fingerprint")
    fingerprint.add_argument("--spec", type=Path, required=True)
    export_command = commands.add_parser("export")
    export_sub = export_command.add_subparsers(dest="action", required=True)
    export_evidence = export_sub.add_parser("evidence")
    export_evidence.add_argument("--run-root", type=Path, required=True)
    export_evidence.add_argument("--type", choices=["performance", "accuracy", "profiling"])
    export_evidence.add_argument("--level", choices=["smoke", "quick", "full", "formal-pr", "sota-report"])
    export_evidence.add_argument("--attempt-id")
    export_fairness = export_sub.add_parser("fairness-candidate")
    export_fairness.add_argument("--run-root", type=Path, required=True)
    export_fairness.add_argument("--name", required=True)
    export_fairness.add_argument("--output", type=Path)
    run = commands.add_parser("run")
    run_sub = run.add_subparsers(dest="action", required=True)
    create = run_sub.add_parser("create")
    create.add_argument("--spec", type=Path, required=True)
    create.add_argument("--allow-inconclusive", action="store_true")
    validate = run_sub.add_parser("validate")
    validate.add_argument("--run-root", type=Path, required=True)
    validate.add_argument("--status", choices=["pass", "fail", "inconclusive"])
    finalize = run_sub.add_parser("finalize")
    finalize.add_argument("--run-root", type=Path, required=True)
    finalize.add_argument("--status", choices=["pass", "fail", "inconclusive"], required=True)
    finalize.add_argument("--reviewed-by")
    finalize.add_argument("--retention-decision", choices=["keep", "compact", "delete-raw", "keep-all"])
    finalize.add_argument("--kept-path", action="append", default=[])
    finalize.add_argument("--deleted-path", action="append", default=[])
    archive = run_sub.add_parser("archive")
    archive.add_argument("--task-id", required=True)
    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("--run-root", type=Path, required=True)
    checkpoint.add_argument("--phase", choices=["created", "baseline", "benchmark", "profiling", "analysis", "discovery", "planning", "implementation", "validation", "finalized", "blocked"], required=True)
    checkpoint.add_argument("--last-success", default="")
    checkpoint.add_argument("--next-command", default="")
    checkpoint.add_argument("--objective")
    checkpoint.add_argument("--state", choices=["active", "blocked", "complete"], default="active")
    checkpoint.add_argument("--active-attempt", default="")
    checkpoint.add_argument("--current-best")
    checkpoint.add_argument("--remaining-gap", type=float)
    checkpoint.add_argument("--blocker", action="append", default=[])
    checkpoint.add_argument("--artifact", action="append", default=[])
    checkpoint.add_argument("--rejected", action="append", default=[])
    checkpoint.add_argument("--cleanup-scope", action="append", default=[])
    attempt = commands.add_parser("attempt")
    attempt_sub = attempt.add_subparsers(dest="action", required=True)
    attempt_add = attempt_sub.add_parser("add")
    attempt_add.add_argument("--run-root", type=Path, required=True)
    attempt_add.add_argument("--spec", type=Path, required=True)
    attempt_add.add_argument("--attempt-id", required=True)
    attempt_add.add_argument("--entry-id")
    attempt_add.add_argument("--phase", required=True)
    attempt_add.add_argument("--status", choices=["running", "pass", "fail", "rejected"], required=True)
    attempt_add.add_argument("--hypothesis", required=True)
    attempt_add.add_argument("--metrics-json", type=Path)
    attempt_add.add_argument("--artifact", action="append", default=[])
    attempt_add.add_argument("--changed-variable", action="append", default=[])
    attempt_add.add_argument("--repeat-index", type=int, default=0)
    attempt_add.add_argument("--parent-attempt")
    attempt_add.add_argument("--source")
    attempt_add.add_argument("--reason", default="")
    attempt_add.add_argument("--decision", default="")
    attempt_add.add_argument("--next-step", default="")
    attempt_list = attempt_sub.add_parser("list")
    attempt_list.add_argument("--run-root", type=Path, required=True)
    attempt_check = attempt_sub.add_parser("check")
    attempt_check.add_argument("--run-root", type=Path, required=True)
    attempt_check.add_argument("--spec", type=Path, required=True)
    attempt_check.add_argument("--changed-variable", action="append", default=[])
    attempt_check.add_argument("--repeat-index", type=int, default=0)
    gate = commands.add_parser("gate")
    gate_sub = gate.add_subparsers(dest="action", required=True)
    gate_check = gate_sub.add_parser("check")
    gate_check.add_argument("--run-root", type=Path, required=True)
    gate_all = gate_sub.add_parser("all")
    gate_all.add_argument("--run-root", type=Path, required=True)
    gate_all.add_argument("--require", action="append", choices=["build", "service", "evidence", "fairness", "big-rock"])
    gate_all.add_argument("--fairness-root", type=Path)
    gate_all.add_argument("--formal", action="store_true")
    gate_all.add_argument("--generate-evidence", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = args.workspace_root.resolve()
    registry_path = args.registry or workspace / "workspace-tasks.json"
    try:
        if args.command == "registry":
            if args.action == "sync":
                data = registry_sync(workspace, registry_path)
            elif args.action == "bind":
                source_override = str(Path(args.source_path).expanduser().resolve()) if args.source_path else None
                data = registry_bind(
                    registry_path, args.task_id, source_override=source_override,
                    run_root=args.run_root, state=args.state, aliases=args.alias,
                    owner=args.owner, priority=args.priority, objective=args.objective,
                    current_phase=args.phase, canonical_task_id=args.canonical_task_id,
                )
            else:
                data = read_json(registry_path, {"tasks": []})
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
            print(experiment_fingerprint(load_spec(args.spec), args.spec))
        elif args.command == "export" and args.action == "evidence":
            print(export_run_evidence(args.run_root, evidence_type=args.type, level=args.level, attempt_id=args.attempt_id))
        elif args.command == "export" and args.action == "fairness-candidate":
            print(export_fairness_candidate(args.run_root, args.name, args.output))
        elif args.command == "checkpoint":
            if args.phase == "implementation":
                gate_errors = validate_big_rock_gate(args.run_root)
                gate_status = read_json(args.run_root / "analysis" / "big-rock-gate.json", {}).get("status")
                if gate_errors or gate_status not in {"PASS", "EXEMPT"}:
                    raise ValueError("Big-Rock Gate blocks implementation: " + "; ".join(gate_errors or [f"status is {gate_status}"]))
            save_checkpoint(args.run_root, {
                "phase": args.phase, "state": args.state, "objective": args.objective,
                "active_attempt": args.active_attempt, "current_best": args.current_best,
                "remaining_gap": args.remaining_gap, "blockers": args.blocker,
                "completed_artifacts": args.artifact, "rejected_candidates": args.rejected,
                "cleanup_scope": args.cleanup_scope, "last_success": args.last_success,
                "next_command": args.next_command,
            })
        elif args.command == "attempt" and args.action == "add":
            spec = load_spec(args.spec)
            repetitions = int(get_nested(spec, "evaluation.performance.repetitions") or 1)
            if args.repeat_index < 0 or args.repeat_index >= repetitions:
                raise ValueError(f"repeat_index must be between 0 and {repetitions - 1}")
            metrics = read_json(args.metrics_json, {}) if args.metrics_json else {}
            code_identity = observed_code_identity(spec, args.spec)
            entry = append_attempt(args.run_root, {
                "entry_id": args.entry_id or f"{args.attempt_id}-{args.status}",
                "run_id": spec["identity"]["task_id"], "attempt_id": args.attempt_id,
                "spec_fingerprint": experiment_fingerprint(spec, args.spec),
                "phase": args.phase, "status": args.status,
                "fingerprint": attempt_fingerprint(spec, args.spec, args.changed_variable, args.repeat_index),
                "repeat_index": args.repeat_index,
                "hypothesis": args.hypothesis, "changed_variables": args.changed_variable,
                "parent_attempt": args.parent_attempt, "source": args.source,
                "code_identity": code_identity,
                "metrics": metrics, "artifacts": args.artifact, "reason": args.reason,
                "decision": args.decision, "next_step": args.next_step,
            })
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        elif args.command == "attempt" and args.action == "list":
            print(json.dumps(read_attempts(args.run_root), ensure_ascii=False, indent=2))
        elif args.command == "attempt" and args.action == "check":
            spec = load_spec(args.spec)
            duplicate = check_duplicate_attempt(args.run_root, attempt_fingerprint(spec, args.spec, args.changed_variable, args.repeat_index))
            print(json.dumps({"duplicate": bool(duplicate), "entry": duplicate}, ensure_ascii=False, indent=2))
            return 1 if duplicate else 0
        elif args.command == "gate" and args.action == "check":
            errors = validate_big_rock_gate(args.run_root)
            gate_status = read_json(args.run_root / "analysis" / "big-rock-gate.json", {}).get("status")
            valid = not errors
            print(json.dumps({"valid": valid, "gate_status": gate_status, "implementation_allowed": valid and gate_status in {"PASS", "EXEMPT"}, "errors": errors}, ensure_ascii=False, indent=2))
            return 2 if errors else 0 if gate_status in {"PASS", "EXEMPT"} else 1
        elif args.command == "gate" and args.action == "all":
            result = run_gate_all(args.run_root, args.require, args.fairness_root, args.formal, args.generate_evidence)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "PASS" else 2
        elif args.command == "run" and args.action == "create":
            print(run_create(args.spec, registry_path, args.allow_inconclusive))
        elif args.command == "run" and args.action == "validate":
            errors = validate_run(args.run_root, args.status)
            print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
            return 2 if errors else 0
        elif args.command == "run" and args.action == "finalize":
            run_finalize(args.run_root, args.status, args.reviewed_by, args.retention_decision, args.kept_path, args.deleted_path, workspace)
        elif args.command == "run" and args.action == "archive":
            registry_archive(registry_path, args.task_id)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
