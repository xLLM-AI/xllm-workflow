#!/usr/bin/env python3
"""Capture normalized NPU and host facts for the benchmark fairness gate."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_mapping(text: str) -> dict[int, tuple[int, int]]:
    mapping = {}
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+|-)\s+(\d+|-)\s+(\S+)", line)
        if not match:
            continue
        npu_id, chip_id, logic_id, _physical_id, name = match.groups()
        if logic_id != "-" and name.lower() != "mcu":
            mapping[int(logic_id)] = (int(npu_id), int(chip_id))
    return mapping


def parse_keyed_by_chip(text: str, fields: dict[str, str]) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    current: dict[str, Any] = {}
    for line in text.splitlines():
        field = re.match(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$", line)
        if not field:
            continue
        key, value = field.groups()
        key = key.strip()
        if key in fields:
            target = fields[key]
            current[target] = int(value) if value.isdigit() else value
        elif key == "Chip ID" and value.isdigit():
            records[int(value)] = current
            current = {}
    return records


def parse_processes(text: str) -> dict[int, list[dict[str, Any]]]:
    records: dict[int, list[dict[str, Any]]] = {}
    current: list[dict[str, Any]] = []
    for line in text.splitlines():
        process = re.search(
            r"Process id:(\d+)\s+Process name:\s*(.*?)\s+Process memory\(MB\):(\d+)", line
        )
        if process:
            pid, name, memory = process.groups()
            current.append({"pid": int(pid), "name": name.strip(), "memory_mb": int(memory)})
            continue
        chip = re.match(r"^\s*Chip ID\s*:\s*(\d+)\s*$", line)
        if chip:
            records[int(chip.group(1))] = current
            current = []
    return records


def proc_start_time(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split(") ", 1)[1].split()
        return fields[19] if len(fields) >= 20 and fields[0] != "Z" else None
    except (FileNotFoundError, IndexError, OSError):
        return None


def attempt_identities(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    identities = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 2 or not all(field.isdigit() for field in fields):
            raise ValueError(f"invalid attempt PID identity: {line!r}")
        identities[int(fields[0])] = fields[1]
    return identities


def swap_used_bytes(meminfo: str) -> int:
    values = {}
    for line in meminfo.splitlines():
        match = re.match(r"^(SwapTotal|SwapFree):\s+(\d+)\s+kB$", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    if set(values) != {"SwapTotal", "SwapFree"}:
        raise ValueError("cannot parse SwapTotal and SwapFree from /proc/meminfo")
    return values["SwapTotal"] - values["SwapFree"]


def active_process_flags(proc_root: Path = Path("/proc")) -> tuple[bool, bool]:
    profiling = False
    building = False
    own_pid = os.getpid()
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").lower()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        profiling |= "msprof" in command
        building |= any(token in command for token in ("ninja", "cmake --build", "tilelang", "bisheng"))
    return profiling, building


class Source:
    def __init__(self, raw_dir: Path, replay_dir: Path | None):
        self.raw_dir = raw_dir
        self.replay_dir = replay_dir
        raw_dir.mkdir(parents=True, exist_ok=True)

    def read(self, filename: str, command: list[str]) -> str:
        if self.replay_dir:
            text = (self.replay_dir / filename).read_text(encoding="utf-8")
        else:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}: {result.stderr.strip()}")
            text = result.stdout
        (self.raw_dir / filename).write_text(text, encoding="utf-8")
        return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--physical-device", dest="devices", type=int, action="append", required=True)
    parser.add_argument("--attempt-pid-file", type=Path)
    parser.add_argument("--replay-dir", type=Path)
    parser.add_argument("--load1", type=float, help="Replay-only host load override")
    parser.add_argument("--meminfo-file", type=Path, default=Path("/proc/meminfo"))
    parser.add_argument("--process-scan-root", type=Path, default=Path("/proc"))
    args = parser.parse_args()
    errors: list[str] = []
    devices: list[dict[str, Any]] = []
    source = Source(args.raw_dir, args.replay_dir)
    try:
        mapping = parse_mapping(source.read("mapping.txt", ["npu-smi", "info", "-m"]))
        identities = attempt_identities(args.attempt_pid_file)
        grouped = sorted({mapping[device][0] for device in args.devices if device in mapping})
        usage_by_npu = {
            npu: parse_keyed_by_chip(
                source.read(f"usages-npu{npu}.txt", ["npu-smi", "info", "-t", "usages", "-i", str(npu)]),
                {"HBM Usage Rate(%)": "hbm_usage_pct", "Aicore Usage Rate(%)": "aicore_usage_pct"},
            )
            for npu in grouped
        }
        health_by_npu = {
            npu: parse_keyed_by_chip(
                source.read(f"health-npu{npu}.txt", ["npu-smi", "info", "-t", "health", "-i", str(npu)]),
                {"Health": "health"},
            )
            for npu in grouped
        }
        process_by_npu = {
            npu: parse_processes(
                source.read(f"processes-npu{npu}.txt", ["npu-smi", "info", "-t", "proc-mem", "-i", str(npu)])
            )
            for npu in grouped
        }
        for physical_id in args.devices:
            if physical_id not in mapping:
                errors.append(f"physical device missing from mapping: {physical_id}")
                continue
            npu_id, chip_id = mapping[physical_id]
            usage = usage_by_npu.get(npu_id, {}).get(chip_id, {})
            health = health_by_npu.get(npu_id, {}).get(chip_id, {})
            if chip_id not in usage_by_npu.get(npu_id, {}):
                errors.append(f"usage record missing for physical device: {physical_id}")
            elif not {"hbm_usage_pct", "aicore_usage_pct"}.issubset(usage):
                errors.append(f"usage fields incomplete for physical device: {physical_id}")
            if chip_id not in health_by_npu.get(npu_id, {}):
                errors.append(f"health record missing for physical device: {physical_id}")
            elif not health.get("health"):
                errors.append(f"health fields incomplete for physical device: {physical_id}")
            if chip_id not in process_by_npu.get(npu_id, {}):
                errors.append(f"process record missing for physical device: {physical_id}")
            processes = []
            for process in process_by_npu.get(npu_id, {}).get(chip_id, []):
                pid = process["pid"]
                started = proc_start_time(pid)
                process.update(
                    host_visible=started is not None,
                    owned_by_attempt=started is not None and identities.get(pid) == started,
                )
                processes.append(process)
            devices.append(
                {
                    "physical_id": physical_id,
                    "health": health.get("health"),
                    "hbm_usage_pct": usage.get("hbm_usage_pct"),
                    "aicore_usage_pct": usage.get("aicore_usage_pct"),
                    "processes": processes,
                }
            )
        meminfo_path = args.meminfo_file
        if args.replay_dir and meminfo_path == Path("/proc/meminfo"):
            meminfo_path = args.replay_dir / "meminfo.txt"
        profiling, building = active_process_flags(args.process_scan_root)
        host = {
            "load1": args.load1 if args.load1 is not None else os.getloadavg()[0],
            "swap_used_bytes": swap_used_bytes(meminfo_path.read_text(encoding="utf-8")),
            "profiling_active": profiling,
            "build_active": building,
        }
    except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as exc:
        errors.append(str(exc))
        host = {}
    snapshot = {
        "schema_version": 1,
        "captured_at": now(),
        "devices": devices,
        "host": host,
        "collection_errors": errors,
        "raw_dir": str(args.raw_dir.resolve()),
    }
    write_json(args.output, snapshot)
    print(json.dumps(snapshot, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
