---
name: xllm-npu-perf-runner
description: xLLM NPU 性能测试执行器。用于执行 evalscope 性能评测，输出 TTFT/TPOT/TPS/吞吐等指标。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 性能测试执行器

负责执行 evalscope 性能评测并收集原始 artifacts。

## 职责边界

- 本 skill：执行 evalscope perf、解析 benchmark_summary、输出 metrics。
- `xllm-npu-server-manager`：启动/停止服务。
- `xllm-npu-accuracy-runner`：执行精度测试。
- `xllm-npu-report-writer`：汇总报告。
- `xllm-npu-benchmark`：公平性审查和框架对比结论。

## 前提条件

- xLLM 服务已启动且健康检查通过（使用 `xllm-npu-server-manager`）。
- `evalscope` 已安装：

```bash
pip show evalscope > /dev/null 2>&1 || pip install evalscope
python3 -c "import evalscope.perf" 2>/dev/null || pip install evalscope[perf]
```

## 参数

| 参数 | 说明 | 示例 |
|---|---|---|
| API URL | 服务 endpoint | `http://localhost:18050/v1` |
| Model Name | 模型标识 | `Qwen35-27B` |
| Tokenizer Path | tokenizer 路径 | `/models/Qwen35-27B` |
| Test Mode | smoke 或 full | `smoke` |
| Run Root | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |

## 工作流

### Step 1: 更新脚本

更新 `scripts/eval_perf.sh` 中 **两个** `evalscope perf` 命令块（parallel=1 和 parallel=5）：

1. `--model <model_name>`
2. `--url <api_url>/chat/completions`，注意在 base URL 后追加 `/chat/completions`
3. `--tokenizer-path <model_path>`
4. 脚本顶部的 `SMOKE_MODE` 变量：
   - **Smoke test**：设置 `SMOKE_MODE="true"`，跳过 parallel=5
   - **Full test**：设置 `SMOKE_MODE="false"`，运行 parallel=1 和 parallel=5

### Step 2: 执行性能测试

```bash
bash <skill_dir>/scripts/eval_perf.sh
```

性能测试行为取决于 Test Mode：
- **Smoke mode**（`SMOKE_MODE="true"`）：只运行 parallel=1、number=4，作为单请求延迟 baseline。
- **Full mode**（`SMOKE_MODE="false"`）：运行两轮：
  1. **Parallel=1, Number=4**：单请求延迟 baseline。
  2. **Parallel=5, Number=20**：并发吞吐测试。

### Step 3: 收集结果

结果默认输出到 `outputs/`。正式 run 应复制或配置输出到 `$RUN_ROOT/perf/`，
并保留完整原始 evalscope 目录。查找 `benchmark_summary.json`，把关键字段同步到
`$RUN_ROOT/perf/metrics.json`。

正式性能 run 必须使用请求级 warmup。evalscope 里设置 `--warmup-num 1`
或更高，除非用户明确要测 cold-start latency。warmup 值必须记录到
`manifest.md` 和 `metrics.json`。

## 脚本

- **性能测试**：`scripts/eval_perf.sh`

## 故障处理

- **性能测试失败**：确认服务完全 ready 后再运行，并检查 URL 是否正确。
- **evalscope 未安装**：运行 `pip install evalscope[perf]`。
