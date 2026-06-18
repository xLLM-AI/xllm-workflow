#!/usr/bin/env python3
"""Start an xLLM service on idle Ascend NPU devices.

The script keeps config.json as the source of truth for xLLM repository and
model settings. Command-line arguments may override those values for one run,
but only interactive backfills for missing required config fields are written
back to config.json.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import signal
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_CONFIG_TEMPLATE = ROOT / "config.example.json"

# Runtime defaults that are not represented in config.json.
HOST = "0.0.0.0"
START_PORT = 18000
MASTER_NODE_ADDR = "127.0.0.1:9748"
HCCL_IF_BASE_PORT = 43432
LOG_DIR = "runs/xllm_start"
COMMUNICATION_BACKEND = "hccl"
NPU_KERNEL_BACKEND = "AUTO"
QWEN3_AUTO_NPU_KERNEL_BACKEND = "TORCH"
BLOCK_SIZE = 128
ENABLE_PREFIX_CACHE = False
ENABLE_CHUNKED_PREFILL = True
ENABLE_SCHEDULE_OVERLAP = True
ENABLE_SHM = True
POLL_INTERVAL_SECONDS = 30
READY_TIMEOUT_SECONDS = 600
FREE_HBM_USAGE_PCT_MAX = 10
FREE_AICORE_USAGE_PCT_MAX = 5
OUTPUT_WIDTH = 88

ASCEND_ENV_SCRIPTS = [
    "/usr/local/Ascend/ascend-toolkit/set_env.sh",
    "/usr/local/Ascend/nnal/atb/set_env.sh",
]

CONFIG_CLI_OVERRIDES = [
    (("code", "xllm", "path"), "xllm_code_path"),
    (("code", "xllm", "origin", "url"), "xllm_origin_url"),
    (("code", "xllm", "origin", "branch"), "xllm_origin_branch"),
    (("code", "xllm", "origin", "commit"), "xllm_origin_commit"),
    (("code", "xllm", "upstream", "url"), "xllm_upstream_url"),
    (("code", "xllm", "upstream", "branch"), "xllm_upstream_branch"),
    (("code", "xllm", "upstream", "commit"), "xllm_upstream_commit"),
    (("xllm_config", "model"), "model"),
    (("xllm_config", "model_id"), "model_id"),
    (("xllm_config", "max_memory_utilization"), "max_memory_utilization"),
    (("xllm_config", "max_seqs_per_batch"), "max_seqs_per_batch"),
    (
        ("xllm_config", "max_tokens_per_chunk_for_prefill"),
        "max_tokens_per_chunk_for_prefill",
    ),
    (("xllm_config", "max_tokens_per_batch"), "max_tokens_per_batch"),
    (("xllm_config", "tp_size"), "tp_size"),
    (("xllm_config", "draft_model"), "draft_model"),
    (("xllm_config", "num_speculative_tokens"), "num_speculative_tokens"),
]


class StartError(RuntimeError):
    """Raised for user-correctable startup errors."""


def separator(char: str = "=") -> str:
    return char * OUTPUT_WIDTH


def format_block(title: str, lines: list[str]) -> str:
    return "\n".join(
        [
            "",
            separator("="),
            title,
            separator("-"),
            *lines,
            separator("="),
            "",
        ]
    )


def print_block(title: str, lines: list[str], stream: Any = sys.stdout) -> None:
    print(format_block(title, lines), file=stream, flush=True)


def display_value(value: Any) -> str:
    if isinstance(value, bool):
        return bool_text(value)
    if value is None:
        return "n/a"
    return str(value)


def format_kv_lines(rows: list[tuple[str, Any]]) -> list[str]:
    if not rows:
        return []
    width = max(len(key) for key, _value in rows)
    return [f"{key.ljust(width)} : {display_value(value)}" for key, value in rows]


def format_kv_block(title: str, rows: list[tuple[str, Any]]) -> str:
    return format_block(title, format_kv_lines(rows))


def print_kv_block(
    title: str,
    rows: list[tuple[str, Any]],
    stream: Any = sys.stdout,
) -> None:
    print(format_kv_block(title, rows), file=stream, flush=True)


def format_table(headers: list[str], rows: list[list[Any]], right_align: set[int] | None = None) -> list[str]:
    right_align = right_align or set()
    text_rows = [[str(value) for value in row] for row in rows]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in text_rows))
        for index in range(len(headers))
    ]

    def format_row(values: list[str]) -> str:
        cells = []
        for index, value in enumerate(values):
            if index in right_align:
                cells.append(value.rjust(widths[index]))
            else:
                cells.append(value.ljust(widths[index]))
        return " | ".join(cells)

    lines = [format_row(headers)]
    lines.append("-+-".join("-" * width for width in widths))
    lines.extend(format_row(row) for row in text_rows)
    return lines


def log_step(message: str) -> None:
    """Print a timestamped progress line immediately."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ==> {message}", flush=True)


@dataclass
class NpuProcess:
    pid: int
    memory_mb: int
    name: str = ""


@dataclass
class NpuChip:
    npu_id: int
    chip_id: int
    logic_id: int


@dataclass
class NpuStatus:
    npu_id: int
    chip_id: int
    logic_id: int
    hbm_usage_pct: int | None = None
    aicore_usage_pct: int | None = None
    processes: list[NpuProcess] = field(default_factory=list)

    def is_free(self, max_hbm_pct: int, max_aicore_pct: int) -> bool:
        if self.processes:
            return False
        if self.hbm_usage_pct is None or self.aicore_usage_pct is None:
            return False
        return (
            self.hbm_usage_pct <= max_hbm_pct
            and self.aicore_usage_pct <= max_aicore_pct
        )


