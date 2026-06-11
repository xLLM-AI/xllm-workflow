#!/usr/bin/env python3
"""Query model PR optimization history.

Searches local model dossier files for PR history, optimization attempts,
known risks, validation notes, and pending ideas.
"""

import argparse
import os
import sys
from pathlib import Path


FRAMEWORKS = {"xllm", "vllm-ascend", "sglang"}


def load_archives(root: str, framework: str | None = None) -> list[dict[str, str]]:
    archives = []
    root_path = Path(root)
    if not root_path.exists():
        return archives

    framework_dirs = [root_path / framework] if framework else [
        path for path in root_path.iterdir() if path.is_dir() and path.name in FRAMEWORKS
    ]
    for framework_dir in framework_dirs:
        if not framework_dir.exists():
            continue
        for md_file in sorted(framework_dir.rglob("*.md")):
            rel = md_file.relative_to(root_path)
            archives.append({
                "framework": rel.parts[0],
                "model": md_file.stem,
                "path": str(rel),
                "content": md_file.read_text(encoding="utf-8"),
            })
    return archives


def search_archives(
    archives: list[dict[str, str]],
    patterns: list[str],
    model: str | None = None,
    path_keyword: str | None = None,
) -> list[dict[str, object]]:
    results = []
    lowered_patterns = [p.lower() for p in patterns if p]
    model_filter = model.lower() if model else None
    path_filter = path_keyword.lower() if path_keyword else None

    for archive in archives:
        haystack = "\n".join([
            archive["framework"],
            archive["model"],
            archive["path"],
            archive["content"],
        ]).lower()

        if model_filter and model_filter not in haystack:
            continue
        if path_filter and path_filter not in archive["content"].lower():
            continue

        match_count = sum(1 for p in lowered_patterns if p in haystack)
        if not lowered_patterns or match_count > 0:
            sections = extract_relevant_sections(archive["content"], lowered_patterns)
            results.append({
                "framework": archive["framework"],
                "model": archive["model"],
                "path": archive["path"],
                "match_count": match_count or 1,
                "sections": sections,
            })

    results.sort(key=lambda r: -r["match_count"])
    return results


def extract_relevant_sections(content: str, patterns: list[str]) -> list[str]:
    sections = []
    lines = content.split("\n")
    current_section = []
    current_header = ""

    for line in lines:
        if line.startswith("## "):
            section_text = "\n".join([current_header] + current_section).lower()
            if current_header and current_section and (
                not patterns or any(p in section_text for p in patterns)
            ):
                sections.append(f"**{current_header}**\n" + "\n".join(current_section[-10:]))
            current_section = []
            current_header = line.strip("# ").strip()
        else:
            current_section.append(line)

    section_text = "\n".join([current_header] + current_section).lower()
    if current_header and current_section and (
        not patterns or any(p in section_text for p in patterns)
    ):
        sections.append(f"**{current_header}**\n" + "\n".join(current_section[-10:]))

    return sections


def format_results(results: list[dict], verbose: bool = False) -> str:
    if not results:
        return "No matching archives found."

    lines = [f"# PR Optimization History Search Results\n"]
    lines.append(f"Found {len(results)} matching model archives.\n")

    for r in results:
        lines.append(f"## {r['framework']}/{r['model']}")
        lines.append(f"Path: `{r['path']}`")
        lines.append(f"Match score: {r['match_count']}\n")

        for section in r["sections"][:5]:
            if verbose:
                lines.append(section)
            else:
                preview = section[:200] + "..." if len(section) > 200 else section
                lines.append(preview)
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query xLLM model PR optimization history")
    parser.add_argument("query", nargs="?", help="Search query (model name, keyword, symbol, PR, etc.)")
    parser.add_argument("--framework", choices=["xllm", "vllm-ascend", "sglang"],
                        help="Only search one framework directory")
    parser.add_argument("--model", help="Filter by model family")
    parser.add_argument("--keyword", action="append", default=[],
                        help="Keyword to search; can be repeated")
    parser.add_argument("--path", dest="path_keyword",
                        help="Filter dossiers containing a file path or symbol")
    parser.add_argument("--archives-dir", default=os.path.join(os.path.dirname(__file__), ".."),
                        help="Path to model-pr-optimization-history directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full section content")
    args = parser.parse_args()

    archives = load_archives(args.archives_dir, args.framework)
    if not archives:
        print(f"No archives found in {args.archives_dir}", file=sys.stderr)
        sys.exit(1)

    patterns = []
    if args.query:
        patterns.extend(args.query.split())
    if args.model:
        patterns.append(args.model)
    patterns.extend(args.keyword)
    if args.path_keyword:
        patterns.append(args.path_keyword)

    results = search_archives(archives, patterns, args.model, args.path_keyword)
    print(format_results(results, args.verbose))


if __name__ == "__main__":
    main()
