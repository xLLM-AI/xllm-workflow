from copy import deepcopy
import importlib.util
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_skill_catalog.py"
SPEC = importlib.util.spec_from_file_location("validate_skill_catalog", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def catalog():
    return MODULE.load_catalog(ROOT / "skills" / "catalog.json")


def errors(value):
    return MODULE.validate_catalog(value, ROOT)


def test_current_skill_catalog_is_valid():
    assert errors(catalog()) == []


def test_catalog_rejects_missing_skill():
    value = catalog()
    value["skills"].pop()
    assert any("catalog missing skill directory" in error for error in errors(value))


def test_catalog_rejects_duplicate_id():
    value = catalog()
    value["skills"].append(deepcopy(value["skills"][0]))
    assert any("duplicate skill id" in error for error in errors(value))


def test_catalog_rejects_invalid_dependency():
    value = catalog()
    value["skills"][0]["dependencies"] = ["missing-skill"]
    assert any("invalid dependency" in error for error in errors(value))


def test_catalog_rejects_alias_cycle():
    value = catalog()
    metadata = {"description": "compatibility redirect", "introduced_in": "PR12", "removal_conditions": "no users remain"}
    value["aliases"] = [
        {"id": "old-a", "target": "old-b", **metadata},
        {"id": "old-b", "target": "old-a", **metadata},
    ]
    assert any("alias cycle" in error for error in errors(value))


def test_catalog_rejects_missing_alias_target():
    value = catalog()
    value["aliases"] = [{"id": "old-a", "target": "missing", "description": "compatibility redirect", "introduced_in": "PR12", "removal_conditions": "no users remain"}]
    assert any("missing alias target" in error for error in errors(value))


def test_catalog_rejects_multiple_alias_targets():
    value = catalog()
    value["aliases"] = [
        {"id": "old-a", "target": "xllm-npu-profiler", "description": "compatibility redirect", "introduced_in": "PR12", "removal_conditions": "no users remain"},
        {"id": "old-a", "target": "xllm-npu-benchmark", "description": "compatibility redirect", "introduced_in": "PR12", "removal_conditions": "no users remain"},
    ]
    assert any("multiple targets" in error for error in errors(value))


def test_catalog_rejects_alias_without_compatibility_metadata():
    value = catalog()
    value["aliases"] = [{"id": "old-a", "target": "xllm-npu-profiler"}]
    assert any("compatibility metadata" in error for error in errors(value))


def test_pr12_preserves_every_baseline_name_as_canonical():
    baseline_names = {
        "ssh-remote-exec", "xllm-npu-accuracy-debug", "xllm-npu-accuracy-runner",
        "xllm-npu-batch-perf", "xllm-npu-benchmark", "xllm-npu-build-gate",
        "xllm-npu-capacity-planner", "xllm-npu-code-review",
        "xllm-npu-compute-simulation", "xllm-npu-eval-runner",
        "xllm-npu-incident-triage", "xllm-npu-perf-runner",
        "xllm-npu-pipeline-analysis", "xllm-npu-profiler",
        "xllm-npu-report-writer", "xllm-npu-server-manager",
        "xllm-npu-sota-loop", "xllm-npu-triton-migration",
        "xllm-npu-xllm-ops-integration",
    }
    value = catalog()
    assert baseline_names <= {skill["id"] for skill in value["skills"]}
    assert value["aliases"] == []


def test_internal_skills_disable_implicit_invocation():
    value = catalog()
    internal = [skill for skill in value["skills"] if skill["visibility"] == "internal"]
    assert {skill["id"] for skill in internal} == {"ssh-remote-exec"}
    for skill in internal:
        policy = ROOT / "skills" / skill["directory"] / "agents" / "openai.yaml"
        assert policy.is_file(), skill["id"]
        text = policy.read_text(encoding="utf-8")
        assert re.search(r"^\s*allow_implicit_invocation:\s*false\s*$", text, re.MULTILINE)