@dataclass
class RuntimeOptions:
    project_root: Path
    config_path: Path
    xllm_code_path: Path
    xllm_bin: Path
    model: str
    model_id: str
    max_memory_utilization: float
    max_seqs_per_batch: int
    max_tokens_per_chunk_for_prefill: int
    max_tokens_per_batch: int
    tp_size: int
    draft_model: str
    num_speculative_tokens: int
    host: str
    start_port: int
    master_node_addr: str
    hccl_if_base_port: int
    log_dir: Path
    communication_backend: str
    npu_kernel_backend: str
    block_size: int
    enable_prefix_cache: bool
    enable_chunked_prefill: bool
    enable_schedule_overlap: bool
    enable_shm: bool
    poll_interval_seconds: int
    ready_timeout_seconds: int
    free_hbm_usage_pct_max: int
    free_aicore_usage_pct_max: int
    npu_kernel_backend_note: str = ""
    extra_xllm_args: list[str] = field(default_factory=list)


@dataclass
class LogSummary:
    path: Path
    available_memory_gb: float | None = None
    total_memory_gb: float | None = None
    max_memory_utilization: float | None = None
    kv_cache_capacity_gb: float | None = None
    blocks: int | None = None
    block_size: int | None = None
    n_layers: int | None = None
    kv_cache_dtype: str = ""
    token_capacity: int | None = None

    @property
    def non_kv_memory_estimate_gb(self) -> float | None:
        if self.available_memory_gb is None or self.total_memory_gb is None:
            return None
        return max(self.total_memory_gb - self.available_memory_gb, 0.0)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StartError(f"Invalid JSON file: {path} ({exc})") from exc


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(config_path: Path, template_path: Path) -> tuple[dict[str, Any], bool]:
    changed = False
    if not config_path.exists():
        if template_path.exists() and config_path.name == "config.json":
            shutil.copyfile(template_path, config_path)
            changed = True
        else:
            return {}, changed

    config = load_json(config_path)
    if template_path.exists():
        template = load_json(template_path)
        changed = merge_missing(config, template) or changed
        if changed:
            save_json(config_path, config)
    return config, changed


def merge_missing(target: dict[str, Any], defaults: dict[str, Any]) -> bool:
    changed = False
    for key, value in defaults.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
            changed = True
        elif isinstance(target[key], dict) and isinstance(value, dict):
            changed = merge_missing(target[key], value) or changed
    return changed


