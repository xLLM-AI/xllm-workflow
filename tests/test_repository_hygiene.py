from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def text_files():
    suffixes = {".md", ".py", ".sh", ".json", ".jsonl", ".yaml", ".yml"}
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.is_file() and path.suffix in suffixes:
            yield path


def test_skill_frontmatter_has_name_and_description():
    skill_files = list(ROOT.glob("skills/*/SKILL.md")) + [
        ROOT / "kernel-pilot/SKILL.md",
        ROOT / "model-pr-optimization-history/SKILL.md",
    ]
    for skill in skill_files:
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\n"), skill
        header = text.split("---", 2)[1]
        assert re.search(r"^name:\s*\S+", header, re.M), skill
        assert re.search(r"^description:\s*.+", header, re.M), skill


def test_skills_do_not_hardcode_single_agent_install_paths():
    forbidden = [
        ".opencode/skills/",
        "$CODEX_HOME/skills/",
        "~/.claude/skills/",
    ]
    skill_files = list(ROOT.glob("skills/*/SKILL.md")) + [
        ROOT / "kernel-pilot/SKILL.md",
        ROOT / "model-pr-optimization-history/SKILL.md",
    ]
    for skill in skill_files:
        text = skill.read_text(encoding="utf-8")
        for item in forbidden:
            assert item not in text, f"{item} found in {skill}"


def test_no_public_readme_forbidden_source_reference():
    forbidden = [
        "B" + "Buf",
        "AI-Coding-" + "Auto-" + "Driven-SKILLS",
        "Auto-" + "Driven",
    ]
    for path in [ROOT / "README.md", ROOT / "README_zh.md"]:
        text = path.read_text(encoding="utf-8")
        for item in forbidden:
            assert item not in text, f"{item} found in {path}"


def test_no_obvious_local_or_credential_strings():
    patterns = [
        r"/home/[A-Za-z][A-Za-z0-9._-]*",
        r"\b[a-z][0-9]{8}\b",
        r"\b[a-z]+pengju\b",
        r"\b[a-z]+pengju[0-9]*\b",
        r"SSH config:\s*`?\d+`?",
        r"\bhost\s*[:=]\s*\d+\b",
        r"192\.168\.",
        "xllm" + "-gpj",
        "jd" + "_openai_20k",
        "BEGIN " + "RSA",
        "PRIVATE " + "KEY",
    ]
    combined = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in text_files())
    for pattern in patterns:
        assert not re.search(pattern, combined), pattern

    allowed_ips = {"0.0.0.0", "127.0.0.1"}
    for match in re.finditer(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", combined):
        assert match.group(0) in allowed_ips, match.group(0)
