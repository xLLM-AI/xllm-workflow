---
name: xllm-npu-pipeline-analysis
description: xLLM、vLLM-Ascend、SGLang 的 NPU serving pipeline 和 layer-level 分析。用于分析 prefill/decode 边界、layer timing、rank skew、graph replay gaps、decode step 间 host bubbles，或把 profiling timeline 事件映射回框架 pipeline 阶段。
---

# xLLM NPU Pipeline 分析

当五表 profiling 报告不足以解释问题，并且需要按 stage、layer、rank 或 decode-step
边界推理时使用本 skill。

## 输入

- 遵循
  [`../../references/profiling-artifact-schema.md`](../../references/profiling-artifact-schema.md).
  的 profiling artifact。
- Workload shape：input tokens、output tokens、parallel、warmup。
- 框架启动命令和 commit。
- 可选：来自 `xllm-npu-profiler` 的 source-map notes。

## Artifact 契约

正式使用本 skill 分析 decode gap、graph replay gap、host bubble 或跨框架
pipeline 差异时，必须在对应 profiling run 目录生成 pipeline artifact。不能只在
聊天或最终总报告中给出口头结论。

最低必需文件：

```text
profiling/<run_id>/
  manifest.md
  timeline_notes.md
  pipeline-analysis.md
  bubble-table.csv
  stage-table.csv
  rank-skew-table.csv
  analysis.json
```

推荐用脚本生成骨架和 decode bubble 统计：

```bash
python skills/xllm-npu-pipeline-analysis/scripts/create_pipeline_artifacts.py \
  --run-dir /path/to/profiling/<run_id> \
  --workload "input=5000 output=50 parallel=1 warmup=5" \
  --framework xllm \
  --boundary "ArgMaxV2AiCore->MODEL_EXECUTE"
```

如果由于 trace 缺失、workload 失败、warmup 混入正式采集、或边界事件无法稳定配对
而不能生成完整表格，必须仍然生成上述文件，并在 `manifest.md` 与
`analysis.json` 中标记 `INCONCLUSIVE`。如果本轮只做临时口头分析，必须在最终回答
中明确标记 `SCHEMA_INCOMPLETE` 和缺失文件。

## 工作流

1. 先为 profiling run 创建或更新上面的 pipeline artifact；decode bubble 分析优先
   用 `create_pipeline_artifacts.py` 自动生成 `bubble-table.csv` 和 `analysis.json`。
2. 将 trace 拆成 prefill、decode、graph replay、communication 和 postprocess 区间。
3. 识别重复的 decode-step 边界。对 xLLM decode，重点关注
   `replaceToken` 结束到下一轮 `GatherV2` 开始这类间隔。
4. 构建表格：

   | 表 | 目的 |
   |---|---|
   | Stage table | 按 step 统计 prefill/decode/postprocess latency |
   | Layer table | 代表性 layer latency 和 top kernels |
   | Rank skew table | 慢 rank、快 rank 与 HCCL wait |
   | Bubble table | Host gap、copy、setup、synchronization、graph replay |

5. 将 top timeline events 映射回可能的源码区域。
6. 只提出可验证的优化：必须能通过 before/after 无 profiling 性能跑分和后续 trace 复核。

## 输出

```text
profiling/<run_id>/
  manifest.md
  timeline_notes.md
  pipeline-analysis.md
  stage-table.csv
  rank-skew-table.csv
  bubble-table.csv
  analysis.json
```

报告必须清楚区分：

- Device compute 瓶颈。
- Communication/rank skew 瓶颈。
- Hostbound dispatch bubbles。
- Postprocess 或 sampling overhead。

## 参考资料

- [`references/pipeline-boundaries.md`](references/pipeline-boundaries.md)
- [`../xllm-npu-profiler/references/source-map.md`](../xllm-npu-profiler/references/source-map.md)
- [`../../references/profiling-artifact-schema.md`](../../references/profiling-artifact-schema.md)
