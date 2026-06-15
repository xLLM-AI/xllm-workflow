#!/usr/bin/env python3
"""Check xllm_ops-to-xLLM NPU runtime integration structure."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Callable


class Check(dict):
    def __init__(self, name: str, status: str, severity: str, detail: str) -> None:
        super().__init__(name=name, status=status, severity=severity, detail=detail)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def sanitize_name(name: str) -> str:
    sanitized = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    return sanitized.strip("._-") or "op"


def default_report_path(op_name: str) -> Path:
    skill_dir = Path(__file__).resolve().parents[1]
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{sanitize_name(op_name)}_xllm_ops_integration"
    return skill_dir / "runs" / "eval" / run_id / "harness.json"


def add_file_check(results: list[Check], name: str, path: Path, required: bool = True) -> None:
    exists = path.exists()
    if exists:
        results.append(Check(name, "PASS", "required" if required else "warn", str(path)))
    elif required:
        results.append(Check(name, "FAIL", "required", f"missing: {path}"))
    else:
        results.append(Check(name, "WARN", "warn", f"missing: {path}"))


def add_content_check(
    results: list[Check],
    name: str,
    path: Path,
    predicate: Callable[[str], bool],
    detail: str,
    required: bool = True,
) -> None:
    if not path.exists():
        status = "FAIL" if required else "WARN"
        results.append(Check(name, status, "required" if required else "warn", f"missing: {path}"))
        return
    ok = predicate(read_text(path))
    status = "PASS" if ok else ("FAIL" if required else "WARN")
    results.append(Check(name, status, "required" if required else "warn", detail))


def find_wrapper(npu_xllm_ops_dir: Path, op_name: str, api_symbol: str | None, aclnn_name: str | None) -> Path | None:
    candidates = [npu_xllm_ops_dir / f"{op_name}.cpp"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    needles = [value for value in [api_symbol, aclnn_name, op_name] if value]
    for path in sorted(npu_xllm_ops_dir.glob("*.cpp")):
        text = read_text(path)
        if any(needle in text for needle in needles):
            return path
    return None


def source_checks(results: list[Check], xllm_ops_root: Path | None, op_name: str, aclnn_name: str | None) -> None:
    if xllm_ops_root is None:
        results.append(Check("xllm_ops root provided", "WARN", "warn", "skip source-side checks"))
        return
    add_file_check(results, "xllm_ops root exists", xllm_ops_root)
    op_dir = xllm_ops_root / "xllm_ops" / op_name
    add_file_check(results, "third_party xllm_ops op dir exists", op_dir, required=False)
    build_aclnn = xllm_ops_root / "xllm_ops" / "build_aclnn.sh"
    add_file_check(results, "third_party xllm_ops build_aclnn exists", build_aclnn, required=False)
    if build_aclnn.exists():
        add_content_check(
            results,
            "third_party build_aclnn lists op",
            build_aclnn,
            lambda text: op_name in text,
            f"expect {op_name}",
            required=False,
        )
    if aclnn_name:
        has_aclnn = False
        for path in xllm_ops_root.rglob("*"):
            if path.is_file() and path.suffix in {".h", ".hpp", ".cpp", ".cc"}:
                if aclnn_name in read_text(path):
                    has_aclnn = True
                    break
        results.append(Check("third_party xllm_ops references aclnn", "PASS" if has_aclnn else "WARN", "warn", f"expect {aclnn_name}"))


def target_checks(
    results: list[Check],
    xllm_root: Path,
    op_name: str,
    api_symbol: str | None,
    aclnn_name: str | None,
    callsite_pattern: str | None,
) -> None:
    npu_dir = xllm_root / "xllm" / "core" / "kernels" / "npu"
    npu_xllm_ops_dir = npu_dir / "xllm_ops"
    api_header = npu_xllm_ops_dir / "xllm_ops_api.h"
    cmake = npu_xllm_ops_dir / "CMakeLists.txt"

    add_file_check(results, "xLLM root exists", xllm_root)
    add_file_check(results, "xLLM NPU kernel dir exists", npu_dir)
    add_file_check(results, "xLLM NPU xllm_ops dir exists", npu_xllm_ops_dir)
    add_file_check(results, "xllm_ops_api.h exists", api_header)
    add_file_check(results, "xllm_ops CMakeLists exists", cmake)

    wrapper = find_wrapper(npu_xllm_ops_dir, op_name, api_symbol, aclnn_name) if npu_xllm_ops_dir.exists() else None
    if wrapper is None:
        results.append(Check("xLLM wrapper file exists", "FAIL", "required", f"cannot find wrapper for {op_name}"))
        return
    results.append(Check("xLLM wrapper file exists", "PASS", "required", str(wrapper)))

    wrapper_name = wrapper.name
    add_content_check(
        results,
        "CMake lists wrapper source",
        cmake,
        lambda text: wrapper_name in text,
        f"expect {wrapper_name}",
    )
    expected_symbol = api_symbol or op_name
    add_content_check(
        results,
        "API header declares wrapper",
        api_header,
        lambda text: expected_symbol in text,
        f"expect {expected_symbol}",
    )
    add_content_check(
        results,
        "wrapper uses xllm namespace",
        wrapper,
        lambda text: "namespace xllm::kernel::npu" in text,
        "expect namespace xllm::kernel::npu",
    )
    if aclnn_name:
        add_content_check(
            results,
            "wrapper references aclnn API",
            wrapper,
            lambda text: aclnn_name in text,
            f"expect {aclnn_name}",
        )
    add_content_check(
        results,
        "wrapper uses EXEC_NPU_CMD or aclnn manual path",
        wrapper,
        lambda text: "EXEC_NPU_CMD" in text or "GetWorkspaceSize" in text,
        "expect EXEC_NPU_CMD or manual aclnn workspace path",
        required=False,
    )
    has_sync = any(token in read_text(wrapper) for token in ["aclrtSynchronizeStream", ".cpu()", ".item()"])
    results.append(Check("wrapper avoids obvious host sync", "WARN" if has_sync else "PASS", "warn", str(wrapper)))

    search_root = xllm_root / "xllm"
    if callsite_pattern:
        matches = []
        for path in search_root.rglob("*"):
            if path.is_file() and path.suffix in {".cc", ".cpp", ".h", ".hpp", ".py"}:
                if path == wrapper or npu_xllm_ops_dir in path.parents:
                    continue
                text = read_text(path)
                if callsite_pattern in text or expected_symbol in text:
                    matches.append(str(path.relative_to(xllm_root)))
        detail = ", ".join(matches[:20]) if matches else f"no callsite references {callsite_pattern} or {expected_symbol}"
        results.append(Check("runtime callsite references wrapper", "PASS" if matches else "WARN", "warn", detail))
    else:
        results.append(Check("runtime callsite pattern provided", "WARN", "warn", "pass --callsite-pattern to check runtime path"))


def summarize(results: list[Check]) -> str:
    if any(item["status"] == "FAIL" and item["severity"] == "required" for item in results):
        return "FAIL"
    if any(item["status"] == "WARN" for item in results):
        return "WARN"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xllm-root", required=True, type=Path)
    parser.add_argument("--xllm-ops-root", type=Path)
    parser.add_argument("--op-name", required=True)
    parser.add_argument("--api-symbol")
    parser.add_argument("--aclnn-name")
    parser.add_argument("--callsite-pattern")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report_path = args.report or default_report_path(args.op_name)
    results: list[Check] = []
    xllm_root = args.xllm_root.resolve()
    xllm_ops_root = args.xllm_ops_root.resolve() if args.xllm_ops_root else None
    source_checks(results, xllm_ops_root, args.op_name, args.aclnn_name)
    target_checks(results, xllm_root, args.op_name, args.api_symbol, args.aclnn_name, args.callsite_pattern)
    status = summarize(results)
    report = {
        "status": status,
        "op_name": args.op_name,
        "api_symbol": args.api_symbol,
        "aclnn_name": args.aclnn_name,
        "xllm_root": str(xllm_root),
        "xllm_ops_root": str(xllm_ops_root) if xllm_ops_root else None,
        "report_path": str(report_path.resolve()),
        "checks": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {state: sum(1 for item in results if item["status"] == state) for state in ["PASS", "WARN", "FAIL"]}
    print(json.dumps({"status": status, "checks": len(results), **counts, "report": str(report_path.resolve())}, ensure_ascii=False))
    for item in results:
        if item["status"] != "PASS":
            print(f"{item['status']}: {item['name']}: {item['detail']}")
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
