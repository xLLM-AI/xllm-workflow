#!/usr/bin/env python3
"""Validate the static contract of a TileLang/PTO optimization run."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ALLOWED_STATUSES = {"待实现", "通过", "淘汰"}
CURRENT_SCHEMA_VERSION = 2
DASHBOARD_LOOP_MARKERS = (
    "## Loop 控制",
    "当前 step：SELECT / IMPLEMENT / VERIFY / REVIEW / DECIDE / CLOSED",
    "最后 Gate 与 verdict：",
    "下一动作：",
)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an optimization run directory.")
    parser.add_argument("run_root", type=Path)
    parser.add_argument(
        "--final",
        action="store_true",
        help="Also enforce final evidence and no pending plans.",
    )
    return parser.parse_args()


def table_statuses(markdown: str) -> list[str]:
    statuses: list[str] = []
    status_index: int | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if "状态" in cells:
            status_index = cells.index("状态")
            continue
        if status_index is None or status_index >= len(cells):
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if cells and re.fullmatch(r"(?i)plan[-_A-Za-z0-9.]+", cells[0]):
            statuses.append(cells[status_index])
    return statuses


def has_files(path: Path) -> bool:
    return path.is_dir() and any(item.is_file() for item in path.rglob("*"))


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
    schema_version: int | None = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"invalid manifest.json: {exc}")
        else:
            schema_version = manifest.get("schema_version")
            if manifest.get("skill") != "tilelang-pto-kernel-workflow":
                errors.append("manifest skill is not tilelang-pto-kernel-workflow")
            if schema_version == 1:
                warnings.append("legacy manifest schema_version=1; loop markers are not enforced")
            elif schema_version != CURRENT_SCHEMA_VERSION:
                warnings.append(f"unknown manifest schema_version={schema_version}")

    dashboard_path = root / "plan-dashboard.md"
    statuses: list[str] = []
    if dashboard_path.is_file():
        dashboard = dashboard_path.read_text(encoding="utf-8")
        statuses = table_statuses(dashboard)
        for status in statuses:
            if status not in ALLOWED_STATUSES:
                errors.append(f"invalid Plan status: {status or '<empty>'}")
        if schema_version == CURRENT_SCHEMA_VERSION:
            for marker in DASHBOARD_LOOP_MARKERS:
                if marker not in dashboard:
                    errors.append(f"missing Dashboard loop marker: {marker}")

    if schema_version == CURRENT_SCHEMA_VERSION:
        plans_dir = root / "plans"
        if plans_dir.is_dir():
            for plan_path in plans_dir.glob("plan-*.md"):
                if "## Round Loop" not in plan_path.read_text(encoding="utf-8"):
                    errors.append(f"missing Round Loop section: {plan_path.relative_to(root)}")

    if args.final:
        if "待实现" in statuses:
            errors.append("final validation has pending Plans")
        for relative in ("final-report.md", "backfill-draft.md"):
            path = root / relative
            if not path.is_file():
                errors.append(f"missing final file: {relative}")
                continue
            text = path.read_text(encoding="utf-8")
            if "<op>" in text or "<created_at>" in text:
                errors.append(f"unresolved template placeholder: {relative}")
        for relative in ("perf/round0", "precision", "model/graph-route"):
            if not has_files(root / relative):
                errors.append(f"final evidence directory is empty: {relative}")

    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"ERROR {error}")

    if errors:
        print(f"FAILED errors={len(errors)} warnings={len(warnings)}")
        return 1
    print(f"OK statuses={len(statuses)} warnings={len(warnings)} final={args.final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
