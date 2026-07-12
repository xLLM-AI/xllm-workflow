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
REQUIRED_ALIAS_FIELDS = {"id", "target", "description", "introduced_in", "removal_conditions"}
SCALAR_FIELDS = {"id", "directory", "category", "visibility", "ownership"}
ROUTING_PRIORITY_RANGE = range(1, 101)
IGNORED_SKILL_PARTS = {".git", ".agents", ".pytest_cache", "__pycache__", "code", "runs"}
REQUIRED_PRESENTATION_FIELDS = {
    "display_name", "display_name_zh", "domain", "role_group", "exposure",
    "summary", "summary_zh", "outputs", "featured",
}
DOMAINS = {
    "lifecycle", "performance", "evaluation", "accuracy", "profiling",
    "reliability", "build", "capacity", "knowledge", "development",
    "reporting", "remote-execution",
}
ROLE_GROUPS = {
    "orchestration", "execution", "analysis-and-diagnosis",
    "planning-and-knowledge", "development-and-review", "gates-and-support",
}
EXPOSURES = {"public-primary", "public-delegated", "public-explicit-only", "internal-explicit-only"}


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
        invalid_scalars = [
            field for field in SCALAR_FIELDS
            if not isinstance(skill[field], str) or not skill[field].strip()
        ]
        if invalid_scalars:
            errors.append(f"skills[{index}] scalar fields must be non-empty strings: {sorted(invalid_scalars)}")
            continue
        skill_id = skill["id"].strip()
        directory = skill["directory"].strip()
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
        if not isinstance(skill["routing_priority"], int) or isinstance(skill["routing_priority"], bool) or skill["routing_priority"] not in ROUTING_PRIORITY_RANGE:
            errors.append(f"routing_priority must be an integer from 1 to 100 for {skill_id}")
        for field in ("primary_intents", "negative_intents", "dependencies", "lifecycle_stage", "framework_scope", "backend_scope"):
            if not isinstance(skill[field], list) or (field != "dependencies" and not skill[field]):
                errors.append(f"{field} must be a non-empty list for {skill_id}")
            elif any(not isinstance(item, str) or not item.strip() for item in skill[field]):
                errors.append(f"{field} entries must be non-empty strings for {skill_id}")
        presentation = skill.get("presentation")
        if not isinstance(presentation, dict):
            errors.append(f"missing presentation metadata for {skill_id}")
        else:
            missing_presentation = REQUIRED_PRESENTATION_FIELDS - presentation.keys()
            if missing_presentation:
                errors.append(f"presentation for {skill_id} missing fields: {sorted(missing_presentation)}")
            for field in ("display_name", "display_name_zh", "domain", "role_group", "exposure", "summary", "summary_zh"):
                if field in presentation and (not isinstance(presentation[field], str) or not presentation[field].strip()):
                    errors.append(f"presentation {field} must be a non-empty string for {skill_id}")
            if presentation.get("domain") not in DOMAINS:
                errors.append(f"invalid presentation domain for {skill_id}: {presentation.get('domain')}")
            if presentation.get("role_group") not in ROLE_GROUPS:
                errors.append(f"invalid presentation role_group for {skill_id}: {presentation.get('role_group')}")
            if presentation.get("exposure") not in EXPOSURES:
                errors.append(f"invalid presentation exposure for {skill_id}: {presentation.get('exposure')}")
            outputs = presentation.get("outputs")
            if not isinstance(outputs, list) or not outputs:
                errors.append(f"presentation outputs must be a non-empty list for {skill_id}")
            elif any(not isinstance(item, str) or not item.strip() for item in outputs):
                errors.append(f"presentation outputs must contain non-empty strings for {skill_id}")
            elif len(outputs) != len(set(outputs)):
                errors.append(f"duplicate presentation output for {skill_id}")
            if type(presentation.get("featured")) is not bool:
                errors.append(f"presentation featured must be boolean for {skill_id}")
            if skill["visibility"] == "internal":
                if presentation.get("exposure") != "internal-explicit-only":
                    errors.append(f"internal presentation exposure must be internal-explicit-only for {skill_id}")
                if presentation.get("featured") is True:
                    errors.append(f"internal skill cannot be featured: {skill_id}")
            elif presentation.get("exposure") == "internal-explicit-only":
                errors.append(f"public skill cannot use internal presentation exposure: {skill_id}")
        skill_file = root / "skills" / directory / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"missing skill directory or SKILL.md: {directory}")
        elif declared_name(skill_file) != skill_id:
            errors.append(f"declared name drift for {directory}: {declared_name(skill_file)!r} != {skill_id!r}")

    actual_skill_files = {path.resolve() for path in (root / "skills").glob("*/SKILL.md")}
    actual_directories = {path.parent.name for path in actual_skill_files}
    for directory in sorted(actual_directories - directories.keys()):
        errors.append(f"catalog missing skill directory: {directory}")
    for skill_id, skill in ids.items():
        dependencies = skill.get("dependencies", [])
        if isinstance(dependencies, list) and all(isinstance(item, str) for item in dependencies) and len(dependencies) != len(set(dependencies)):
            errors.append(f"duplicate dependency for {skill_id}")
        if skill_id in dependencies:
            errors.append(f"self dependency for {skill_id}")
        for dependency in dependencies:
            if dependency not in ids:
                errors.append(f"invalid dependency for {skill_id}: {dependency}")

    repository_skill_files = {
        path.resolve()
        for path in root.rglob("SKILL.md")
        if not any(part in IGNORED_SKILL_PARTS for part in path.relative_to(root).parts)
    }
    for path in sorted(repository_skill_files - actual_skill_files):
        errors.append(f"orphan SKILL.md outside catalog/install policy: {path.relative_to(root)}")

    alias_targets: dict[str, str] = {}
    for index, alias in enumerate(aliases):
        if not isinstance(alias, dict) or not REQUIRED_ALIAS_FIELDS <= alias.keys():
            errors.append(f"aliases[{index}] missing required compatibility metadata")
            continue
        alias_id, target = alias["id"], alias["target"]
        for field in REQUIRED_ALIAS_FIELDS:
            if not isinstance(alias[field], str) or not alias[field].strip():
                errors.append(f"alias {alias_id} has empty {field}")
        if not isinstance(alias_id, str) or not alias_id.strip() or not isinstance(target, str) or not target.strip():
            continue
        if alias_id in ids:
            errors.append(f"alias collides with canonical id: {alias_id}")
        if alias_id in alias_targets and alias_targets[alias_id] != target:
            errors.append(f"alias has multiple targets: {alias_id}")
        elif alias_id in alias_targets:
            errors.append(f"duplicate alias id: {alias_id}")
        alias_targets[alias_id] = target

    for alias_id, target in alias_targets.items():
        if target not in ids:
            errors.append(f"missing alias target for {alias_id}: {target}")
        if target in alias_targets:
            errors.append(f"alias target must be canonical for {alias_id}: {target}")
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
