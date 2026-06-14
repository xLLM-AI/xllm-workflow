---
name: xllm-npu-sota-loop
description: 系统化推进 xLLM NPU 性能优化闭环，从目标定义、基线、profiling、实现、review、验证到最终沉淀。适用于需要持续提升 xLLM NPU 推理性能或建立可复用优化流程的任务。
---

# xLLM NPU SOTA 优化闭环

使用本 skill 处理端到端 xLLM NPU 优化任务。它的目标不是让 agent 直接写
patch，而是先建立公平基线、收集证据、选择一个可 review 的优化点、验证结果，
最后沉淀可复用经验。

本流程借鉴 PolyArch/humanize 中“独立 review + 迭代反馈”的纪律，但不是
Humanize RLCR 实现本身。本仓库使用面向 xLLM NPU 的 evidence loop：

```text
Research -> Learn -> Code -> Review -> Validate -> Record
```

## Phase 0: 目标与环境

先明确优化目标，再开始实验。

必须记录：

- 模型和 tokenizer；
- dtype、量化、图模式、投机解码和框架参数；
- NPU 型号和卡数；
- 框架 commit 和启动命令；
- workload、采样参数、并发、SLA 和 artifact root；
- 精度与性能的验证门禁。

在仓库外创建 run root：

```bash
mkdir -p "$RUN_ROOT"/{benchmark,profiles,analysis,history,kernel,patches,humanize}
```

manifest 字段参考 `../../reference/io_specs/run-manifest-template.md`。

## Phase 0.5: 查询历史

改代码前先查模型和 PR 历史：

```text
Use `reference/pr_history/` to query prior work for <model_name>,
related operators, risky source paths, failed attempts, and known validations.
```

把有效结论写入 run root，例如：

```text
$RUN_ROOT/history/model-history-notes.md
```

Qwen3.5/MTP 相关材料只是可选历史参考。只有当前任务涉及该模型族或投机解码时
才加载。

## Phase 1: 公平基线

在改代码前先启动服务并收集 warmed-up baseline。

使用：

- `../xllm-npu-eval-runner/SKILL.md`：服务启动和 evalscope artifact 收集；
- `../xllm-npu-benchmark/SKILL.md`：公平性检查和结果对比。

规则：

- 使用相同模型、tokenizer、dtype、硬件、workload、采样参数和 SLA；
- 每个被比较框架都要独立调优；
- 保留失败候选和失败原因；
- 记录完整启动命令；
- 保存原始 benchmark 输出和归一化 summary。

性能产物应满足：

- `../../reference/io_specs/perf-artifact-schema.md`
- `../../reference/io_specs/run-manifest-template.md`

## Phase 2: 差距判断

用基线判断是否需要继续优化。

```text
gap = (reference_throughput - target_throughput) / reference_throughput
```

如果目标已经达成，记录结果并停止。如果差距明确，进入证据采集。

## Phase 3: 证据采集

选择 patch 前必须先收集解释差距的证据。

默认使用 `../xllm-npu-profiler/SKILL.md` 做 profiling。根据症状补充：

- `../xllm-npu-pipeline-analysis/SKILL.md`：prefill/decode 边界、decode 空泡、层耗时、rank skew；
- `../xllm-npu-capacity-planner/SKILL.md`：HBM、KV cache、并发容量和 OOM 风险；
- `../xllm-npu-compute-simulation/SKILL.md`：FLOPs、MFU 和硬件理论下界；
- `../xllm-npu-accuracy-debug/SKILL.md`：乱码输出、分数下降、GPU/NPU 不一致；
- `../xllm-npu-incident-triage/SKILL.md`：crash、hang、图模式失败、HCCL 问题。

profiling 是诊断证据，不能替代正式的非 profiling 前后性能对比。

## Phase 4: 优化计划

计划必须从证据导出，而不是凭直觉直接写 patch。

计划应包含：

- 根因假设；
- 相关源码路径或框架组件；
- 下一轮只做一个优化点；
- 预期收益；
- 精度、内存、图模式、通信和兼容性风险；
- 精确的验证命令和必须产出的 artifact。

建议写到：

```text
$RUN_ROOT/humanize/refined-plan.md
```

算子迁移先用 `../xllm-npu-op-migration/SKILL.md`。

## Phase 5: Evidence Loop 迭代

每轮按这个顺序执行：

```text
Research: 阅读证据，选择下一轮最窄优化目标
Learn:    查询模型历史和已有失败尝试
Code:     实现一个可 review 的修改
Review:   执行 NPU 专项代码审查
Validate: 重新构建、测试、benchmark、profiling，并按需检查精度
Record:   更新 run ledger 和可复用 reference
```

推荐 skill 路由：

| 阶段 | 推荐 skill | 产物 |
|---|---|---|
| Research | `xllm-npu-benchmark`, `xllm-npu-profiler`, `xllm-npu-pipeline-analysis`, `xllm-npu-capacity-planner`, `xllm-npu-compute-simulation`, `xllm-npu-accuracy-debug` | 证据摘要 |
| Learn | `reference/pr_history/` | 相关历史和风险 |
| Code | `xllm-npu-op-migration`, 目标仓库本地 skill | 一个 patch 或实验 |
| Review | `xllm-npu-code-review`, 目标仓库 review 规则 | 分级 review findings |
| Validate | `xllm-npu-eval-runner`, `xllm-npu-benchmark`, `xllm-npu-profiler`, `xllm-npu-accuracy-debug`, `xllm-npu-incident-triage` | 验证报告 |
| Record | `xllm-npu-sota-loop`, `humanize/`, `reference/pr_history/` | attempt ledger、optimization ledger、可复用经验 |

## 验证要求

选择能证明或否定当前修改的最小验证集合。

常见门禁：

- build 通过；
- 相关单测或集成测试通过；
- 可能影响正确性时，跑精度 smoke 或数据集子集；
- warmed-up 性能复测体现预期趋势；
- 以性能为目标时，profiling 能解释性能变化；
- 没有带入无关文件或私有环境信息。

## 停止条件

满足任一条件即可停止：

- 达到或超过目标；
- 结果落入约定的平局阈值；
- profiling 证明瓶颈是当前范围外的硬件或框架限制；
- 连续三轮 evidence loop 都没有改善；
- 下一步依赖当前环境没有的外部决策、硬件或数据。

更多细节见 `references/stop-conditions.md`。

## 最终输出

闭环结束时交付：

- final benchmark summary；
- final root-cause 或 bottleneck 解释；
- validation summary；
- patch summary；
- known risks 和 follow-up work；
- run-root ledger 更新。

具体 ledger 写入 run root，不写回本仓库：

```text
$RUN_ROOT/humanize/attempt-ledger.md
$RUN_ROOT/humanize/optimization-ledger.md
$RUN_ROOT/humanize/source-idea-ledger.md
$RUN_ROOT/humanize/lineage.jsonl
```

## 可选历史参考

仅在当前任务相关时加载：

- `references/qwen35-mtp-case.md`
- `references/mtp-transpose-elimination-case.md`
- `../xllm-npu-benchmark/references/mtp-benchmark-lessons.md`
- `../xllm-npu-profiler/references/mtp-profiling-lessons.md`
- `../../reference/pr_history/qwen35-mtp.md`
