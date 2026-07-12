import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/xllm-npu-build-gate/scripts/build_gate.py"
SPEC = importlib.util.spec_from_file_location("build_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


def command(*args, cwd=None, check=True):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
    )


def init_repo(tmp_path):
    repo = tmp_path / "xllm"
    repo.mkdir()
    command("git", "init", "-b", "main", cwd=repo)
    command("git", "config", "user.name", "Test User", cwd=repo)
    command("git", "config", "user.email", "test@example.com", cwd=repo)
    (repo / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\n")
    (repo / "src").mkdir()
    (repo / "src/server.cc").write_text("int main() { return 0; }\n")
    command("git", "add", ".", cwd=repo)
    command("git", "commit", "-m", "initial", cwd=repo)
    return repo


def make_cache(repo, *, source=None, python=None, architecture=None):
    build_dir = repo / "build/cmake.test"
    build_dir.mkdir(parents=True)
    values = {
        "CMAKE_HOME_DIRECTORY": source or repo,
        "Python3_EXECUTABLE": python or sys.executable,
        "CMAKE_SYSTEM_PROCESSOR": architecture or gate.platform.machine(),
        "CMAKE_CXX_COMPILER": "/usr/bin/c++",
    }
    (build_dir / "CMakeCache.txt").write_text(
        "".join(f"{key}:STRING={value}\n" for key, value in values.items())
    )
    return build_dir


def invoke(repo, run_root, *extra, env=None):
    full_env = os.environ.copy()
    full_env["BASH_ENV"] = "/dev/null"
    if env:
        full_env.update(env)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--run-root",
            str(run_root),
            "--skip-toolchain-checks",
            *map(str, extra),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=full_env,
    )


def read_artifact(run_root, name):
    return json.loads((run_root / "build" / name).read_text())


