import json
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "init_xllm_workspace", ROOT / "scripts" / "init_xllm_workspace.py"
)
init = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(init)


def test_resolve_repo_config_writes_cli_values(tmp_path):
    config_path = tmp_path / "config.json"
    config = {"active": {"framework": "xllm"}}

    repo = init.resolve_repo_config(
        config,
        config_path,
        repo_url="https://example.com/xllm.git",
        ref="main",
        ref_type="branch",
        assume_yes=True,
    )

    assert repo == {
        "url": "https://example.com/xllm.git",
        "ref": "main",
        "ref_type": "branch",
    }
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["repositories"]["xllm"] == repo


def test_resolve_repo_config_requires_missing_values_in_noninteractive_mode(tmp_path):
    with pytest.raises(init.InitError):
        init.resolve_repo_config(
            {},
            tmp_path / "config.json",
            repo_url=None,
            ref=None,
            ref_type=None,
            assume_yes=True,
        )


def test_link_xllm_skills_links_agent_and_legacy_skill_dirs(tmp_path, monkeypatch):
    xllm_dir = tmp_path / "code" / "xllm"
    skill_a = xllm_dir / ".agents" / "skills" / "debug"
    skill_b = xllm_dir / "skills" / "profile"
    skill_a.mkdir(parents=True)
    skill_b.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("---\nname: debug\ndescription: debug\n---\n", encoding="utf-8")
    (skill_b / "SKILL.md").write_text("---\nname: profile\ndescription: profile\n---\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    monkeypatch.setattr(init, "ROOT", tmp_path)

    linked, skipped = init.link_xllm_skills(xllm_dir, skills_dir)

    assert skipped == []
    assert linked == [
        "xllm-debug -> code/xllm/.agents/skills/debug",
        "xllm-profile -> code/xllm/skills/profile",
    ]
    assert (skills_dir / "xllm-debug").is_symlink()
    assert (skills_dir / "xllm-profile").is_symlink()


def test_link_xllm_skills_does_not_replace_real_directory(tmp_path, monkeypatch):
    xllm_dir = tmp_path / "code" / "xllm"
    source = xllm_dir / ".agents" / "skills" / "debug"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: debug\ndescription: debug\n---\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    existing = skills_dir / "xllm-debug"
    existing.mkdir(parents=True)
    monkeypatch.setattr(init, "ROOT", tmp_path)

    linked, skipped = init.link_xllm_skills(xllm_dir, skills_dir)

    assert linked == []
    assert skipped == ["xllm-debug (目标已存在且不是软链)"]
    assert existing.is_dir()
    assert not existing.is_symlink()
