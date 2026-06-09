---
name: xllm-npu-eval-runner
description: xLLM NPU 评测执行器。用于启动或复用 xLLM 服务、执行 evalscope 性能评测、精度评测和 artifact 收集。本 skill 只产出原始 perf/accuracy artifacts；公平性和基线对比交给 xllm-npu-benchmark，精度根因分析交给 xllm-npu-accuracy-debug，msprof 分析交给 xllm-npu-profiler。
---

# xLLM NPU 评测执行器

本 skill 是 xLLM NPU 评测的执行层：启动或复用 xLLM 服务，运行 evalscope
性能和精度 workload，并写出可复现 artifacts。

当评测涉及多个 serving 框架且依赖环境不同，例如 xLLM 与 vLLM-Ascend
分别在不同容器中运行时，本 skill 作为执行器配合 `xllm-npu-benchmark`：
宿主机负责调度，容器只负责各自框架的服务启动和命令执行。

它不负责最终性能公平性结论、精度根因分析或 profiling 解读：

| 需求 | 使用 |
|---|---|
| 启动服务并运行 evalscope | 本 skill |
| 对比 baseline/current 或框架 A/B | `xllm-npu-benchmark` |
| 定位坏答案、CEval 掉分、乱码 | `xllm-npu-accuracy-debug` |
| 采集和分析 msprof trace | `xllm-npu-profiler` |
| 驱动端到端优化循环 | `xllm-npu-sota-loop` |

## 工作流概览

```
1. 参数对齐（必要时询问用户）
       |
2. 更新 3 个脚本（run.sh, eval_perf.sh, eval_acc.sh）
       |
3. 检查依赖（evalscope, evalscope[perf]）
       |
4. 创建 Run Root 和 Manifest
       |
5. 启动 xLLM 服务（已运行则跳过）
       |
6. 等待服务 ready
       |
7. 运行性能测试（eval_perf.sh）
       |
8. 运行精度测试（eval_acc.sh）
       |
9. 写入 Metrics 和 Report
```

正式结论必须在本 runner 完成后，将 artifacts 交给 `xllm-npu-benchmark`
或 `xllm-npu-accuracy-debug` 继续分析。

## Step 1: 参数对齐

如果当前脚本、run manifest 或服务 endpoint 里没有以下参数，先与用户确认：

| 参数 | 说明 | 影响 |
|---|---|---|
| **API URL** | 服务 endpoint，例如 `http://localhost:18050/v1` | 3 个脚本 |
| **Model Name** | 模型标识，例如 `Qwen35-27B` | 3 个脚本 |
| **Model Path** | 主模型权重路径 | `run.sh` 的 `--model`，`eval_perf.sh` 的 `--tokenizer-path` |
| **Draft Model Path** | 投机解码 draft model 路径 | `run.sh` 的 `--draft_model` |
| **xLLM Binary Path** | xllm server binary 路径 | `run.sh` 的 `XLLM_BIN` 变量 |
| **TP (NNODES)** | Tensor parallelism degree | `run.sh` 的 `NNODES` 变量 |
| **NPU Devices** | 使用的 NPU 设备 ID，例如 `0,1,2,3` | `run.sh` 的 `ASCEND_RT_VISIBLE_DEVICES` 变量 |
| **Test Mode** | Smoke test 快速验证或 Full test 完整评测 | `eval_perf.sh` 是否跳过 parallel=5，`eval_acc.sh` 的 subset datasets |

缺失参数一次性询问。可以基于当前脚本值提供默认建议：
- API URL: `http://localhost:18050/v1`
- Model Name: `Qwen35-27B`
- Model Path: `<model-root>/Qwen35-27B`
- Draft Model Path: `<model-root>/Qwen35-27B-mtp`
- xLLM Binary Path: `<project_root>/xllm/build/xllm/core/server/xllm`
- TP: `4`
- NPU Devices: `0,1,2,3`
- Test Mode: `smoke`（推荐用于快速验证）

## Step 2: 更新脚本

参数收集完后，**原子化**更新 3 个脚本（一次性改完）。

### 脚本位置

无论 skill 是安装给 Codex、Claude Code、opencode，还是直接从仓库 checkout
加载，脚本路径都要按当前 skill 目录解析。

- **启动**：`scripts/run.sh`
- **性能**：`scripts/eval_perf.sh`
- **精度**：`scripts/eval_acc.sh`

### run.sh 更新点

使用当前 agent 的正常文件编辑方式更新 `scripts/run.sh` 中这些字段：