def test_selects_incremental_build_and_writes_provenance(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    (repo / "src/server.cc").write_text("int main() { return 1; }\n")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--incremental-command",
        "true",
        "--binary",
        "/bin/true",
        "--jobs",
        "16",
        env={"CTEST_PARALLEL_LEVEL": "640"},
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    verdict = read_artifact(run_root, "verdict.json")
    environment = read_artifact(run_root, "environment.json")
    provenance = read_artifact(run_root, "binary-provenance.json")
    assert plan["strategy"] == "incremental"
    assert verdict["status"] == "PASS"
    assert provenance["binary"]["sha256"]
    normalized = environment["normalized_build_environment"]
    assert normalized["CMAKE_BUILD_PARALLEL_LEVEL"] == "16"
    assert normalized["CTEST_PARALLEL"] == "16"
    assert normalized["CTEST_PARALLEL_LEVEL_ignored"] == "640"
    assert normalized["MAX_JOBS"] == "16"
    assert (run_root / "build/submodules.txt").is_file()
    assert (run_root / "build/build.log").read_text().startswith("$ true")


def test_cache_identity_mismatch_forces_reconfigure(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo, source=tmp_path / "different-checkout")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--configure-command",
        "true",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    assert plan["strategy"] == "reconfigure"
    assert "cmake_source_mismatch" in plan["cmake_mismatches"]


def test_cached_libtorch_wrong_architecture_forces_reconfigure(tmp_path):
    repo = init_repo(tmp_path)
    build_dir = make_cache(repo)
    cached_libtorch = build_dir / "_deps/libtorch-src/lib/libtorch.so"
    cached_libtorch.parent.mkdir(parents=True)
    cached_libtorch.write_text("not an architecture-compatible shared library\n")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--configure-command",
        "true",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    assert plan["strategy"] == "reconfigure"
    assert "cached_libtorch_architecture_mismatch" in plan["cmake_mismatches"]


def test_tilelang_change_selects_targeted_strategy_and_caps_workers(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    path = repo / "xllm/compiler/tilelang/attention/kernel.py"
    path.parent.mkdir(parents=True)
    path.write_text("# changed\n")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--tilelang-command",
        "true",
        "--binary",
        "/bin/true",
        "--tilelang-worker-cap",
        "16",
        "--jobs",
        "640",
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    assert plan["strategy"] == "tilelang-targeted"
    assert plan["tilelang"]["worker_cap"] == 16
    assert plan["tilelang"]["start_method"] == "spawn"
    assert plan["requested_jobs"] == 640
    assert plan["jobs"] == 16


def test_missing_required_patch_blocks_before_build(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--incremental-command",
        "printf should-not-run",
        "--binary",
        "/bin/true",
        "--required-patch",
        tmp_path / "weight-loading-fix.patch",
    )

    assert result.returncode == 2
    verdict = read_artifact(run_root, "verdict.json")
    assert verdict["status"] == "BLOCKED"
    assert any(item.startswith("required_patch_missing:") for item in verdict["blockers"])
    assert (run_root / "build/build.log").read_text() == "Build not executed.\n"


def test_failed_build_preserves_log_and_failed_verdict(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--incremental-command",
        "echo compile-failed; exit 23",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 1
    verdict = read_artifact(run_root, "verdict.json")
    assert verdict["status"] == "FAILED"
    assert "build_command_failed:23" in verdict["failures"]
    assert "compile-failed" in (run_root / "build/build.log").read_text()


def test_bare_repository_is_failed_with_verdict_artifact(tmp_path):
    repo = tmp_path / "bare.git"
    command("git", "init", "--bare", repo)
    run_root = tmp_path / "run"

    result = invoke(repo, run_root)

    assert result.returncode == 1
    verdict = read_artifact(run_root, "verdict.json")
    assert verdict["status"] == "FAILED"
    assert "bare repositories" in verdict["failures"][0]
    for name in (
        "environment.json",
        "build-plan.json",
        "submodules.txt",
        "source-fingerprint.json",
        "build.log",
        "binary-provenance.json",
        "verdict.json",
    ):
        assert (run_root / "build" / name).is_file()


def test_xllm_ops_marker_mismatch_requires_reinstall_before_build(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    ops = repo / "third_party/xllm_ops"
    ops.mkdir(parents=True)
    command("git", "init", "-b", "main", cwd=ops)
    command("git", "config", "user.name", "Test User", cwd=ops)
    command("git", "config", "user.email", "test@example.com", cwd=ops)
    (ops / "op.cc").write_text("// op\n")
    command("git", "add", ".", cwd=ops)
    command("git", "commit", "-m", "ops", cwd=ops)
    marker = tmp_path / ".xllm_ops_git_head"
    marker.write_text("0" * 40 + "\n")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--opp-marker",
        marker,
        "--xllm-ops-command",
        "echo rebuild-opp",
        "--configure-command",
        "echo build-xllm",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    provenance = read_artifact(run_root, "binary-provenance.json")
    assert plan["actions"][0] == "rebuild_and_install_xllm_ops"
    assert plan["commands"] == ["echo rebuild-opp", "echo build-xllm"]
    assert provenance["xllm_ops"]["matches"] is False


def test_vllm_ascend_adapter_does_not_require_cmake_or_xllm_ops(tmp_path):
    repo = init_repo(tmp_path)
    shutil.rmtree(repo / "CMakeLists.txt") if (repo / "CMakeLists.txt").is_dir() else (repo / "CMakeLists.txt").unlink()
    command("git", "add", "-u", cwd=repo)
    command("git", "commit", "-m", "python build", cwd=repo)
    (repo / "vllm_ascend").mkdir()
    (repo / "vllm_ascend/runtime.py").write_text("# changed\n")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--framework",
        "vllm-ascend",
        "--execute",
        "--incremental-command",
        "true",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    provenance = read_artifact(run_root, "binary-provenance.json")
    assert plan["framework"] == "vllm-ascend"
    assert plan["cmake_identity"]["applicable"] is False
    assert provenance["xllm_ops"]["applicable"] is False


def test_sglang_adapter_selects_generic_targeted_command(tmp_path):
    repo = init_repo(tmp_path)
    path = repo / "sgl-kernel/csrc/attention.cc"
    path.parent.mkdir(parents=True)
    path.write_text("// changed\n")
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--framework",
        "sglang",
        "--execute",
        "--targeted-command",
        "true",
        "--binary",
        "/bin/true",
        "--jobs",
        "32",
        "--tilelang-worker-cap",
        "1",
    )

    assert result.returncode == 0, result.stderr
    plan = read_artifact(run_root, "build-plan.json")
    assert plan["strategy"] == "framework-targeted"
    assert plan["commands"] == ["true"]
    assert plan["jobs"] == 32
    assert plan["tilelang"]["applicable"] is False


def test_plan_without_executed_binary_is_blocked(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    run_root = tmp_path / "run"

    result = invoke(repo, run_root, "--binary", "/bin/true")

    assert result.returncode == 2
    verdict = read_artifact(run_root, "verdict.json")
    assert verdict["status"] == "BLOCKED"
    assert "build_execution_not_requested" in verdict["blockers"]


def test_no_output_timeout_stops_stalled_build_and_records_progress(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--incremental-command",
        "printf 'family=attention variants=32\\n'; sleep 5",
        "--binary",
        "/bin/true",
        "--no-output-timeout",
        "1",
    )

    assert result.returncode == 1
    verdict = read_artifact(run_root, "verdict.json")
    provenance = read_artifact(run_root, "binary-provenance.json")
    assert verdict["status"] == "FAILED"
    assert "build_command_failed:124" in verdict["failures"]
    assert provenance["execution"][0]["timed_out"] is True
    assert provenance["execution"][0]["last_output"] == "family=attention variants=32"
    assert "BUILD_GATE_TIMEOUT" in (run_root / "build/build.log").read_text()


def test_uninitialized_submodule_is_blocked(tmp_path):
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    command("git", "init", "-b", "main", cwd=dependency)
    command("git", "config", "user.name", "Test User", cwd=dependency)
    command("git", "config", "user.email", "test@example.com", cwd=dependency)
    (dependency / "dep.txt").write_text("dependency\n")
    command("git", "add", ".", cwd=dependency)
    command("git", "commit", "-m", "dependency", cwd=dependency)

    repo = init_repo(tmp_path)
    command(
        "git",
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        dependency,
        "third_party/dependency",
        cwd=repo,
    )
    command("git", "commit", "-am", "add submodule", cwd=repo)
    shutil.rmtree(repo / "third_party/dependency")
    make_cache(repo)
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--configure-command",
        "true",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 2
    verdict = read_artifact(run_root, "verdict.json")
    assert "submodule_uninitialized:third_party/dependency" in verdict["blockers"]


def test_submodule_commit_mismatch_is_blocked(tmp_path):
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    command("git", "init", "-b", "main", cwd=dependency)
    command("git", "config", "user.name", "Test User", cwd=dependency)
    command("git", "config", "user.email", "test@example.com", cwd=dependency)
    (dependency / "dep.txt").write_text("dependency\n")
    command("git", "add", ".", cwd=dependency)
    command("git", "commit", "-m", "dependency", cwd=dependency)
    repo = init_repo(tmp_path)
    command("git", "-c", "protocol.file.allow=always", "submodule", "add", dependency, "third_party/dependency", cwd=repo)
    command("git", "commit", "-am", "add submodule", cwd=repo)
    submodule = repo / "third_party/dependency"
    command("git", "config", "user.name", "Test User", cwd=submodule)
    command("git", "config", "user.email", "test@example.com", cwd=submodule)
    (submodule / "dep.txt").write_text("different commit\n")
    command("git", "add", ".", cwd=submodule)
    command("git", "commit", "-m", "different", cwd=submodule)
    make_cache(repo)

    result = invoke(repo, tmp_path / "run", "--execute", "--incremental-command", "true", "--binary", "/bin/true")

    assert result.returncode == 2
    assert "submodule_commit_mismatch:third_party/dependency" in read_artifact(tmp_path / "run", "verdict.json")["blockers"]


def test_linked_worktree_identity_is_recorded(tmp_path):
    repo = init_repo(tmp_path)
    lane = tmp_path / "eval-lane"
    command("git", "worktree", "add", "-b", "candidate", lane, cwd=repo)
    make_cache(lane)
    run_root = tmp_path / "run"

    result = invoke(
        lane,
        run_root,
        "--execute",
        "--incremental-command",
        "true",
        "--binary",
        "/bin/true",
    )

    assert result.returncode == 0, result.stderr
    environment = read_artifact(run_root, "environment.json")
    plan = read_artifact(run_root, "build-plan.json")
    assert environment["repo_identity"]["kind"] == "linked_worktree"
    assert "linked_worktree_detected" in plan["reasons"]


def test_required_npu_gate_records_devices_and_probe(tmp_path):
    repo = init_repo(tmp_path)
    make_cache(repo)
    device_root = tmp_path / "dev"
    device_root.mkdir()
    for name in ("davinci0", "davinci_manager", "devmm_svm", "hisi_hdc"):
        (device_root / name).touch()
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    npu_smi = fakebin / "npu-smi"
    npu_smi.write_text("#!/bin/sh\necho 'NPU 0 OK'\n")
    npu_smi.chmod(0o755)
    run_root = tmp_path / "run"

    result = invoke(
        repo,
        run_root,
        "--execute",
        "--incremental-command",
        "true",
        "--binary",
        "/bin/true",
        "--require-npu",
        "--device-root",
        device_root,
        env={"PATH": f"{fakebin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    npu_gate = read_artifact(run_root, "environment.json")["npu_gate"]
    assert npu_gate["npu_smi"]["returncode"] == 0
    assert npu_gate["davinci_devices"] == [str(device_root / "davinci0")]
    assert all(npu_gate["device_nodes"].values())
