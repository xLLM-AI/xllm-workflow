---
name: xllm-npu-eval-runner
description: xLLM NPU EvalScope 测评执行器。用于对已确定的 OpenAI-compatible 服务运行 evalscope 性能测评、精度测评并收集原始 artifacts。本 skill 不负责启动脚本开发、构建验证或服务事故诊断；构建门禁交给 xllm-npu-build-gate，公平性和基线对比交给 xllm-npu-benchmark，精度根因分析交给 xllm-npu-accuracy-debug，msprof 分析交给 xllm-npu-profiler，编译失败诊断交给 xllm-npu-incident-triage。
---

# xLLM NPU EvalScope 测评执行器

本 skill 是 xLLM NPU EvalScope 测评的执行层：围绕已确定的 API URL、模型名
和 tokenizer/model path，运行 evalscope 性能和精度 workload，并写出可复现
artifacts。服务启动只作为测评前置条件检查；启动脚本开发、服务拉起体验优化或
启动故障诊断不属于本 skill 的主要职责。

当评测涉及多个 serving 框架且依赖环境不同，例如 xLLM 与 vLLM-Ascend
分别在不同容器中运行时，本 skill 作为执行器配合 `xllm-npu-benchmark`：
宿主机负责调度，容器只负责各自框架的服务启动和命令执行。

它不负责最终性能公平性结论、精度根因分析或 profiling 解读：

| 需求 | 使用 |
|---|---|
| 使用 evalscope 测评并收集 artifacts | 本 skill |
| 编译、构建、build gate、NPU 门禁 | `xllm-npu-build-gate` |
| 只启动/停止服务 | `xllm-npu-server-manager` |
| 只跑性能测试 | `xllm-npu-perf-runner` |
| 只跑精度测试 | `xllm-npu-accuracy-runner` |
| 只生成报告 | `xllm-npu-report-writer` |

## 工作流概览

```
1. 参数对齐（必要时询问用户）
       |
2. 配置并委托 3 个子 skill（server-manager、perf-runner、accuracy-runner）
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

## 远程执行约束

通过 SSH 远程调度容器时，必须遵守
[`ssh-remote-exec`](../ssh-remote-exec/SKILL.md) skill
中的连接方式、引号规范和密码认证方式，避免命令解析错误导致误判。

## Step 1: 参数对齐

如果当前脚本、run manifest 或服务 endpoint 里没有以下参数，先与用户确认：

| 参数 | 说明 | 影响 |
|---|---|---|
| **API URL** | 服务 endpoint，例如 `http://localhost:18050/v1` | perf/accuracy runner |
| **Model Name** | 模型标识，例如 `Qwen35-27B` | perf/accuracy runner |
| **Model Path** | 主模型权重路径 | server-manager 的 `MODEL_PATH`、perf-runner 的 `TOKENIZER_PATH` |
| **Draft Model Path** | 投机解码 draft model 路径 | server-manager 的 `DRAFT_MODEL_PATH` |
| **xLLM Binary Path** | xllm server binary 路径 | server-manager 的 `XLLM_BIN` |
| **TP (NNODES)** | Tensor parallelism degree | server-manager 的 `NNODES` |
| **NPU Devices** | 使用的 NPU 设备 ID，例如 `0,1,2,3` | server-manager 的 `ASCEND_RT_VISIBLE_DEVICES` |
| **Test Mode** | Smoke test 快速验证或 Full test 完整评测 | perf workload 与 accuracy-runner 的 `TEST_MODE` |

缺失参数一次性询问。可以基于当前脚本值提供默认建议：
- API URL: `http://localhost:18050/v1`
- Model Name: `Qwen35-27B`
- Model Path: `<model-root>/Qwen35-27B`
- Draft Model Path: `<model-root>/Qwen35-27B-mtp`
- xLLM Binary Path: `<project_root>/code/xllm/build/xllm/core/server/xllm`
- TP: `4`
- NPU Devices: `0,1,2,3`
- Test Mode: `smoke`（推荐用于快速验证）

