#!/usr/bin/env python3
"""Validate the workflow skill catalog and compatibility alias graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


REQUIRED_SKILL_FIELDS = {
    "id", "directory", "category", "visibility", "routing_priority",
    "primary_intents", "negative_intents", "dependencies", "lifecycle_stage",
    "framework_scope", "backend_scope", "ownership",
}
CATEGORIES = {"orchestrator", "planner", "runner", "analyzer", "gate", "support"}
VISIBILITIES = {"public", "internal", "compatibility"}


def load_catalog(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("catalog root must be an object")
    return value


def declared_name(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    match = re.search(r"^name:\s*(\S+)", text.split("---", 2)[1], re.MULTILINE)
    return match.group(1) if match else None


def validate_catalog(catalog: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    skills = catalog.get("skills")
    aliases = catalog.get("aliases")
    if catalog.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(skills, list):
        return errors + ["skills must be a list"]
    if not isinstance(aliases, list):
        return errors + ["aliases must be a list"]

    ids: dict[str, dict[str, Any]] = {}
    directories: dict[str, str] = {}
    for index, skill in enumerate(skills):
        if not isinstance(skill, dict):
            errors.append(f"skills[{index}] must be an object")
            continue
        missing = REQUIRED_SKILL_FIELDS - skill.keys()
        if missing:
            errors.append(f"{skill.get('id', index)} missing fields: {sorted(missing)}")
            continue
        skill_id = skill["id"]
        directory = skill["directory"]
        if skill_id in ids:
            errors.append(f"duplicate skill id: {skill_id}")
        ids[skill_id] = skill
        if directory in directories:
            errors.append(f"duplicate skill directory: {directory}")
        directories[directory] = skill_id
        if skill["category"] not in CATEGORIES:
            errors.append(f"invalid category for {skill_id}: {skill['category']}")
        if skill["visibility"] not in VISIBILITIES:
            errors.append(f"invalid visibility for {skill_id}: {skill['visibility']}")
        if not isinstance(skill["routing_priority"], int):
            errors.append(f"routing_priority must be integer for {skill_id}")
        for field in ("primary_intents", "negative_intents", "dependencies", "lifecycle_stage", "framework_scope", "backend_scope"):
            if not isinstance(skill[field], list) or (field != "dependencies" and not skill[field]):
                errors.append(f"{field} must be a non-empty list for {skill_id}")
        skill_file = root / "skills" / directory / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"missing skill directory or SKILL.md: {directory}")
        elif declared_name(skill_file) != skill_id:
            errors.append(f"declared name drift for {directory}: {declared_name(skill_file)!r} != {skill_id!r}")

    actual_directories = {path.parent.name for path in (root / "skills").glob("*/SKILL.md")}
    for directory in sorted(actual_directories - directories.keys()):
        errors.append(f"catalog missing skill directory: {directory}")
    for skill_id, skill in ids.items():
        for dependency in skill.get("dependencies", []):
            if dependency not in ids:
                errors.append(f"invalid dependency for {skill_id}: {dependency}")

    alias_targets: dict[str, str] = {}
    for index, alias in enumerate(aliases):
        if not isinstance(alias, dict) or not {"id", "target"} <= alias.keys():
            errors.append(f"aliases[{index}] must contain id and target")
            continue
        alias_id, target = alias["id"], alias["target"]
        if alias_id in ids:
            errors.append(f"alias collides with canonical id: {alias_id}")
        if alias_id in alias_targets and alias_targets[alias_id] != target:
            errors.append(f"alias has multiple targets: {alias_id}")
        elif alias_id in alias_targets:
            errors.append(f"duplicate alias id: {alias_id}")
        alias_targets[alias_id] = target

    resolvable = set(ids) | set(alias_targets)
    for alias_id, target in alias_targets.items():
        if target not in resolvable:
            errors.append(f"missing alias target for {alias_id}: {target}")
        seen = {alias_id}
        current = target
        while current in alias_targets:
            if current in seen:
                errors.append(f"alias cycle involving {alias_id}")
                break
            seen.add(current)
            current = alias_targets[current]

    inventory = root / "docs" / "pr12" / "SKILL_INVENTORY.md"
    if inventory.is_file():
        inventory_text = inventory.read_text(encoding="utf-8")
        for skill_id in ids:
            if f"`{skill_id}`" not in inventory_text:
                errors.append(f"inventory documentation missing: {skill_id}")
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("skills/catalog.json"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = validate_catalog(load_catalog(args.catalog), args.root.resolve())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"skill catalog valid: {args.catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