1. `MODEL_PATH="<model_path>"`
2. `DRAFT_MODEL_PATH="<draft_model_path>"`
3. `XLLM_BIN="<xllm_binary_path>"`
4. `NNODES=<tp>`
5. `ASCEND_RT_VISIBLE_DEVICES=<npu_devices>`
6. `START_PORT` 应与 API URL 里的端口一致

### eval_perf.sh 更新点

更新 `scripts/eval_perf.sh` 里 **两个** `evalscope perf` 命令块
（parallel=1 和 parallel=5）：

1. `--model <model_name>`
2. `--url <api_url>/chat/completions`，注意在 base URL 后追加 `/chat/completions`
3. `--tokenizer-path <model_path>`
4. 脚本顶部的 `SMOKE_MODE` 变量：
   - **Smoke test**：设置 `SMOKE_MODE="true"`，跳过 parallel=5
   - **Full test**：设置 `SMOKE_MODE="false"`，运行 parallel=1 和 parallel=5

### eval_acc.sh 更新点

更新 `scripts/eval_acc.sh`：

1. `--model <model_name>`
2. `--api-url <api_url>`
3. `--datasets` 参数按 Test Mode 选择：
   - **Smoke test**：`--datasets ceval --dataset-args '{"ceval": {"subset_list": ["computer_network", "operating_system", "marxism"]}}'`
   - **Full test**：`--datasets ceval`

## Step 3: 检查依赖

启动服务前确认 `evalscope` 已安装：

```bash
pip show evalscope > /dev/null 2>&1 || pip install evalscope
python3 -c "import evalscope.perf" 2>/dev/null || pip install evalscope[perf]
```

如果检查失败，安装缺失 package。两项都确认可用后再进入 Step 4。

## Step 4: 创建 Run Root 和 Manifest

服务启动前创建 run root：

```bash
RUN_ROOT="${RUN_ROOT:-runs/eval/$(date +%Y%m%d_%H%M%S)_xllm_npu_eval}"
mkdir -p "$RUN_ROOT"/{env,service,perf,accuracy}
```

使用 [`references/run-manifest-template.md`](../../references/run-manifest-template.md)
写入 `manifest.md`。
至少记录：

- xLLM branch、commit 和 dirty diff 状态。
- Model path、可选 draft model path、tokenizer path。
- Device ids、CANN/driver/torch_npu 版本（可用时）。
- 服务启动命令和 API URL。
- Workload shape、sampling 参数、warmup count、parallel 和 number。
- 本次 run 是 `smoke`、`quick` 还是 `full`。
- 如果通过宿主机调度容器，记录 container name、image tag/digest、
  `docker inspect` 摘要、挂载目录和 NPU 设备映射。

保存运行前环境快照：

```bash
npu-smi info > "$RUN_ROOT/env/npu-smi.before.txt"
pgrep -af 'xllm|vllm|sglang|python|evalscope|msprof' > "$RUN_ROOT/env/process.before.txt" || true
free -h > "$RUN_ROOT/env/mem.before.txt"
uptime > "$RUN_ROOT/env/load.before.txt"
```

## 宿主机调度容器模式

如果当前 agent 在宿主机执行，并需要分别进入 xLLM 容器和 vLLM-Ascend 容器：

1. 在宿主机创建统一 `RUN_ROOT`，并确保两个容器都挂载该目录。
2. 使用 `docker exec <container> ...` 启动/停止服务、查询框架版本和复制日志。
3. evalscope 优先在宿主机或统一 client 容器运行；如果必须在服务容器内运行，
   两边 evalscope 版本必须记录并尽量保持一致。
4. 正式性能 run 不默认使用 `docker run --rm`。若使用 `--rm` 做 smoke，
   必须把 logs、metrics、evalscope outputs 和 manifest 挂载到宿主机。
5. 每个框架测试前后都从宿主机保存 `npu-smi info`、`pgrep`、`free -h` 和
   `uptime`，用于环境门禁。

示例命令骨架：

```bash
# 宿主机执行；容器名和路径来自用户环境，不在 skill 中写死。
docker exec <xllm_container> bash <start_xllm_script>
curl -sS http://127.0.0.1:<xllm_port>/v1/models
evalscope perf --url http://127.0.0.1:<xllm_port>/v1/chat/completions ...
docker exec <xllm_container> bash <stop_xllm_script>

docker exec <vllm_container> bash <start_vllm_script>
curl -sS http://127.0.0.1:<vllm_port>/v1/models
evalscope perf --url http://127.0.0.1:<vllm_port>/v1/chat/completions ...
docker exec <vllm_container> bash <stop_vllm_script>
```

## Step 5: 启动 xLLM 服务

启动前先检查服务是否已经运行：

