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

| 参数 | 说明 | 示例 |
|---|---|---|
| API URL | 服务 endpoint | `http://localhost:18050/v1` |
| Model Path | 主模型权重路径 | `/models/Qwen35-27B` |
| Draft Model Path | 投机解码 draft model 路径 | `/models/Qwen35-27B-mtp` |
| xLLM Binary Path | xllm server binary 路径 | `<project_root>/xllm/build/xllm/core/server/xllm` |
| TP (NNODES) | Tensor parallelism degree | `4` |
| NPU Devices | 使用的 NPU 设备 ID | `0,1,2,3` |
| Run Root | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |

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
[`references/ssh-exec-constraints.md`](references/ssh-exec-constraints.md)
中的引号规范。

## 脚本

- **启动**：`scripts/run.sh` — 启动 xLLM 服务进程

## 故障处理

- **服务无法启动**：检查 `log/node_*.log`。常见原因包括端口冲突、NPU 显存不足、模型路径错误。
- **健康检查超时**：确认 NPU 设备可用（`npu-smi info`），检查端口是否被占用。
