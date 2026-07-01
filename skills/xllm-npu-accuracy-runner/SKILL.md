---
name: xllm-npu-accuracy-runner
description: xLLM NPU 精度测试执行器。用于执行 evalscope 精度评测（CEval 等数据集），输出分数和预测结果。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 精度测试执行器

负责执行 evalscope 精度评测并收集原始 artifacts。

## 职责边界

- 本 skill：执行 evalscope accuracy、解析分数、输出预测结果。
- `xllm-npu-server-manager`：启动/停止服务。
- `xllm-npu-perf-runner`：执行性能测试。
- `xllm-npu-report-writer`：汇总报告。
- `xllm-npu-accuracy-debug`：精度异常根因分析。

## 前提条件

- xLLM 服务已启动且健康检查通过（使用 `xllm-npu-server-manager`）。
- `evalscope` 已安装：

```bash
pip show evalscope > /dev/null 2>&1 || pip install evalscope
```

## 参数

| 参数 | 说明 | 示例 |
|---|---|---|
| API URL | 服务 endpoint | `http://localhost:18050/v1` |
| Model Name | 模型标识 | `Qwen35-27B` |
| Test Mode | smoke 或 full | `smoke` |
| Run Root | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |

## 工作流

### Step 1: 更新脚本

更新 `scripts/eval_acc.sh`：

1. `--model <model_name>`
2. `--api-url <api_url>`
3. `--datasets` 参数按 Test Mode 选择：
   - **Smoke test**：`--datasets ceval --dataset-args '{"ceval": {"subset_list": ["computer_network", "operating_system", "marxism"]}}'`
   - **Full test**：`--datasets ceval`

### Step 2: 执行精度测试

```bash
bash <skill_dir>/scripts/eval_acc.sh
```

**重要**：精度评测要设置较长 timeout，例如 1 小时。精度评测通常明显慢于性能测试。

### Step 3: 收集结果

精度结果会打印到 stdout。正式 run 要在 `$RUN_ROOT/accuracy/` 下保存原始预测、
失败样本、score 文件和简短 `report.md`。artifact 结构遵循
[`../../reference/io_specs/accuracy-artifact-schema.md`](../../reference/io_specs/accuracy-artifact-schema.md)。

## 脚本

- **精度测试**：`scripts/eval_acc.sh`

## 故障处理

- **精度测试失败**：确认 evalscope 已安装（`pip show evalscope`），并检查 API 连通性。
- **乱码或异常答案**：抽取 failed_cases.jsonl，交由 `xllm-npu-accuracy-debug` 分析。
