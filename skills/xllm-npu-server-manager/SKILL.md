---
name: xllm-npu-server-manager
description: xLLM NPU 服务生命周期管理器。用于以不可覆盖的 attempt 启动和停止服务，执行模型身份 ready 检查、真实生成 smoke 请求、PID/端口/NPU 清理门禁，并生成 Run Evidence Gate 所需的机器可读 artifacts。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 服务管理器

负责 xLLM 服务的生命周期管理：启动、停止、健康检查、真实请求验证和清理证明。

## 职责边界

- 本 skill：启动/停止服务、健康检查、环境快照、进程管理。
- 被以下 skill 依赖：`xllm-npu-eval-runner`、`xllm-npu-perf-runner`、`xllm-npu-accuracy-runner`、`xllm-npu-batch-perf`。

## 工作流

### Step 1: 参数对齐

如果以下参数未提供，先与用户确认：

| 参数 | 环境变量 | 说明 | 示例 |
|---|---|---|---|
| API URL | `API_URL` | 服务 endpoint | `http://localhost:18050/v1` |
| Model Path | `MODEL_PATH` | 主模型权重路径 | `<model_path>` |
| Draft Model Path | `DRAFT_MODEL_PATH` | 投机解码 draft model 路径（留空则禁用 MTP） | `<draft_model_path>` |
| xLLM Binary Path | `XLLM_BIN` | xllm server binary 路径 | `<project_root>/code/xllm/build/xllm/core/server/xllm` |
| TP (NNODES) | `NNODES` | Tensor parallelism degree | `4` |
| Visible Devices | `ASCEND_RT_VISIBLE_DEVICES` | 可见的 NPU 设备 ID（逗号分隔） | `0,1,2,3` |
| Start Port | `START_PORT` | 起始端口 | `17112` |
| Run Root | `RUN_ROOT` | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |

可选高级参数（均有默认值，按需覆盖）：

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `MAX_MEMORY_UTILIZATION` | 显存利用率上限 | `0.75` |
| `MAX_TOKENS_PER_BATCH` | 每 batch 最大 token 数 | `8192` |
| `MAX_SEQS_PER_BATCH` | 每 batch 最大序列数 | `8` |
| `BLOCK_SIZE` | KV cache block 大小 | `128` |
| `COMMUNICATION_BACKEND` | 通信后端 | `lccl` |
| `MAX_CONCURRENT_REQUESTS` | 最大并发请求数 | `8` |
| `ENABLE_PREFIX_CACHE` | 启用 prefix cache | `true` |
| `ENABLE_CHUNKED_PREFILL` | 启用 chunked prefill | `true` |
| `ENABLE_SCHEDULE_OVERLAP` | 启用 schedule overlap | `true` |
| `ENABLE_GRAPH` | 启用 graph mode | `true` |
| `ENABLE_SHM` | 启用共享内存 | `true` |
| `NUM_SPECULATIVE_TOKENS` | 投机解码 token 数（0 则禁用 MTP） | `0` |
| `NPU_MEMORY_FRACTION` | NPU 显存分配比例 | `0.90` |
| `PROFILING_MODE` | profiling 模式 | `dynamic` |
| `SOURCE_VENDOR_ENV` | 是否加载标准 Ascend/ATB 环境脚本 | `true` |
| `ATTEMPT_ID` | 不可覆盖的服务尝试 ID | `attempt-<UTC>-<pid>` |
| `PID_FILE` | 本次启动的 PID manifest | `$RUN_ROOT/service/$ATTEMPT_ID/pids.txt` |
| `STOP_TIMEOUT` | TERM 后等待秒数，超时再 KILL | `30` |

### Step 2: 创建 Run Root 和环境快照

```bash
RUN_ROOT="${RUN_ROOT:-runs/eval/$(date +%Y%m%d_%H%M%S)_xllm_npu_eval}"
mkdir -p "$RUN_ROOT"/{env,service}
```

保存运行前环境快照：

```bash
npu-smi info > "$RUN_ROOT/env/npu-smi.before.txt"
pgrep -af 'xllm|vllm|sglang|python|evalscope|msprof' > "$RUN_ROOT/env/process.before.txt" || true
free -h > "$RUN_ROOT/env/mem.before.txt"
uptime > "$RUN_ROOT/env/load.before.txt"
```

