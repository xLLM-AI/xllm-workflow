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
    config = {"xllm": {"model": {"model_id": "qwen35-27b"}}}

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
    assert saved["code"]["xllm"]["origin"] == {
        "url": "https://example.com/xllm.git",
        "branch": "main",
        "commit": "",
    }


def test_resolve_repo_config_reads_legacy_repository_values(tmp_path):
    repo = init.resolve_repo_config(
        {
            "repositories": {
                "xllm": {
                    "url": "https://example.com/legacy-xllm.git",
                    "ref": "abc1234",
                    "ref_type": "commit",
                }
            }
        },
        tmp_path / "config.json",
        repo_url=None,
        ref=None,
        ref_type=None,
        assume_yes=True,
    )

    assert repo == {
        "url": "https://example.com/legacy-xllm.git",
        "ref": "abc1234",
        "ref_type": "commit",
    }


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


def test_load_config_creates_local_config_from_template(tmp_path):
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "config.example.json"
    template_path.write_text(
        json.dumps({"active": {"framework": "xllm"}}) + "\n",
        encoding="utf-8",
    )

    config = init.load_config(config_path, template_path)

    assert config == {"active": {"framework": "xllm"}}
    assert json.loads(config_path.read_text(encoding="utf-8")) == config


def test_link_workspace_skills_links_project_and_xllm_skill_dirs(tmp_path, monkeypatch):
    project_skill = tmp_path / "skills" / "project-review"
    project_skill.mkdir(parents=True)
    (project_skill / "SKILL.md").write_text(
        "---\nname: project-review\ndescription: review\n---\n",
        encoding="utf-8",
    )

    xllm_dir = tmp_path / "code" / "xllm"
    skill_a = xllm_dir / ".agents" / "skills" / "debug"
    skill_b = xllm_dir / "skills" / "profile"
    skill_a.mkdir(parents=True)
    skill_b.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("---\nname: debug\ndescription: debug\n---\n", encoding="utf-8")
    (skill_b / "SKILL.md").write_text("---\nname: profile\ndescription: profile\n---\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    monkeypatch.setattr(init, "ROOT", tmp_path)
    monkeypatch.setattr(init, "PROJECT_SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(init, "WORKSPACE_SKILLS_DIR", skills_dir)

    project_linked, project_skipped, xllm_linked, xllm_skipped = init.link_workspace_skills(xllm_dir)

    assert project_skipped == []
    assert xllm_skipped == []
    assert project_linked[0].startswith("project-review -> skills/project-review")
    assert xllm_linked[0].startswith("xllm-debug -> code/xllm/.agents/skills/debug")
    assert xllm_linked[1].startswith("xllm-profile -> code/xllm/skills/profile")
    assert (skills_dir / "project-review").exists()
    assert (skills_dir / "xllm-debug").exists()
    assert (skills_dir / "xllm-profile").exists()


def test_link_skill_dirs_does_not_replace_real_directory(tmp_path, monkeypatch):
    source = tmp_path / "skills" / "debug"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: debug\ndescription: debug\n---\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    existing = skills_dir / "debug"
    existing.mkdir(parents=True)
    monkeypatch.setattr(init, "ROOT", tmp_path)

    linked, skipped = init.link_skill_dirs([source], skills_dir)

    assert linked == []
    assert skipped == ["debug (目标已存在且不是软链)"]
    assert existing.is_dir()
    assert not existing.is_symlink()


def test_install_project_skills_links_to_target_dir(tmp_path, monkeypatch):
    source = tmp_path / "skills" / "triage"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: triage\ndescription: triage\n---\n", encoding="utf-8")
    target_dir = tmp_path / ".codex" / "skills"
    monkeypatch.setattr(init, "ROOT", tmp_path)
    monkeypatch.setattr(init, "PROJECT_SKILLS_DIR", tmp_path / "skills")

    linked, skipped = init.install_project_skills(target_dir)

    assert skipped == []
    assert linked[0].startswith("triage -> skills/triage")
    assert (target_dir / "triage").exists()


def test_link_skill_dirs_copies_when_windows_symlink_privilege_is_missing(tmp_path, monkeypatch):
    source = tmp_path / "skills" / "triage"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: triage\ndescription: triage\n---\n", encoding="utf-8")
    skills_dir = tmp_path / ".codex" / "skills"
    monkeypatch.setattr(init, "ROOT", tmp_path)

    def raise_windows_privilege_error(self, target, target_is_directory=False):
        err = OSError("missing privilege")
        err.winerror = 1314
        raise err

    monkeypatch.setattr(Path, "symlink_to", raise_windows_privilege_error)

    linked, skipped = init.link_skill_dirs([source], skills_dir)

    assert skipped == []
    assert linked == ["triage -> skills/triage (copied; symlink unavailable)"]
    assert (skills_dir / "triage" / "SKILL.md").is_file()
