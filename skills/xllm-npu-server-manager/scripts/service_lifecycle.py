#!/usr/bin/env python3
"""Record and validate immutable service-attempt lifecycle evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def result(path: Path, status: str, **values: Any) -> int:
    document = {"schema_version": 1, "generated_at": now(), "status": status, **values}
    write_json(path, document)
    print(json.dumps(document, sort_keys=True))
    return 0 if status == "PASS" else 1


def command_launch(args: argparse.Namespace) -> int:
    attempt = args.attempt_dir.resolve()
    required = [args.command_file.resolve(), args.pid_file.resolve(), *map(Path.resolve, args.logs)]
    missing = [str(path) for path in required if not path.exists()]
    outside = [str(path) for path in required if attempt not in path.parents]
    if missing:
        return result(attempt / "launch.json", "FAILED", attempt_id=args.attempt_id, missing=missing)
    if outside:
        return result(
            attempt / "launch.json",
            "FAILED",
            attempt_id=args.attempt_id,
            error="service artifacts must be attempt-scoped",
            outside_attempt=outside,
        )
    environment_keys = (
        "ASCEND_RT_VISIBLE_DEVICES",
        "LD_LIBRARY_PATH",
        "PYTORCH_INSTALL_PATH",
        "PYTORCH_NPU_INSTALL_PATH",
        "NPU_MEMORY_FRACTION",
        "PYTORCH_NPU_ALLOC_CONF",
        "HCCL_CONNECT_TIMEOUT",
        "HCCL_IF_BASE_PORT",
        "OMP_NUM_THREADS",
    )
    write_json(
        attempt / "environment.json",
        {
            "schema_version": 1,
            "generated_at": now(),
            "environment": {key: os.environ[key] for key in environment_keys if key in os.environ},
        },
    )
    return result(
        attempt / "launch.json",
        "PASS",
        attempt_id=args.attempt_id,
        api_url=args.api_url,
        model=args.model,
        command_file=str(args.command_file.resolve()),
        pid_file=str(args.pid_file.resolve()),
        logs=[str(path.resolve()) for path in args.logs],
        ports=args.ports,
        visible_devices=args.visible_devices,
    )


def fetch_json(url: str, *, payload: dict[str, Any] | None = None, timeout: float = 3) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def command_ready(args: argparse.Namespace) -> int:
    output = args.attempt_dir / "ready.json"
    deadline = time.monotonic() + args.timeout
    error = "not attempted"
    first_attempt = True
    while first_attempt or time.monotonic() <= deadline:
        first_attempt = False
        try:
            payload = fetch_json(args.api_url.rstrip("/") + "/models")
            ids = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
            if args.expected_model_id and args.expected_model_id not in ids:
                error = f"expected model id not advertised: {args.expected_model_id}"
            else:
                return result(
                    output,
                    "PASS",
                    attempt_id=args.attempt_id,
                    endpoint=args.api_url,
                    advertised_model_ids=ids,
                )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            error = str(exc)
        time.sleep(args.interval)
    return result(output, "FAILED", attempt_id=args.attempt_id, endpoint=args.api_url, error=error)


def command_smoke(args: argparse.Namespace) -> int:
    output = args.attempt_dir / "smoke.json"
    response_path = args.attempt_dir / "smoke-response.json"
    payload = (
        read_json(args.request_json)
        if args.request_json
        else {
            "model": args.model,
            "messages": [{"role": "user", "content": args.prompt}],
            "temperature": 0,
            "max_tokens": args.max_tokens,
        }
    )
    try:
        response = fetch_json(args.api_url.rstrip("/") + "/chat/completions", payload=payload, timeout=args.timeout)
        write_json(response_path, response)
        choices = response.get("choices") if isinstance(response, dict) else None
        if not isinstance(choices, list) or not choices:
            return result(output, "FAILED", attempt_id=args.attempt_id, error="response has no choices")
        return result(
            output,
            "PASS",
            attempt_id=args.attempt_id,
            request_source=str(args.request_json.resolve()) if args.request_json else "generated",
            response=str(response_path.resolve()),
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return result(output, "FAILED", attempt_id=args.attempt_id, error=str(exc))


def process_identity_matches(pid: int, start_time: str) -> bool:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split(") ", 1)[1].split()
        return len(fields) >= 20 and fields[19] == start_time and fields[0] != "Z"
    except (FileNotFoundError, IndexError, OSError):
        return False


def parse_pid_file(path: Path) -> list[tuple[int, str]]:
    identities = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 2 or not all(field.isdigit() for field in fields):
            raise ValueError(f"invalid PID identity: {line!r}")
        identities.append((int(fields[0]), fields[1]))
    return identities


def port_is_free(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def command_cleanup(args: argparse.Namespace) -> int:
    output = args.attempt_dir / "cleanup.json"
    try:
        alive = [pid for pid, started in parse_pid_file(args.pid_file) if process_identity_matches(pid, started)]
    except (FileNotFoundError, ValueError, OSError) as exc:
        return result(output, "FAILED", attempt_id=args.attempt_id, error=str(exc))
    occupied_ports = [port for port in args.ports if not port_is_free(args.host, port)]
    status = "PASS" if not alive and not occupied_ports else "FAILED"
    return result(
        output,
        status,
        attempt_id=args.attempt_id,
        remaining_pids=alive,
        occupied_ports=occupied_ports,
        npu_quiescence=args.npu_quiescence,
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    launch = sub.add_parser("launch")
    launch.add_argument("--attempt-dir", type=Path, required=True)
    launch.add_argument("--attempt-id", required=True)
    launch.add_argument("--api-url", required=True)
    launch.add_argument("--model", required=True)
    launch.add_argument("--command-file", type=Path, required=True)
    launch.add_argument("--pid-file", type=Path, required=True)
    launch.add_argument("--log", dest="logs", type=Path, action="append", required=True)
    launch.add_argument("--port", dest="ports", type=int, action="append", required=True)
    launch.add_argument("--visible-device", dest="visible_devices", type=int, action="append", required=True)
    launch.set_defaults(func=command_launch)

    ready = sub.add_parser("ready")
    ready.add_argument("--attempt-dir", type=Path, required=True)
    ready.add_argument("--attempt-id", required=True)
    ready.add_argument("--api-url", required=True)
    ready.add_argument("--expected-model-id")
    ready.add_argument("--timeout", type=float, default=600)
    ready.add_argument("--interval", type=float, default=5)
    ready.set_defaults(func=command_ready)

    smoke = sub.add_parser("smoke")
    smoke.add_argument("--attempt-dir", type=Path, required=True)
    smoke.add_argument("--attempt-id", required=True)
    smoke.add_argument("--api-url", required=True)
    smoke.add_argument("--model", required=True)
    smoke.add_argument("--request-json", type=Path)
    smoke.add_argument("--prompt", default="Reply with OK.")
    smoke.add_argument("--max-tokens", type=int, default=1)
    smoke.add_argument("--timeout", type=float, default=30)
    smoke.set_defaults(func=command_smoke)

    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--attempt-dir", type=Path, required=True)
    cleanup.add_argument("--attempt-id", required=True)
    cleanup.add_argument("--pid-file", type=Path, required=True)
    cleanup.add_argument("--host", default="127.0.0.1")
    cleanup.add_argument("--port", dest="ports", type=int, action="append", default=[])
    cleanup.add_argument("--npu-quiescence", choices=("PASS", "FAILED", "NOT_CHECKED"), default="NOT_CHECKED")
    cleanup.set_defaults(func=command_cleanup)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    sys.exit(arguments.func(arguments))
