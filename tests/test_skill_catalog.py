from copy import deepcopy
import importlib.util
from pathlib import Path


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
    value["aliases"] = [{"id": "old-a", "target": "old-b"}, {"id": "old-b", "target": "old-a"}]
    assert any("alias cycle" in error for error in errors(value))


def test_catalog_rejects_missing_alias_target():
    value = catalog()
    value["aliases"] = [{"id": "old-a", "target": "missing"}]
    assert any("missing alias target" in error for error in errors(value))


def test_catalog_rejects_multiple_alias_targets():
    value = catalog()
    value["aliases"] = [
        {"id": "old-a", "target": "xllm-npu-profiler"},
        {"id": "old-a", "target": "xllm-npu-benchmark"},
    ]
    assert any("multiple targets" in error for error in errors(value))
