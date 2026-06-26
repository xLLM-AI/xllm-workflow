import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "start_xllm_service", ROOT / "scripts" / "start_xllm_service.py"
)
start = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = start
SPEC.loader.exec_module(start)


def base_config(model="/models/Qwen3-8B"):
    return {
        "code": {
            "xllm": {
                "path": "code/xllm",
                "origin": {
                    "url": "https://example.com/origin.git",
                    "branch": "main",
                    "commit": "",
                },
                "upstream": {
                    "url": "https://example.com/upstream.git",
                    "branch": "main",
                    "commit": "",
                },
            }
        },
        "xllm_config": {
            "model": model,
            "model_id": "Qwen3-8B",
            "max_memory_utilization": 0.8,
            "max_seqs_per_batch": 1024,
            "max_tokens_per_chunk_for_prefill": -1,
            "max_tokens_per_batch": 10240,
            "tp_size": 1,
            "draft_model": "",
            "num_speculative_tokens": 0,
        },
    }


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def make_xllm_bin(code_path):
    binary = code_path / "build" / "lib.linux-aarch64-cpython-311" / "xllm" / "xllm"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def parser_options():
    parser = start.build_arg_parser()
    return {
        option
        for action in parser._actions
        for option in action.option_strings
    }


def test_config_startup_fields_have_cli_overrides():
    parser = start.build_arg_parser()
    dests = {action.dest for action in parser._actions}

    for _keys, attr in start.CONFIG_CLI_OVERRIDES:
        assert attr in dests

    options = parser_options()
    assert "--xllm-code-path" in options
    assert "--model" in options
    assert "--num-speculative-tokens" in options
    assert "--npu-kernel-backend" in options


def test_cli_overrides_config_without_writing(tmp_path):
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "config.example.json"
    config = base_config(model="/models/config")
    write_json(config_path, config)
    write_json(template_path, config)
    xllm_bin = make_xllm_bin(tmp_path / "code" / "xllm")

    args = start.build_arg_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--config-template",
            str(template_path),
            "--xllm-bin",
            str(xllm_bin),
            "--model",
            "/models/cli",
            "--tp-size",
            "2",
            "--max-memory-utilization",
            "0.73",
        ]
    )

    loaded, _changed = start.load_config(config_path, template_path)
    effective = start.apply_config_cli_overrides(loaded, args)
    options = start.build_runtime_options(effective, config_path, args)

    assert options.model == "/models/cli"
    assert options.tp_size == 2
    assert options.max_memory_utilization == 0.73
    assert json.loads(config_path.read_text(encoding="utf-8"))["xllm_config"]["model"] == "/models/config"


def test_existing_config_values_drive_runtime_options(tmp_path):
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "config.example.json"
    config = base_config(model="/models/from-config")
    config["xllm_config"].update(
        {
            "model_id": "from-config",
            "max_memory_utilization": 0.66,
            "max_seqs_per_batch": 17,
            "max_tokens_per_chunk_for_prefill": 2048,
            "max_tokens_per_batch": 4096,
            "tp_size": 3,
            "draft_model": "/models/draft",
            "num_speculative_tokens": 4,
        }
    )
    write_json(config_path, config)
    write_json(template_path, base_config())
    xllm_bin = make_xllm_bin(tmp_path / "code" / "xllm")

    args = start.build_arg_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--config-template",
            str(template_path),
            "--xllm-bin",
            str(xllm_bin),
        ]
    )
    loaded, _changed = start.load_config(config_path, template_path)
    effective = start.apply_config_cli_overrides(loaded, args)
    options = start.build_runtime_options(effective, config_path, args)

    assert options.model == "/models/from-config"
    assert options.npu_kernel_backend == "AUTO"
    assert options.npu_kernel_backend_note == ""
    assert options.max_memory_utilization == 0.66
    assert options.max_seqs_per_batch == 17
    assert options.max_tokens_per_chunk_for_prefill == 2048
    assert options.max_tokens_per_batch == 4096
    assert options.tp_size == 3
    assert options.draft_model == "/models/draft"
    assert options.num_speculative_tokens == 4


def test_qwen3_auto_uses_torch_backend_by_default(tmp_path):
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "config.example.json"
    config = base_config(model="/models/Qwen3-1.7B")
    config["xllm_config"]["model_id"] = "Qwen3-1.7B"
    write_json(config_path, config)
    write_json(template_path, config)
    xllm_bin = make_xllm_bin(tmp_path / "code" / "xllm")

    args = start.build_arg_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--config-template",
            str(template_path),
            "--xllm-bin",
            str(xllm_bin),
        ]
    )
    loaded, _changed = start.load_config(config_path, template_path)
    effective = start.apply_config_cli_overrides(loaded, args)
    options = start.build_runtime_options(effective, config_path, args)

    assert options.npu_kernel_backend == "TORCH"
    assert "Qwen3 detected" in options.npu_kernel_backend_note