def get_nested(data: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def set_nested(data: dict[str, Any], keys: tuple[str, ...], value: Any) -> None:
    current = data
    for key in keys[:-1]:
        next_value = current.setdefault(key, {})
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[keys[-1]] = value


def apply_config_cli_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    effective = copy.deepcopy(config)
    for keys, attr in CONFIG_CLI_OVERRIDES:
        value = getattr(args, attr, None)
        if value is not None:
            set_nested(effective, keys, value)
    return effective


def prompt_required(label: str) -> str:
    value = input(f"{label}: ").strip()
    while not value:
        log_step("Value cannot be empty.")
        value = input(f"{label}: ").strip()
    return value


def ensure_required_model(
    config: dict[str, Any],
    effective: dict[str, Any],
    config_path: Path,
    args: argparse.Namespace,
) -> None:
    if str(get_nested(effective, ("xllm_config", "model"), "") or "").strip():
        return
    if args.non_interactive or not sys.stdin.isatty():
        raise StartError(
            "Missing xllm_config.model. Pass --model or fill config.json."
        )

    print_block(
        "Missing required config",
        [
            "config.json is missing xllm_config.model.",
            "Please enter a model path or Hugging Face model name.",
        ],
    )
    model = prompt_required("Model path or Hugging Face model name")
    set_nested(config, ("xllm_config", "model"), model)
    set_nested(effective, ("xllm_config", "model"), model)
    save_json(config_path, config)
    print_kv_block("Config updated", [("path", display_path(config_path, config_path.parent))])


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def as_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise StartError(f"{field_name} must be an integer, got {value!r}") from exc


def as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StartError(f"{field_name} must be a number, got {value!r}") from exc


def as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    raise StartError(f"{field_name} must be a boolean, got {value!r}")


def as_choice(value: Any, field_name: str, choices: set[str]) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in choices:
        return normalized
    allowed = ", ".join(sorted(choices))
    raise StartError(f"{field_name} must be one of {allowed}, got {value!r}")


def resolve_path(value: str | Path, root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def discover_xllm_bin(code_path: Path) -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(sorted(code_path.glob("build/lib.*/xllm/xllm")))
    candidates.extend(
        [
            code_path / "build" / "xllm" / "core" / "server" / "xllm",
            code_path / "build" / "bin" / "xllm",
            code_path / "xllm",
        ]
    )
    found = shutil.which("xllm")
    if found:
        candidates.append(Path(found))
    return candidates


def resolve_xllm_bin(
    cli_value: str | None,
    code_path: Path,
    project_root: Path,
    non_interactive: bool,
) -> Path:
    if cli_value:
        if os.sep not in cli_value and (os.altsep is None or os.altsep not in cli_value):
            found = shutil.which(cli_value)
            if found:
                return Path(found).resolve()
        path = resolve_path(cli_value, project_root)
        if path.is_file():
            return path.resolve()
        raise StartError(f"xLLM binary does not exist: {path}")

    for candidate in discover_xllm_bin(code_path):
        if candidate.is_file():
            return candidate.resolve()

    if non_interactive or not sys.stdin.isatty():
        raise StartError(
            "Could not find xLLM binary. Pass --xllm-bin or build xLLM under code.xllm.path."
        )

    print_kv_block(
        "xLLM binary not found",
        [
            ("code path", code_path),
            ("next step", "enter xLLM binary path"),
        ],
    )
    entered = prompt_required("xLLM binary path")
    path = resolve_path(entered, project_root)
    if not path.is_file():
        raise StartError(f"xLLM binary does not exist: {path}")
    return path.resolve()


def runtime_arg(args: argparse.Namespace, attr: str, default: Any) -> Any:
    value = getattr(args, attr, None)
    return default if value is None else value


def is_qwen3_model(model: str, model_id: str) -> bool:
    joined = f"{model} {model_id}".lower()
    return "qwen3" in joined


def resolve_npu_kernel_backend(
    model: str,
    model_id: str,
    requested_backend: Any,
    cli_backend: str | None,
) -> tuple[str, str]:
    backend = as_choice(
        requested_backend,
        "npu_kernel_backend",
        {"AUTO", "ATB", "TORCH"},
    )
    if cli_backend is None and backend == "AUTO" and is_qwen3_model(model, model_id):
        return (
            QWEN3_AUTO_NPU_KERNEL_BACKEND,
            (
                "Qwen3 detected and --npu-kernel-backend was not provided; "
                f"using {QWEN3_AUTO_NPU_KERNEL_BACKEND} to avoid the observed "
                "ATB weight-loading stall. Pass --npu-kernel-backend ATB to force ATB."
            ),
        )
    return backend, ""


def build_runtime_options(
    effective: dict[str, Any],
    config_path: Path,
    args: argparse.Namespace,
) -> RuntimeOptions:
    project_root = config_path.resolve().parent
    code_path_value = str(get_nested(effective, ("code", "xllm", "path"), "code/xllm"))
    xllm_code_path = resolve_path(code_path_value, project_root)
    xllm_bin = resolve_xllm_bin(
        args.xllm_bin,
        xllm_code_path,
        project_root,
        args.non_interactive,
    )
    cfg = get_nested(effective, ("xllm_config",), {})
    if not isinstance(cfg, dict):
        raise StartError("config.json field xllm_config must be an object.")

    log_dir = resolve_path(str(runtime_arg(args, "log_dir", LOG_DIR)), project_root)
    model = str(cfg.get("model") or "")
    model_id = str(cfg.get("model_id") or "")
    npu_kernel_backend, npu_kernel_backend_note = resolve_npu_kernel_backend(
        model,
        model_id,
        runtime_arg(args, "npu_kernel_backend", NPU_KERNEL_BACKEND),
        args.npu_kernel_backend,
    )
    return RuntimeOptions(
        project_root=project_root,
        config_path=config_path,
        xllm_code_path=xllm_code_path,
        xllm_bin=xllm_bin,
        model=model,
        model_id=model_id,
        max_memory_utilization=as_float(
            cfg.get("max_memory_utilization"), "xllm_config.max_memory_utilization"
        ),
        max_seqs_per_batch=as_int(
            cfg.get("max_seqs_per_batch"), "xllm_config.max_seqs_per_batch"
        ),
        max_tokens_per_chunk_for_prefill=as_int(
            cfg.get("max_tokens_per_chunk_for_prefill"),
            "xllm_config.max_tokens_per_chunk_for_prefill",
        ),
        max_tokens_per_batch=as_int(
            cfg.get("max_tokens_per_batch"), "xllm_config.max_tokens_per_batch"
        ),
        tp_size=as_int(cfg.get("tp_size"), "xllm_config.tp_size"),
        draft_model=str(cfg.get("draft_model") or ""),
        num_speculative_tokens=as_int(
            cfg.get("num_speculative_tokens"), "xllm_config.num_speculative_tokens"
        ),
        host=str(runtime_arg(args, "host", HOST)),
        start_port=as_int(runtime_arg(args, "start_port", START_PORT), "start_port"),
        master_node_addr=str(runtime_arg(args, "master_node_addr", MASTER_NODE_ADDR)),
        hccl_if_base_port=as_int(
            runtime_arg(args, "hccl_if_base_port", HCCL_IF_BASE_PORT),
            "hccl_if_base_port",
        ),
        log_dir=log_dir,
        communication_backend=str(
            runtime_arg(args, "communication_backend", COMMUNICATION_BACKEND)
        ),
        npu_kernel_backend=npu_kernel_backend,
        npu_kernel_backend_note=npu_kernel_backend_note,
        block_size=as_int(runtime_arg(args, "block_size", BLOCK_SIZE), "block_size"),
        enable_prefix_cache=as_bool(
            runtime_arg(args, "enable_prefix_cache", ENABLE_PREFIX_CACHE),
            "enable_prefix_cache",
        ),
        enable_chunked_prefill=as_bool(
            runtime_arg(args, "enable_chunked_prefill", ENABLE_CHUNKED_PREFILL),
            "enable_chunked_prefill",
        ),
        enable_schedule_overlap=as_bool(
            runtime_arg(args, "enable_schedule_overlap", ENABLE_SCHEDULE_OVERLAP),
            "enable_schedule_overlap",
        ),
        enable_shm=as_bool(
            runtime_arg(args, "enable_shm", ENABLE_SHM),
            "enable_shm",
        ),
        poll_interval_seconds=as_int(
            runtime_arg(args, "poll_interval_seconds", POLL_INTERVAL_SECONDS),
            "poll_interval_seconds",
        ),
        ready_timeout_seconds=as_int(
            runtime_arg(args, "ready_timeout_seconds", READY_TIMEOUT_SECONDS),
            "ready_timeout_seconds",
        ),
        free_hbm_usage_pct_max=as_int(
            runtime_arg(args, "free_hbm_usage_pct_max", FREE_HBM_USAGE_PCT_MAX),
            "free_hbm_usage_pct_max",
        ),
        free_aicore_usage_pct_max=as_int(
            runtime_arg(args, "free_aicore_usage_pct_max", FREE_AICORE_USAGE_PCT_MAX),
            "free_aicore_usage_pct_max",
        ),
        extra_xllm_args=list(args.extra_xllm_arg or []),
    )


def parse_npu_mapping(text: str) -> list[NpuChip]:
    chips: list[NpuChip] = []
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+|-)\s+(\d+|-)\s+(\S+)", line)
        if not match:
            continue
        npu_id, chip_id, logic_id, _phy_id, chip_name = match.groups()
        if logic_id == "-" or chip_name.lower() == "mcu":
            continue
        chips.append(NpuChip(int(npu_id), int(chip_id), int(logic_id)))
    return chips


def parse_npu_usages(text: str) -> dict[int, dict[str, int]]:
    usages: dict[int, dict[str, int]] = {}
    current: dict[str, int] = {}
    for line in text.splitlines():
        field = re.match(r"^\s*([^:]+?)\s*:\s*([0-9]+)\s*$", line)
        if not field:
            continue
        key, raw_value = field.groups()
        value = int(raw_value)
        key = key.strip()
        if key == "HBM Usage Rate(%)":
            current["hbm_usage_pct"] = value
        elif key == "Aicore Usage Rate(%)":
            current["aicore_usage_pct"] = value
        elif key == "Chip ID":
            usages[value] = current
            current = {}
    return usages


def parse_npu_processes(text: str) -> dict[int, list[NpuProcess]]:
    processes: dict[int, list[NpuProcess]] = {}
    current: list[NpuProcess] = []
    for line in text.splitlines():
        proc = re.search(
            r"Process id:(\d+)\s+Process name:\s*(.*?)\s+Process memory\(MB\):(\d+)",
            line,
        )
        if proc:
            pid, name, memory = proc.groups()
            current.append(NpuProcess(int(pid), int(memory), name.strip()))
            continue
        chip = re.match(r"^\s*Chip ID\s*:\s*(\d+)\s*$", line)
        if chip:
            processes[int(chip.group(1))] = current
            current = []
    return processes


CommandRunner = Callable[[list[str]], str]


def run_text(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise StartError(f"Command failed: {' '.join(cmd)}\n{detail}")
    return result.stdout


def query_npu_status(runner: CommandRunner = run_text) -> list[NpuStatus]:
    mapping = parse_npu_mapping(runner(["npu-smi", "info", "-m"]))
    by_npu: dict[int, list[NpuChip]] = {}
    for chip in mapping:
        by_npu.setdefault(chip.npu_id, []).append(chip)

    statuses: list[NpuStatus] = []
    for npu_id, chips in sorted(by_npu.items()):
        usages = parse_npu_usages(runner(["npu-smi", "info", "-t", "usages", "-i", str(npu_id)]))
        processes = parse_npu_processes(
            runner(["npu-smi", "info", "-t", "proc-mem", "-i", str(npu_id)])
        )
        for chip in chips:
            usage = usages.get(chip.chip_id, {})
            statuses.append(
                NpuStatus(
                    npu_id=chip.npu_id,
                    chip_id=chip.chip_id,
                    logic_id=chip.logic_id,
                    hbm_usage_pct=usage.get("hbm_usage_pct"),
                    aicore_usage_pct=usage.get("aicore_usage_pct"),
                    processes=processes.get(chip.chip_id, []),
                )
            )
    return sorted(statuses, key=lambda item: item.logic_id)


def select_idle_devices(
    tp_size: int,
    free_hbm_usage_pct_max: int,
    free_aicore_usage_pct_max: int,
    poll_interval_seconds: int,
    once: bool,
    runner: CommandRunner = run_text,
) -> list[int]:
    if tp_size <= 0:
        raise StartError(f"tp_size must be positive, got {tp_size}")

    attempt = 0
    while True:
        attempt += 1
        statuses = query_npu_status(runner)
        free = [
            status.logic_id
            for status in statuses
            if status.is_free(free_hbm_usage_pct_max, free_aicore_usage_pct_max)
        ]
        if len(free) >= tp_size:
            return free[:tp_size]

        busy = ", ".join(
            f"{item.logic_id}(hbm={item.hbm_usage_pct},aicore={item.aicore_usage_pct},procs={len(item.processes)})"
            for item in statuses
        )
        message = (
            f"No enough idle NPU devices for tp_size={tp_size}. "
            f"free={free}, all=[{busy}]"
        )
        if once:
            raise StartError(message)
        log_step(f"{message}; retry in {poll_interval_seconds}s (attempt {attempt})")
        time.sleep(poll_interval_seconds)


def normalize_bind_host(host: str) -> str:
    return "" if host in {"0.0.0.0", "::"} else host


def is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((normalize_bind_host(host), port))
        except OSError:
            return False
    return True


def parse_master_addr(master_node_addr: str) -> tuple[str, int]:
    if ":" not in master_node_addr:
        raise StartError(f"master_node_addr must be host:port, got {master_node_addr!r}")
    host, port_text = master_node_addr.rsplit(":", 1)
    if not host:
        raise StartError(f"master_node_addr host is empty: {master_node_addr!r}")
    return host, as_int(port_text, "master_node_addr port")


def find_free_api_start(
    host: str,
    requested_start: int,
    tp_size: int,
    checker: Callable[[str, int], bool] = is_port_free,
) -> int:
    port = requested_start
    while True:
        if all(checker(host, candidate) for candidate in range(port, port + tp_size)):
            return port
        port += 1


def find_free_single_port(
    host: str,
    requested_port: int,
    reserved: set[int],
    checker: Callable[[str, int], bool] = is_port_free,
) -> int:
    port = requested_port
    while True:
        if port not in reserved and checker(host, port):
            return port
        port += 1


def resolve_ports(
    host: str,
    requested_start_port: int,
    tp_size: int,
    master_node_addr: str,
    checker: Callable[[str, int], bool] = is_port_free,
) -> tuple[int, str]:
    api_start = find_free_api_start(host, requested_start_port, tp_size, checker)
    master_host, master_port = parse_master_addr(master_node_addr)
    api_ports = set(range(api_start, api_start + tp_size))
    actual_master_port = find_free_single_port(master_host, master_port, api_ports, checker)
    return api_start, f"{master_host}:{actual_master_port}"


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def build_xllm_args(options: RuntimeOptions, rank: int, port: int, master_addr: str) -> list[str]:
    args = [
        str(options.xllm_bin),
        "--model",
        options.model,
        "--host",
        options.host,
        f"--devices=npu:{rank}",
        "--port",
        str(port),
        f"--master_node_addr={master_addr}",
        f"--nnodes={options.tp_size}",
        f"--max_memory_utilization={options.max_memory_utilization}",
        f"--max_seqs_per_batch={options.max_seqs_per_batch}",
        f"--max_tokens_per_chunk_for_prefill={options.max_tokens_per_chunk_for_prefill}",
        f"--max_tokens_per_batch={options.max_tokens_per_batch}",
        f"--block_size={options.block_size}",
        f"--communication_backend={options.communication_backend}",
        f"--npu_kernel_backend={options.npu_kernel_backend}",
        f"--enable_prefix_cache={bool_text(options.enable_prefix_cache)}",
        f"--enable_chunked_prefill={bool_text(options.enable_chunked_prefill)}",
        f"--enable_schedule_overlap={bool_text(options.enable_schedule_overlap)}",
        f"--enable_shm={bool_text(options.enable_shm)}",
        f"--num_speculative_tokens={options.num_speculative_tokens}",
        f"--node_rank={rank}",
        "--task=generate",
        "--backend=llm",
    ]
    if options.model_id:
        args.extend(["--model_id", options.model_id])
    if options.draft_model:
        args.extend(
            [
                "--draft_model",
                options.draft_model,
                f"--draft_devices=npu:{rank}",
            ]
        )
    args.extend(options.extra_xllm_args)
    return args


def build_shell_command(xllm_args: list[str]) -> str:
    source_parts = [
        f"if [ -f {shlex.quote(path)} ]; then source {shlex.quote(path)}; fi"
        for path in ASCEND_ENV_SCRIPTS
    ]
    command = " ".join(shlex.quote(item) for item in xllm_args)
    return "; ".join(source_parts + [f"exec {command}"])


def build_multiline_exec_command(xllm_args: list[str]) -> list[str]:
    if not xllm_args:
        return []

    parts: list[str] = []
    index = 1
    while index < len(xllm_args):
        current = xllm_args[index]
        next_item = xllm_args[index + 1] if index + 1 < len(xllm_args) else None
        if (
            current.startswith("--")
            and "=" not in current
            and next_item is not None
            and not next_item.startswith("--")
        ):
            parts.append(f"{shlex.quote(current)} {shlex.quote(next_item)}")
            index += 2
            continue
        parts.append(shlex.quote(current))
        index += 1

    if not parts:
        return [f"exec {shlex.quote(xllm_args[0])}"]

    lines = [f"exec {shlex.quote(xllm_args[0])} \\"]
    for part_index, part in enumerate(parts):
        suffix = " \\" if part_index < len(parts) - 1 else ""
        lines.append(f"  {part}{suffix}")
    return lines


def build_multiline_shell_command(xllm_args: list[str]) -> list[str]:
    source_lines = [
        f"if [ -f {shlex.quote(path)} ]; then source {shlex.quote(path)}; fi"
        for path in ASCEND_ENV_SCRIPTS
    ]
    return source_lines + build_multiline_exec_command(xllm_args)


def command_env_lines(selected_devices: list[int], hccl_if_base_port: int) -> list[str]:
    return [
        f"ASCEND_RT_VISIBLE_DEVICES={','.join(str(item) for item in selected_devices)}",
        f"HCCL_IF_BASE_PORT={hccl_if_base_port}",
    ]


def command_record_text(env_lines: list[str], command_lines: list[str]) -> str:
    return "\n".join(env_lines + command_lines) + "\n"


def format_start_command_block(
    rank: int,
    env_lines: list[str],
    command_lines: list[str],
    command_path: Path | None = None,
    log_path: Path | None = None,
) -> str:
    lines = [
        "",
        separator("="),
        f"xLLM launch command (rank {rank})",
    ]
    if command_path is not None:
        lines.append(f"command file: {command_path}")
    if log_path is not None:
        lines.append(f"log file: {log_path}")
    lines.extend(
        [
            separator("-"),
            *env_lines,
            *command_lines,
            separator("="),
            "",
        ]
    )
    return "\n".join(lines)


def print_start_command_block(
    rank: int,
    env_lines: list[str],
    command_lines: list[str],
    command_path: Path | None = None,
    log_path: Path | None = None,
) -> None:
    print(
        format_start_command_block(rank, env_lines, command_lines, command_path, log_path),
        flush=True,
    )


def service_dir_path(log_dir: Path, timestamp: str | None = None) -> Path:
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / stamp / "service"


def prepare_service_dir(log_dir: Path, timestamp: str | None = None) -> Path:
    service_dir = service_dir_path(log_dir, timestamp)
    service_dir.mkdir(parents=True, exist_ok=True)
    return service_dir


def build_rank_commands(
    options: RuntimeOptions,
    api_start_port: int,
    master_addr: str,
) -> list[list[str]]:
    return [
        build_xllm_args(options, rank, api_start_port + rank, master_addr)
        for rank in range(options.tp_size)
    ]


def write_start_commands(
    options: RuntimeOptions,
    service_dir: Path,
    selected_devices: list[int],
    api_start_port: int,
    master_addr: str,
) -> list[list[str]]:
    commands = build_rank_commands(options, api_start_port, master_addr)
    env_lines = command_env_lines(selected_devices, options.hccl_if_base_port)
    for rank, xllm_args in enumerate(commands):
        command_lines = build_multiline_shell_command(xllm_args)
        command_path = service_dir / f"start_command_rank_{rank}.txt"
        command_path.write_text(command_record_text(env_lines, command_lines), encoding="utf-8")
    return commands


def launch_processes(
    options: RuntimeOptions,
    service_dir: Path,
    selected_devices: list[int],
    api_start_port: int,
    master_addr: str,
) -> list[subprocess.Popen[Any]]:
    commands = write_start_commands(options, service_dir, selected_devices, api_start_port, master_addr)
    env = os.environ.copy()
    env["ASCEND_RT_VISIBLE_DEVICES"] = ",".join(str(item) for item in selected_devices)
    env["HCCL_IF_BASE_PORT"] = str(options.hccl_if_base_port)
    cwd = options.xllm_code_path if options.xllm_code_path.is_dir() else options.project_root

    processes: list[subprocess.Popen[Any]] = []
    pid_lines: list[str] = []
    for rank, command in enumerate(commands):
        log_path = service_dir / f"node_{rank}.log"
        shell_command = build_shell_command(command)
        command_lines = build_multiline_shell_command(command)
        command_path = service_dir / f"start_command_rank_{rank}.txt"
        log_step(f"Launching rank {rank}: log={log_path}, command={command_path}")
        print_start_command_block(
            rank,
            command_env_lines(selected_devices, options.hccl_if_base_port),
            command_lines,
            command_path,
            log_path,
        )
        with log_path.open("ab") as log_file:
            proc = subprocess.Popen(
                ["bash", "-lc", shell_command],
                cwd=cwd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        processes.append(proc)
        log_step(f"Launched rank {rank}: pid={proc.pid}")
        pid_lines.append(f"rank={rank} pid={proc.pid} log={log_path}")

    (service_dir / "pids.txt").write_text("\n".join(pid_lines) + "\n", encoding="utf-8")
    return processes


def terminate_processes(processes: list[subprocess.Popen[Any]], grace_seconds: int = 10) -> None:
    live = [proc for proc in processes if proc.poll() is None]
    if not live:
        return
    pids = ", ".join(str(proc.pid) for proc in live)
    log_step(f"Stopping startup processes after failed launch: pids=[{pids}]")
    for proc in live:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            proc.terminate()

    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        if all(proc.poll() is not None for proc in live):
            return
        time.sleep(0.2)

    still_live = [proc for proc in live if proc.poll() is None]
    if not still_live:
        return
    pids = ", ".join(str(proc.pid) for proc in still_live)
    log_step(f"Force killing startup processes: pids=[{pids}]")
    for proc in still_live:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            proc.kill()


def connect_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def truncate_for_log(value: str, limit: int = 220) -> str:
    normalized = " ".join(value.strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def last_nonempty_log_line(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_bytes().decode("utf-8", errors="ignore").replace("\x00", "").splitlines()
    for line in reversed(lines):
        if line.strip():
            return truncate_for_log(line)
    return ""


def startup_log_diagnostic(path: Path) -> str:
    if not path.exists():
        return "startup log not created yet"
    stat = path.stat()
    idle_seconds = max(0, int(time.time() - stat.st_mtime))
    last_line = last_nonempty_log_line(path)
    if not last_line:
        return f"log_size={stat.st_size}B, log_idle={idle_seconds}s, last_log=n/a"
    return f"log_size={stat.st_size}B, log_idle={idle_seconds}s, last_log={last_line!r}"


def wait_for_ready(
    host: str,
    api_port: int,
    timeout_seconds: int,
    processes: list[subprocess.Popen[Any]],
    service_dir: Path,
) -> str:
    endpoint = f"http://{connect_host(host)}:{api_port}/v1"
    ready_url = f"{endpoint}/models"
    deadline = time.time() + timeout_seconds
    started = time.time()
    next_log = started
    first_log = service_dir / "node_0.log"
    print_kv_block(
        "Waiting for service readiness",
        [
            ("health check", ready_url),
            ("timeout", f"{timeout_seconds}s"),
            ("startup log", first_log),
        ],
    )
    while time.time() < deadline:
        for proc in processes:
            if proc.poll() is not None:
                raise StartError(f"xLLM process exited before ready: pid={proc.pid}, rc={proc.returncode}")
        try:
            with urlopen(ready_url, timeout=3) as response:
                if 200 <= response.status < 500:
                    elapsed = int(time.time() - started)
                    print_kv_block(
                        "Readiness check passed",
                        [
                            ("elapsed", f"{elapsed}s"),
                            ("health check", ready_url),
                        ],
                    )
                    return endpoint
        except URLError:
            pass
        except TimeoutError:
            pass
        now = time.time()
        if now >= next_log:
            elapsed = int(now - started)
            pids = ", ".join(str(proc.pid) for proc in processes)
            log_step(
                f"Still waiting for service ready: elapsed={elapsed}s/{timeout_seconds}s, "
                f"pids=[{pids}], {startup_log_diagnostic(first_log)}, log={first_log}"
            )
            next_log = now + 10
        time.sleep(5)
    raise StartError(f"xLLM service is not ready after {timeout_seconds}s: {ready_url}")


def unit_to_gb(value: float, unit: str) -> float:
    normalized = unit.upper()
    factors = {
        "B": 1 / (1024 ** 3),
        "KB": 1 / (1024 ** 2),
        "MB": 1 / 1024,
        "GB": 1,
        "TB": 1024,
    }
    return value * factors.get(normalized, 1)


def parse_log_summary(path: Path, fallback_block_size: int) -> LogSummary:
    summary = LogSummary(path=path, block_size=fallback_block_size)
    if not path.exists():
        return summary
    text = path.read_bytes().decode("utf-8", errors="ignore").replace("\x00", "")
    block_match = None
    memory_match = None
    kv_match = None
    for match in re.finditer(
        r"Block info, block_size: (\d+), .*?n_layers: (\d+), dtype: (\S+), kv_cache_dtype: (\S+)",
        text,
    ):
        block_match = match
    for match in re.finditer(
        r"available memory: ([0-9.]+) ([A-Z]+), total memory: ([0-9.]+) ([A-Z]+).*?"
        r"Using max_memory_utilization: ([0-9.]+)",
        text,
    ):
        memory_match = match
    for match in re.finditer(
        r"kv cache capacity: ([0-9.]+) ([A-Z]+), blocks: (\d+), .*?"
        r"n_layers: (\d+), kv_cache_dtype: (\S+)",
        text,
    ):
        kv_match = match

    if block_match:
        summary.block_size = int(block_match.group(1))
        summary.n_layers = int(block_match.group(2))
        summary.kv_cache_dtype = block_match.group(4).rstrip(",")
    if memory_match:
        summary.available_memory_gb = unit_to_gb(float(memory_match.group(1)), memory_match.group(2))
        summary.total_memory_gb = unit_to_gb(float(memory_match.group(3)), memory_match.group(4))
        summary.max_memory_utilization = float(memory_match.group(5))
    if kv_match:
        summary.kv_cache_capacity_gb = unit_to_gb(float(kv_match.group(1)), kv_match.group(2))
        summary.blocks = int(kv_match.group(3))
        summary.n_layers = int(kv_match.group(4))
        summary.kv_cache_dtype = kv_match.group(5).rstrip(",")
    if summary.blocks is not None and summary.block_size is not None:
        summary.token_capacity = summary.blocks * summary.block_size
    return summary


def parse_service_summaries(service_dir: Path, tp_size: int, fallback_block_size: int) -> list[LogSummary]:
    return [
        parse_log_summary(service_dir / f"node_{rank}.log", fallback_block_size)
        for rank in range(tp_size)
    ]


def gb_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} GB"


def int_text(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def format_summary(
    options: RuntimeOptions,
    selected_devices: list[int],
    requested_start_port: int,
    actual_start_port: int,
    requested_master_addr: str,
    actual_master_addr: str,
    endpoint: str,
    service_dir: Path,
    summaries: list[LogSummary],
) -> str:
    blocks = [
        format_kv_block(
            "xLLM service ready",
            [
                ("endpoint", endpoint),
                ("model", options.model),
                ("model id", options.model_id or "n/a"),
                ("xLLM binary", options.xllm_bin),
                ("TP size", options.tp_size),
                ("NPU kernel backend", options.npu_kernel_backend),
                ("selected NPU logic IDs", ",".join(str(item) for item in selected_devices)),
                ("API start port", f"requested={requested_start_port}, actual={actual_start_port}"),
                ("master addr", f"requested={requested_master_addr}, actual={actual_master_addr}"),
                ("log dir", service_dir),
            ],
        )
    ]
    capacities = []
    rows = []
    for rank, item in enumerate(summaries):
        if item.token_capacity is not None:
            capacities.append(item.token_capacity)
        rows.append(
            [
                rank,
                gb_text(item.total_memory_gb),
                gb_text(item.available_memory_gb),
                gb_text(item.non_kv_memory_estimate_gb),
                gb_text(item.kv_cache_capacity_gb),
                int_text(item.blocks),
                int_text(item.block_size),
                int_text(item.token_capacity),
                item.kv_cache_dtype or "n/a",
            ]
        )
    memory_lines = format_table(
        [
            "Rank",
            "Total",
            "Available",
            "Weight/non-KV",
            "KV Cache",
            "Blocks",
            "Block",
            "Tokens",
            "KV dtype",
        ],
        rows,
        right_align={0, 1, 2, 3, 4, 5, 6, 7},
    )
    if capacities:
        memory_lines.extend(["", f"Minimum token capacity across ranks: {min(capacities)}"])
    else:
        memory_lines.extend(["", "KV Cache summary was not found yet. Inspect node logs for details."])
    memory_lines.append("Weight/non-KV is estimated as total memory minus available memory.")
    blocks.append(format_block("Startup memory summary", memory_lines))
    return "\n".join(blocks)


def tail_file(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return ""
    text = path.read_bytes().decode("utf-8", errors="ignore").replace("\x00", "")
    return "\n".join(text.splitlines()[-max_lines:])


def print_startup_failure(exc: Exception, service_dir: Path, stream: Any = sys.stderr) -> None:
    first_log = service_dir / "node_0.log"
    print_kv_block(
        "xLLM startup failed",
        [
            ("error", str(exc)),
            ("service dir", service_dir),
            ("startup log", first_log),
        ],
        stream=stream,
    )
    tail = tail_file(first_log)
    if tail:
        print_block(
            "Last startup log lines",
            tail.splitlines(),
            stream=stream,
        )


def add_bool_pair(parser: argparse.ArgumentParser, name: str, dest: str, help_text: str) -> None:
    parser.add_argument(f"--enable-{name}", dest=dest, action="store_true", default=None, help=help_text)
    if help_text.startswith("Enable "):
        disable_help = "Disable " + help_text[len("Enable "):]
    else:
        disable_help = f"Disable {name}"
    parser.add_argument(f"--disable-{name}", dest=dest, action="store_false", help=disable_help)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start xLLM on idle Ascend NPU devices.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.json")
    parser.add_argument(
        "--config-template",
        default=str(DEFAULT_CONFIG_TEMPLATE),
        help="Path to config.example.json",
    )

    parser.add_argument("--xllm-code-path", help="Override code.xllm.path")
    parser.add_argument("--xllm-origin-url", help="Override code.xllm.origin.url")
    parser.add_argument("--xllm-origin-branch", help="Override code.xllm.origin.branch")
    parser.add_argument("--xllm-origin-commit", help="Override code.xllm.origin.commit")
    parser.add_argument("--xllm-upstream-url", help="Override code.xllm.upstream.url")
    parser.add_argument("--xllm-upstream-branch", help="Override code.xllm.upstream.branch")
    parser.add_argument("--xllm-upstream-commit", help="Override code.xllm.upstream.commit")

    parser.add_argument("--model", help="Override xllm_config.model")
    parser.add_argument("--model-id", help="Override xllm_config.model_id")
    parser.add_argument("--max-memory-utilization", type=float, help="Override xllm_config.max_memory_utilization")
    parser.add_argument("--max-seqs-per-batch", type=int, help="Override xllm_config.max_seqs_per_batch")
    parser.add_argument(
        "--max-tokens-per-chunk-for-prefill",
        type=int,
        help="Override xllm_config.max_tokens_per_chunk_for_prefill",
    )
    parser.add_argument("--max-tokens-per-batch", type=int, help="Override xllm_config.max_tokens_per_batch")
    parser.add_argument("--tp-size", type=int, help="Override xllm_config.tp_size")
    parser.add_argument("--draft-model", help="Override xllm_config.draft_model")
    parser.add_argument("--num-speculative-tokens", type=int, help="Override xllm_config.num_speculative_tokens")

    parser.add_argument("--xllm-bin", help="xLLM binary path. Overrides auto discovery from code.xllm.path.")
    parser.add_argument("--host", help="Service host")
    parser.add_argument("--start-port", type=int, help="First API port to try")
    parser.add_argument("--master-node-addr", help="Master address in host:port form")
    parser.add_argument("--hccl-if-base-port", type=int, help="HCCL_IF_BASE_PORT value")
    parser.add_argument("--log-dir", help="Base log directory")
    parser.add_argument("--communication-backend", help="xLLM communication backend")
    parser.add_argument(
        "--npu-kernel-backend",
        choices=["AUTO", "ATB", "TORCH", "auto", "atb", "torch"],
        help=(
            "xLLM --npu_kernel_backend value. Script AUTO uses TORCH for Qwen3 "
            "unless this option is explicitly set."
        ),
    )
    parser.add_argument("--block-size", type=int, help="KV cache block size")
    add_bool_pair(parser, "prefix-cache", "enable_prefix_cache", "Enable prefix cache")
    add_bool_pair(parser, "chunked-prefill", "enable_chunked_prefill", "Enable chunked prefill")
    add_bool_pair(parser, "schedule-overlap", "enable_schedule_overlap", "Enable schedule overlap")
    add_bool_pair(parser, "shm", "enable_shm", "Enable shared memory")
    parser.add_argument("--poll-interval-seconds", type=int, help="Idle-device polling interval")
    parser.add_argument("--ready-timeout-seconds", type=int, help="Service ready timeout")
    parser.add_argument("--free-hbm-usage-pct-max", type=int, help="Max HBM usage for an idle chip")
    parser.add_argument("--free-aicore-usage-pct-max", type=int, help="Max AICore usage for an idle chip")
    parser.add_argument(
        "--extra-xllm-arg",
        action="append",
        help="Pass one extra raw argument to xLLM. Repeat for multiple arguments.",
    )

    parser.add_argument("--dry-run", action="store_true", help="Print selected config and commands without starting")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting for missing values")
    parser.add_argument("--once", action="store_true", help="Check idle devices once instead of polling")
    return parser


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    template_path = Path(args.config_template).expanduser()
    if not template_path.is_absolute():
        template_path = Path.cwd() / template_path

    log_step(f"Loading config: {config_path}")
    config, changed = load_config(config_path, template_path)
    if changed:
        log_step(f"Backfilled missing config fields from template: {template_path}")
    effective = apply_config_cli_overrides(config, args)
    ensure_required_model(config, effective, config_path, args)
    options = build_runtime_options(effective, config_path, args)
    print_kv_block(
        "Effective startup configuration",
        [
            ("config", config_path),
            ("model", options.model),
            ("model id", options.model_id or "n/a"),
            ("xLLM binary", options.xllm_bin),
            ("xLLM code path", options.xllm_code_path),
            ("TP size", options.tp_size),
            ("NPU kernel backend", options.npu_kernel_backend),
            ("max memory utilization", options.max_memory_utilization),
            ("max seqs per batch", options.max_seqs_per_batch),
            ("max tokens per batch", options.max_tokens_per_batch),
            ("chunked prefill chunk", options.max_tokens_per_chunk_for_prefill),
        ],
    )
    if options.npu_kernel_backend_note:
        log_step(options.npu_kernel_backend_note)

    print_kv_block(
        "Idle NPU scan",
        [
            ("required chips", options.tp_size),
            ("max HBM usage", f"{options.free_hbm_usage_pct_max}%"),
            ("max AICore usage", f"{options.free_aicore_usage_pct_max}%"),
            ("poll interval", f"{options.poll_interval_seconds}s"),
            ("single pass only", args.once),
        ],
    )
    selected_devices = select_idle_devices(
        options.tp_size,
        options.free_hbm_usage_pct_max,
        options.free_aicore_usage_pct_max,
        options.poll_interval_seconds,
        args.once,
    )
    print_kv_block(
        "NPU selection",
        [
            ("selected logic IDs", ",".join(str(item) for item in selected_devices)),
            ("ASCEND_RT_VISIBLE_DEVICES", ",".join(str(item) for item in selected_devices)),
        ],
    )
    actual_start_port, actual_master_addr = resolve_ports(
        options.host,
        options.start_port,
        options.tp_size,
        options.master_node_addr,
    )
    endpoint = f"http://{connect_host(options.host)}:{actual_start_port}/v1"
    print_kv_block(
        "Port resolution",
        [
            ("host", options.host),
            ("endpoint", endpoint),
            ("API start port", f"requested={options.start_port}, actual={actual_start_port}"),
            ("master addr", f"requested={options.master_node_addr}, actual={actual_master_addr}"),
            ("HCCL_IF_BASE_PORT", options.hccl_if_base_port),
        ],
    )
    if args.dry_run:
        service_dir = service_dir_path(options.log_dir)
        commands = build_rank_commands(options, actual_start_port, actual_master_addr)
        print_kv_block(
            "Dry run summary",
            [
                ("action", "xLLM will not be started"),
                ("endpoint", endpoint),
                ("selected NPU logic IDs", ",".join(str(item) for item in selected_devices)),
                ("NPU kernel backend", options.npu_kernel_backend),
                ("log dir preview", service_dir),
            ],
        )
        for rank, command in enumerate(commands):
            print_start_command_block(
                rank,
                command_env_lines(selected_devices, options.hccl_if_base_port),
                build_multiline_shell_command(command),
            )
        return 0

    service_dir = prepare_service_dir(options.log_dir)
    print_kv_block(
        "Service artifacts",
        [
            ("service dir", service_dir),
            ("pid file", service_dir / "pids.txt"),
            ("rank logs", service_dir / "node_<rank>.log"),
        ],
    )
    processes = launch_processes(
        options,
        service_dir,
        selected_devices,
        actual_start_port,
        actual_master_addr,
    )
    try:
        endpoint = wait_for_ready(
            options.host,
            actual_start_port,
            options.ready_timeout_seconds,
            processes,
            service_dir,
        )
    except StartError as exc:
        terminate_processes(processes)
        print_startup_failure(exc, service_dir)
        return 1
    except KeyboardInterrupt:
        terminate_processes(processes)
        raise

    summaries = parse_service_summaries(service_dir, options.tp_size, options.block_size)
    print(
        format_summary(
            options,
            selected_devices,
            options.start_port,
            actual_start_port,
            options.master_node_addr,
            actual_master_addr,
            endpoint,
            service_dir,
            summaries,
        )
    )
    return 0


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print_block("Interrupted", ["Startup interrupted by user."], stream=sys.stderr)
        return 130
    except StartError as exc:
        print_block("Error", [str(exc)], stream=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
