#!/usr/bin/env python3
"""Validate framework CLI availability and key flags for NPU benchmarking."""

import argparse
import json
import os
import subprocess
import sys


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", "Command timed out"
    except Exception as e:
        return -3, "", str(e)


def validate_xllm(model: str, extra_flags: list[str]) -> dict:
    checks = {"framework": "xllm", "checks": []}

    rc, out, err = run_command(["xllm", "serve", "--help"])
    if rc != 0:
        checks.append({"check": "xllm serve --help", "pass": False, "detail": err})
    else:
        checks.append({"check": "xllm serve --help", "pass": True})
        important_flags = [
            "tensor-parallel-size", "pipeline-parallel-size",
            "graph-mode", "block-size", "max-model-len",
            "gpu-memory-utilization", "max-num-seqs",
        ]
        for flag in important_flags:
            found = f"--{flag}" in out
            checks.append({"check": f"--{flag} available", "pass": found})

    rc, out, err = run_command(["npu-smi", "info"])
    if rc != 0:
        checks.append({"check": "npu-smi info", "pass": False, "detail": err})
    else:
        checks.append({"check": "npu-smi info", "pass": True})
        a3_count = out.lower().count("910b3") + out.lower().count("910b") + out.count("A3")
        checks.append({"check": f"NPU A3 count >= 1", "pass": a3_count > 0, "detail": f"detected={a3_count}"})

    return checks


def validate_vllm_ascend(model: str, extra_flags: list[str]) -> dict:
    checks = {"framework": "vllm-ascend", "checks": []}

    rc, out, err = run_command(["vllm", "serve", "--help"])
    if rc != 0:
        checks.append({"check": "vllm serve --help", "pass": False, "detail": err})
    else:
        checks.append({"check": "vllm serve --help", "pass": True})
        important_flags = [
            "tensor-parallel-size", "pipeline-parallel-size",
            "max-model-len", "gpu-memory-utilization",
            "enforce-eager", "block-size",
        ]
        for flag in important_flags:
            found = f"--{flag}" in out
            checks.append({"check": f"--{flag} available", "pass": found})

    return checks


def validate_environment() -> dict:
    env_checks = {"checks": []}

    for var in ["ASCEND_RT_VISIBLE_DEVICES", "ASCEND_HOME", "CANN_VERSION"]:
        val = os.environ.get(var, "")
        env_checks["checks"].append({
            "check": f"{var} set",
            "pass": bool(val),
            "detail": val[:50] if val else "not set",
        })

    return env_checks


def main():
    parser = argparse.ArgumentParser(description="Validate framework CLI for NPU benchmark")
    parser.add_argument("--framework", required=True, choices=["xllm", "vllm-ascend"])
    parser.add_argument("--model", required=True, help="Model path")
    parser.add_argument("--extra-flags", default="", help="Extra flags (space-separated)")
    parser.add_argument("--output", help="Output JSON path for validation report")
    args = parser.parse_args()

    extra_flags = args.extra_flags.split() if args.extra_flags else []

    if args.framework == "xllm":
        checks = validate_xllm(args.model, extra_flags)
    else:
        checks = validate_vllm_ascend(args.model, extra_flags)

    env_checks = validate_environment()

    report = {
        "framework_checks": checks,
        "environment_checks": env_checks,
        "model_path": args.model,
        "extra_flags": extra_flags,
    }

    all_pass = (
        all(c["pass"] for c in checks["checks"])
        and all(c["pass"] for c in env_checks["checks"])
    )
    report["overall_pass"] = all_pass

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Validation report written to {args.output}")

    if all_pass:
        print("PASS: All checks passed.")
    else:
        print("FAIL: Some checks failed.")
        for check in checks["checks"]:
            if not check["pass"]:
                detail = check.get("detail", "")
                print(f"  FAIL: {check['check']} {detail}")
        for check in env_checks["checks"]:
            if not check["pass"]:
                detail = check.get("detail", "")
                print(f"  FAIL: {check['check']} {detail}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
