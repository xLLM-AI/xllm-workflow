---
name: xllm-npu-server-manager
description: xLLM NPU 服务管理器。用于启动、停止、复用 xLLM 服务，执行健康检查，保存环境快照。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 服务管理器

负责 xLLM 服务的生命周期管理：启动、停止、健康检查和环境快照。

## 职责边界

- 本 skill：启动/停止服务、健康检查、环境快照、进程管理。
- `xllm-npu-perf-runner`：执行 evalscope 性能测试。
- `xllm-npu-accuracy-runner`：执行 evalscope 精度测试。
- `xllm-npu-report-writer`：汇总 artifacts 生成报告。

## 工作流

### Step 1: 参数对齐

如果以下参数未提供，先与用户确认：

| 参数 | 环境变量 | 说明 | 示例 |
|---|---|---|---|
| API URL | `API_URL` | 服务 endpoint | `http://localhost:18050/v1` |
| Model Path | `MODEL_PATH` | 主模型权重路径 | `/models/Qwen35-27B` |
| Draft Model Path | `DRAFT_MODEL_PATH` | 投机解码 draft model 路径（留空则禁用 MTP） | `/models/Qwen35-27B-mtp` |
| xLLM Binary Path | `XLLM_BIN` | xllm server binary 路径 | `<project_root>/xllm/build/xllm/core/server/xllm` |
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
export MODEL_PATH="/models/Qwen35-27B"
export NNODES=4
export ASCEND_RT_VISIBLE_DEVICES="0,1,2,3"
export START_PORT=17112
# ... 其他可选参数
bash <skill_dir>/scripts/run.sh
```

启动前先检查服务是否已经运行：

```bash
if curl -s <api_url>/models > /dev/null 2>&1; then
  echo "xLLM service already running, skipping startup."
else
  echo "Starting xLLM service..."
  bash <skill_dir>/scripts/run.sh
fi
```

### Step 4: 等待服务 Ready

轮询服务 health endpoint，直到有响应：

```bash
for i in $(seq 1 60); do
  if curl -s <api_url>/models > /dev/null 2>&1; then
    echo "Service is ready!"
    break
  fi
  echo "Waiting for service... ($i/60)"
  sleep 10
done
```

如果 10 分钟内没有启动成功，检查 `log/node_0.log` 并向用户报告错误。

### Step 5: 停止服务（按需）

```bash
pkill -9 xllm || true
sleep 2
pgrep -af xllm > "$RUN_ROOT/env/process.after_stop.txt" || true
```

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

- **启动**：`scripts/run.sh` — 启动 xLLM 服务进程

## 故障处理

- **服务无法启动**：检查 `log/node_*.log`。常见原因包括端口冲突、NPU 显存不足、模型路径错误。
- **健康检查超时**：确认 NPU 设备可用（`npu-smi info`），检查端口是否被占用。
