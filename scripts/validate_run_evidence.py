#!/usr/bin/env python3
"""Validate machine-readable NPU run evidence and write a claim verdict."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable


SCHEMA_VERSION = 1
EVIDENCE_TYPES = ("performance", "accuracy", "profiling")
CLAIM_SCOPE_BY_LEVEL = {
    "smoke": "smoke",
    "quick": "quick",
    "full": "formal",
    "formal-pr": "formal",
    "sota-report": "formal",
}
STATUSES = {"PASS", "INCONCLUSIVE", "BLOCKED"}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
HEX_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")

COMMON_REQUIRED = (
    "schema_version",
    "run_id",
    "evidence_type",
    "level",
    "identity.framework",
    "identity.repo_path",
    "identity.commit",
    "identity.dirty_diff_sha256",
    "identity.binary_path",
    "identity.binary_sha256",
    "identity.build_verdict",
    "identity.binary_provenance",
    "environment.physical_device_ids",
    "environment.visible_device_order",
    "environment.hardware",
    "environment.software_stack",
    "model.name",
    "model.path",
    "model.tokenizer_path",
    "model.dtype",
    "service.attempt_id",
    "service.api_url",
    "service.startup_command",
    "service.pid_file",
    "service.logs",
    "service.ready.status",
    "service.ready.artifact",
    "service.smoke.status",
    "service.smoke.artifact",
    "service.cleanup.status",
    "service.cleanup.artifact",
    "workload.request_fingerprint",
    "workload.sampling",
    "artifacts",
    "artifacts.environment.before",
    "artifacts.environment.after",
)

TYPE_REQUIRED = {
    "performance": (
        "workload.parallel",
        "workload.number",
        "workload.warmup_num",
        "workload.profiling_attached",
        "artifacts.performance.raw",
        "artifacts.performance.metrics",
    ),
    "accuracy": (
        "workload.prompt_template_sha256",
        "workload.dataset_fingerprint",
        "workload.answer_extractor_version",
        "artifacts.accuracy.request_config",
        "artifacts.accuracy.dataset_config",
        "artifacts.accuracy.raw_predictions",
        "artifacts.accuracy.failed_cases",
        "artifacts.accuracy.score",
    ),
    "profiling": (
        "profiling.attached_parent_pid",
        "profiling.warmup_before_capture",
        "profiling.workload_status",
        "artifacts.profiling.prof",
        "artifacts.profiling.export",
        "artifacts.profiling.capture_log",
        "artifacts.profiling.workload_log",
        "artifacts.profiling.analysis",
    ),
}


class EvidenceError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EvidenceError(f"missing JSON artifact: {path}") from error
    except json.JSONDecodeError as error:
        raise EvidenceError(f"invalid JSON artifact {path}: {error}") from error


def get_path(document: Any, dotted: str) -> Any:
    value = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def resolve_artifact(run_root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (run_root / path).resolve()


def iter_string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if value.strip():
            yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_string_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_string_values(item)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_path(path: Path, hash_max_bytes: int) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return record
    stat = path.stat()
    record.update(
        {
            "kind": "directory" if path.is_dir() else "file",
            "mtime_ns": stat.st_mtime_ns,
        }
    )
    if path.is_file():
        record["size_bytes"] = stat.st_size
        record["sha256"] = sha256_file(path) if stat.st_size <= hash_max_bytes else None
        record["hash_skipped"] = stat.st_size > hash_max_bytes
        return record
    files = [item for item in path.rglob("*") if item.is_file()]
    record["file_count"] = len(files)
    record["size_bytes"] = sum(item.stat().st_size for item in files)
    record["latest_mtime_ns"] = max(
        (item.stat().st_mtime_ns for item in files), default=stat.st_mtime_ns
    )
    return record


def collect_declared_paths(run_root: Path, document: dict[str, Any]) -> list[Path]:
    values: list[str] = []
    values.extend(iter_string_values(document.get("artifacts", {})))
    for dotted in (
        "identity.build_verdict",
        "identity.binary_provenance",
        "service.startup_command",
        "service.pid_file",
        "service.logs",
        "service.ready.artifact",
        "service.smoke.artifact",
        "service.cleanup.artifact",
    ):
        values.extend(iter_string_values(get_path(document, dotted)))
    paths = {resolve_artifact(run_root, value) for value in values}
    return sorted(paths, key=str)


def compare_optional_field(
    source: dict[str, Any],
    source_key: str,
    expected: Any,
    label: str,
    mismatches: list[str],
) -> None:
    actual = get_path(source, source_key)
    if actual is not None and actual != expected:
        mismatches.append(f"{label}:{actual!r}!={expected!r}")


def validate_build_identity(
    run_root: Path,
    document: dict[str, Any],
    blockers: list[str],
    mismatches: list[str],
) -> None:
    verdict_path = resolve_artifact(run_root, get_path(document, "identity.build_verdict"))
    provenance_path = resolve_artifact(
        run_root, get_path(document, "identity.binary_provenance")
    )
    try:
        verdict = load_json(verdict_path)
        provenance = load_json(provenance_path)
    except EvidenceError as error:
        mismatches.append(str(error))
        return
    if verdict.get("status") != "PASS" or verdict.get("binary_ready") is not True:
        blockers.append(f"build_gate_not_passed:{verdict.get('status')}")
    expected_commit = get_path(document, "identity.commit")
    expected_binary = get_path(document, "identity.binary_path")
    expected_sha = get_path(document, "identity.binary_sha256")
    compare_optional_field(provenance, "commit", expected_commit, "build_commit", mismatches)
    compare_optional_field(
        provenance, "binary.path", expected_binary, "binary_path", mismatches
    )
    compare_optional_field(
        provenance, "binary.sha256", expected_sha, "binary_sha256", mismatches
    )


def validate_service(
    run_root: Path,
    document: dict[str, Any],
    blockers: list[str],
    mismatches: list[str],
) -> None:
    attempt_id = str(get_path(document, "service.attempt_id") or "")
    for gate in ("ready", "smoke"):
        status = str(get_path(document, f"service.{gate}.status") or "").upper()
        if status != "PASS":
            blockers.append(f"service_{gate}_not_passed:{status or 'missing'}")
        artifact_value = get_path(document, f"service.{gate}.artifact")
        if isinstance(artifact_value, str):
            try:
                artifact = load_json(resolve_artifact(run_root, artifact_value))
                if str(artifact.get("status", "")).upper() != "PASS":
                    blockers.append(f"service_{gate}_artifact_not_passed")
                compare_optional_field(
                    artifact,
                    "attempt_id",
                    attempt_id,
                    f"service_{gate}_attempt_id",
                    mismatches,
                )
            except EvidenceError as error:
                mismatches.append(str(error))
    cleanup = str(get_path(document, "service.cleanup.status") or "").upper()
    if cleanup != "PASS":
        mismatches.append(f"service_cleanup_not_passed:{cleanup or 'missing'}")
    cleanup_value = get_path(document, "service.cleanup.artifact")
    if isinstance(cleanup_value, str):
        try:
            artifact = load_json(resolve_artifact(run_root, cleanup_value))
            if str(artifact.get("status", "")).upper() != "PASS":
                mismatches.append("service_cleanup_artifact_not_passed")
            if str(artifact.get("npu_quiescence", "")).upper() != "PASS":
                mismatches.append("service_cleanup_npu_quiescence_not_passed")
            compare_optional_field(
                artifact,
                "attempt_id",
                attempt_id,
                "service_cleanup_attempt_id",
                mismatches,
            )
        except EvidenceError as error:
            mismatches.append(str(error))
    service_paths: list[str] = []
    for dotted in (
        "service.startup_command",
        "service.pid_file",
        "service.logs",
        "service.ready.artifact",
        "service.smoke.artifact",
        "service.cleanup.artifact",
    ):
        service_paths.extend(iter_string_values(get_path(document, dotted)))
    if attempt_id and not all(attempt_id in path for path in service_paths):
        mismatches.append("service_artifacts_not_attempt_scoped")


def validate_performance(
    run_root: Path, document: dict[str, Any], mismatches: list[str]
) -> None:
    warmup = get_path(document, "workload.warmup_num")
    if not isinstance(warmup, int) or warmup < 1:
        mismatches.append("formal_performance_requires_request_warmup")
    if get_path(document, "workload.profiling_attached") is not False:
        mismatches.append("performance_profiling_state_must_be_explicitly_false")
    metrics_value = get_path(document, "artifacts.performance.metrics")
    if not isinstance(metrics_value, str):
        return
    try:
        metrics = load_json(resolve_artifact(run_root, metrics_value))
    except EvidenceError as error:
        mismatches.append(str(error))
        return
    compare_optional_field(metrics, "run_id", document.get("run_id"), "metrics_run_id", mismatches)
    compare_optional_field(
        metrics, "commit", get_path(document, "identity.commit"), "metrics_commit", mismatches
    )
    compare_optional_field(
        metrics, "model", get_path(document, "model.name"), "metrics_model", mismatches
    )
    success = metrics.get("success")
    total = metrics.get("total")
    if not isinstance(success, int) or not isinstance(total, int) or total < 1:
        mismatches.append("performance_request_counts_missing")
    elif success != total:
        mismatches.append(f"performance_requests_failed:{success}/{total}")


def validate_accuracy(run_root: Path, document: dict[str, Any], mismatches: list[str]) -> None:
    for dotted in ("workload.prompt_template_sha256", "workload.dataset_fingerprint"):
        value = get_path(document, dotted)
        if not isinstance(value, str) or not HEX_SHA256.fullmatch(value):
            mismatches.append(f"invalid_sha256:{dotted}")
    score_value = get_path(document, "artifacts.accuracy.score")
    if not isinstance(score_value, str):
        return
    try:
        score = load_json(resolve_artifact(run_root, score_value))
    except EvidenceError as error:
        mismatches.append(str(error))
        return
    if str(score.get("status", "")).lower() != "pass":
        mismatches.append(f"accuracy_score_not_passed:{score.get('status')}")
    compare_optional_field(score, "run_id", document.get("run_id"), "score_run_id", mismatches)


def validate_profiling(document: dict[str, Any], mismatches: list[str]) -> None:
    parent_pid = get_path(document, "profiling.attached_parent_pid")
    if not isinstance(parent_pid, int) or parent_pid < 1:
        mismatches.append("profiling_parent_pid_missing")
    if get_path(document, "profiling.warmup_before_capture") is not True:
        mismatches.append("profiling_warmup_not_proven_before_capture")
    if str(get_path(document, "profiling.workload_status") or "").upper() != "PASS":
        mismatches.append("profiling_workload_not_passed")


def compare_artifact_index(
    run_root: Path,
    index: dict[str, Any],
    mismatches: list[str],
) -> Path:
    canonical = run_root / "artifact-index.json"
    if not canonical.exists():
        write_json(canonical, index)
        return canonical
    try:
        previous = load_json(canonical)
    except EvidenceError as error:
        mismatches.append(str(error))
        current = run_root / "artifact-index.current.json"
        write_json(current, index)
        return current
    if previous.get("artifacts") != index.get("artifacts"):
        mismatches.append("declared_artifacts_changed_after_index")
        current = run_root / "artifact-index.current.json"
        write_json(current, index)
        return current
    return canonical


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hash-max-bytes", type=int, default=64 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_root = args.run_root.resolve()
    evidence_path = (
        args.evidence.resolve() if args.evidence else run_root / "run-evidence.json"
    )
    output_path = args.output.resolve() if args.output else run_root / "evidence-verdict.json"
    missing: list[str] = []
    blockers: list[str] = []
    mismatches: list[str] = []
    warnings: list[str] = []
    evidence_type: str | None = None
    artifact_index_path: Path | None = None

    try:
        if args.hash_max_bytes < 0:
            raise EvidenceError("--hash-max-bytes must be non-negative")
        document = load_json(evidence_path)
        if not isinstance(document, dict):
            raise EvidenceError("run-evidence.json must contain a JSON object")
        evidence_type = document.get("evidence_type")
        if evidence_type not in EVIDENCE_TYPES:
            raise EvidenceError(f"unsupported evidence_type: {evidence_type!r}")
        level = document.get("level")
        if level not in CLAIM_SCOPE_BY_LEVEL:
            raise EvidenceError(f"unsupported level: {level!r}")
        required = (*COMMON_REQUIRED, *TYPE_REQUIRED[evidence_type])
        missing.extend(dotted for dotted in required if is_missing(get_path(document, dotted)))
        if document.get("schema_version") != SCHEMA_VERSION:
            blockers.append(f"unsupported_schema_version:{document.get('schema_version')}")
        commit = get_path(document, "identity.commit")
        binary_sha = get_path(document, "identity.binary_sha256")
        request_fingerprint = get_path(document, "workload.request_fingerprint")
        if isinstance(commit, str) and not HEX_COMMIT.fullmatch(commit):
            mismatches.append("invalid_commit_identity")
        for label, value in (
            ("identity.binary_sha256", binary_sha),
            ("workload.request_fingerprint", request_fingerprint),
        ):
            if isinstance(value, str) and not HEX_SHA256.fullmatch(value):
                mismatches.append(f"invalid_sha256:{label}")
        physical = get_path(document, "environment.physical_device_ids")
        visible = get_path(document, "environment.visible_device_order")
        if isinstance(physical, list) and isinstance(visible, list) and len(physical) != len(visible):
            mismatches.append("physical_and_visible_device_count_mismatch")

        if missing:
            warnings.append("required evidence fields are missing")
        if isinstance(get_path(document, "identity.build_verdict"), str) and isinstance(
            get_path(document, "identity.binary_provenance"), str
        ):
            validate_build_identity(run_root, document, blockers, mismatches)
        validate_service(run_root, document, blockers, mismatches)
        if evidence_type == "performance":
            validate_performance(run_root, document, mismatches)
        elif evidence_type == "accuracy":
            validate_accuracy(run_root, document, mismatches)
        else:
            validate_profiling(document, mismatches)

        declared_paths = collect_declared_paths(run_root, document)
        artifact_records = [index_path(path, args.hash_max_bytes) for path in declared_paths]
        missing.extend(
            f"artifact:{record['path']}" for record in artifact_records if not record["exists"]
        )
        index = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "run_id": document.get("run_id"),
            "artifacts": artifact_records,
        }
        artifact_index_path = compare_artifact_index(run_root, index, mismatches)
    except (EvidenceError, OSError, ValueError) as error:
        blockers.append(str(error))

    if blockers:
        status = "BLOCKED"
        claim_scope = "none"
    elif missing or mismatches:
        status = "INCONCLUSIVE"
        claim_scope = "smoke_debug"
    else:
        status = "PASS"
        claim_scope = CLAIM_SCOPE_BY_LEVEL.get(document.get("level"), "none")
    assert status in STATUSES
    verdict = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "run_root": str(run_root),
        "evidence": str(evidence_path),
        "evidence_type": evidence_type,
        "status": status,
        "claim_scope": claim_scope,
        "missing": sorted(set(missing)),
        "blockers": sorted(set(blockers)),
        "mismatches": sorted(set(mismatches)),
        "warnings": sorted(set(warnings)),
        "artifact_index": str(artifact_index_path) if artifact_index_path else None,
    }
    write_json(output_path, verdict)
    print(json.dumps(verdict, ensure_ascii=False))
    return {"PASS": 0, "INCONCLUSIVE": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
