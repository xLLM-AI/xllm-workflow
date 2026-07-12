from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "routing" / "cases.json"


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
        "development", "evaluation", "framework", "history", "incident", "internal",
        "lifecycle", "optimization", "pipeline", "profiling", "report", "review", "service",
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
        assert len(case["expected_primary"]) == 1, case["id"]
        assert case["current_primary_candidates"], case["id"]
        for primary in case["expected_primary"]:
            if primary == sentinel:
                missing_route_cases += 1
            else:
                assert primary in names, (case["id"], primary)
        for field in ("current_primary_candidates", "allowed_followups", "forbidden_primary"):
            assert set(case[field]) <= names, (case["id"], field)
        expected = set(case["expected_primary"])
        allowed = set(case["allowed_followups"])
        forbidden = set(case["forbidden_primary"])
        assert expected.isdisjoint(allowed), case["id"]
        assert expected.isdisjoint(forbidden), case["id"]
        assert allowed.isdisjoint(forbidden), case["id"]
    assert missing_route_cases == 0
    lifecycle_cases = [case for case in corpus["cases"] if case["family"] in {"lifecycle", "internal"}]
    assert all(case["expected_primary"] == ["xllm-experiment-lifecycle"] for case in lifecycle_cases)


def test_baseline_records_real_ambiguity_without_fake_accuracy():
    corpus = load_corpus()
    assert "accuracy" not in corpus["scoring"]
    ambiguous = [case for case in corpus["cases"] if len(case["current_primary_candidates"]) > 1]
    assert len(ambiguous) >= 20


def test_internal_skills_never_win_expected_primary_routing():
    catalog = json.loads((ROOT / "skills" / "catalog.json").read_text(encoding="utf-8"))
    internal = {skill["id"] for skill in catalog["skills"] if skill["visibility"] == "internal"}
    expected = {primary for case in load_corpus()["cases"] for primary in case["expected_primary"]}
    assert internal.isdisjoint(expected)


def test_every_public_skill_is_covered_by_routing_corpus():
    catalog = json.loads((ROOT / "skills" / "catalog.json").read_text(encoding="utf-8"))
    public = {skill["id"] for skill in catalog["skills"] if skill["visibility"] == "public"}
    cases = load_corpus()["cases"]
    covered = {
        name
        for case in cases
        for field in ("expected_primary", "allowed_followups")
        for name in case[field]
    }
    assert public <= covered, sorted(public - covered)
