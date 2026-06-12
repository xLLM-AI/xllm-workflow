#!/usr/bin/env python3
"""Initialize the local xLLM workspace under code/xllm.

The script is intentionally repeatable:
- It clones xLLM only when code/xllm is missing or empty.
- It records missing repository settings in config.json.
- It links xLLM skills into the parent .agents/skills directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_XLLM_DIR = ROOT / "code" / "xllm"
DEFAULT_SKILLS_DIR = ROOT / ".agents" / "skills"
CONFIG_KEY = "repositories"
XLLM_KEY = "xllm"


class InitError(RuntimeError):
    """Raised for user-correctable initialization errors."""


def run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(cmd)
    print(f"[run] {printable}")
    subprocess.run(cmd, cwd=cwd, check=True)


def load_config(path: Path) -> dict[str, Any]:
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


def normalize_repo_config(config: dict[str, Any]) -> dict[str, Any]:
    repositories = config.setdefault(CONFIG_KEY, {})
    if not isinstance(repositories, dict):
        raise InitError(f"config.json 中 `{CONFIG_KEY}` 必须是对象。")

    repo = repositories.setdefault(XLLM_KEY, {})
    if not isinstance(repo, dict):
        raise InitError(f"config.json 中 `{CONFIG_KEY}.{XLLM_KEY}` 必须是对象。")
    return repo


def resolve_repo_config(
    config: dict[str, Any],
    config_path: Path,
    repo_url: str | None,
    ref: str | None,
    ref_type: str | None,
    assume_yes: bool,
) -> dict[str, str]:
    repo = normalize_repo_config(config)
    changed = False

    if repo_url:
        repo["url"] = repo_url
        changed = True
    if ref:
        repo["ref"] = ref
        changed = True
    if ref_type:
        repo["ref_type"] = ref_type
        changed = True

    missing = [key for key in ("url", "ref", "ref_type") if not repo.get(key)]
    if missing:
        if assume_yes or not sys.stdin.isatty():
            raise InitError(
                "缺少 xLLM 仓库配置。请使用参数补齐，例如: "
                "python scripts/init_xllm_workspace.py "
                "--repo-url <git-url> --ref <branch-or-commit> --ref-type branch"
            )

        print("config.json 缺少 xLLM 仓库配置，请输入后脚本会写回 config.json。")
        if not repo.get("url"):
            repo["url"] = prompt_required("xLLM git 仓库 URL")
            changed = True
        if not repo.get("ref"):
            repo["ref"] = prompt_required("xLLM 分支名或 commit")
            changed = True
        if not repo.get("ref_type"):
            repo["ref_type"] = prompt_ref_type(str(repo["ref"]))
            changed = True

    if repo.get("ref_type") not in {"branch", "commit"}:
        raise InitError("xLLM ref_type 必须是 branch 或 commit。")

    if changed:
        save_config(config_path, config)
        print(f"[config] 已更新 {display_path(config_path)}")

    return {
        "url": str(repo["url"]),
        "ref": str(repo["ref"]),
        "ref_type": str(repo["ref_type"]),
    }


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


def relative_symlink_target(source: Path, link: Path) -> str:
    return os.path.relpath(source.resolve(), link.parent.resolve())


def link_xllm_skills(xllm_dir: Path, skills_dir: Path) -> tuple[list[str], list[str]]:
    skills_dir.mkdir(parents=True, exist_ok=True)
    linked: list[str] = []
    skipped: list[str] = []

    for source in find_skill_dirs(xllm_dir):
        link_name = f"xllm-{source.name}"
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


def print_summary(xllm_dir: Path, linked: list[str], skipped: list[str]) -> None:
    print()
    print("初始化完成。")
    print(f"- xLLM 目录: {display_path(xllm_dir)}")

    if linked:
        print("- 已链接 xLLM skills:")
        for item in linked:
            print(f"  - {item}")
    else:
        print("- 未发现可链接的 xLLM skills。")

    if skipped:
        print("- 以下 skill 链接被跳过:")
        for item in skipped:
            print(f"  - {item}")

    print()
    print("请在当前目录启动 Codex:")
    print(f"  cd {ROOT}")
    print("  codex")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize code/xllm for Codex.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="配置文件路径")
    parser.add_argument("--xllm-dir", type=Path, default=DEFAULT_XLLM_DIR, help="xLLM 代码目录")
    parser.add_argument("--repo-url", help="xLLM git 仓库 URL，会写入 config.json")
    parser.add_argument("--ref", help="xLLM 分支名或 commit，会写入 config.json")
    parser.add_argument("--ref-type", choices=["branch", "commit"], help="ref 类型")
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
        linked, skipped = link_xllm_skills(xllm_dir, DEFAULT_SKILLS_DIR)
        print_summary(xllm_dir, linked, skipped)
    except subprocess.CalledProcessError as exc:
        print(f"[error] 命令执行失败，退出码 {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode
    except InitError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
