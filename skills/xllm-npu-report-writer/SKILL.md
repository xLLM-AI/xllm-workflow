---
name: xllm-npu-report-writer
description: xLLM NPU 评测报告生成器。汇总 run root 下的性能、精度、环境 artifacts，生成结构化 report.md。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 评测报告生成器

汇总 run root 下的所有 artifacts，生成结构化执行报告。

## 职责边界

- 本 skill：读取 artifacts、汇总指标、生成 report.md。
- `xllm-npu-server-manager`：启动/停止服务。
- `xllm-npu-perf-runner`：执行性能测试。
- `xllm-npu-accuracy-runner`：执行精度测试。
- `xllm-npu-benchmark`：公平性审查和框架对比结论。

## 输入

| 参数 | 说明 | 示例 |
|---|---|---|
| Run Root | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |

## 工作流

### Step 1: 读取 artifacts

从 `$RUN_ROOT` 读取：

- `manifest.md` — run 元信息
- `env/` — 环境快照（npu-smi、进程表、内存、负载）
- `perf/metrics.json` — 性能指标
- `perf/` — evalscope 原始输出
- `accuracy/` — 精度评测结果

### Step 2: 生成报告

写出 `$RUN_ROOT/report.md`，包含：

1. **执行摘要**：运行了什么、什么配置、什么结论等级。
2. **性能指标表**：TTFT、TPOT、TPS、Output throughput 的 avg/P50/P90/P99。
3. **精度分数表**：各数据集分数。
4. **环境信息**：NPU 型号、CANN 版本、框架 commit。
5. **Artifact 路径**：原始数据存放位置。
6. **结论等级**：本次 run 是否足够支撑正式结论（smoke / quick / full）。

### Step 3: 可选 Baseline 对比

从 GitHub 获取 baseline 数据（如有）：

```
BENCHMARK_URL=https://raw.githubusercontent.com/jd-opensource/xllm/main/docs/benchmark/baseline.md
```

构建对比表：

```
| Metric | Current | Baseline | Delta | Status |
|---|---|---|---|---|
| Output Throughput (tok/s) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
| TTFT (ms) | XXXX | XXXX | -X.X% | PASS/FAIL |
| TPOT (ms) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
```

状态规则：
- **Performance metrics**：current >= baseline * 0.95 判定 PASS，容忍 5%。
- **Latency metrics**：current <= baseline * 1.05 判定 PASS，容忍 5%。
- **Accuracy metrics**：current >= baseline - 0.02 判定 PASS，容忍 2 个百分点。

## 输出

```
$RUN_ROOT/report.md
```

报告需要说明执行了什么、原始 artifacts 存在哪里，以及本次 run 是否足够支撑正式结论。
如果只是 smoke run，必须明确说明。
