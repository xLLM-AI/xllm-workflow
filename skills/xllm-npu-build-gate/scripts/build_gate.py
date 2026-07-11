#!/usr/bin/env python3
"""Deterministic xLLM build preflight, plan selection, and provenance gate."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shlex
import subprocess
import sys
import time
from typing import Any


SCHEMA_VERSION = 1
RECONFIGURE_PREFIXES = (
    ".gitmodules",
    "CMakeLists.txt",
    "cmake/",
    "setup.py",
    "pyproject.toml",
    "third_party/",
)
TILELANG_MARKERS = ("tilelang", ".tl", "kernels/")
SAFE_ENV_KEYS = (
    "ATB_HOME_PATH",
    "ASCEND_HOME_PATH",
    "ASCEND_OPP_PATH",
    "ASCEND_CUSTOM_OPP_PATH",
    "CMAKE_BUILD_PARALLEL_LEVEL",
    "CTEST_PARALLEL",
    "CTEST_PARALLEL_LEVEL",
    "LD_LIBRARY_PATH",
    "LIBTORCH_ROOT",
    "MAX_JOBS",
    "PYTHON_INCLUDE_PATH",
    "PYTHON_LIB_PATH",
    "PYTORCH_INSTALL_PATH",
    "PYTORCH_NPU_INSTALL_PATH",
    "XLLM_OPP_MARKER",
)


class GateError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        rendered = shlex.join(command)
        detail = result.stderr.strip() or result.stdout.strip()
        raise GateError(f"command failed ({result.returncode}): {rendered}: {detail}")
    return result


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args], check=check)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def command_output(command: list[str]) -> dict[str, Any]:
    result = run(command, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def resolve_repo(path: Path) -> tuple[Path, dict[str, Any]]:
    requested = path.resolve()
    bare = git(requested, "rev-parse", "--is-bare-repository").stdout.strip() == "true"
    if bare:
        raise GateError("bare repositories cannot produce a build binary; use a checkout or worktree")
    root = Path(git(requested, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    git_dir = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip()).resolve()
    common_dir_text = git(root, "rev-parse", "--git-common-dir").stdout.strip()
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    return root, {
        "requested_path": str(requested),
        "root": str(root),
        "git_dir": str(git_dir),
        "git_common_dir": str(common_dir),
        "kind": "linked_worktree" if git_dir != common_dir else "checkout",
        "is_bare": False,
    }


def choose_base_ref(repo: Path, requested: str | None) -> str:
    candidates = [requested] if requested else ["origin/main", "main", "HEAD^"]
    for candidate in candidates:
        if candidate and git(repo, "rev-parse", "--verify", candidate, check=False).returncode == 0:
            return candidate
    return "HEAD"


def collect_changed_paths(repo: Path, base_ref: str) -> list[str]:
    paths: set[str] = set()
    comparisons = [
        ["diff", "--name-only", f"{base_ref}...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
    ]
    for arguments in comparisons:
        result = git(repo, *arguments, check=False)
        if result.returncode == 0:
            paths.update(line for line in result.stdout.splitlines() if line)
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", check=False)
    paths.update(line for line in untracked.stdout.splitlines() if line)
    return sorted(paths)


def collect_submodules(repo: Path, output_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    result = git(repo, "submodule", "status", "--recursive", check=False)
    raw = result.stdout
    if result.stderr:
        raw += ("\n" if raw else "") + result.stderr
    output_path.write_text(raw, encoding="utf-8")
    entries: list[dict[str, str]] = []
    blockers: list[str] = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(.)([0-9a-f]+)\s+(\S+)(?:\s+\((.*)\))?$", line)
        if not match:
            continue
        prefix, commit, path, description = match.groups()
        state = {
            " ": "clean",
            "-": "uninitialized",
            "+": "commit_mismatch",
            "U": "conflict",
        }.get(prefix, "unknown")
        entries.append(
            {
                "path": path,
                "commit": commit,
                "state": state,
                "description": description or "",
            }
        )
        if state in {"uninitialized", "commit_mismatch", "conflict", "unknown"}:
            blockers.append(f"submodule_{state}:{path}")
    if result.returncode != 0:
        blockers.append("submodule_status_failed")
    return entries, blockers


def parse_cmake_cache(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line or ":" not in line:
            continue
        key_type, value = line.split("=", 1)
        key, _kind = key_type.split(":", 1)
        values[key] = value
    return values


def architecture_matches_file_output(machine: str, output: str) -> bool:
    normalized = machine.lower()
    if normalized in {"aarch64", "arm64"}:
        return "aarch64" in output.lower() or "arm64" in output.lower()
    if normalized in {"x86_64", "amd64"}:
        return "x86-64" in output.lower() or "x86_64" in output.lower()
    return normalized in output.lower()


def discover_build_dir(repo: Path, requested: Path | None) -> Path | None:
    if requested:
        return requested.resolve()
    candidates = sorted((repo / "build").glob("cmake.*")) if (repo / "build").is_dir() else []
    matching = [path for path in candidates if (path / "CMakeCache.txt").is_file()]
    return matching[-1].resolve() if matching else None


def cmake_identity(repo: Path, build_dir: Path | None) -> tuple[dict[str, Any], list[str]]:
    if build_dir is None:
        return {"build_dir": None, "cache_present": False}, ["cmake_cache_missing"]
    cache_path = build_dir / "CMakeCache.txt"
    cache = parse_cmake_cache(cache_path)
    identity: dict[str, Any] = {
        "build_dir": str(build_dir),
        "cache_path": str(cache_path),
        "cache_present": bool(cache),
        "cache_sha256": sha256_file(cache_path) if cache_path.is_file() else None,
        "source_dir": cache.get("CMAKE_HOME_DIRECTORY"),
        "system_processor": cache.get("CMAKE_SYSTEM_PROCESSOR"),
        "cxx_compiler": cache.get("CMAKE_CXX_COMPILER"),
        "python_executable": next(
            (
                cache[key]
                for key in (
                    "Python_EXECUTABLE",
                    "Python3_EXECUTABLE",
                    "PYTHON_EXECUTABLE",
                )
                if key in cache
            ),
            None,
        ),
        "torch_dir": cache.get("Torch_DIR"),
    }
    mismatches: list[str] = []
    if not cache:
        mismatches.append("cmake_cache_missing")
        return identity, mismatches
    if identity["source_dir"] and Path(identity["source_dir"]).resolve() != repo:
        mismatches.append("cmake_source_mismatch")
    cached_python = identity["python_executable"]
    if cached_python and Path(cached_python).resolve() != Path(sys.executable).resolve():
        mismatches.append("python_abi_mismatch")
    cached_arch = (identity["system_processor"] or "").lower()
    current_arch = platform.machine().lower()
    aliases = {"arm64": "aarch64", "amd64": "x86_64"}
    if aliases.get(cached_arch, cached_arch) != aliases.get(current_arch, current_arch):
        mismatches.append("cmake_architecture_mismatch")
    cached_libtorch = build_dir / "_deps/libtorch-src/lib/libtorch.so"
    if cached_libtorch.is_file():
        probe = command_output(["file", str(cached_libtorch)])
        identity["cached_libtorch"] = probe
        if probe["returncode"] != 0 or not architecture_matches_file_output(
            current_arch, probe["stdout"]
        ):
            mismatches.append("cached_libtorch_architecture_mismatch")
    return identity, mismatches


def file_fingerprints(repo: Path) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    candidates = [
        repo / ".gitmodules",
        repo / "CMakeLists.txt",
        repo / "setup.py",
        repo / "pyproject.toml",
    ]
    for path in candidates:
        if path.is_file():
            fingerprints[str(path.relative_to(repo))] = sha256_file(path)
    return fingerprints


def untracked_fingerprints(repo: Path) -> dict[str, str]:
    result = git(repo, "ls-files", "--others", "--exclude-standard", "-z", check=False)
    fingerprints: dict[str, str] = {}
    for relative in (item for item in result.stdout.split("\0") if item):
        path = repo / relative
        if path.is_file():
            fingerprints[relative] = sha256_file(path)
    return fingerprints


def find_opp_marker(repo: Path, requested: Path | None) -> Path | None:
    candidates: list[Path] = []
    if requested:
        candidates.append(requested)
    env_marker = os.environ.get("XLLM_OPP_MARKER")
    if env_marker:
        candidates.append(Path(env_marker))
    for root in os.environ.get("ASCEND_CUSTOM_OPP_PATH", "").split(":"):
        if root:
            candidates.append(Path(root) / ".xllm_ops_git_head")
    candidates.append(repo / "third_party/xllm_ops/.xllm_ops_git_head")
    return next((path.resolve() for path in candidates if path.is_file()), None)


def xllm_ops_identity(repo: Path, marker_path: Path | None) -> dict[str, Any]:
    source = repo / "third_party/xllm_ops"
    source_head = None
    if source.is_dir() and git(source, "rev-parse", "HEAD", check=False).returncode == 0:
        source_head = git(source, "rev-parse", "HEAD").stdout.strip()
    marker = find_opp_marker(repo, marker_path)
    marker_head = marker.read_text(encoding="utf-8").strip() if marker else None
    return {
        "source_path": str(source),
        "source_head": source_head,
        "marker_path": str(marker) if marker else None,
        "marker_head": marker_head,
        "matches": bool(source_head and marker_head and source_head == marker_head),
        "rebuild_required": bool(source_head and source_head != marker_head),
    }


def required_patch_identity(repo: Path, patch_paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    blockers: list[str] = []
    for raw_path in patch_paths:
        path = raw_path.resolve()
        record: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
        if not path.is_file():
            blockers.append(f"required_patch_missing:{path}")
            records.append(record)
            continue
        record["sha256"] = sha256_file(path)
        reverse = run(
            ["git", "-C", str(repo), "apply", "--reverse", "--check", str(path)],
            check=False,
        )
        record["applied"] = reverse.returncode == 0
        if not record["applied"]:
            blockers.append(f"required_patch_not_applied:{path}")
        records.append(record)
    return records, blockers


def collect_toolchain(skip: bool) -> tuple[dict[str, Any], list[str]]:
    record: dict[str, Any] = {
        "skipped": skip,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "machine": platform.machine(),
    }
    if skip:
        return record, []
    blockers: list[str] = []
    probe = run(
        [
            "timeout",
            "30",
            sys.executable,
            "-c",
            (
                "import json, os, sysconfig, torch, torch_npu; "
                "print(json.dumps({'python_include': sysconfig.get_paths()['include'], "
                "'torch_root': os.path.dirname(torch.__file__), "
                "'torch_cxx11_abi': bool(torch.compiled_with_cxx11_abi())}))"
            ),
        ],
        check=False,
    )
    record["python_torch_probe"] = {
        "returncode": probe.returncode,
        "stderr": probe.stderr.strip(),
    }
    if probe.returncode == 0:
        record.update(json.loads(probe.stdout))
        if not Path(record["python_include"]).is_dir():
            blockers.append("python_headers_missing")
        torch_library = Path(record["torch_root"]) / "lib/libtorch.so"
        record["libtorch"] = command_output(["file", str(torch_library)])
        if record["libtorch"]["returncode"] != 0:
            blockers.append("libtorch_missing")
        elif not architecture_matches_file_output(
            platform.machine(), record["libtorch"]["stdout"]
        ):
            blockers.append("libtorch_architecture_mismatch")
    else:
        blockers.append("torch_or_python_probe_failed")
    atb_home = os.environ.get("ATB_HOME_PATH")
    atb_header = Path(atb_home) / "include/atb/atb_infer.h" if atb_home else None
    record["atb_header"] = str(atb_header) if atb_header else None
    record["atb_header_present"] = bool(atb_header and atb_header.is_file())
    if not record["atb_header_present"]:
        blockers.append("atb_headers_missing")
    return record, blockers


def collect_npu_gate(require: bool, device_root: Path) -> tuple[dict[str, Any], list[str]]:
    record: dict[str, Any] = {"required": require, "device_root": str(device_root)}
    if not require:
        record["skipped"] = True
        return record, []
    blockers: list[str] = []
    probe = run(["timeout", "30", "npu-smi", "info"], check=False)
    record["npu_smi"] = {
        "returncode": probe.returncode,
        "stdout": probe.stdout.strip(),
        "stderr": probe.stderr.strip(),
    }
    if probe.returncode != 0:
        blockers.append("npu_smi_failed")
    required_nodes = ["davinci_manager", "devmm_svm", "hisi_hdc"]
    node_status = {
        name: (device_root / name).exists()
        for name in required_nodes
    }
    davinci_devices = sorted(
        str(path) for path in device_root.glob("davinci[0-9]*") if path.exists()
    )
    record["device_nodes"] = node_status
    record["davinci_devices"] = davinci_devices
    blockers.extend(f"npu_device_node_missing:{name}" for name, present in node_status.items() if not present)
    if not davinci_devices:
        blockers.append("npu_device_node_missing:davinciN")
    processes = run(
        ["pgrep", "-af", "xllm|vllm|sglang|python|evalscope|msprof"],
        check=False,
    )
    record["related_processes"] = processes.stdout.splitlines()
    return record, blockers


def choose_strategy(
    *,
    changed_paths: list[str],
    cmake_mismatches: list[str],
    submodules: list[dict[str, str]],
    repo_kind: str,
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    actions: list[str] = []
    mismatch_paths = [entry["path"] for entry in submodules if entry["state"] == "commit_mismatch"]
    reconfigure_paths = [
        path for path in changed_paths if path.startswith(RECONFIGURE_PREFIXES)
    ]
    tilelang_paths = [
        path for path in changed_paths if any(marker in path.lower() for marker in TILELANG_MARKERS)
    ]
    if cmake_mismatches or mismatch_paths or reconfigure_paths:
        strategy = "reconfigure"
        reasons.extend(cmake_mismatches)
        reasons.extend(f"submodule_commit_changed:{path}" for path in mismatch_paths)
        reasons.extend(f"configure_input_changed:{path}" for path in reconfigure_paths)
        actions.extend(["close_submodules", "run_configure_build"])
    elif tilelang_paths:
        strategy = "tilelang-targeted"
        reasons.extend(f"tilelang_changed:{path}" for path in tilelang_paths)
        actions.append("build_affected_tilelang_families")
    else:
        strategy = "incremental"
        reasons.append("cmake_identity_matches")
        if changed_paths:
            reasons.extend(f"ordinary_source_changed:{path}" for path in changed_paths)
        actions.append("build_incremental_xllm_target")
    if repo_kind == "linked_worktree":
        reasons.append("linked_worktree_detected")
    return strategy, reasons, actions


def parse_build_env(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise GateError(f"--build-env must use KEY=VALUE: {value}")
        key, item = value.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise GateError(f"invalid environment variable name: {key}")
        parsed[key] = item
    return parsed


def selected_commands(args: argparse.Namespace, strategy: str, ops_rebuild: bool) -> list[str]:
    commands: list[str] = []
    if ops_rebuild:
        if not args.xllm_ops_command:
            return []
        commands.append(args.xllm_ops_command)
    mapping = {
        "reconfigure": args.configure_command,
        "incremental": args.incremental_command,
        "tilelang-targeted": args.tilelang_command,
    }
    command = mapping[strategy]
    if command:
        commands.append(command)
    return commands


def execute_commands(
    repo: Path,
    commands: list[str],
    environment: dict[str, str],
    log_path: Path,
    no_output_timeout: int,
) -> tuple[int, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        for command in commands:
            log.write(f"$ {command}\n")
            log.flush()
            process = subprocess.Popen(
                ["bash", "-lc", command],
                cwd=repo,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            last_output_at = time.monotonic()
            last_output = ""
            timed_out = False
            while process.poll() is None:
                events = selector.select(timeout=0.2)
                if events:
                    line = process.stdout.readline()
                    if line:
                        last_output = line.rstrip()
                        last_output_at = time.monotonic()
                        log.write(line)
                        log.flush()
                        sys.stdout.write(line)
                if time.monotonic() - last_output_at >= no_output_timeout:
                    timed_out = True
                    message = (
                        f"BUILD_GATE_TIMEOUT: no output for {no_output_timeout}s; "
                        f"last_output={last_output!r}\n"
                    )
                    log.write(message)
                    log.flush()
                    sys.stderr.write(message)
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
            selector.close()
            for line in process.stdout:
                last_output = line.rstrip()
                log.write(line)
                sys.stdout.write(line)
            returncode = process.wait()
            if timed_out:
                returncode = 124
            records.append(
                {
                    "command": command,
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "last_output": last_output,
                }
            )
            if returncode != 0:
                return returncode, records
    return 0, records


def binary_provenance(binary: Path | None) -> tuple[dict[str, Any], list[str]]:
    if binary is None:
        return {"path": None, "ready": False}, ["binary_path_not_provided"]
    path = binary.resolve()
    record: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "executable": os.access(path, os.X_OK),
    }
    failures: list[str] = []
    if not path.is_file():
        failures.append("binary_missing")
        record["ready"] = False
        return record, failures
    record["sha256"] = sha256_file(path)
    record["size_bytes"] = path.stat().st_size
    record["file"] = command_output(["file", str(path)])
    record["ldd_r"] = command_output(["ldd", "-r", str(path)])
    if not record["executable"]:
        failures.append("binary_not_executable")
    if record["file"]["returncode"] != 0:
        failures.append("binary_file_probe_failed")
    elif "ELF" not in record["file"]["stdout"]:
        failures.append("binary_not_elf")
    if record["ldd_r"]["returncode"] != 0:
        failures.append("binary_ldd_failed")
    ldd_text = f"{record['ldd_r']['stdout']}\n{record['ldd_r']['stderr']}"
    if "not found" in ldd_text:
        failures.append("binary_dependency_missing")
    record["ready"] = not failures
    return record, failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="xLLM checkout/worktree")
    parser.add_argument("--run-root", type=Path, required=True, help="artifact run root")
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--required-patch", action="append", type=Path, default=[])
    parser.add_argument("--opp-marker", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--configure-command")
    parser.add_argument("--incremental-command")
    parser.add_argument("--tilelang-command")
    parser.add_argument("--xllm-ops-command")
    parser.add_argument("--build-env", action="append", default=[])
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 16))
    parser.add_argument("--tilelang-worker-cap", type=int, default=16)
    parser.add_argument("--tilelang-start-method", choices=("spawn", "fork", "forkserver"), default="spawn")
    parser.add_argument("--no-output-timeout", type=int, default=900)
    parser.add_argument("--skip-toolchain-checks", action="store_true")
    parser.add_argument("--require-npu", action="store_true")
    parser.add_argument("--device-root", type=Path, default=Path("/dev"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact_dir = args.run_root.resolve() / "build"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    build_log = artifact_dir / "build.log"
    if not build_log.exists():
        build_log.write_text("Build not executed.\n", encoding="utf-8")

    status = "BLOCKED"
    phase = "preflight"
    blockers: list[str] = []
    failures: list[str] = []
    try:
        repo, repo_identity = resolve_repo(args.repo)
        base_ref = choose_base_ref(repo, args.base_ref)
        changed_paths = collect_changed_paths(repo, base_ref)
        submodules, submodule_blockers = collect_submodules(
            repo, artifact_dir / "submodules.txt"
        )
        blockers.extend(submodule_blockers)
        build_dir = discover_build_dir(repo, args.build_dir)
        cmake, cmake_mismatches = cmake_identity(repo, build_dir)
        toolchain, toolchain_blockers = collect_toolchain(args.skip_toolchain_checks)
        blockers.extend(toolchain_blockers)
        npu_gate, npu_blockers = collect_npu_gate(args.require_npu, args.device_root)
        blockers.extend(npu_blockers)
        patches, patch_blockers = required_patch_identity(repo, args.required_patch)
        blockers.extend(patch_blockers)
        ops = xllm_ops_identity(repo, args.opp_marker)
        strategy, reasons, actions = choose_strategy(
            changed_paths=changed_paths,
            cmake_mismatches=cmake_mismatches,
            submodules=submodules,
            repo_kind=repo_identity["kind"],
        )
        if ops["rebuild_required"]:
            actions.insert(0, "rebuild_and_install_xllm_ops")
            reasons.append("xllm_ops_head_does_not_match_opp_marker")

        if args.jobs < 1 or args.tilelang_worker_cap < 1 or args.no_output_timeout < 1:
            raise GateError(
                "--jobs, --tilelang-worker-cap, and --no-output-timeout must be positive integers"
            )
        requested_build_env = parse_build_env(args.build_env)
        effective_jobs = (
            min(args.jobs, args.tilelang_worker_cap)
            if strategy == "tilelang-targeted"
            else args.jobs
        )
        build_env = os.environ.copy()
        build_env.update(requested_build_env)
        build_env["MAX_JOBS"] = str(effective_jobs)
        build_env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(effective_jobs)
        build_env["CTEST_PARALLEL"] = str(effective_jobs)
        build_env.pop("CTEST_PARALLEL_LEVEL", None)
        build_env["BUILD_GATE_START_METHOD"] = args.tilelang_start_method
        build_env["BUILD_GATE_TILELANG_WORKERS"] = str(args.tilelang_worker_cap)
        commands = selected_commands(args, strategy, ops["rebuild_required"])
        required_command_count = 1 + int(ops["rebuild_required"])
        if args.execute and len(commands) != required_command_count:
            blockers.append(f"build_command_missing_for_strategy:{strategy}")
            if ops["rebuild_required"] and not args.xllm_ops_command:
                blockers.append("xllm_ops_rebuild_command_missing")

        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        branch = git(repo, "branch", "--show-current").stdout.strip()
        status_text = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
        diff = git(repo, "diff", "--binary", "HEAD", check=False).stdout.encode()
        untracked = untracked_fingerprints(repo)
        dirty_material = diff + json.dumps(untracked, sort_keys=True).encode()
        source_fingerprint = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "repo": str(repo),
            "branch": branch,
            "commit": head,
            "base_ref": base_ref,
            "dirty": bool(status_text),
            "dirty_status": status_text.splitlines(),
            "dirty_diff_sha256": sha256_bytes(dirty_material),
            "changed_paths": changed_paths,
            "files": file_fingerprints(repo),
            "untracked_files": untracked,
            "submodules": submodules,
            "xllm_ops": ops,
            "required_patches": patches,
        }
        environment = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "repo_identity": repo_identity,
            "host": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "cpu_count": os.cpu_count(),
            },
            "toolchain": toolchain,
            "npu_gate": npu_gate,
            "selected_environment": {
                key: os.environ.get(key) for key in SAFE_ENV_KEYS if key in os.environ
            },
            "normalized_build_environment": {
                "MAX_JOBS": build_env["MAX_JOBS"],
                "CMAKE_BUILD_PARALLEL_LEVEL": build_env["CMAKE_BUILD_PARALLEL_LEVEL"],
                "CTEST_PARALLEL": build_env["CTEST_PARALLEL"],
                "CTEST_PARALLEL_LEVEL_ignored": os.environ.get("CTEST_PARALLEL_LEVEL"),
                "BUILD_GATE_START_METHOD": build_env["BUILD_GATE_START_METHOD"],
                "BUILD_GATE_TILELANG_WORKERS": build_env["BUILD_GATE_TILELANG_WORKERS"],
            },
            "requested_build_environment": requested_build_env,
        }
        plan = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "strategy": strategy,
            "reasons": reasons,
            "actions": actions,
            "commands": commands,
            "execute_requested": args.execute,
            "jobs": effective_jobs,
            "requested_jobs": args.jobs,
            "tilelang": {
                "worker_cap": args.tilelang_worker_cap,
                "start_method": args.tilelang_start_method,
                "changed_paths": [
                    path
                    for path in changed_paths
                    if any(marker in path.lower() for marker in TILELANG_MARKERS)
                ],
            },
            "no_output_timeout_seconds": args.no_output_timeout,
            "cmake_identity": cmake,
            "cmake_mismatches": cmake_mismatches,
            "blockers": sorted(set(blockers)),
        }
        write_json(artifact_dir / "environment.json", environment)
        write_json(artifact_dir / "source-fingerprint.json", source_fingerprint)
        write_json(artifact_dir / "build-plan.json", plan)

        execution: list[dict[str, Any]] = []
        build_returncode: int | None = None
        if blockers:
            status = "BLOCKED"
        elif args.execute:
            phase = "build"
            build_returncode, execution = execute_commands(
                repo,
                commands,
                build_env,
                build_log,
                args.no_output_timeout,
            )
            if build_returncode != 0:
                status = "FAILED"
                failures.append(f"build_command_failed:{build_returncode}")
            else:
                phase = "binary_validation"
        else:
            blockers.append("build_execution_not_requested")

        binary, binary_failures = binary_provenance(args.binary)
        if args.execute and build_returncode == 0:
            failures.extend(binary_failures)
            status = "PASS" if not binary_failures else "FAILED"
        elif not args.execute and not blockers and not binary_failures:
            status = "PASS"
            phase = "existing_binary_validation"
        elif not args.execute:
            status = "BLOCKED"
            blockers.extend(binary_failures)

        binary_record = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "repo": str(repo),
            "branch": branch,
            "commit": head,
            "dirty_diff_sha256": source_fingerprint["dirty_diff_sha256"],
            "submodules": submodules,
            "cmake_identity": cmake,
            "xllm_ops": ops,
            "required_patches": patches,
            "strategy": strategy,
            "build_commands": commands,
            "execution": execution,
            "binary": binary,
        }
        write_json(artifact_dir / "binary-provenance.json", binary_record)
    except (GateError, OSError, ValueError, json.JSONDecodeError) as error:
        failures.append(str(error))
        status = "FAILED"

    placeholder = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "unavailable": True,
        "reason": failures[-1] if failures else "gate_did_not_reach_this_phase",
    }
    for name in (
        "environment.json",
        "source-fingerprint.json",
        "build-plan.json",
        "binary-provenance.json",
    ):
        path = artifact_dir / name
        if not path.exists():
            write_json(path, placeholder)
    submodule_path = artifact_dir / "submodules.txt"
    if not submodule_path.exists():
        submodule_path.write_text("Unavailable.\n", encoding="utf-8")

    verdict = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": status,
        "phase": phase,
        "blockers": sorted(set(blockers)),
        "failures": sorted(set(failures)),
        "binary_ready": status == "PASS",
        "artifacts": {
            "environment": "environment.json",
            "build_plan": "build-plan.json",
            "submodules": "submodules.txt",
            "source_fingerprint": "source-fingerprint.json",
            "build_log": "build.log",
            "binary_provenance": "binary-provenance.json",
        },
    }
    write_json(artifact_dir / "verdict.json", verdict)
    print(json.dumps(verdict, ensure_ascii=False))
    return {"PASS": 0, "FAILED": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
