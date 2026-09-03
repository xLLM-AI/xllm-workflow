#!/usr/bin/env python3
"""Initialize a non-destructive TileLang/PTO operator work package."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
OP_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

TEMPLATES = {
    "baseline-template.md": "baseline.md",
    "plan-dashboard-template.md": "plan-dashboard.md",
    "progress-template.md": "progress.md",
    "final-report-template.md": "final-report.md",
    "final-evidence-template.json": "final-evidence.json",
    "backfill-template.md": "backfill-draft.md",
    "plan-template.md": "plans/_template.md",
}

DIRECTORIES = (
    "analysis",
    "plans",
    "source-audit/tilelang",
    "source-audit/pto",
    "precision/golden",
    "precision/atk",
    "perf/round0",
    "perf/final",
    "model/graph-route",
    "model/rollback",
    "model/tpot",
)

ANALYSIS_FILES = {
    "analysis/memory.md": "Memory",
    "analysis/sync.md": "Sync",
    "analysis/compute.md": "Compute / Instruction",
    "analysis/task-map.md": "Task Map / Tiling",
    "analysis/precision.md": "Precision",
    "analysis/arbitration.md": "Arbitration",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a TileLang/PTO work package without overwriting existing files."
    )
    parser.add_argument("--op", required=True, help="Stable operator identifier.")
    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
        help="Existing target repository root.",
    )
    parser.add_argument(
        "--output-root",
        default="optimization-analysis",
        help="Directory under repo-root. Default: optimization-analysis",
    )
    return parser.parse_args()


def write_new(path: Path, content: str, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(path)


def main() -> int:
    args = parse_args()
    if not OP_PATTERN.fullmatch(args.op):
        raise SystemExit(
            "--op must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen."
        )

    repo_root = args.repo_root.expanduser().resolve()
    if not repo_root.is_dir():
        raise SystemExit(f"repo root does not exist: {repo_root}")

    output_root = Path(args.output_root)
    if output_root.is_absolute() or ".." in output_root.parts:
        raise SystemExit("--output-root must be a safe path relative to repo-root.")

    run_root = repo_root / output_root / args.op
    run_root.mkdir(parents=True, exist_ok=True)
    for relative in DIRECTORIES:
        (run_root / relative).mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc).isoformat()
    replacements = {
        "<op>": args.op,
        "<created_at>": created_at,
    }
    created: list[Path] = []
    skipped: list[Path] = []

    for source_name, target_name in TEMPLATES.items():
        content = (ASSETS / source_name).read_text(encoding="utf-8")
        for old, new in replacements.items():
            content = content.replace(old, new)
        write_new(run_root / target_name, content, created, skipped)

    for relative, title in ANALYSIS_FILES.items():
        content = (
            f"# {title} Analysis — {args.op}\n\n"
            "## Evidence\n\n"
            "## Bound / Risk\n\n"
            "## Candidates\n\n"
            "## Artifact Paths\n"
        )
        write_new(run_root / relative, content, created, skipped)

    manifest = {
        "schema_version": 2,
        "skill": "tilelang-pto-kernel-workflow",
        "op": args.op,
        "created_at": created_at,
        "repo_root": str(repo_root),
        "run_root": str(run_root),
    }
    write_new(
        run_root / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        created,
        skipped,
    )

    print(f"run_root={run_root}")
    print(f"created={len(created)}")
    print(f"skipped_existing={len(skipped)}")
    for path in skipped:
        print(f"skip {path.relative_to(run_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
