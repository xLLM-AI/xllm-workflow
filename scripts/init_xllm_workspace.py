#!/usr/bin/env python3
"""Initialize the local xLLM workspace under code/xllm.

The script is intentionally repeatable:
- It clones xLLM only when code/xllm is missing or empty.
- It records missing repository settings in config.json.
- It can prepare the parent workspace .agents/skills directory.
- It can install this project's skills into a Codex or Claude skills directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_CONFIG_TEMPLATE = ROOT / "config.example.json"
DEFAULT_XLLM_DIR = ROOT / "code" / "xllm"
PROJECT_SKILLS_DIR = ROOT / "skills"
WORKSPACE_SKILLS_DIR = ROOT / ".agents" / "skills"
CODE_KEY = "code"
LEGACY_CONFIG_KEY = "repositories"
XLLM_KEY = "xllm"


class InitError(RuntimeError):
    """Raised for user-correctable initialization errors."""


def run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(cmd)
    print(f"[run] {printable}")
    subprocess.run(cmd, cwd=cwd, check=True)


def load_config(path: Path, template_path: Path = DEFAULT_CONFIG_TEMPLATE) -> dict[str, Any]:
    if not path.exists():
        if template_path.exists() and path.name == "config.json":
            shutil.copyfile(template_path, path)
            print(f"[config] 已从 {display_path(template_path)} 生成 {display_path(path)}")
        else:
            return {}
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InitError(f"配置文件不是合法 JSON: {path} ({exc})") from exc


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def prompt_required(label: str) -> str:
    value = input(f"{label}: ").strip()
    while not value:
        print("不能为空，请重新输入。")
        value = input(f"{label}: ").strip()
    return value


def infer_ref_type(ref: str) -> str | None:
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        return "commit"
    return None


def prompt_ref_type(ref: str) -> str:
    inferred = infer_ref_type(ref)
    if inferred:
        question = "ref 类型 [branch/commit] (默认 commit): "
        default = "commit"
    else:
        question = "ref 类型 [branch/commit] (默认 branch): "
        default = "branch"

    while True:
        value = input(question).strip().lower() or default
        if value in {"branch", "commit"}:
            return value
        print("请输入 branch 或 commit。")


def ensure_dict(parent: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = parent.setdefault(key, {})
    if not isinstance(value, dict):
        raise InitError(f"config.json 中 `{label}` 必须是对象。")
    return value


def normalize_repo_config(config: dict[str, Any]) -> dict[str, Any]:
    code = ensure_dict(config, CODE_KEY, CODE_KEY)
    repo = ensure_dict(code, XLLM_KEY, f"{CODE_KEY}.{XLLM_KEY}")
    origin = ensure_dict(repo, "origin", f"{CODE_KEY}.{XLLM_KEY}.origin")
    upstream = ensure_dict(repo, "upstream", f"{CODE_KEY}.{XLLM_KEY}.upstream")
    repo.setdefault("path", "code/xllm")
    origin.setdefault("url", "")
    origin.setdefault("branch", "")
    origin.setdefault("commit", "")
    upstream.setdefault("url", "")
    upstream.setdefault("branch", "")
    upstream.setdefault("commit", "")

    legacy = config.get(LEGACY_CONFIG_KEY, {})
    if isinstance(legacy, dict) and isinstance(legacy.get(XLLM_KEY), dict):
        legacy_repo = legacy[XLLM_KEY]
        if legacy_repo.get("url") and not origin.get("url"):
            origin["url"] = legacy_repo["url"]
        legacy_ref = legacy_repo.get("ref")
        legacy_ref_type = legacy_repo.get("ref_type") or infer_ref_type(str(legacy_ref or ""))
        if legacy_ref and legacy_ref_type == "commit" and not origin.get("commit"):
            origin["commit"] = legacy_ref
        elif legacy_ref and not origin.get("branch"):
            origin["branch"] = legacy_ref

    return repo


def selected_repo_source(repo: dict[str, Any]) -> dict[str, str]:
    origin = repo["origin"]
    upstream = repo["upstream"]
    url = str(origin.get("url") or upstream.get("url") or "")
    commit = str(origin.get("commit") or upstream.get("commit") or "")
    branch = str(origin.get("branch") or upstream.get("branch") or "")

    if commit:
        return {"url": url, "ref": commit, "ref_type": "commit"}
    return {"url": url, "ref": branch, "ref_type": "branch"}


def resolve_repo_config(
    config: dict[str, Any],
    config_path: Path,
    repo_url: str | None,
    ref: str | None,
    ref_type: str | None,
    assume_yes: bool,
) -> dict[str, str]:
    repo = normalize_repo_config(config)
    origin = repo["origin"]
    changed = False

    if repo_url:
        origin["url"] = repo_url
        changed = True
    if ref:
        effective_ref_type = ref_type or infer_ref_type(ref) or "branch"
        if effective_ref_type == "commit":
            origin["commit"] = ref
        else:
            origin["branch"] = ref
        changed = True

    selected = selected_repo_source(repo)
    missing = []
    if not selected["url"]:
        missing.append("origin.url")
    if not selected["ref"]:
        missing.append("origin.branch 或 origin.commit")
    if missing:
        if assume_yes or not sys.stdin.isatty():
            raise InitError(
                "缺少 xLLM 仓库配置。请使用参数补齐，例如: "
                "python scripts/init_xllm_workspace.py "
                "--repo-url <git-url> --ref <branch-or-commit> --ref-type branch"
            )

        print("config.json 缺少 xLLM 仓库配置，请输入后脚本会写回 config.json。")
        if not selected["url"]:
            origin["url"] = prompt_required("xLLM origin git 仓库 URL")
            changed = True
        if not selected["ref"]:
            entered_ref = prompt_required("xLLM 分支名或 commit")
            entered_ref_type = prompt_ref_type(entered_ref)
            if entered_ref_type == "commit":
                origin["commit"] = entered_ref
            else:
                origin["branch"] = entered_ref
            changed = True

    selected = selected_repo_source(repo)

    if changed:
        save_config(config_path, config)
        print(f"[config] 已更新 {display_path(config_path)}")

    return selected


def dir_has_code(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def clone_xllm(repo: dict[str, str], target_dir: Path) -> None:
    if dir_has_code(target_dir):
        if (target_dir / ".git").exists():
            print(f"[code] {display_path(target_dir)} 已存在 git 仓库，跳过 clone。")
        else:
            print(f"[code] {display_path(target_dir)} 非空，跳过 clone。")
        return

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        target_dir.rmdir()

    if repo["ref_type"] == "branch":
        run([
            "git",
            "clone",
            "--branch",
            repo["ref"],
            "--single-branch",
            repo["url"],
            str(target_dir),
        ])
    else:
        run(["git", "clone", repo["url"], str(target_dir)])
        run(["git", "checkout", repo["ref"]], cwd=target_dir)


def find_skill_dirs(xllm_dir: Path) -> list[Path]:
    roots = [
        xllm_dir / ".agents" / "skills",
        xllm_dir / "skills",
    ]
    skill_dirs: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not (child / "SKILL.md").is_file():
                continue
            resolved = child.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            skill_dirs.append(child)
    return skill_dirs


def find_project_skill_dirs(project_skills_dir: Path | None = None) -> list[Path]:
    project_skills_dir = project_skills_dir or PROJECT_SKILLS_DIR
    if not project_skills_dir.is_dir():
        return []
    return [
        child
        for child in sorted(project_skills_dir.iterdir())
        if (child / "SKILL.md").is_file()
    ]


def relative_symlink_target(source: Path, link: Path) -> str:
    return os.path.relpath(source.resolve(), link.parent.resolve())


def link_skill_dirs(
    skill_dirs: list[Path],
    skills_dir: Path,
    name_prefix: str = "",
) -> tuple[list[str], list[str]]:
    skills_dir.mkdir(parents=True, exist_ok=True)
    linked: list[str] = []
    skipped: list[str] = []

    for source in skill_dirs:
        link_name = f"{name_prefix}{source.name}"
        link = skills_dir / link_name

        if link.exists() and not link.is_symlink():
            skipped.append(f"{link_name} (目标已存在且不是软链)")
            continue

        target = relative_symlink_target(source, link)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target, target_is_directory=True)
        linked.append(f"{link_name} -> {display_path(source)}")

    return linked, skipped


def link_workspace_skills(xllm_dir: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    project_linked, project_skipped = link_skill_dirs(
        find_project_skill_dirs(),
        WORKSPACE_SKILLS_DIR,
    )
    xllm_linked, xllm_skipped = link_skill_dirs(
        find_skill_dirs(xllm_dir),
        WORKSPACE_SKILLS_DIR,
        name_prefix="xllm-",
    )
    return project_linked, project_skipped, xllm_linked, xllm_skipped


def default_agent_skills_dir(agent: str) -> Path:
    if agent == "codex":
        return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser() / "skills"
    if agent == "claude":
        return Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude"))).expanduser() / "skills"
    raise InitError(f"未知 agent 类型: {agent}")


def install_project_skills(target_dir: Path) -> tuple[list[str], list[str]]:
    return link_skill_dirs(find_project_skill_dirs(), target_dir)


def print_workspace_summary(
    xllm_dir: Path,
    project_linked: list[str],
    project_skipped: list[str],
    xllm_linked: list[str],
    xllm_skipped: list[str],
) -> None:
    print()
    print("初始化完成。")
    print(f"- xLLM 目录: {display_path(xllm_dir)}")

    if project_linked:
        print("- 已链接本项目 skills 到 .agents/skills:")
        for item in project_linked:
            print(f"  - {item}")
    else:
        print("- 未发现可链接的本项目 skills。")

    if xllm_linked:
        print("- 已链接 xLLM 仓内 skills 到 .agents/skills:")
        for item in xllm_linked:
            print(f"  - {item}")
    else:
        print("- 未发现可链接的 xLLM 仓内 skills。")

    skipped = project_skipped + xllm_skipped
    if skipped:
        print("- 以下 skill 链接被跳过:")
        for item in skipped:
            print(f"  - {item}")

    print()
    print("请在当前目录启动 Codex:")
    print(f"  cd {ROOT}")
    print("  codex")


def print_xllm_summary(
    xllm_dir: Path,
    target_dir: Path,
    agent: str,
    linked: list[str],
    skipped: list[str],
) -> None:
    print()
    print("初始化完成。")
    print(f"- xLLM 目录: {display_path(xllm_dir)}")
    print(f"- {agent} skills 目录: {target_dir}")

    if linked:
        print("- 已安装本项目 skills:")
        for item in linked:
            print(f"  - {item}")
    else:
        print("- 未发现可安装的本项目 skills。")

    if skipped:
        print("- 以下 skill 链接被跳过:")
        for item in skipped:
            print(f"  - {item}")

    command = "codex" if agent == "codex" else "claude"
    print()
    print("请在 xLLM 目录启动 code agent:")
    print(f"  cd {xllm_dir}")
    print(f"  {command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize code/xllm for Codex.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="配置文件路径")
    parser.add_argument("--xllm-dir", type=Path, default=DEFAULT_XLLM_DIR, help="xLLM 代码目录")
    parser.add_argument("--repo-url", help="xLLM git 仓库 URL，会写入 config.json")
    parser.add_argument("--ref", help="xLLM 分支名或 commit，会写入 config.json")
    parser.add_argument("--ref-type", choices=["branch", "commit"], help="ref 类型")
    parser.add_argument(
        "--mode",
        choices=["workspace", "xllm"],
        default="workspace",
        help="workspace: 在本项目根目录启动 agent；xllm: 在 code/xllm 下启动 agent",
    )
    parser.add_argument(
        "--install-project-skills",
        action="store_true",
        help="方式 2 快捷参数：把本项目 skills 安装到 agent skills 目录，并在 code/xllm 下启动",
    )
    parser.add_argument("--agent", choices=["codex", "claude"], default="codex", help="方式 2 的 code agent 类型")
    parser.add_argument("--target-dir", type=Path, help="方式 2 的 skills 安装目录；默认按 --agent 选择")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="非交互模式；缺少配置时直接失败，适合 CI 或自动化",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    xllm_dir = args.xllm_dir.resolve()
    mode = "xllm" if args.install_project_skills else args.mode

    try:
        config = load_config(config_path)
        repo = resolve_repo_config(
            config,
            config_path,
            args.repo_url,
            args.ref,
            args.ref_type,
            args.yes,
        )
        clone_xllm(repo, xllm_dir)
        if mode == "workspace":
            project_linked, project_skipped, xllm_linked, xllm_skipped = link_workspace_skills(xllm_dir)
            print_workspace_summary(xllm_dir, project_linked, project_skipped, xllm_linked, xllm_skipped)
        else:
            target_dir = (args.target_dir.expanduser() if args.target_dir else default_agent_skills_dir(args.agent)).resolve()
            linked, skipped = install_project_skills(target_dir)
            print_xllm_summary(xllm_dir, target_dir, args.agent, linked, skipped)
    except subprocess.CalledProcessError as exc:
        print(f"[error] 命令执行失败，退出码 {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode
    except InitError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
