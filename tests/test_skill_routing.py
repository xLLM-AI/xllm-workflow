from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "routing" / "cases.yaml"


def skill_names() -> set[str]:
    names = set()
    for path in ROOT.glob("skills/*/SKILL.md"):
        header = path.read_text(encoding="utf-8").split("---", 2)[1]
        match = re.search(r"^name:\s*(\S+)", header, re.MULTILINE)
        assert match, path
        names.add(match.group(1))
    return names


def load_corpus() -> dict:
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_routing_corpus_has_required_coverage():
    corpus = load_corpus()
    cases = corpus["cases"]
    assert corpus["schema_version"] == 1
    assert corpus["scoring"]["kind"] == "auditable_specification"
    assert len(cases) >= 30
    assert len({case["id"] for case in cases}) == len(cases)
    required = {
        "accuracy", "batch", "benchmark", "build", "capacity", "compute",
        "development", "evaluation", "framework", "incident", "internal",
        "lifecycle", "optimization", "pipeline", "profiling", "report", "service",
    }
    assert required <= {case["family"] for case in cases}


def test_routing_references_are_auditable():
    corpus = load_corpus()
    names = skill_names()
    sentinel = corpus["missing_route_sentinel"]
    missing_route_cases = 0
    for case in corpus["cases"]:
        assert case["prompt"].strip(), case["id"]
        assert case["reason"].strip(), case["id"]
        assert case["expected_primary"], case["id"]
        assert case["current_primary_candidates"], case["id"]
        for primary in case["expected_primary"]:
            if primary == sentinel:
                missing_route_cases += 1
            else:
                assert primary in names, (case["id"], primary)
        for field in ("current_primary_candidates", "allowed_followups", "forbidden_primary"):
            assert set(case[field]) <= names, (case["id"], field)
        assert not set(case["expected_primary"]) & set(case["forbidden_primary"]), case["id"]
    assert missing_route_cases >= 5


def test_baseline_records_real_ambiguity_without_fake_accuracy():
    corpus = load_corpus()
    assert "accuracy" not in corpus["scoring"]
    ambiguous = [case for case in corpus["cases"] if len(case["current_primary_candidates"]) > 1]
    assert len(ambiguous) >= 20
