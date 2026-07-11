---
name: xllm-npu-perf-runner
description: xLLM NPU 性能测试执行器。用于执行 evalscope 性能评测，输出 TTFT/TPOT/TPS/吞吐等指标。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 性能测试执行器

负责执行 evalscope 性能评测并收集原始 artifacts。

## 职责边界

- 本 skill：执行 evalscope perf、解析 benchmark_summary、输出 metrics。
- 依赖：`xllm-npu-server-manager`（启动/停止服务）。
- 公平性审查和框架对比结论：交由 `xllm-npu-benchmark`。

## 前提条件

- xLLM 服务已启动且健康检查通过（使用 `xllm-npu-server-manager`）。
- `evalscope` 已安装：

```bash
pip show evalscope > /dev/null 2>&1 || pip install evalscope
python3 -c "import evalscope.perf" 2>/dev/null || pip install evalscope[perf]
```

## 参数

| 参数 | 环境变量 | 说明 | 默认值 |
|---|---|---|---|
| API URL | `API_URL` | 服务 endpoint | `http://127.0.0.1:17112/v1` |
| Model Name | `MODEL` | 模型标识 | `Qwen35-27B` |
| Tokenizer Path | `TOKENIZER_PATH` | tokenizer 路径 | `/models/Qwen35-27B` |
| Parallel List | `PARALLEL_LIST` | 并发数列表（逗号分隔） | `1` |
| Number | `NUMBER` | 每个并发级别的请求数基数 | `4` |
| Warmup Num | `WARMUP_NUM` | warmup 请求数 | `2` |
| Input Tokens | `INPUT_TOKENS` | 输入 token 长度 | `20000` |
| Output Tokens | `OUTPUT_TOKENS` | 输出 token 长度 | `1024` |
| Output Dir | `OUTPUT_DIR` | 结果输出目录 | `outputs` |
| Run Root | `RUN_ROOT` | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |

## 工作流

### Step 1: 设置环境变量

通过环境变量配置 `scripts/eval_perf.sh`，无需手动编辑脚本：

```bash
export MODEL="Qwen35-27B"
export API_URL="http://127.0.0.1:17112/v1"
export TOKENIZER_PATH="/models/Qwen35-27B"
export PARALLEL_LIST="1,2,4"
export NUMBER=4
export WARMUP_NUM=2
export INPUT_TOKENS=20000
export OUTPUT_TOKENS=1024
export OUTPUT_DIR="$RUN_ROOT/perf"
```

- `PARALLEL_LIST` 控制测试哪些并发级别，用逗号分隔。
- `NUMBER` 是每个并发级别的请求数基数，实际请求数 = `NUMBER * PARALLEL`。
- `WARMUP_NUM` 必须大于 0，除非明确测试冷启动。

### Step 2: 执行性能测试

```bash
bash <skill_dir>/scripts/eval_perf.sh
```

脚本会遍历 `PARALLEL_LIST` 中的每个并发值，依次执行 evalscope perf。

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
