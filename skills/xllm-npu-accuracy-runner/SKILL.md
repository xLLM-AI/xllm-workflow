---
name: xllm-npu-accuracy-runner
description: xLLM NPU 精度测试执行器。用于执行 evalscope 精度评测（CEval 等数据集），输出分数和预测结果。可独立使用，也可作为 xllm-npu-eval-runner 编排流程的一部分。
---

# xLLM NPU 精度测试执行器

负责执行 evalscope 精度评测并收集原始 artifacts。

## 职责边界

- 本 skill：执行 evalscope accuracy、解析分数、输出预测结果。
- 依赖：`xllm-npu-server-manager`（启动/停止服务）。
- 精度异常根因分析：交由 `xllm-npu-accuracy-debug`。

## 前提条件

- xLLM 服务已启动且健康检查通过（使用 `xllm-npu-server-manager`）。
- `evalscope` 已安装：

```bash
pip show evalscope > /dev/null 2>&1 || pip install evalscope
```

## 参数

| 参数 | 环境变量 | 说明 | 示例 |
|---|---|---|---|
| API URL | `API_URL` | 服务 endpoint | `http://localhost:18050/v1` |
| Model Name | `MODEL_NAME` | 模型标识 | `Qwen35-27B` |
| Test Mode | `TEST_MODE` | `smoke` 或 `full` | `smoke` |
| Run Root | `RUN_ROOT` | 产物根目录 | `runs/eval/20260622_xllm_npu_eval` |
| Work Dir | `WORK_DIR` | EvalScope 原始产物目录 | `$RUN_ROOT/accuracy` |
| API Key | `OPENAI_API_KEY` | OpenAI-compatible API key | `EMPTY` |

## 工作流

### Step 1: 配置环境变量

无需修改脚本。设置本次 run 的参数：

```bash
export MODEL_NAME="Qwen35-27B"
export API_URL="http://127.0.0.1:17112/v1"
export TEST_MODE="smoke"
export RUN_ROOT="runs/eval/<run_id>"
export WORK_DIR="$RUN_ROOT/accuracy"
```

- `smoke` 只跑固定的 CEval 子集；`full` 跑完整 CEval。
- `WORK_DIR` 未设置时默认为 `${RUN_ROOT:-outputs}/accuracy`。

### Step 2: 执行精度测试

```bash
bash <skill_dir>/scripts/eval_acc.sh
```

**重要**：精度评测要设置较长 timeout，例如 1 小时。精度评测通常明显慢于性能测试。

### Step 3: 收集结果

精度结果会打印到 stdout，并通过 `--work-dir` 写入 `$WORK_DIR`。正式 run 要在
`$RUN_ROOT/accuracy/` 下保存原始预测、
失败样本、score 文件和简短 `report.md`。artifact 结构遵循
[`../../reference/io_specs/accuracy-artifact-schema.md`](../../reference/io_specs/accuracy-artifact-schema.md)。

正式精度 run 必须把 prompt template、dataset/request order、answer extractor、binary
和 service attempt 写入 `run-evidence.json`，并通过
[`../../scripts/validate_run_evidence.py`](../../scripts/validate_run_evidence.py)。
缺少任一 fingerprint 时只能作为 smoke/debug，不能复用为后续 binary/config 的精度 PASS。

## 脚本

- **精度测试**：`scripts/eval_acc.sh`

## 故障处理

- **精度测试失败**：确认 evalscope 已安装（`pip show evalscope`），并检查 API 连通性。
- **乱码或异常答案**：抽取 failed_cases.jsonl，交由 `xllm-npu-accuracy-debug` 分析。