def test_cli_npu_kernel_backend_overrides_qwen3_auto(tmp_path):
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "config.example.json"
    config = base_config(model="/models/Qwen3-1.7B")
    config["xllm_config"]["model_id"] = "Qwen3-1.7B"
    write_json(config_path, config)
    write_json(template_path, config)
    xllm_bin = make_xllm_bin(tmp_path / "code" / "xllm")

    args = start.build_arg_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--config-template",
            str(template_path),
            "--xllm-bin",
            str(xllm_bin),
            "--npu-kernel-backend",
            "ATB",
        ]
    )
    loaded, _changed = start.load_config(config_path, template_path)
    effective = start.apply_config_cli_overrides(loaded, args)
    options = start.build_runtime_options(effective, config_path, args)

    assert options.npu_kernel_backend == "ATB"
    assert options.npu_kernel_backend_note == ""


def test_missing_schema_fields_are_backfilled_from_template(tmp_path):
    config_path = tmp_path / "config.json"
    template_path = tmp_path / "config.example.json"
    write_json(config_path, {"code": {"xllm": {"path": "code/xllm"}}})
    write_json(template_path, base_config(model=""))

    config, changed = start.load_config(config_path, template_path)

    assert changed is True
    assert config["xllm_config"]["tp_size"] == 1
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["code"]["xllm"]["path"] == "code/xllm"
    assert saved["xllm_config"]["max_tokens_per_batch"] == 10240


def test_missing_model_prompt_writes_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config = base_config(model="")
    write_json(config_path, config)
    effective = json.loads(json.dumps(config))
    args = start.build_arg_parser().parse_args(["--config", str(config_path)])

    class Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(start.sys, "stdin", Tty())
    monkeypatch.setattr("builtins.input", lambda _prompt: "/models/prompted")

    start.ensure_required_model(config, effective, config_path, args)

    assert effective["xllm_config"]["model"] == "/models/prompted"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["xllm_config"]["model"] == "/models/prompted"


def test_resolve_xllm_bin_uses_code_path_build_candidate(tmp_path):
    code_path = tmp_path / "code" / "xllm"
    binary = make_xllm_bin(code_path)

    resolved = start.resolve_xllm_bin(None, code_path, tmp_path, non_interactive=True)

    assert resolved == binary.resolve()


def test_parse_and_select_idle_npu_devices():
    mapping = """
    NPU ID                         Chip ID                        Chip Logic ID                  Chip Phy-ID                    Chip Name
    0                              0                              0                              0                              Ascend910
    0                              1                              1                              1                              Ascend910
    0                              2                              -                              -                              Mcu
    1                              0                              2                              2                              Ascend910
    """
    usages0 = """
    HBM Usage Rate(%)              : 4
    Aicore Usage Rate(%)           : 0
    Chip ID                        : 0

    HBM Usage Rate(%)              : 78
    Aicore Usage Rate(%)           : 0
    Chip ID                        : 1
    """
    proc0 = """
    No process in device.
    Chip ID                        : 0

    Process id:3229095 Process name:                  Process memory(MB):48208
    Chip ID                        : 1
    """
    usages1 = """
    HBM Usage Rate(%)              : 3
    Aicore Usage Rate(%)           : 0
    Chip ID                        : 0
    """
    proc1 = """
    No process in device.
    Chip ID                        : 0
    """

    def runner(cmd):
        joined = " ".join(cmd)
        if joined == "npu-smi info -m":
            return mapping
        if joined == "npu-smi info -t usages -i 0":
            return usages0
        if joined == "npu-smi info -t proc-mem -i 0":
            return proc0
        if joined == "npu-smi info -t usages -i 1":
            return usages1
        if joined == "npu-smi info -t proc-mem -i 1":
            return proc1
        raise AssertionError(joined)

    selected = start.select_idle_devices(
        tp_size=2,
        free_hbm_usage_pct_max=10,
        free_aicore_usage_pct_max=5,
        poll_interval_seconds=0,
        once=True,
        runner=runner,
    )

    assert selected == [0, 2]


def test_resolve_ports_avoids_busy_api_and_master_ports():
    busy = {18000, 9748}

    def checker(_host, port):
        return port not in busy

    api_start, master_addr = start.resolve_ports(
        "0.0.0.0",
        18000,
        2,
        "127.0.0.1:9748",
        checker=checker,
    )

    assert api_start == 18001
    assert master_addr == "127.0.0.1:9749"


def test_master_port_moves_when_it_overlaps_api_range():
    def checker(_host, _port):
        return True

    api_start, master_addr = start.resolve_ports(
        "0.0.0.0",
        18000,
        2,
        "127.0.0.1:18001",
        checker=checker,
    )

    assert api_start == 18000
    assert master_addr == "127.0.0.1:18002"


