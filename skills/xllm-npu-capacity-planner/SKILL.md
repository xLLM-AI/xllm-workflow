---
name: xllm-npu-capacity-planner
description: xLLM / vLLM-Ascend / SGLang NPU serving 容量规划。用于分析 HBM 预算、KV cache 容量、max concurrency、block size、max model length、MTP/speculative 预留显存、OOM 风险，以及启动日志如何解释 Ascend NPU 的可承载请求容量。
---

# xLLM NPU 容量规划

用于判断某个 serving 配置是否有足够 NPU 显存承载目标 workload，并说明真正限制容量的参数。

## 输入

先收集：

- 模型名、dtype、hidden size、layers、attention heads、KV heads。
- 框架和 commit。
- NPU 型号、卡数、可见设备。
- 启动参数：TP/PP/EP、`block_size`、`max_model_len`、
  `max_memory_utilization`, `max_tokens_per_batch`, `max_seqs_per_batch`.
- MTP/speculative 参数：draft model path、`num_speculative_tokens`、日志中的
  linear/cache 预留字节数。
- 启动日志和 metrics 中关于 HBM、KV blocks、xTensor、block manager、
  reserved memory 或 OOM 的信息。

## 工作流

1. 使用
   [`../../reference/io_specs/run-manifest-template.md`](../../reference/io_specs/run-manifest-template.md).
   创建 run manifest。
2. 解析启动日志中的模型显存、可用 HBM、KV blocks、block size、
   reserved linear bytes 和分配失败信息。
3. 构建容量表：

   | 类别 | Bytes / Blocks | 来源 | 备注 |
   |---|---:|---|---|
   | 模型权重 | | startup log / estimate | per rank |
   | Runtime workspace | | startup log | ATB / graph / xTensor |
   | KV cache | | block manager | block 数和 token 容量 |
   | Spec/MTP reserve | | startup log | draft/verify 额外开销 |
   | Free margin | | npu-smi / log | 安全余量 |

4. 在目标 prompt/output/concurrency shape 下估算请求容量。
5. 归类瓶颈：HBM 硬 OOM、KV blocks、scheduler budget、
   speculative reserve、graph/workspace reserve 或碎片化。
6. 输出简短调参方案，包含安全参数变更和验证步骤。

## 输出

写入：

```text
runs/capacity/<run_id>/
  manifest.md
  startup-log-excerpt.txt
  capacity.json
  report.md
```

`report.md` must include:

- 容量结论：pass / risk / fail / inconclusive。
- 限制资源及证据。
- before/after 参数建议。
- 该结果是否足够支撑正式 benchmark。

## 参考资料

- [`references/capacity-log-patterns.md`](references/capacity-log-patterns.md)
- [`../../reference/io_specs/run-manifest-template.md`](../../reference/io_specs/run-manifest-template.md)
- [`../../reference/io_specs/perf-artifact-schema.md`](../../reference/io_specs/perf-artifact-schema.md)