## Step 2: 配置子 skill

本 skill 是编排层，不复制或修改 runner 脚本。参数收集完后，通过环境变量依次委托：

1. `xllm-npu-server-manager`：`MODEL_PATH`、`DRAFT_MODEL_PATH`、`XLLM_BIN`、
   `NNODES`、`ASCEND_RT_VISIBLE_DEVICES`、`START_PORT`、`RUN_ROOT`。
2. `xllm-npu-perf-runner`：`MODEL`、`API_URL`、`TOKENIZER_PATH`、
   `PARALLEL_LIST`、`NUMBER`、`WARMUP_NUM`、`OUTPUT_DIR=$RUN_ROOT/perf`。
3. `xllm-npu-accuracy-runner`：`MODEL_NAME`、`API_URL`、`TEST_MODE`、
   `RUN_ROOT`、`WORK_DIR=$RUN_ROOT/accuracy`。

所有实际值必须写入 manifest；同一次 run 不得通过手改共享脚本保存配置。

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

使用 [`reference/io_specs/run-manifest-template.md`](../../reference/io_specs/run-manifest-template.md)
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

### 构建前置验证

如果测评前需要编译验证（build gate、NPU 门禁、多候选构建复用），
参考 [`xllm-npu-build-gate`](../xllm-npu-build-gate/SKILL.md) skill。

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
  bash <xllm-npu-server-manager-skill-dir>/scripts/run.sh
fi
```

其中 server-manager 的环境变量按 Step 2 设置，不修改其共享脚本。

如果服务已可用，跳到 Step 7（运行性能测试）。

**重要**：服务在后台启动。启动后必须等待服务 ready。

## Step 6: 等待服务 Ready

轮询服务 health endpoint，直到有响应：

```bash
ready=false
for i in $(seq 1 60); do
  if curl -s <api_url>/models > /dev/null 2>&1; then
    echo "Service is ready!"
    ready=true
    break
  fi
  echo "Waiting for service... ($i/60)"
  sleep 10
done
[ "$ready" = true ] || {
  bash <xllm-npu-server-manager-skill-dir>/scripts/stop.sh
  exit 1
}
```

如果 10 分钟内没有启动成功，检查 `log/node_0.log` 并向用户报告错误。

## Step 7: 运行性能测试

```bash
export OUTPUT_DIR="$RUN_ROOT/perf"
bash <xllm-npu-perf-runner-skill-dir>/scripts/eval_perf.sh
```

性能 workload 由 `PARALLEL_LIST` 和 `NUMBER` 显式定义。例如 smoke 可使用
`PARALLEL_LIST=1 NUMBER=4`；full run 可使用 `PARALLEL_LIST=1,5 NUMBER=4`。
这两个实际值必须写入 manifest，runner 不通过隐藏开关改写 workload。

结果默认输出到 `outputs/`。正式 run 应复制或配置输出到 `$RUN_ROOT/perf/`，
并保留完整原始 evalscope 目录。查找 `benchmark_summary.json`，把关键字段同步到
`$RUN_ROOT/perf/metrics.json`。

正式性能 run 必须使用请求级 warmup。evalscope 里设置 `--warmup-num 1`
或更高，除非用户明确要测 cold-start latency。warmup 值必须记录到
`manifest.md` 和 `metrics.json`。

## Step 8: 运行精度测试

```bash
export WORK_DIR="$RUN_ROOT/accuracy"
bash <xllm-npu-accuracy-runner-skill-dir>/scripts/eval_acc.sh
```

**重要**：精度评测要设置较长 timeout，例如 1 小时。精度评测通常明显慢于性能测试。

精度结果会打印到 stdout。正式 run 要在 `$RUN_ROOT/accuracy/` 下保存原始预测、
失败样本、score 文件和简短 `report.md`。artifact 结构遵循
[`reference/io_specs/accuracy-artifact-schema.md`](../../reference/io_specs/accuracy-artifact-schema.md)。

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