def test_build_xllm_args_contains_rank_ports_and_config_values(tmp_path):
    xllm_bin = make_xllm_bin(tmp_path / "code" / "xllm")
    options = start.RuntimeOptions(
        project_root=tmp_path,
        config_path=tmp_path / "config.json",
        xllm_code_path=tmp_path / "code" / "xllm",
        xllm_bin=xllm_bin,
        model="/models/Qwen3-8B",
        model_id="Qwen3-8B",
        max_memory_utilization=0.75,
        max_seqs_per_batch=16,
        max_tokens_per_chunk_for_prefill=8192,
        max_tokens_per_batch=16384,
        tp_size=2,
        draft_model="/models/draft",
        num_speculative_tokens=3,
        host="0.0.0.0",
        start_port=18000,
        master_node_addr="127.0.0.1:9748",
        hccl_if_base_port=43432,
        log_dir=tmp_path / "runs",
        communication_backend="hccl",
        npu_kernel_backend="TORCH",
        block_size=128,
        enable_prefix_cache=False,
        enable_chunked_prefill=True,
        enable_schedule_overlap=True,
        enable_shm=True,
        poll_interval_seconds=30,
        ready_timeout_seconds=600,
        free_hbm_usage_pct_max=10,
        free_aicore_usage_pct_max=5,
    )

    command = start.build_xllm_args(options, rank=1, port=18001, master_addr="127.0.0.1:9749")

    assert str(xllm_bin) == command[0]
    assert "--model" in command
    assert "/models/Qwen3-8B" in command
    assert "--host" in command
    assert "0.0.0.0" in command
    assert "--devices=npu:1" in command
    assert "--port" in command
    assert "18001" in command
    assert "--master_node_addr=127.0.0.1:9749" in command
    assert "--max_memory_utilization=0.75" in command
    assert "--max_seqs_per_batch=16" in command
    assert "--max_tokens_per_chunk_for_prefill=8192" in command
    assert "--max_tokens_per_batch=16384" in command
    assert "--communication_backend=hccl" in command
    assert "--npu_kernel_backend=TORCH" in command
    assert "--enable_prefix_cache=false" in command
    assert "--enable_chunked_prefill=true" in command
    assert "--draft_model" in command
    assert "/models/draft" in command
    assert "--num_speculative_tokens=3" in command


def test_format_start_command_block_is_readable(tmp_path):
    env_lines = ["ASCEND_RT_VISIBLE_DEVICES=2", "HCCL_IF_BASE_PORT=43432"]
    command_lines = [
        "if [ -f /env.sh ]; then source /env.sh; fi",
        "exec /bin/xllm \\",
        "  --model /models/qwen \\",
        "  --host 0.0.0.0",
    ]
    block = start.format_start_command_block(
        0,
        env_lines,
        command_lines,
        tmp_path / "start_command_rank_0.txt",
        tmp_path / "node_0.log",
    )

    assert block.startswith("\n" + "=" * 88)
    assert "\nxLLM launch command (rank 0)\n" in block
    assert f"command file: {tmp_path / 'start_command_rank_0.txt'}" in block
    assert f"log file: {tmp_path / 'node_0.log'}" in block
    assert "\n" + "-" * 88 + "\n" in block
    assert "ASCEND_RT_VISIBLE_DEVICES=2\n" in block
    assert "exec /bin/xllm \\\n" in block
    assert "  --model /models/qwen \\\n" in block
    assert "  --host 0.0.0.0\n" in block
    assert block.endswith("=" * 88 + "\n")


def test_build_multiline_shell_command_groups_flag_values():
    command_lines = start.build_multiline_shell_command(
        [
            "/bin/xllm",
            "--model",
            "/models/qwen",
            "--host",
            "0.0.0.0",
            "--devices=npu:0",
        ]
    )

    assert command_lines[-4:] == [
        "exec /bin/xllm \\",
        "  --model /models/qwen \\",
        "  --host 0.0.0.0 \\",
        "  --devices=npu:0",
    ]


def test_parse_log_summary_calculates_token_capacity(tmp_path):
    log = tmp_path / "node_0.log"
    log.write_text(
        """
I20260616 llm_engine.cpp:209] Block info, block_size: 128, n_local_kv_heads: 8, head_dim: 128, n_layers: 28, dtype: BFloat16, kv_cache_dtype: auto
I20260616 llm_engine.cpp:416] worker #0: available memory: 56.46 GB, total memory: 61.27 GB. Using max_memory_utilization: 0.8, max_cache_size: 0.00 B
I20260616 llm_engine.cpp:473] kv cache capacity: 44.20 GB, blocks: 3233, slot_size: 4096, index_slot_size: 0, scale_slot_size: 0, linear_slot_size: 0, linear_blocks: 202, reserved_linear_bytes: 0.00 B, n_layers: 28, kv_cache_dtype: auto
""",
        encoding="utf-8",
    )

    summary = start.parse_log_summary(log, fallback_block_size=64)

    assert summary.total_memory_gb == 61.27
    assert summary.available_memory_gb == 56.46
    assert round(summary.non_kv_memory_estimate_gb, 2) == 4.81
    assert summary.kv_cache_capacity_gb == 44.20
    assert summary.blocks == 3233
    assert summary.block_size == 128
    assert summary.token_capacity == 3233 * 128
