#!/usr/bin/env python3
"""Validate normalized NPU benchmark fairness evidence without implicit thresholds."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = 1
COMPARE_FIELDS = (
    "identity.hardware_fingerprint",
    "identity.device_backend",
    "identity.physical_device_ids",
    "identity.visible_device_order",
    "identity.model_fingerprint",
    "identity.tokenizer_fingerprint",
    "identity.dtype",
    "identity.quantization",
    "identity.workload_fingerprint",
    "identity.sampling_fingerprint",
    "identity.sla_fingerprint",
    "identity.optimization_policy_fingerprint",
)
POLICY_FIELDS = (
    "max_preexisting_hbm_pct",
    "max_idle_aicore_pct",
    "max_host_load1_delta_pct",
    "min_idle_samples",
)


class GateError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"missing JSON: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get(document: Any, dotted: str) -> Any:
    value = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def validate_device_snapshot(
    candidate: str,
    label: str,
    snapshot: Any,
    run_root: Path,
    expected_ids: list[Any],
    expected_backend: str,
    blockers: list[str],
    findings: list[str],
) -> None:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("devices"), list):
        blockers.append(f"{candidate}:{label}:missing_devices")
        return
    if snapshot.get("backend") != expected_backend:
        blockers.append(f"{candidate}:{label}:backend_mismatch")
    parser_version = snapshot.get("parser_version")
    if isinstance(parser_version, bool) or not isinstance(parser_version, int) or parser_version < 1:
        blockers.append(f"{candidate}:{label}:invalid_parser_version")
    if not isinstance(snapshot.get("collection_errors"), list):
        blockers.append(f"{candidate}:{label}:missing_collection_errors")
    elif snapshot.get("collection_errors"):
        blockers.append(f"{candidate}:{label}:snapshot_collection_errors")
    if missing(snapshot.get("raw_dir")):
        blockers.append(f"{candidate}:{label}:missing_raw_dir")
    elif not resolve(run_root, snapshot["raw_dir"]).is_dir():
        blockers.append(f"{candidate}:{label}:missing_raw_artifacts")
    devices = snapshot["devices"]
    observed_ids = [device.get("physical_id") for device in devices if isinstance(device, dict)]
    if observed_ids != expected_ids:
        findings.append(f"{candidate}:{label}:device_order_mismatch")
    for device in devices:
        if not isinstance(device, dict):
            blockers.append(f"{candidate}:{label}:invalid_device")
            continue
        device_id = device.get("physical_id")
        if str(device.get("health", "")).upper() != "OK":
            findings.append(f"{candidate}:{label}:device_{device_id}_health_not_ok")
        processes = device.get("processes")
        if not isinstance(processes, list):
            blockers.append(f"{candidate}:{label}:device_{device_id}_missing_processes")
            continue
        for process in processes:
            if not isinstance(process, dict):
                blockers.append(f"{candidate}:{label}:device_{device_id}_invalid_process")
            elif process.get("host_visible") is not True:
                findings.append(f"{candidate}:{label}:device_{device_id}_stale_or_unknown_pid")
            elif process.get("owned_by_attempt") is not True:
                findings.append(f"{candidate}:{label}:device_{device_id}_foreign_process")
            elif label == "before":
                findings.append(f"{candidate}:{label}:device_{device_id}_preexisting_process")


def validate_candidate(
    root: Path,
    candidate: Any,
    policy: dict[str, Any],
    blockers: list[str],
    findings: list[str],
) -> None:
    name = str(candidate.get("name", "unnamed")) if isinstance(candidate, dict) else "unnamed"
    if not isinstance(candidate, dict):
        blockers.append(f"{name}:invalid_candidate")
        return
    blocker_count = len(blockers)
    for dotted in ("campaign_fingerprint", *COMPARE_FIELDS, "run_root", "evidence_verdict", "environment.before", "environment.idle_samples", "environment.after"):
        if missing(get(candidate, dotted)):
            blockers.append(f"{name}:missing:{dotted}")
    if len(blockers) > blocker_count:
        return
    run_root = resolve(root, candidate["run_root"])
    evidence_path = resolve(run_root, candidate["evidence_verdict"])
    if run_root != evidence_path and run_root not in evidence_path.parents:
        blockers.append(f"{name}:evidence_verdict_outside_run_root")
        return
    evidence = load_json(evidence_path)
    evidence_run_root = evidence.get("run_root")
    if not isinstance(evidence_run_root, str) or Path(evidence_run_root).resolve() != run_root:
        blockers.append(f"{name}:evidence_verdict_run_root_mismatch")
    if evidence.get("status") != "PASS" or evidence.get("claim_scope") != "formal":
        findings.append(f"{name}:run_evidence_not_formal_pass")
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file():
        blockers.append(f"{name}:missing_manifest")
    else:
        manifest = load_json(manifest_path)
        if manifest.get("fingerprint") != candidate.get("campaign_fingerprint"):
            blockers.append(f"{name}:campaign_fingerprint_mismatch")
    if get(candidate, "identity.profiling_attached") is not False:
        findings.append(f"{name}:profiling_attached")
    if get(candidate, "identity.tuning_completed") is not True:
        findings.append(f"{name}:tuning_not_completed")

    expected_ids = get(candidate, "identity.physical_device_ids")
    visible_order = get(candidate, "identity.visible_device_order")
    expected_backend = get(candidate, "identity.device_backend")
    if not isinstance(expected_ids, list) or not isinstance(visible_order, list):
        blockers.append(f"{name}:invalid_device_identity")
        return
    if len(expected_ids) != len(visible_order):
        findings.append(f"{name}:physical_and_visible_device_count_mismatch")
    before = get(candidate, "environment.before")
    after = get(candidate, "environment.after")
    idle_samples = get(candidate, "environment.idle_samples")
    validate_device_snapshot(name, "before", before, run_root, expected_ids, expected_backend, blockers, findings)
    validate_device_snapshot(name, "after", after, run_root, expected_ids, expected_backend, blockers, findings)
    if not isinstance(idle_samples, list) or len(idle_samples) < policy["min_idle_samples"]:
        blockers.append(f"{name}:insufficient_idle_samples")
        idle_samples = []
    for index, sample in enumerate(idle_samples):
        validate_device_snapshot(name, f"idle_{index}", sample, run_root, expected_ids, expected_backend, blockers, findings)
        for device in sample.get("devices", []) if isinstance(sample, dict) else []:
            usage = device.get("aicore_usage_pct") if isinstance(device, dict) else None
            if not isinstance(usage, (int, float)):
                blockers.append(f"{name}:idle_{index}:missing_aicore_usage")
            elif usage > policy["max_idle_aicore_pct"]:
                findings.append(f"{name}:idle_{index}:aicore_above_policy")
    if isinstance(before, dict):
        for device in before.get("devices", []):
            usage = device.get("hbm_usage_pct") if isinstance(device, dict) else None
            if not isinstance(usage, (int, float)):
                blockers.append(f"{name}:before:missing_hbm_usage")
            elif usage > policy["max_preexisting_hbm_pct"]:
                findings.append(f"{name}:before:hbm_above_policy")

    before_host = before.get("host", {}) if isinstance(before, dict) else {}
    after_host = after.get("host", {}) if isinstance(after, dict) else {}
    for label, host in (("before", before_host), ("after", after_host)):
        if not isinstance(host.get("load1"), (int, float)) or not isinstance(host.get("swap_used_bytes"), int):
            blockers.append(f"{name}:{label}:missing_host_load_or_swap")
        if host.get("profiling_active") is not False:
            findings.append(f"{name}:{label}:profiling_process_active")
        if host.get("build_active") is not False:
            findings.append(f"{name}:{label}:build_process_active")
    before_load = before_host.get("load1")
    after_load = after_host.get("load1")
    if isinstance(before_load, (int, float)) and isinstance(after_load, (int, float)):
        denominator = max(abs(before_load), 1.0)
        delta_pct = abs(after_load - before_load) / denominator * 100
        if delta_pct > policy["max_host_load1_delta_pct"]:
            findings.append(f"{name}:host_load_delta_above_policy")
    if before_host.get("swap_used_bytes") != after_host.get("swap_used_bytes"):
        findings.append(f"{name}:swap_changed_during_run")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison-root", type=Path, required=True)
    parser.add_argument("--input", default="fairness.json")
    parser.add_argument("--output", default="fairness-verdict.json")
    args = parser.parse_args()
    root = args.comparison_root.resolve()
    blockers: list[str] = []
    findings: list[str] = []
    mismatches: list[str] = []
    document: dict[str, Any] = {}
    try:
        document = load_json(resolve(root, args.input))
        if document.get("schema_version") != SCHEMA_VERSION:
            raise GateError(f"unsupported schema_version: {document.get('schema_version')!r}")
        if missing(document.get("comparison_id")):
            blockers.append("missing_comparison_id")
        policy = document.get("policy")
        if not isinstance(policy, dict):
            raise GateError("missing policy")
        for field in POLICY_FIELDS[:-1]:
            value = policy.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                blockers.append(f"missing_or_invalid_policy:{field}")
        for field in ("max_preexisting_hbm_pct", "max_idle_aicore_pct"):
            if isinstance(policy.get(field), (int, float)) and policy[field] > 100:
                blockers.append(f"missing_or_invalid_policy:{field}")
        idle_count = policy.get("min_idle_samples")
        if isinstance(idle_count, bool) or not isinstance(idle_count, int) or idle_count < 1:
            blockers.append("missing_or_invalid_policy:min_idle_samples")
        candidates = document.get("candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            blockers.append("comparison_requires_at_least_two_candidates")
            candidates = []
        names = [candidate.get("name") for candidate in candidates if isinstance(candidate, dict)]
        if any(missing(name) for name in names) or len(names) != len(set(names)):
            blockers.append("candidate_names_must_be_unique_and_nonempty")
        if not blockers:
            for candidate in candidates:
                validate_candidate(root, candidate, policy, blockers, findings)
            baseline = candidates[0]
            for candidate in candidates[1:]:
                for dotted in COMPARE_FIELDS:
                    if get(candidate, dotted) != get(baseline, dotted):
                        mismatches.append(f"{candidate.get('name', 'unnamed')}:{dotted}")
    except (GateError, OSError, ValueError, TypeError) as exc:
        blockers.append(str(exc))

    if blockers:
        status = "BLOCKED"
    elif findings or mismatches:
        status = "INCONCLUSIVE"
    else:
        status = "PASS"
    verdict = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "comparison_id": document.get("comparison_id"),
        "status": status,
        "claim_scope": "formal" if status == "PASS" else "none",
        "blockers": sorted(set(blockers)),
        "contamination_findings": sorted(set(findings)),
        "candidate_mismatches": sorted(set(mismatches)),
        "policy": document.get("policy"),
    }
    write_json(resolve(root, args.output), verdict)
    print(json.dumps(verdict, sort_keys=True))
    return {"PASS": 0, "INCONCLUSIVE": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    sys.exit(main())