使用 [`../../reference/io_specs/run-manifest-template.md`](../../reference/io_specs/run-manifest-template.md)
写入 `manifest.md`，至少记录：

- xLLM branch、commit 和 dirty diff 状态。
- Model path、draft model path、tokenizer path。
- Device ids、CANN/driver/torch_npu 版本。
- 服务启动命令和 API URL。

### Step 3: 启动服务

通过环境变量配置后启动：

```bash
export MODEL_PATH="<model_path>"
export NNODES=4
export ASCEND_RT_VISIBLE_DEVICES="0,1,2,3"
export START_PORT=17112
# ... 其他可选参数
bash <skill_dir>/scripts/run.sh
```

`run.sh` 创建新的 `$RUN_ROOT/service/$ATTEMPT_ID/`，保存 `command.sh`、`pids.txt`、
`node_*.log`、`environment.json` 和 `launch.json`。已有 attempt 直接报错，不覆盖。正式 run 不要把
`LOG_DIR`、`PID_FILE` 或 `COMMAND_FILE` 指向 attempt 目录之外；这些覆盖项只用于兼容旧调用方。

### Step 4: 执行 Ready 和 Smoke Gate

执行模型身份 ready gate：

```bash
python3 <skill_dir>/scripts/service_lifecycle.py ready \
  --attempt-dir "$RUN_ROOT/service/$ATTEMPT_ID" \
  --attempt-id "$ATTEMPT_ID" \
  --api-url "$API_URL" \
  --expected-model-id "$MODEL_ID"
```

随后发送真实 OpenAI-compatible 生成请求。需要严格固定请求时，通过
`--request-json` 传入已归档 payload：

```bash
python3 <skill_dir>/scripts/service_lifecycle.py smoke \
  --attempt-dir "$RUN_ROOT/service/$ATTEMPT_ID" \
  --attempt-id "$ATTEMPT_ID" \
  --api-url "$API_URL" \
  --model "$MODEL_ID"
```

ready 和 smoke 分别写入 `ready.json`、`smoke.json`；原始响应保存为
`smoke-response.json`。HTTP ready 不能替代真实生成 smoke。

### Step 5: 停止服务（按需）

只停止本次 `run.sh` 写入 PID manifest 的进程，避免误杀共享主机或容器中的其他服务：

```bash
export NPU_PHYSICAL_DEVICES="2,3"
bash <skill_dir>/scripts/stop.sh
pgrep -af xllm > "$RUN_ROOT/env/process.after_stop.txt" || true
```

`stop.sh` 先发送 TERM，等待 `STOP_TIMEOUT`，仅对 PID 和 `/proc` start time 都匹配的
进程发送 KILL。attempt 模式保留 `pids.txt`，检查 PID 和端口后写入 `cleanup.json`。

进程退出和端口释放不能证明 NPU context/HBM 已清理。cleanup 只在 snapshot 采集无
错误、设备列表非空且所有目标卡 process 列表为空时写 `npu_quiescence: PASS`。
缺少 snapshot 或由调用方直接声明 PASS 都不能通过正式 Run Evidence。

## 宿主机调度容器模式

如果当前 agent 在宿主机执行，并需要进入容器操作：

1. 在宿主机创建统一 `RUN_ROOT`，并确保容器挂载该目录。
2. 使用 `docker exec <container> ...` 启动/停止服务。
3. 正式 run 不默认使用 `docker run --rm`。
4. 操作前后保存 `npu-smi info`、`pgrep`、`free -h` 和 `uptime`。

远程 SSH 调度时，遵守
[`ssh-remote-exec`](../ssh-remote-exec/SKILL.md) skill
中的连接方式和引号规范。

## 脚本

- **启动**：`scripts/run.sh` — 启动服务并写入不可覆盖的 attempt artifacts
- **门禁**：`scripts/service_lifecycle.py` — 执行 ready、smoke、cleanup 证据检查
- **停止**：`scripts/stop.sh` — 只停止 PID manifest 中属于本次 run 的进程

## 故障处理

- **服务无法启动**：检查 `log/node_*.log`。常见原因包括端口冲突、NPU 显存不足、模型路径错误。
- **健康检查超时**：确认 NPU 设备可用（`npu-smi info`），检查端口是否被占用。