```bash
if curl -s <api_url>/models > /dev/null 2>&1; then
  echo "xLLM service already running, skipping startup."
else
  echo "Starting xLLM service..."
  bash <skill_dir>/scripts/run.sh
fi
```

如果服务已可用，跳到 Step 7（运行性能测试）。

**重要**：服务在后台启动。启动后必须等待服务 ready。

## Step 6: 等待服务 Ready

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

## Step 7: 运行性能测试

```bash
bash <skill_dir>/scripts/eval_perf.sh
```

性能测试行为取决于 Test Mode：
- **Smoke mode**（`SMOKE_MODE="true"`）：只运行 parallel=1、number=4，作为单请求延迟 baseline。
- **Full mode**（`SMOKE_MODE="false"`）：运行两轮：
  1. **Parallel=1, Number=4**：单请求延迟 baseline。
  2. **Parallel=5, Number=20**：并发吞吐测试。

结果默认输出到 `outputs/`。正式 run 应复制或配置输出到 `$RUN_ROOT/perf/`，
并保留完整原始 evalscope 目录。查找 `benchmark_summary.json`，把关键字段同步到
`$RUN_ROOT/perf/metrics.json`。

正式性能 run 必须使用请求级 warmup。evalscope 里设置 `--warmup-num 1`
或更高，除非用户明确要测 cold-start latency。warmup 值必须记录到
`manifest.md` 和 `metrics.json`。

## Step 8: 运行精度测试

```bash
bash <skill_dir>/scripts/eval_acc.sh
```

**重要**：精度评测要设置较长 timeout，例如 1 小时。精度评测通常明显慢于性能测试。

精度结果会打印到 stdout。正式 run 要在 `$RUN_ROOT/accuracy/` 下保存原始预测、
失败样本、score 文件和简短 `report.md`。artifact 结构遵循
[`references/accuracy-artifact-schema.md`](../../references/accuracy-artifact-schema.md)。

## Step 9: 写入 Metrics 和 Report

本 runner 应写出简洁执行报告：

```text
$RUN_ROOT/
  manifest.md
  env/
  service/
  perf/
  accuracy/
  report.md
```

报告需要说明执行了什么、原始 artifacts 存在哪里，以及本次 run 是否足够支撑正式结论。
如果只是 smoke run，必须明确说明。

## 可选：从 GitHub 获取 Baseline

从 GitHub 仓库获取 benchmark baseline 数据：

```
BENCHMARK_URL=https://raw.githubusercontent.com/jd-opensource/xllm/main/docs/benchmark/baseline.md
```

使用当前 agent 可用的 web 或 shell 网络工具获取该 URL。如果返回 404，告诉用户
baseline 文件尚未上传，并跳过比较步骤。

解析 markdown 表格，提取匹配模型和配置的 baseline 值。

这里的 baseline comparison 只是便利检查。正式 benchmark comparison 属于
`xllm-npu-benchmark`，由它验证公平性、环境门禁、warmup 和可比启动参数。

## 可选：快速对比表

构建对比表并展示给用户：

### 性能对比模板

```
| Metric | Current | Baseline | Delta | Status |
|---|---|---|---|---|
| Output Throughput (tok/s) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
| TTFT (ms) | XXXX | XXXX | -X.X% | PASS/FAIL |
| TPOT (ms) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
| ITL (ms) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
```

### 精度对比模板

```
| Dataset | Current | Baseline | Delta | Status |
|---|---|---|---|---|
| ceval (overall) | XX.X% | XX.X% | +X.X% | PASS/FAIL |
```

### 状态规则

- **Performance metrics**（throughput, tok/s）：current >= baseline * 0.95 判定 PASS，容忍 5%。
- **Latency metrics**（TTFT, TPOT, ITL, ms）：current <= baseline * 1.05 判定 PASS，容忍 5%。
- **Accuracy metrics**：current >= baseline - 0.02 判定 PASS，容忍 2 个百分点。

### 报告总结

表格之后给一句总结：
- 全部 PASS：`All metrics within acceptable range of baseline.`
- 任一 FAIL：`WARNING: X metrics below baseline. Check [specific metrics] for details.`

## 故障处理

- **服务无法启动**：检查 `log/node_*.log`。常见原因包括端口冲突、NPU 显存不足、模型路径错误。
- **性能测试失败**：确认服务完全 ready 后再运行，并检查 URL 是否正确。
- **精度测试失败**：确认 evalscope 已安装（`pip show evalscope`），并检查 API 连通性。
- **找不到 Baseline**：GitHub baseline 文件可能还不存在，提示用户上传 `benchmark_baseline.md`。
