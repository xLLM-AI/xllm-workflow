#!/usr/bin/env python3
"""Validate the fail-closed contract of a TileLang/PTO work package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"待实现", "通过", "淘汰"}
ALLOWED_STEPS = {"SELECT", "IMPLEMENT", "VERIFY", "REVIEW", "DECIDE", "CLOSED"}
CURRENT_SCHEMA_VERSION = 2
FINAL_EVIDENCE_SCHEMA_VERSION = 1
PLAN_ID_PATTERN = re.compile(r"plan-[A-Za-z0-9][A-Za-z0-9._-]*")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

DASHBOARD_REQUIRED_LABELS = (
    "- 当前 Plan：",
    "- 当前 step：",
    "- 本轮唯一主要变量：",
    "- 最后 Gate 与 verdict：",
    "- 下一动作：",
    "- 回退或派生目标：",
)
FINAL_DASHBOARD_LABELS = (
    "- Baseline：",
    "- round0：",
    "- 当前通过 baseline：",
    "- 当前 round：",
    *DASHBOARD_REQUIRED_LABELS,
)
FINAL_CHECKLIST_ITEMS = (
    "无待实现 Plan",
    "最终代码已与 round0 同口径复采",
    "通过 Plan 均在最终路径",
    "淘汰 Plan 已回退",
    "可叠加组合已实测",
    "kernel / model / precision 分开报告",
    "rollback smoke 通过",
)
FINAL_REPORT_LABELS = (
    "- 通过 Plan：",
    "- 淘汰 Plan：",
    "- 公平 baseline：",
    "- 按 Shape 延迟 / 加速比：",
    "- Graph 路由 / 调用次数：",
    "- Golden / 连续 state：",
    "- 任务精度：",
    "- rollback 与 smoke：",
    "- final evidence：",
    "- final Profile：",
    "- precision：",
)
FINAL_CHECK_PREFIXES = {
    "performance_ab": Path("perf/final"),
    "precision": Path("precision"),
    "route": Path("model/graph-route"),
    "rollback": Path("model/rollback"),
}
REQUIRED_FILES = (
    "baseline.md",
    "plan-dashboard.md",
    "progress.md",
    "manifest.json",
    "analysis/memory.md",
    "analysis/sync.md",
    "analysis/compute.md",
    "analysis/task-map.md",
    "analysis/precision.md",
    "analysis/arbitration.md",
)
REQUIRED_DIRS = (
    "plans",
    "source-audit/tilelang",
    "source-audit/pto",
    "precision/golden",
    "precision/atk",
    "perf/round0",
    "model/graph-route",
    "model/tpot",
)
V2_REQUIRED_DIRS = ("perf/final", "model/rollback")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a TileLang/PTO work package.")
    parser.add_argument("run_root", type=Path)
    parser.add_argument(
        "--final",
        action="store_true",
        help="Require decided Plans and verified final evidence.",
    )
    return parser.parse_args()


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def section(markdown: str, heading: str) -> list[str] | None:
    lines = markdown.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == heading) + 1
    except StopIteration:
        return None
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return lines[start:end]


def labeled_value(markdown: str, label: str) -> str | None:
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith(label):
            return line[len(label):].strip()
    return None


def meaningful(value: str | None) -> bool:
    if value is None or not value.strip() or re.search(r"<[^>]+>", value):
        return False
    return value.strip().lower() not in {
        "-", "todo", "tbd", "pending", "n/a", "na", "待补充", "待完成", "未填写"
    }


def parse_plans_table(markdown: str) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    body = section(markdown, "## Plans")
    if body is None:
        return [], ["missing Dashboard section: ## Plans"]
    table = [line.strip() for line in body if line.strip().startswith("|")]
    if len(table) < 2:
        return [], ["missing Plans table header or separator"]

    header = table_cells(table[0])
    required = {"plan_id", "状态", "round", "文件"}
    missing = required - set(header)
    if missing:
        errors.append(f"Plans table missing columns: {', '.join(sorted(missing))}")
    if len(header) != len(set(header)):
        errors.append("Plans table has duplicate columns")
    separator = table_cells(table[1])
    if len(separator) != len(header) or not separator_row(separator):
        errors.append("Plans table has an invalid separator row")

    rows: list[dict[str, str]] = []
    for row_number, raw_line in enumerate(table[2:], start=1):
        cells = table_cells(raw_line)
        if separator_row(cells):
            errors.append(f"Plans row {row_number} is an unexpected separator")
            continue
        if len(cells) != len(header):
            errors.append(
                f"Plans row {row_number} has {len(cells)} cells; expected {len(header)}"
            )
            continue
        rows.append(dict(zip(header, cells)))
    return rows, errors


def safe_relative_path(root: Path, value: str) -> Path | None:
    relative = Path(value.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def validate_plan_rows(
    root: Path,
    rows: list[dict[str, str]],
    enforce_round_loop: bool,
    final: bool,
    errors: list[str],
) -> None:
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        plan_id = row.get("plan_id", "")
        status = row.get("状态", "")
        round_value = row.get("round", "")
        file_value = row.get("文件", "")

        if not PLAN_ID_PATTERN.fullmatch(plan_id):
            errors.append(f"invalid plan_id in Plans row {index}: {plan_id or '<empty>'}")
        elif plan_id in seen:
            errors.append(f"duplicate plan_id in Plans table: {plan_id}")
        else:
            seen.add(plan_id)
        if status not in ALLOWED_STATUSES:
            errors.append(f"invalid Plan status for {plan_id or f'row {index}'}: {status or '<empty>'}")
        if not round_value.isdigit() or int(round_value) < 1:
            errors.append(f"invalid round for {plan_id or f'row {index}'}: {round_value or '<empty>'}")

        expected_file = f"plans/{plan_id}.md" if PLAN_ID_PATTERN.fullmatch(plan_id) else None
        if expected_file is None or file_value.replace("\\", "/") != expected_file:
            errors.append(
                f"Plan file must be plans/<plan_id>.md for {plan_id or f'row {index}'}"
            )
            continue
        plan_path = safe_relative_path(root, file_value)
        if plan_path is None or not plan_path.is_file():
            errors.append(f"missing Plan file: {file_value}")
            continue
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read Plan file {file_value}: {exc}")
            continue
        if not plan_text.strip():
            errors.append(f"empty Plan file: {file_value}")
        if enforce_round_loop and "## Round Loop" not in plan_text:
            errors.append(f"missing Round Loop section: {file_value}")
        if final:
            if re.search(r"<[^>]+>", plan_text):
                errors.append(f"unresolved template placeholder: {file_value}")
            first_line = plan_text.splitlines()[0].strip() if plan_text.splitlines() else ""
            if not first_line.startswith(f"# {plan_id} "):
                errors.append(f"Plan heading does not match plan_id: {file_value}")
            if labeled_value(plan_text, "- 最终状态：") != status:
                errors.append(f"Plan final status does not match Dashboard: {plan_id}")


def load_json_object(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError) as exc:
        errors.append(f"invalid {label}: {exc}")
        return None
    if not isinstance(value, dict) or not value:
        errors.append(f"{label} must be a non-empty JSON object")
        return None
    return value


def validate_final_evidence(
    root: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, str]],
    errors: list[str],
) -> None:
    evidence_path = root / "final-evidence.json"
    if not evidence_path.is_file():
        errors.append("missing final file: final-evidence.json")
        return
    evidence = load_json_object(evidence_path, "final-evidence.json", errors)
    if evidence is None:
        return
    if (
        type(evidence.get("schema_version")) is not int
        or evidence["schema_version"] != FINAL_EVIDENCE_SCHEMA_VERSION
    ):
        errors.append(
            f"unsupported final-evidence schema_version={evidence.get('schema_version')!r}"
        )
    if evidence.get("work_package_schema_version") != manifest.get("schema_version"):
        errors.append("final-evidence work_package_schema_version does not match manifest")
    if evidence.get("op") != manifest.get("op"):
        errors.append("final-evidence op does not match manifest")
    if evidence.get("verdict") != "pass":
        errors.append("final-evidence verdict must be pass")

    plans = evidence.get("plans")
    if not isinstance(plans, dict):
        errors.append("final-evidence plans must be an object")
    else:
        expected = {
            "passed": {row.get("plan_id", "") for row in rows if row.get("状态") == "通过"},
            "eliminated": {row.get("plan_id", "") for row in rows if row.get("状态") == "淘汰"},
        }
        normalized: dict[str, set[str]] = {}
        for key, expected_ids in expected.items():
            values = plans.get(key)
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                errors.append(f"final-evidence plans.{key} must be a string list")
                normalized[key] = set()
                continue
            normalized[key] = set(values)
            if len(values) != len(normalized[key]):
                errors.append(f"final-evidence plans.{key} contains duplicates")
            if normalized[key] != expected_ids:
                errors.append(f"final-evidence plans.{key} does not match Dashboard")
        if normalized.get("passed", set()) & normalized.get("eliminated", set()):
            errors.append("final-evidence Plan sets overlap")

    checks = evidence.get("checks")
    if not isinstance(checks, dict):
        errors.append("final-evidence checks must be an object")
        return
    for name, required_prefix in FINAL_CHECK_PREFIXES.items():
        record = checks.get(name)
        if not isinstance(record, dict):
            errors.append(f"missing final-evidence check: {name}")
            continue
        if record.get("verdict") != "pass":
            errors.append(f"final-evidence check {name} verdict must be pass")
        artifact = record.get("artifact")
        digest = record.get("sha256")
        if not isinstance(artifact, str) or not artifact:
            errors.append(f"final-evidence check {name} artifact must be a path")
            continue
        relative = Path(artifact.replace("\\", "/"))
        prefix_parts = tuple(required_prefix.parts)
        if tuple(relative.parts[: len(prefix_parts)]) != prefix_parts:
            errors.append(f"final-evidence check {name} artifact must be under {required_prefix}")
            continue
        artifact_path = safe_relative_path(root, artifact)
        if artifact_path is None or not artifact_path.is_file():
            errors.append(f"missing final-evidence artifact for {name}: {artifact}")
            continue
        try:
            payload = artifact_path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read final-evidence artifact for {name}: {exc}")
            continue
        if not payload:
            errors.append(f"empty final-evidence artifact for {name}: {artifact}")
            continue
        if artifact_path.suffix.lower() != ".json":
            errors.append(f"final-evidence artifact for {name} must be JSON: {artifact}")
        else:
            artifact_json = load_json_object(artifact_path, f"artifact {artifact}", errors)
            if artifact_json is not None:
                if type(artifact_json.get("schema_version")) is not int or artifact_json["schema_version"] != 1:
                    errors.append(f"artifact {artifact} schema_version must be 1")
                if artifact_json.get("verdict") != "pass":
                    errors.append(f"artifact {artifact} verdict must be pass")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            errors.append(f"final-evidence check {name} sha256 is invalid")
        elif hashlib.sha256(payload).hexdigest() != digest:
            errors.append(f"final-evidence check {name} sha256 mismatch")


def validate_final_dashboard(markdown: str, errors: list[str]) -> None:
    for label in FINAL_DASHBOARD_LABELS:
        if not meaningful(labeled_value(markdown, label)):
            errors.append(f"final Dashboard field is empty: {label}")
    if labeled_value(markdown, "- 当前 step：") != "CLOSED":
        errors.append("final Dashboard current step must be CLOSED")
    verdict = labeled_value(markdown, "- 最后 Gate 与 verdict：")
    if meaningful(verdict) and "PASS" not in verdict.upper():
        errors.append("final Dashboard last Gate verdict must contain PASS")

    checklist = section(markdown, "## 最终验收")
    if checklist is None:
        errors.append("missing Dashboard section: ## 最终验收")
        return
    checklist_text = "\n".join(checklist)
    for item in FINAL_CHECKLIST_ITEMS:
        pattern = rf"^- \[[xX]\] {re.escape(item)}\s*$"
        if not re.search(pattern, checklist_text, re.MULTILINE):
            errors.append(f"unchecked or missing final Dashboard item: {item}")


def validate_final_report(
    markdown: str,
    rows: list[dict[str, str]],
    errors: list[str],
) -> None:
    for label in FINAL_REPORT_LABELS:
        if not meaningful(labeled_value(markdown, label)):
            errors.append(f"final-report field is empty: {label}")
    passed_ids = set(PLAN_ID_PATTERN.findall(labeled_value(markdown, "- 通过 Plan：") or ""))
    eliminated_ids = set(PLAN_ID_PATTERN.findall(labeled_value(markdown, "- 淘汰 Plan：") or ""))
    for row in rows:
        plan_id = row.get("plan_id", "")
        if row.get("状态") == "通过" and plan_id not in passed_ids:
            errors.append(f"final-report missing passed Plan: {plan_id}")
        if row.get("状态") == "淘汰" and plan_id not in eliminated_ids:
            errors.append(f"final-report missing eliminated Plan: {plan_id}")


def main() -> int:
    args = parse_args()
    root = args.run_root.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        print(f"ERROR run directory does not exist: {root}")
        return 2

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing file: {relative}")
    for relative in REQUIRED_DIRS:
        if not (root / relative).is_dir():
            errors.append(f"missing directory: {relative}")

    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {}
    schema_version: int | None = None
    if manifest_path.is_file():
        loaded_manifest = load_json_object(manifest_path, "manifest.json", errors)
        if loaded_manifest is not None:
            manifest = loaded_manifest
            schema_version = manifest.get("schema_version")
            if manifest.get("skill") != "tilelang-pto-kernel-workflow":
                errors.append("manifest skill is not tilelang-pto-kernel-workflow")
            if not isinstance(manifest.get("op"), str) or not manifest["op"].strip():
                errors.append("manifest op must be a non-empty string")
            if type(schema_version) is not int or schema_version != CURRENT_SCHEMA_VERSION:
                errors.append(f"unsupported manifest schema_version={schema_version!r}")
            else:
                for relative in V2_REQUIRED_DIRS:
                    if not (root / relative).is_dir():
                        errors.append(f"missing directory: {relative}")

    dashboard_path = root / "plan-dashboard.md"
    dashboard = ""
    rows: list[dict[str, str]] = []
    if dashboard_path.is_file():
        dashboard = dashboard_path.read_text(encoding="utf-8")
        rows, table_errors = parse_plans_table(dashboard)
        errors.extend(table_errors)
        enforce_round_loop = schema_version == CURRENT_SCHEMA_VERSION
        validate_plan_rows(root, rows, enforce_round_loop, args.final, errors)
        if enforce_round_loop:
            if section(dashboard, "## Loop 控制") is None:
                errors.append("missing Dashboard section: ## Loop 控制")
            for label in DASHBOARD_REQUIRED_LABELS:
                value = labeled_value(dashboard, label)
                if value is None:
                    errors.append(f"missing Dashboard loop field: {label}")
            step = labeled_value(dashboard, "- 当前 step：")
            if step is not None and step not in ALLOWED_STEPS:
                errors.append(f"invalid Dashboard current step: {step or '<empty>'}")

    if args.final:
        if not rows:
            errors.append("final validation requires at least one Plan row")
        if any(row.get("状态") == "待实现" for row in rows):
            errors.append("final validation has pending Plans")
        if dashboard:
            validate_final_dashboard(dashboard, errors)

        final_report_path = root / "final-report.md"
        if not final_report_path.is_file():
            errors.append("missing final file: final-report.md")
        else:
            final_report = final_report_path.read_text(encoding="utf-8")
            if not final_report.strip():
                errors.append("empty final file: final-report.md")
            elif "<op>" in final_report or "<created_at>" in final_report:
                errors.append("unresolved template placeholder: final-report.md")
            validate_final_report(final_report, rows, errors)

        backfill_path = root / "backfill-draft.md"
        if not backfill_path.is_file():
            errors.append("missing final file: backfill-draft.md")
        else:
            backfill = backfill_path.read_text(encoding="utf-8")
            if not backfill.strip():
                errors.append("empty final file: backfill-draft.md")
            elif "<op>" in backfill or "<created_at>" in backfill:
                errors.append("unresolved template placeholder: backfill-draft.md")

        validate_final_evidence(root, manifest, rows, errors)

    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"ERROR {error}")

    if errors:
        print(f"FAILED errors={len(errors)} warnings={len(warnings)}")
        return 1
    print(f"OK statuses={len(rows)} warnings={len(warnings)} final={args.final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
